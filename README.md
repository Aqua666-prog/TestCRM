# Agency CRM

Мини-CRM агентства: Telegram-бот собирает имя, контакт и запрос; все заявки попадают в одну модель Lead. Менеджер может создавать заявки вручную, добавлять несколько тегов и фильтровать список.

**Статус: локально реализовано и проверено. Production и реальный Telegram пока не проверены; публичной ссылки ещё нет.** Не сдавать работу как завершённую до production-приёмки ниже.

Python 3.12+, FastAPI, SQLAlchemy, Jinja2; SQLite локально, PostgreSQL в production. Без React/Next.js. См. PRODUCT.md, IMPLEMENTATION.md, ARCHITECTURE.md и TEST_REPORT.md.

## Локальный запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
cp .env.example .env
uvicorn app.main:app --reload
```

Открыть http://localhost:8000. Локальные значения входа из `.env.example`: `admin` / `change-me-local`. Изменить их перед доступом извне. SQLite `crm.db` создаётся автоматически, данные сохраняются между запусками. Для production тестовые пароли недопустимы.

```bash
python -m pytest -q
```

`requirements.lock` фиксирует проверенное окружение, включая pytest. `requirements.txt` — основные прямые зависимости, `requirements-dev.txt` — зависимости тестов.

## Telegram

1. Создать бота у @BotFather, получить токен и username.
2. Сохранить `TELEGRAM_BOT_TOKEN` в секретах хостинга или локальном `.env`; не вставлять в исходники, команды shell, коммиты и README. Не публиковать содержимое `.env` и вывод `docker compose config`.
3. Создать независимые случайные `TELEGRAM_WEBHOOK_SECRET`, `APP_SECRET`, `CRM_PASSWORD`, каждый не менее 32 символов; `TELEGRAM_WEBHOOK_SECRET` должен состоять из букв, цифр, `_` и `-`. Для пароля PostgreSQL удобно 32 случайных hex-символа.
4. После публикации задать `PUBLIC_BASE_URL=https://ваш-домен` и настроить webhook командой ниже. Webhook открыт для Telegram, веб-CRM требует пароль.

Команды бота: `/start` и `/new` начинают новую заявку (сбрасывая незавершённую), `/cancel` отменяет. Сообщение без активного диалога вызывает вопрос об имени; затем нужно ответить на три вопроса. В контактном шаге поддерживается объект Telegram contact. Группы и обновления без сообщения игнорируются. Бот никогда не считает username пользователя автоматически подтверждённым контактом.

## Production: Railway (выбранный хостинг)

Railway автоматически собирает Dockerfile. В настройках сервиса задайте команду `python -m app.run`, health `/health`, одну реплику и restart policy On Failure с 5 попытками. Config-as-Code устарел: новые сервисы с 2026-08-28 не могут подключать `railway.json`, поэтому настройки задаются через UI/API. `python -m app.run` слушает `PORT`; для этого развёртывания `PORT=8000` и target port домена тоже 8000. PostgreSQL URL в формах `postgres://`, `postgresql://` и `postgresql+psycopg://` поддерживается. Собственный Caddy на Railway не нужен.

1. Подключить аккаунт Railway, создать проект и PostgreSQL с постоянным volume.
2. Создать сервис приложения из этого проекта, настроить публичный HTTPS-домен на порт приложения.
3. В Variables приложения задать `APP_ENV=production`, reference `DATABASE_URL` на PostgreSQL, `PUBLIC_BASE_URL` на полученный HTTPS-домен, `CRM_USERNAME`, `CRM_PASSWORD`, `APP_SECRET`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`. Секретные значения вводить как Variables, не как файлы репозитория.
4. Развернуть приложение, дождаться успешного healthcheck. Затем выполнить внутри сервиса `python -m scripts.setup_webhook`.
5. Выполнить реальную production-приёмку ниже и обновить TEST_REPORT. Для проверки HTML-форм можно выполнить `python -m scripts.acceptance_web --create-manual`; после настоящего диалога бота — `python -m scripts.acceptance_web --telegram-name 'Тест MVP'`. Скрипт читает credentials из environment, не отправляет искусственные Telegram updates и создаёт только явно подписанные тестовые данные.

Официальные инструкции: https://docs.railway.com/guides/fastapi и https://docs.railway.com/databases/postgresql.

## Альтернатива: сервер + Docker Compose

Нужны Linux-сервер с Docker Compose, постоянный диск, домен с DNS на этот сервер и открытые 80/443. DNS и выпуск сертификата должны быть готовы до настройки webhook. Это выбранный простой путь деплоя; конфигурация подготовлена, но в текущем окружении Docker не запускался.

На сервере скопировать проект и `.env.example` в `.env`. Заполнить `.env`:

- `APP_ENV=production`;
- `DOMAIN` — домен без схемы и пути;
- `PUBLIC_BASE_URL=https://` + этот же домен;
- `POSTGRES_PASSWORD` — случайный hex-пароль;
- `CRM_USERNAME`, сильный `CRM_PASSWORD`, `APP_SECRET`;
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`.

Compose сам задаёт DATABASE_URL на PostgreSQL внутри сети. Если выбран другой хостинг, задать DATABASE_URL напрямую; `postgresql://` автоматически преобразуется в psycopg URL.

