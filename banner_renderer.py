"""
banner_renderer.py — Рендер баннеров MestiDelivery Partners Bot
================================================================
Берёт базовый PNG-баннер и накладывает на него динамические поля
(текст) строго по пиксельной спецификации ``banners-spec-fix.json``.

Публичный API::

    from banner_renderer import renderer, render
    png_bytes = render("order_new_restaurant", {
        "order_number": "#66",
        "items": "3 items · Khinkali, Khachapuri, Lobiani",
        "order_total": "₾ 98.00",
        "accept_timer": "5:00",
    })

Логика:
  • Шрифты берутся из ``fonts/`` (Archivo Black, Unbounded, Manrope).
    Для переменных (Unbounded/Manrope) выставляется ось Weight.
  • Cyrillic-fallback: если поле помечено ``cyrillic_support: latin_only``
    (Archivo), а в значении есть кириллица — подставляется Unbounded
    (полная кириллица), как требует предупреждение в спецификации.
  • Автофит: размер шрифта подбирается от font_size_max до font_size_min,
    пока текст не влезет в зону (с учётом max_lines / max_chars).
  • Поддержаны спец-случаи: outline-стиль (welcome), rating-pill
    (inline_after:NAME), status_badge (conditional), strikethrough-линия.
"""

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from io import BytesIO
from typing import Optional

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# ─────────────────────────────────────────────────────────────────────────────
#  Пути
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPEC_PATH = os.path.join(BASE_DIR, "banners-spec-fix.json")
FONTS_DIR = os.path.join(BASE_DIR, "fonts")

# Спецификация → базовый PNG. Берём префикс имени файла из поля "file"
# (в нём после скобок идёт описание, нам нужен только префикс до пробела/скобки).
_KIND_TO_PNG = {
    "welcome": "MestiDelivery-Banner-1c.png",
    "order_new_restaurant": "MestiDelivery-Banner-2a-order-notification.png",
    "order_cancelled_restaurant": "MestiDelivery-Banner-3a-order-cancelled.png",
    "profile_restaurant": "MestiDelivery-Banner-4a-restaurant-profile.png",
    "order_new_courier": "MestiDelivery-Banner-5a-courier-new-delivery.png",
    "profile_courier": "MestiDelivery-Banner-6a-courier-profile.png",
    "order_taken_courier": "MestiDelivery-Banner-7a-order-taken.png",
}

# Параметры переменных шрифтов: {family: (path, min_weight, max_weight)}
_VARIABLE_FONTS = {
    "Unbounded": ("Unbounded.ttf", 200, 900),
    "Manrope": ("Manrope.ttf", 200, 800),
}
_STATIC_FONTS = {
    # Archivo в дизайне используется только весом 900 → статический Black.
    "Archivo": "ArchivoBlack.ttf",
}
# Запасные системные шрифты на случай, если fonts/ пустой.
_SYSTEM_FALLBACK = {
    "Archivo": r"C:\Windows\Fonts\arialbd.ttf",   # bold sans
    "Unbounded": r"C:\Windows\Fonts\tahomabd.ttf", # bold cyrillic
    "Manrope": r"C:\Windows\Fonts\segoeui.ttf",    # clean cyrillic sans
}

_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")

# ─────────────────────────────────────────────────────────────────────────────
#  Цвета
# ─────────────────────────────────────────────────────────────────────────────
def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    if not color:
        return (255, 255, 255)
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


def _hex_to_rgba(color: str, alpha: float = 1.0) -> tuple[int, int, int, int]:
    r, g, b = _hex_to_rgb(color)
    return (r, g, b, int(255 * max(0.0, min(1.0, alpha))))


# ─────────────────────────────────────────────────────────────────────────────
#  Шрифты
# ─────────────────────────────────────────────────────────────────────────────
def _font_path_for(family: str) -> tuple[str, bool, int, int]:
    """Возвращает (path, is_variable, wght_min, wght_max)."""
    if family in _STATIC_FONTS:
        p = os.path.join(FONTS_DIR, _STATIC_FONTS[family])
        if os.path.exists(p):
            return p, False, 900, 900
        return _SYSTEM_FALLBACK[family], False, 900, 900
    if family in _VARIABLE_FONTS:
        fname, wmin, wmax = _VARIABLE_FONTS[family]
        p = os.path.join(FONTS_DIR, fname)
        if os.path.exists(p):
            return p, True, wmin, wmax
        return _SYSTEM_FALLBACK[family], False, wmin, wmax
    # Неизвестное семейство → любой доступный
    return _SYSTEM_FALLBACK.get(family, r"C:\Windows\Fonts\arial.ttf"), False, 400, 700


