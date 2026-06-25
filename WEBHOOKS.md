# Admin integrations webhooks (backend)

Двунаправленные вебхуки на edge-слое (gateway) для интеграции внешних админ-систем
(CRM, аналитика, диспетчерские) с заказами.

- **Исходящие (outbound):** Mestigo пушит события заказа на подписанные URL.
- **Входящие (inbound):** внешняя система шлёт обновление статуса заказа.

Подписки и лог доставок — локальный SQLite gateway (`webhooks.db`), управляются через админ-API.

## Где что живёт
- Пакет: `services/gateway/integrations/webhooks/` (`store.go`, `manager.go`, `signing.go`)
- HTTP-хендлеры: `services/gateway/handlers/webhooks.go`
- Врезка событий: `services/gateway/handlers/handlers.go` (`fanOutOrderCreated`, `emitOrderEvent`)
- Регистрация роутов: `services/gateway/main.go`

## События (event types)
| Событие | Когда | Полезная нагрузка |
|---|---|---|
| `order.created` | создан новый заказ | order_id, restaurant_id, total, customer_name, phone, address, items, payment_method |
| `order.status_changed` | сменён статус | order_id, status |

Подписка принимает список событий или wildcard `*`.

## Подпись (HMAC-SHA256)
Каждая подписка имеет `secret`. Все исходящие запросы подписаны:
- заголовок `X-Mestigo-Signature: sha256=<hex>`
- заголовок `X-Mestigo-Event: <event>`
- тело — JSON, подпись считается по **сырому** телу.

Входящие проверяются той же подписью (`Verify`, timing-safe).

## Admin API (требует JWT админа)

База: `/api` (зеркалится в `/api/v1`).

### Создать подписку
`POST /api/webhooks/subscriptions`
```json
{
  "name": "crm-sync",
  "url": "https://crm.example.com/hooks/mestigo",
  "secret": "любой-длинный-секрет",
  "events": ["order.created", "order.status_changed"],
  "direction": "outbound",
  "is_active": true
}
```
- `direction`: `outbound` | `inbound` | `bidirectional`
- `secret` опционален — если пуст, генерируется (вернётся **один раз** в ответе, дальше маскируется).

Ответ `201`:
```json
{ "id": 1, "name": "crm-sync", "secret": "<полный секрет>", "events": [...], ... }
```

### Список / получить / обновить / удалить
- `GET    /api/webhooks/subscriptions` — список (секрет замаскирован)
- `GET    /api/webhooks/subscriptions/:id`
- `PUT    /api/webhooks/subscriptions/:id` — те же поля; `secret` пустой = не меняется
- `DELETE /api/webhooks/subscriptions/:id`

### Лог доставок
`GET /api/webhooks/subscriptions/:id/deliveries?limit=50` — последние доставки (status, http_status, last_response, created_at).

## Входящий вебхук (приём статусов)
`POST /api/webhooks/inbound` (также `/webhooks/inbound` на корне и под `/api/v1`)

Заголовки:
- `X-Mestigo-Subscription: <id или name>` — какая подписка
- `X-Mestigo-Signature: sha256=<hex>` — HMAC тела с секретом подписки

Тело:
```json
{ "order_id": 123, "status": "accepted", "payment_method": "card" }
```
- `status` проходит через FSM order-сервиса (`validateStateTransition`).
- `payment_method` опционален (для подтверждения оплаты).
- Подписка должна быть `direction = inbound | bidirectional` и `is_active`.
- Коды: `200` (ok), `401` (нет подписки), `403` (подпись), `400` (тело), `502` (сбой смены статуса).

### Пример: отправить статус с подписью
```bash
BODY='{"order_id":123,"status":"accepted"}'
SECRET='ваш-секрет'
SIG="sha256=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')"
curl -X POST https://api.mestigo.ge/api/webhooks/inbound \
  -H "Content-Type: application/json" \
  -H "X-Mestigo-Subscription: crm-sync" \
  -H "X-Mestigo-Signature: $SIG" \
  --data "$BODY"
```

## Гарантии доставки
- Best-effort, **без** ретраев/очереди (MVP). Доставка логируется в `webhook_deliveries`.
- Таймаут HTTP — 8с на подписку. Весь fan-out идёт в фоновой горутине, не блокирует заказ.
- `delivered` = HTTP 2xx, иначе `failed` (с кодом ответа в логе).
