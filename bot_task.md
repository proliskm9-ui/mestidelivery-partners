# ОПИСАНИЕ ПРОЕКТА
Ты — Senior Python-разработчик. [cite_start]Твоя задача: написать микросервис Telegram-бота для платформы доставки еды MestiDelivery[cite: 1, 6]. 
[cite_start]Бот работает как легковесный шлюз между основным бэкендом и партнерами (ресторанами и курьерами)[cite: 8].

# ТЕХНИЧЕСКИЙ СТЕК
- Python 3.11+
- aiogram 3.x (для работы с Telegram API)
- aiohttp или FastAPI (для поднятия внутреннего HTTP-сервера)
- [cite_start]Внутреннее in-memory хранилище (или SQLite) для кэширования состояний сообщений.

# ГЛАВНОЕ АРХИТЕКТУРНОЕ ПРАВИЛО
[cite_start]Бот НЕ содержит сложной бизнес-логики и базы данных[cite: 11]. [cite_start]Единственный источник достоверных данных (Single Source of Truth) — это основной бэкенд[cite: 12]. [cite_start]Бот только пересылает пуши и транслирует нажатия кнопок обратно на бэкенд[cite: 13].

# 1. ТРЕБОВАНИЯ К HTTP-СЕРВЕРУ БОТА (Входящие запросы от Backend)
[cite_start]Бот должен поднять сервер и слушать следующие POST-запросы (Content-Type: application/json)[cite: 61, 62]. [cite_start]Все запросы должны валидироваться по наличию статического токена в заголовке `X-Bot-Security-Token`[cite: 120].

- [cite_start]`POST /api/bot/v1/restaurant/new-order`: Уведомляет ресторан[cite: 63, 64]. [cite_start]Отправляет текст с суммой и кнопку-URL для открытия Mini App [cite: 29, 30, 65-71].
- [cite_start]`POST /api/bot/v1/couriers/broadcast`: Веерная рассылка пулу курьеров (по массиву `couriers_telegram_ids`)[cite: 74, 75, 84]. [cite_start]Сообщение содержит адрес ресторана, адрес клиента, сумму[cite: 37, 38]. [cite_start]Кнопки: [Принять] (URL в Mini App) и [Отклонить] (Callback)[cite: 40, 41].
- [cite_start]`POST /api/bot/v1/couriers/assign-order`: Бэкенд сообщает, кто выиграл заказ[cite: 86, 87]. [cite_start]Бот обновляет сообщение курьера-победителя (добавляет Callback-кнопку [Забрал заказ]) [cite: 48, 49, 88-93]. [cite_start]Для проигравших курьеров (массив `losers_telegram_ids`) бот меняет текст на "Заказ уже взят" и удаляет кнопки[cite: 50, 91].
- [cite_start]`POST /api/bot/v1/orders/sync-state`: Принудительно обновляет текст и кнопки сообщения курьера при смене статуса на бэкенде (например, на [Заказ передан]) [cite: 94-102].

# 2. ТРЕБОВАНИЯ К CALLBACK-ЗАПРОСАМ (Исходящие запросы на Backend)
[cite_start]Когда курьер нажимает инлайн-кнопки (кроме URL), бот отправляет запрос на основной бэкенд[cite: 104]:
- [cite_start]`POST https://api.mestidelivery.com/api/v1/bot-callback`[cite: 106].
- [cite_start]Payload: `{"order_id": int, "telegram_id": int, "action": str}` [cite: 109-113].
- [cite_start]Возможные action: `rejected`, `picked_up`, `arrived`, `completed`[cite: 114].

[cite_start]ВАЖНОЕ ПРАВИЛО СИНХРОНИЗАЦИИ: Бот обязан дождаться HTTP 200 OK от бэкенда, и только потом обновлять UI в Telegram (вызывать `editMessageText` и т.д.)[cite: 116]. [cite_start]Если бэкенд вернул ошибку, бот должен показать alert через `answerCallbackQuery`[cite: 117]. [cite_start]При нажатии [Отклонить] (`rejected`) бот должен удалить (или скрыть кнопки) сообщение локально у этого курьера[cite: 42].

# 3. КЭШИРОВАНИЕ СОСТОЯНИЙ (STATE CACHE)
[cite_start]Чтобы бот мог редактировать конкретные сообщения курьеров при событиях `assign-order` или `sync-state`, реализуй потокобезопасное хранилище. 
Оно должно сохранять связку: `[order_id + telegram_id] -> message_id`. [cite_start]При отправке рассылки бот сохраняет `message_id`, чтобы потом знать, какое именно сообщение обновить у победителя и удалить у проигравших[cite: 118].

# ПОРЯДОК РАБОТЫ (ЗАДАЧА ДЛЯ AI)
1. Напиши каркас приложения: инициализация бота aiogram, настройка aiohttp-сервера.
2. Реализуй Middleware для проверки `X-Bot-Security-Token`.
3. Создай класс/модуль для In-Memory хранения State (`order_id` + `tg_id` = `message_id`).
4. Напиши роуты (эндпоинты) aiohttp для приема команд от бэкенда.
5. Напиши обработчики (handlers) для Callback-кнопок бота и отправку запросов на бэкенд.