_font_cache: dict[tuple, ImageFont.FreeTypeFont] = {}


def _load_font(family: str, weight: int, size: float) -> ImageFont.FreeTypeFont:
    size = max(6, int(round(size)))
    path, is_var, wmin, wmax = _font_path_for(family)
    weight = max(wmin, min(wmax, int(weight)))
    key = (path, weight, size)
    f = _font_cache.get(key)
    if f is not None:
        return f
    f = ImageFont.truetype(path, size)
    if is_var:
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            try:
                f.set_variation_by_name(str(weight))
            except Exception:
                pass
    _font_cache[key] = f
    return f


def _resolve_family(zone: dict, text: str) -> str:
    """Подставляет Cyrillic-безопасное семейство при необходимости."""
    family = zone.get("font_family", "Manrope")
    cyrillic_support = zone.get("cyrillic_support", "full")
    if cyrillic_support == "latin_only" and _CYRILLIC_RE.search(text):
        # Архива нет в кириллице — меняем на Unbounded (полная кириллица).
        return "Unbounded"
    return family


# ─────────────────────────────────────────────────────────────────────────────
#  Текст: перенос, обрезка, замер
# ─────────────────────────────────────────────────────────────────────────────
def _truncate(text: str, max_chars: Optional[int]) -> str:
    if max_chars and len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "…"
    return text


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> float:
    if "₾" in text:
        size_pt = int(getattr(font, "size", 24) or 24)
        cur = _currency_font(size_pt)
        total = 0.0
        for ch in text:
            use = cur if ch == "₾" else font
            try:
                total += float(use.getlength(ch))
            except Exception:
                total += float(draw.textlength(ch, font=use))
        return total
    try:
        return draw.textlength(text, font=font)
    except Exception:
        return font.getlength(text)


def _wrap_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    max_width: float,
    max_lines: Optional[int],
) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = w if not cur else f"{cur} {w}"
        if _text_width(draw, trial, font) <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)

    # Если одна «длинная» слово-цепочка шире зоны — режем по символам.
    final: list[str] = []
    for ln in lines:
        if _text_width(draw, ln, font) <= max_width:
            final.append(ln)
            continue
        buf = ""
        for ch in ln:
            if _text_width(draw, buf + ch, font) <= max_width:
                buf += ch
            else:
                final.append(buf)
                buf = ch
        if buf:
            final.append(buf)
    lines = final

    if max_lines and len(lines) > max_lines:
        kept = lines[: max_lines - 1]
        # Последнюю видимую строку дополняем хвостом с ellipsis-вписыванием.
        tail = " ".join(lines[max_lines - 1:])
        ell = "…"
        while tail and _text_width(draw, tail + ell, font) > max_width:
            tail = tail[:-1]
        kept.append((tail + ell).strip() if tail else ell)
        lines = kept
    return lines


def _line_metrics(font) -> tuple[float, float]:
    """Возвращает (line_height, ascent_offset_top) для шрифта."""
    try:
        ascent, descent = font.getmetrics()
    except Exception:
        ascent, descent = font.size, 2
    return ascent + descent, ascent


