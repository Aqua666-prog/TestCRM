# Отчёт о проверке

Дата: 2026-10-01. Проверял Codex в ChatGPT Work Mode. Среда: Python 3.12.14, зависимости зафиксированы в requirements.lock.

**Текущий статус: локальные проверки и production веб-сценарий успешны; полный Telegram end-to-end ещё НЕ выполнен.** Приложение работает на Railway/PostgreSQL по HTTPS, настоящий webhook настроен. Ожидается диалог пользователя с ботом и последующая проверка созданного лида.

| Проверка | Результат |
| --- | --- |
| Автоматические тесты `python -m pytest -q` | 9 passed |
| Telegram webhook → имя → контакт → запрос → Lead → HTML CRM | PASS, отправка ответа Telegram имитирована |
| Назначение двух тегов → фильтр по тегу → сброс фильтра → снятие тегов | PASS |
| Ручная заявка, source=manual, chat_id=NULL | PASS |
| Повтор update_id | PASS, один Lead и один успешно отмеченный ответ |
| Временный отказ отправки → повтор update | PASS, один Lead и повтор доставки сохранённого ответа |
| Перезапуск приложения между шагами диалога | PASS, состояние сохранено в SQLite |
| Контакт Telegram contact | PASS |
| Пустые/слишком длинные поля, отмена диалога | PASS |
| Аутентификация CRM, CSRF, secret webhook, HTML escaping | PASS |
| Повтор названия тега с другим регистром, неизвестные теги | PASS |
| Health, игнорирование неподдерживаемого update, production guard | PASS |
| Реально запущенный Uvicorn + HTTP smoke | PASS, две заявки, два тега и фильтр; тестовый sender |
| Python compileall | PASS |
| Railway entry point с PORT=18081 → health → вход в CRM | PASS, локальный HTTP-сервер |
| PostgreSQL runtime | PASS, production startup, health SELECT 1, ручной Lead и many-to-many теги |
| Dockerfile, публичный HTTPS | PASS, Railway build/deploy SUCCESS, /health HTTP 200 |
| Docker Compose, Caddy | НЕ ВЫПОЛНЕНО, альтернативный деплой |
| Настоящий Telegram Bot API и webhook production | PASS: getMe, setWebhook, getWebhookInfo; входящие сообщения ещё ожидаются |
| Production HTML: ручной Lead → два тега → оба фильтра → снятие тегов | PASS, Lead #1 «Приёмка MVP — вручную» |

## Метод и диагностика

Автоматические тесты отправляют Telegram-compatible JSON в webhook FastAPI через TestClient, проверяют данные SQLAlchemy и HTML. Sender подменён для детерминированного тестирования; сетевой сбой тоже воспроизводится подменой. Для локального HTTP smoke отдельно запущен Uvicorn: запросы проходят настоящий TCP/HTTP-сервер, а ответ Telegram по-прежнему имитирован. После исправления влияния SOCKS proxy environment локальный smoke повторён успешно (`trust_env=False` только у локального тестового HTTP-клиента).

Тестовый PostgreSQL пытались запустить через временный pgserver. Среда не позволила создать/выбрать системного пользователя, необходимого PostgreSQL, поэтому это не объявлено успешной проверкой. Проверенный SQLite-сценарий не доказывает работоспособность production PostgreSQL. Полный набор может запускаться на выделенной БД через переменную `CRM_TEST_POSTGRES_URL`: допускается только база с именем `crm_test`; её таблицы будут сбрасываться между тестами. Не указывать production database. pgserver не является зависимостью продукта.

В окружении тестов есть одно предупреждение Starlette о будущем переходе TestClient с httpx на httpx2. На результаты текущих тестов оно не влияет; закреплённые версии воспроизводят проверенное окружение.

## Заполнить после реального деплоя

- CRM HTTPS URL: https://agency-crm-production-7a74.up.railway.app/.
- Telegram bot username: @t8stcrmbot.
- Дата и оператор веб-приёмки: 2026-10-01, Codex, production HTML-формы через HTTP-клиент.
- Реальный диалог → Lead в CRM → два тега → фильтры: ожидает проверки.
- Ручная заявка на production: PASS, создалась и видна в HTML CRM.
- Сохранение данных и диалога после перезапуска production: ожидает проверки.
- Проблемы, диагноз, исправление, повторный полный сценарий: заполнить по факту.

Инструкция приёмки — README.md. Не включать токен, пароль CRM или реальные контакты клиентов в этот отчёт.

## Подготовка Railway

Адаптирован контейнерный entry point под PORT, поддержаны варианты PostgreSQL URL. После изменений повторно: 9 passed, затем успешный запуск с PORT=18081, health и авторизованный доступ к CRM. Созданы production-сервисы agency-crm и Postgres, volume, HTTPS-домен. Секрет бота сохранён как Railway Variable, отсутствует в исходниках и Git. railway.json удалён: UI Railway сообщает, что новые сервисы с 2026-08-28 не могут использовать устаревший Config-as-Code. Настройки задаются непосредственно сервису.

Первый рабочий деплой: a3c0b55b-40ce-442b-87c9-e486114ac9d4, SUCCESS. Runtime: Uvicorn 0.0.0.0:8000, одна реплика, health /health. Webhook URL соответствует production endpoint.

Диагностика проверок: локальный httpx не мог создать SOCKS transport; установлен socksio в рабочий venv, после этого Bot API и webhook успешно проверены. В production такой proxy environment отсутствует. Первый acceptance-скрипт не находил теги, поскольку ожидал заглавные буквы, а продукт нормализует название через casefold. Исправлено ожидание скрипта, повторный полный ручной веб-сценарий PASS. Ошибка не затрагивала сохранение тегов в приложении.
