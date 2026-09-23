import logging
from aiohttp import web
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNotFound

from config import BOT_SECURITY_TOKEN
from database import mark_user_blocked
from order_notifications import format_order_status_message, normalize_language
from referral import get_referral_info, bind_referral

log = logging.getLogger(__name__)
SECURITY_HEADER = 'X-Bot-Security-Token'


def check_token(request: web.Request) -> bool:
    if not BOT_SECURITY_TOKEN:
        log.error('BOT_SECURITY_TOKEN is not configured')
        return False
    return request.headers.get(SECURITY_HEADER) == BOT_SECURITY_TOKEN


def add_cors(resp: web.Response) -> web.Response:
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Bot-Security-Token'
    return resp


async def handle_options(request: web.Request) -> web.Response:
    return add_cors(web.Response(status=204))


async def handle_customer_order_status(request: web.Request) -> web.Response:
    bot: Bot = request.app['bot']
    if not check_token(request):
        return add_cors(web.json_response({'ok': False, 'error': 'unauthorized'}, status=401))

    try:
        data = await request.json()
    except Exception:
        return add_cors(web.json_response({'ok': False, 'error': 'bad json'}, status=400))

    order_id = data.get('order_id')
    telegram_user_id = data.get('telegram_user_id')
    status = (data.get('status') or '').strip().lower()
    language = normalize_language(data.get('language'))
    restaurant_name = (data.get('restaurant_name') or 'MestiDelivery').strip()

    if not order_id or not telegram_user_id or status not in {'accepted', 'preparing', 'delivering', 'delivered'}:
        return add_cors(web.json_response({'ok': False, 'error': 'invalid payload'}, status=400))

    text = format_order_status_message(
        status=status,
        language=language,
        order_id=order_id,
        restaurant_name=restaurant_name,
    )

    try:
        await bot.send_message(chat_id=int(telegram_user_id), text=text, parse_mode='HTML')
        return add_cors(web.json_response({'ok': True, 'sent': True}))
    except (TelegramForbiddenError, TelegramNotFound) as exc:
        await mark_user_blocked(int(telegram_user_id))
        log.warning('customer order-status: user blocked bot %s (%s)', telegram_user_id, exc)
        return add_cors(web.json_response({'ok': True, 'sent': False, 'blocked': True}))
    except TelegramBadRequest as exc:
        log.warning('customer order-status: telegram bad request for %s (%s)', telegram_user_id, exc)
        return add_cors(web.json_response({'ok': True, 'sent': False, 'error': str(exc)}))
    except Exception as exc:
        log.exception('customer order-status: unexpected error for order %s', order_id)
        return add_cors(web.json_response({'ok': False, 'error': str(exc)}, status=500))


async def handle_referral_info(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        data = {}
    user_id = data.get('user_id')
    phone = data.get('phone')
    info = get_referral_info(user_id=user_id, phone=phone)
    return add_cors(web.json_response(info))


async def handle_referral_bind(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return add_cors(web.json_response({'ok': False, 'error': 'invalid json'}, status=400))
    phone = data.get('phone')
    ref_code = data.get('ref_code')
    user_id = data.get('user_id')
    res = bind_referral(referee_phone=phone, ref_code=ref_code, referee_user_id=user_id)
    return add_cors(web.json_response(res))


def make_http_app(bot: Bot) -> web.Application:
    app = web.Application()
    app['bot'] = bot
    app.router.add_get('/healthz', lambda _: add_cors(web.json_response({'ok': True})))
    app.router.add_post('/api/bot/v1/customer/order-status', handle_customer_order_status)
    app.router.add_options('/api/bot/v1/customer/order-status', handle_options)
    
    # Referral endpoints
    app.router.add_post('/api/bot/v1/customer/referral/info', handle_referral_info)
    app.router.add_options('/api/bot/v1/customer/referral/info', handle_options)
    app.router.add_post('/api/bot/v1/customer/referral/bind', handle_referral_bind)
    app.router.add_options('/api/bot/v1/customer/referral/bind', handle_options)
    
    return app