```bash
chmod 600 .env
docker compose up -d --build
docker compose ps
curl --fail https://ваш-домен/health
docker compose exec app python -m scripts.setup_webhook
```

Ожидается `{"status":"ok"}`. Затем открыть HTTPS CRM и войти. PostgreSQL хранится в volume `postgres_data`; `docker compose down -v` удаляет данные, не использовать для обычного перезапуска. Caddy хранит сертификаты в volume. Docker image не содержит `.env`, Git или tests; тестовый отправитель в production отсутствует.

При обновлении: сохранить backup, обновить исходники, `docker compose up -d --build`, повторить health и приёмку. Если меняется схема, сначала добавить и проверить миграции; create_all не обновляет существующие таблицы.

## Обязательная production-приёмка

Проводится на **настоящем боте и публичной CRM**, после настройки webhook:

1. Открыть `https://t.me/<username вашего бота>`, отправить `/start`.
2. После вопроса отправить уникальное имя, например «Приёмка 2026-10-01».
3. После следующего вопроса отправить контакт, затем текст запроса.
4. Получить сообщение «Заявка №… передана агентству».
5. Открыть CRM, убедиться, что видны те же три поля и источник Telegram.
6. Создать два тега, раскрыть «Теги» у этой заявки, выбрать оба и сохранить.
7. Отфильтровать список по первому тегу: заявка видна. Проверить второй тег.
8. Выбрать «Все теги» и создать отдельную ручную заявку; проверить источник «Вручную» и поля.
9. При фильтре по одному из первых тегов ручная заявка без тега отсутствует.
10. Перезапустить app; проверить, что заявки и теги сохранились. Незавершённый диалог тоже должен продолжиться.

Записать адрес CRM, username бота, дату, результаты и фактические проблемы в TEST_REPORT. Сохранять только обезличенные скриншоты. Токен и персональные данные в отчёт не включать.

## Диагностика

- CRM недоступна: `docker compose ps`, health, DNS/80/443, затем `docker compose logs --tail=50 app proxy`. Не публиковать логи без проверки на секреты.
- Health 503: проверить состояние db и доступность БД. После исправления снова выполнить health и приёмку.
- Бот молчит: проверить переменные и повторно запустить setup_webhook. Неправильный секрет даёт 403, временная ошибка отправки ответа — 503; Telegram повторяет update. Не включать DEBUG-логи httpx: адрес Bot API содержит токен.
- Лид создан, но ответ не доставлен: повтор того же update доставит сохранённую реплику без нового лида. При длительной недоступности Telegram требуется операторская диагностика; отдельного фонового retry-worker нет.
- Ошибка ввода: заполнить поля в пределах указанной длины; просроченную форму обновить.

## Проверка запущенного HTTP-сервера локально

Дополнительная проверка HTTP использует **имитированный отправитель Telegram**, не доказывает доставку через Bot API. Создаёт две тестовые заявки и два тега. Использовать отдельную тестовую БД.

```bash
DATABASE_URL=sqlite:///./smoke.db TELEGRAM_WEBHOOK_SECRET=local-smoke-secret \
  uvicorn tests.smoke_server:app --host 127.0.0.1 --port 8000
# В другом терминале:
TELEGRAM_WEBHOOK_SECRET=local-smoke-secret python -m scripts.smoke_http
```

Установки environment относятся только к этим локальным тестам. Не отправлять синтетические обновления в production: их update_id могут конфликтовать с реальными Telegram-обновлениями.