# ─────────────────────────────────────────────────────────────────────────────
#  Рендер одной текстовой зоны
# ─────────────────────────────────────────────────────────────────────────────
def _draw_text_zone(
    draw: ImageDraw.ImageDraw, img: Image.Image, zone: dict, value: str
) -> Optional[dict]:
    """Рисует зону. Возвращает геометрию первой строки {right_x, top_y, line_h, size}."""
    if value is None:
        return None
    text = str(value)
    if zone.get("text_transform") == "uppercase":
        text = text.upper()
    text = _truncate(text, zone.get("max_chars"))

    family = _resolve_family(zone, text)
    weight = int(zone.get("font_weight", 700))
    size_max = float(zone.get("font_size_max", zone.get("font_size", 24)))
    size_min = float(zone.get("font_size_min", size_max))
    max_lines = zone.get("max_lines")
    style = zone.get("style", "fill")
    fill_color = zone.get("fill_color", "#FFFFFF")
    stroke_color = zone.get("stroke_color")
    stroke_width = float(zone.get("stroke_width", 0))

    zx, zy = float(zone["x"]), float(zone["y"])
    zw, zh = float(zone["width"]), float(zone["height"])
    align = zone.get("align", "left")
    valign = zone.get("vertical_align", "center")

    def _fits(fnt, lns) -> bool:
        lh, _ = _line_metrics(fnt)
        total_h = lh * len(lns)
        max_w = max((_text_width(draw, ln, fnt) for ln in lns), default=0)
        return total_h <= zh + 0.5 and max_w <= zw + 0.5

    # Автофит: от max вниз, только пока НЕ влезает.
    size = size_max
    font = _load_font(family, weight, size)
    lines = _wrap_lines(draw, text, font, zw, max_lines)
    while size > size_min and not _fits(font, lines):
        size -= 1
        font = _load_font(family, weight, size)
        lines = _wrap_lines(draw, text, font, zw, max_lines)

    line_h, ascent = _line_metrics(font)
    total_h = line_h * len(lines)

    if valign == "top":
        top_y = zy
    elif valign == "bottom":
        top_y = zy + zh - total_h
    else:
        top_y = zy + (zh - total_h) / 2

    first_right = zx
    first_top = top_y
    first_x = zx
    for i, ln in enumerate(lines):
        w = _text_width(draw, ln, font)
        if align == "center":
            x = zx + (zw - w) / 2
        elif align == "right":
            x = zx + zw - w
        else:
            x = zx
        y = top_y + i * line_h + (line_h - ascent) / 2
        if i == 0:
            first_right = x + w
            first_top = y
            first_x = x
        _draw_line(
            img,
            ln,
            font,
            x,
            y,
            style,
            fill_color,
            stroke_color,
            stroke_width,
            glow=zone.get("glow"),
            text_shadow=zone.get("text_shadow"),
        )

    if zone.get("strikethrough_digits") and lines:
        _draw_digits_strikethrough(
            img,
            draw,
            lines[0],
            font,
            first_x,
            first_top,
            ascent,
            color=zone.get("strikethrough_color", "#E5484D"),
            opacity=float(zone.get("strikethrough_opacity", 0.9)),
            height=float(zone.get("strikethrough_height", 3)),
        )

    return {
        "right_x": first_right,
        "top_y": first_top,
        "line_h": line_h,
        "size": size,
    }


def _draw_digits_strikethrough(
    base: Image.Image,
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    text_x: float,
    text_y: float,
    ascent: float,
    *,
    color: str = "#E5484D",
    opacity: float = 0.9,
    height: float = 3,
) -> None:
    """Красная черта только по цифрам суммы (не по ₾), вплотную к ширине цифр."""
    m = re.search(r"\d", text)
    if not m:
        return
    prefix = text[: m.start()]
    amount = text[m.start() :]
    # Обрезаем хвостовые пробелы у amount — иначе линия длиннее цифр.
    amount_stripped = amount.rstrip()
    if not amount_stripped:
        return
    prefix_w = _text_width(draw, prefix, font)
    amount_w = _text_width(draw, amount_stripped, font)
    # Небольшой зазор после ₾, чтобы черта не «сливалась» с перекладиной символа.
    gap = 3.0 if prefix.strip() else 0.0
    x0 = text_x + prefix_w + gap
    x1 = text_x + prefix_w + amount_w
    if x1 - x0 < 8:
        return
    mid_y = text_y + ascent * 0.50
    h = max(2.0, height)
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle(
        [x0, mid_y - h / 2, x1, mid_y + h / 2],
        fill=_hex_to_rgba(color, opacity),
    )
    base.alpha_composite(overlay)


def _currency_font(size: float):
    """Шрифт с глифом ₾ (в Archivo/Unbounded/Manrope его нет)."""
    size = max(6, int(round(size)))
    key = ("__currency__", size)
    f = _font_cache.get(key)
    if f is not None:
        return f
    for path in (
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ):
        if os.path.exists(path):
            f = ImageFont.truetype(path, size)
            _font_cache[key] = f
            return f
    f = ImageFont.load_default()
    _font_cache[key] = f
    return f


def _draw_line(
    base: Image.Image,
    text: str,
    font,
    x: float,
    y: float,
    style: str,
    fill_color: str,
    stroke_color: Optional[str],
    stroke_width: float,
    glow: Optional[dict] = None,
    text_shadow: Optional[dict] = None,
):
    """Рисует одну строку. При style=='outline' — полый контур."""
    xi, yi = int(round(x)), int(round(y))

    if style == "outline" and stroke_color:
        # Полый контур посимвольно: заливка → дилатация → вычитание.
        #
        # Нельзя: Pillow stroke_width + MinFilter по всей строке — у плотных
        # кириллических глифов (Unbounded 900) обводки слипаются, эрозия
        # оставляет «смазанные» буквы (часто «РЕ…»).
        # Нельзя: один MaxFilter на всю строку — те же мостики между буквами.
        # Посимвольно + позиция через getlength(prefix) — кернинг как у строки.
        sw = max(1, int(round(stroke_width)))
        stroke_rgba = _hex_to_rgba(stroke_color, 1.0)
        layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))

        def _prefix_w(prefix: str) -> float:
            if not prefix:
                return 0.0
            try:
                return float(font.getlength(prefix))
            except Exception:
                return float(measure.textlength(prefix, font=font))

        for i, ch in enumerate(text):
            if ch.isspace() or ch == "\u00a0":
                continue
            cx = int(round(xi + _prefix_w(text[:i])))
            mask = Image.new("L", base.size, 0)
            ImageDraw.Draw(mask).text(
                (cx, yi), ch, font=font, fill=255, embedded_color=False
            )
            dilated = mask
            for _ in range(sw):
                dilated = dilated.filter(ImageFilter.MaxFilter(3))
            ring = ImageChops.subtract(dilated, mask)
            layer.paste(stroke_rgba, (0, 0), ring)

        base.alpha_composite(layer)
        return

    # Обычная заливка (опционально со stroke по контуру).
    # ₾ отсутствует в бренд-шрифтах — рисуем через Arial Bold, остальное primary.
    sw = max(0, int(round(stroke_width)))
    fill_rgba = _hex_to_rgba(fill_color, 1.0)
    stroke_rgba = (
        _hex_to_rgba(stroke_color or fill_color, 1.0) if sw else None
    )

    def _paint_text(target: Image.Image, ox: int, oy: int, rgba) -> None:
        od = ImageDraw.Draw(target)
        if "₾" in text:
            size_pt = int(getattr(font, "size", 24) or 24)
            cur_font = _currency_font(size_pt)
            cursor = float(ox)
            for ch in text:
                use = cur_font if ch == "₾" else font
                od.text(
                    (int(round(cursor)), oy),
                    ch,
                    font=use,
                    fill=rgba,
                    stroke_width=sw,
                    stroke_fill=stroke_rgba,
                    embedded_color=False,
                )
                try:
                    cursor += float(use.getlength(ch))
                except Exception:
                    cursor += float(od.textlength(ch, font=use))
        else:
            od.text(
                (ox, oy),
                text,
                font=font,
                fill=rgba,
                stroke_width=sw,
                stroke_fill=stroke_rgba,
                embedded_color=False,
            )

    if text_shadow:
        sh_blur = max(0, int(round(float(text_shadow.get("blur", 2)))))
        sh_op = float(text_shadow.get("opacity", 0.4))
        sh_dx = int(round(float(text_shadow.get("offset_x", 0))))
        sh_dy = int(round(float(text_shadow.get("offset_y", 1))))
        sh_rgba = _hex_to_rgba(text_shadow.get("color", "#000000"), sh_op)
        shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
        _paint_text(shadow, xi + sh_dx, yi + sh_dy, sh_rgba)
        if sh_blur > 0:
            shadow = shadow.filter(ImageFilter.GaussianBlur(radius=sh_blur))
        base.alpha_composite(shadow)

    if glow:
        g_blur = max(1, int(round(float(glow.get("blur", 14)))))
        g_op = float(glow.get("opacity", 0.5))
        g_rgba = _hex_to_rgba(glow.get("color", fill_color), g_op)
        bloom = Image.new("RGBA", base.size, (0, 0, 0, 0))
        _paint_text(bloom, xi, yi, g_rgba)
        bloom = bloom.filter(ImageFilter.GaussianBlur(radius=g_blur))
        base.alpha_composite(bloom)
        # Второй, чуть плотнее проход — «грязь» неона как в макете.
        bloom2 = Image.new("RGBA", base.size, (0, 0, 0, 0))
        _paint_text(bloom2, xi, yi, _hex_to_rgba(glow.get("color", fill_color), g_op * 0.65))
        bloom2 = bloom2.filter(ImageFilter.GaussianBlur(radius=max(1, g_blur // 2)))
        base.alpha_composite(bloom2)

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    _paint_text(overlay, xi, yi, fill_rgba)
    base.alpha_composite(overlay)


def _apply_film_grain(img: Image.Image, amount: float = 0.12) -> Image.Image:
    """Лёгкая плёночная грязь поверх баннера (overlay soft-light)."""
    import random

    amount = max(0.0, min(0.45, float(amount)))
    if amount <= 0:
        return img
    w, h = img.size
    # Half-res grain → после апскейла крупнее и «живее».
    gw, gh = max(1, w // 2), max(1, h // 2)
    rng = random.Random(5)
    noise = Image.new("L", (gw, gh))
    noise.putdata([rng.randint(0, 255) for _ in range(gw * gh)])
    noise = noise.resize((w, h), Image.Resampling.BILINEAR)
    noise = noise.filter(ImageFilter.GaussianBlur(radius=0.55))
    noise_rgb = Image.merge("RGB", (noise, noise, noise))
    base = img.convert("RGB")
    overlaid = ImageChops.overlay(base, noise_rgb)
    mixed = Image.blend(base, overlaid, amount)
    return mixed.convert("RGBA")


# ─────────────────────────────────────────────────────────────────────────────
#  Спец-зоны: rating pill, status_badge, strikethrough
# ─────────────────────────────────────────────────────────────────────────────
def _draw_rating_pill(
    base: Image.Image,
    zone: dict,
    value: str,
    anchor_x: float,
    top_y: float,
    line_h: float,
):
    """Звезда (вектор) + число сразу после имени (anchor: inline_after:<name>)."""
    text = str(value).strip()
    family = _resolve_family(zone, text)
    weight = int(zone.get("font_weight", 900))
    size = float(zone.get("font_size_max", 22))
    font = _load_font(family, weight, size)
    star_rgb = _hex_to_rgb(zone.get("star_color", "#35E07A"))
    fill = _hex_to_rgb(zone.get("fill_color", "#F2F6F3"))
    gap = float(zone.get("gap", 22))

    pad_x, pad_y = 12, 7
    star_r = size * 0.38
    star_gap = 8
    num_w = _text_width_safe(base, text, font)
    pill_h = size + pad_y * 2
    pill_w = pad_x * 2 + star_r * 2 + star_gap + num_w

    zone_h = float(zone.get("height", line_h))
    # Смещение вниз (+): только если задано в зоне (курьер), ресторан не трогаем.
    optical_down = float(zone.get("offset_y", 0))
    box_y0 = top_y + (zone_h - pill_h) / 2 + optical_down
    box_x0 = anchor_x + gap
    box_x1 = box_x0 + pill_w
    box_y1 = box_y0 + pill_h

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    radius = pill_h / 2
    od.rounded_rectangle(
        [box_x0, box_y0, box_x1, box_y1],
        radius=radius,
        fill=(18, 28, 22, 220),
    )
    star_cx = box_x0 + pad_x + star_r
    star_cy = (box_y0 + box_y1) / 2
    _draw_star(od, star_cx, star_cy, star_r, star_rgb + (255,))
    num_x = star_cx + star_r + star_gap
    # Выравниваем чернила глифов по центру звезды (не em-box / not baseline hacks).
    try:
        _l, top, _r, bottom = font.getbbox(text)
        # Оптический mid + чуть ниже (после прошлого подъёма).
        baseline_y = star_cy - (top + bottom) / 2 + 1
    except Exception:
        baseline_y = star_cy - size * 0.34
    od.text((num_x, baseline_y), text, font=font, fill=fill + (255,))
    base.alpha_composite(overlay)


def _text_width_safe(img: Image.Image, text: str, font) -> float:
    d = ImageDraw.Draw(img)
    return _text_width(d, text, font)


def _draw_star(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color):
    import math
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    draw.polygon(pts, fill=color)


def _draw_status_badge(base: Image.Image, zone: dict, fields: dict):
    """Pill OPEN/CLOSED / ON LINE — как в макете: тонкая зелёная обводка, без тёмной подложки снаружи."""
    cond = zone.get("conditional") or {}
    raw = (fields.get(zone.get("field")) or "").strip().lower()
    branch = cond.get(raw) or next(iter(cond.values()), None)
    if not branch:
        return
    text = str(branch.get("text", raw)).upper()
    accent = _hex_to_rgb(branch.get("fill_color", zone.get("fill_color", "#35E07A")))
    # В макете 4a текст OPEN белый; accent — точка и stroke.
    text_rgb = _hex_to_rgb(branch.get("text_color", zone.get("text_color", "#F2F6F3")))

    family = _resolve_family(zone, text)
    weight = int(zone.get("font_weight", 700))
    size = float(zone.get("font_size_max", 11.5))
    font = _load_font(family, weight, size)

    zx, zy = float(zone["x"]), float(zone["y"])
    zw, zh = float(zone["width"]), float(zone["height"])
    pad_x = 14
    dot_r = 4.0
    gap = 8
    tw = _text_width_safe(base, text, font)
    pill_w = pad_x * 2 + dot_r * 2 + gap + tw
    pill_h = max(28.0, min(zh, size + 14))
    if zone.get("align") == "right":
        x0 = zx + zw - pill_w
    else:
        x0 = zx
    y0 = zy + (zh - pill_h) / 2
    x1, y1 = x0 + pill_w, y0 + pill_h

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    # Без внешнего glow-прямоугольника — он и давал «вторую плашку» в Telegram.
    fill = (14, 26, 20, 245) if raw in ("open", "online") else (28, 16, 16, 245)
    border = accent + (200,)
    od.rounded_rectangle(
        [x0, y0, x1, y1],
        radius=pill_h / 2,
        fill=fill,
        outline=border,
        width=1,
    )
    dcx = x0 + pad_x + dot_r
    dcy = (y0 + y1) / 2
    od.ellipse(
        [dcx - dot_r, dcy - dot_r, dcx + dot_r, dcy + dot_r],
        fill=accent + (255,),
    )
    try:
        ascent, descent = font.getmetrics()
    except Exception:
        ascent, descent = int(size), 2
    tx = dcx + dot_r + gap
    ty = dcy - (ascent - descent) / 2 - 1
    od.text((tx, ty), text, font=font, fill=text_rgb + (255,))
    base.alpha_composite(overlay)


def _draw_static_element(base: Image.Image, el: dict):
    kind = el.get("type", "rect")
    if kind != "rect":
        return
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle(
        [el["x"], el["y"], el["x"] + el["width"], el["y"] + el["height"]],
        fill=_hex_to_rgba(el.get("fill_color", "#FFFFFF"), el.get("opacity", 1.0)),
    )
    base.alpha_composite(overlay)


# ─────────────────────────────────────────────────────────────────────────────
#  Главный класс
# ─────────────────────────────────────────────────────────────────────────────
class BannerRenderer:
    def __init__(self, spec_path: str = SPEC_PATH):
        with open(spec_path, "r", encoding="utf-8") as f:
            self.spec = json.load(f)
        self._images: dict[str, Image.Image] = {}
        for kind, fname in _KIND_TO_PNG.items():
            p = os.path.join(BASE_DIR, fname)
            self._images[kind] = Image.open(p).convert("RGBA")

    def _resolve_value(self, zone: dict, fields: dict) -> Optional[str]:
        field = zone.get("field")
        # Условные поля (status_badge).
        cond = zone.get("conditional")
        if cond:
            raw = fields.get(field)
            key = (raw or "").strip().lower()
            if key in cond:
                spec_branch = cond[key]
                return spec_branch.get("text", raw)
            # Если ключ не распознан — отдаём «позитивную» ветку по умолчанию
            # (первую в порядке), чтобы бейдж всегда отрисовался.
            first = next(iter(cond.values()))
            return first.get("text", str(raw) if raw is not None else "")
        val = fields.get(field)
        if val is None:
            return None
        return str(val)

    def render(self, kind: str, fields: dict) -> bytes:
        if kind not in self.spec or kind not in self._images:
            raise KeyError(f"Unknown banner kind: {kind}")
        cfg = self.spec[kind]
        img = self._images[kind].copy()
        draw = ImageDraw.Draw(img)

        # 1. Статические элементы (например, strikethrough-линия над cancel_total).
        for el in cfg.get("static_elements", []):
            _draw_static_element(img, el)

        # 2. Динамические зоны. Сначала «обычные», отдельно — inline (rating) и badge.
        inline_zones = []
        name_right_x = {}
        name_top_y = {}
        name_line_h = {}
        name_zone_y = {}
        name_zone_h = {}

        for zone in cfg["dynamic_zones"]:
            field = zone.get("field") or ""
            anchor = zone.get("anchor") or ""
            if str(anchor).startswith("inline_after:"):
                inline_zones.append(zone)
                continue
            if field == "status_badge" and zone.get("conditional"):
                # Baked badges (ресторан OPEN / курьер ON LINE) — не дублируем второй плашкой.
                if (
                    kind in ("profile_restaurant", "profile_courier")
                    or zone.get("skip")
                    or zone.get("baked_in_png")
                ):
                    continue
                _draw_status_badge(img, zone, fields)
                continue
            value = self._resolve_value(zone, fields)
            if value is None or value == "":
                continue
            geo = _draw_text_zone(draw, img, zone, value)
            if geo and field:
                name_right_x[field] = geo["right_x"]
                name_top_y[field] = geo["top_y"]
                name_line_h[field] = geo["line_h"]
                name_zone_y[field] = float(zone["y"])
                name_zone_h[field] = float(zone.get("height", geo["line_h"]))

        # 3. Inline-зоны (rating-pill) — позиция зависит от уже отрисованного поля.
        for zone in inline_zones:
            value = self._resolve_value(zone, fields)
            if value is None or value == "":
                continue
            anchor = str(zone["anchor"])
            target = anchor.split("inline_after:", 1)[1]
            ax = name_right_x.get(target, zone.get("x", 0))
            # Центр pill по высоте зоны имени (не по baseline).
            zy = name_zone_y.get(target, float(zone.get("y", 0)))
            zh = name_zone_h.get(target, float(zone.get("height", 24)))
            lh = name_line_h.get(target, zh)
            _draw_rating_pill(img, {**zone, "height": zh}, value, ax, zy, lh)

        grain = cfg.get("film_grain")
        if grain:
            img = _apply_film_grain(img, float(grain))

        out = img.convert("RGB")
        buf = BytesIO()
        out.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    def kinds(self) -> list[str]:
        return list(self._KIND_TO_PNG.keys())


# Синглтон для повторного использования внутри бота.
renderer = BannerRenderer()


def render(kind: str, fields: dict) -> bytes:
    """Удобная обёртка над синглтоном-рендерером."""
    return renderer.render(kind, fields)


# ─────────────────────────────────────────────────────────────────────────────
#  Smoke-тест: python banner_renderer.py  →  рендерит все 6 баннеров в out/
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    out_dir = os.path.join(BASE_DIR, "out")
    os.makedirs(out_dir, exist_ok=True)
    samples = {
        "welcome": {"partner_name": "Ресторан «BBQ Garden»"},
        "order_new_restaurant": {
            "order_number": "#66",
            "items": "3 items · Khinkali, Khachapuri, Lobiani",
            "order_total": "₾ 98.00",
            "accept_timer": "5:00",
        },
        "order_cancelled_restaurant": {
            "order_number": "#66",
            "cancel_total": "₾ 98.00",
            "cancel_time": "18:42",
            "cancel_reason": "Customer changed their mind before preparation started",
            "cancelled_by": "Cancelled by customer",
        },
        "profile_restaurant": {
            "restaurant_name": "Sunset Restaurant",
            "rating": "4.9",
            "status_badge": "open",
            "active_orders": "3 active orders",
            "payout": "₾ 1,240",
        },
        "order_new_courier": {
            "pickup_address": "Sunset Restaurant - Seti Square 4",
            "dropoff_address": "Vittorio Sella St 12, apt 3",
            "route_distance": "2.4 km",
            "courier_payout": "₾ 14.50",
        },
        "order_taken_courier": {
            "pickup_address": "Sunset Restaurant · Seti Square 4",
            "dropoff_address": "Vittorio Sella St 12, apt 3",
            "order_number": "#167",
            "event_time": "16:28",
            "missed_payout": "₾ 14.50",
        },
        "profile_courier": {
            "courier_name": "Giorgi Abashidze",
            "rating": "4.8",
            "status_badge": "online",
            "deliveries_count": "12 deliveries",
            "earnings": "₾ 186",
        },
    }
    for kind, fields in samples.items():
        data = render(kind, fields)
        path = os.path.join(out_dir, f"{kind}.png")
        with open(path, "wb") as f:
            f.write(data)
        print(f"OK  {kind:32s} {len(data):>8d} bytes  ->  {path}")
    print(f"\nAll {len(samples)} banners rendered into {out_dir}")
