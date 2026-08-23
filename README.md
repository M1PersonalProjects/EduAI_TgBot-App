# EduAI

EduAI — единая образовательная платформа с WebApp, FastAPI backend, Telegram-ботом и AI-тьютором. Проект поддерживает роли **Ученик**, **Учитель** (техническое значение роли в БД/API — `parent`) и **Администратор**, работу с учебниками и Book Mode, задания, интерактивные приложения, вложения, прогресс и геймификацию.

## Архитектура

```text
WebApp / Telegram
        │
        ▼
FastAPI routers / Telegram handlers
        │
        ▼
shared services
  ├─ tutor / context / memory
  ├─ task generation and checking
  ├─ attachments
  ├─ interactive apps
  ├─ textbook digitization
  ├─ gamification
  └─ services/ai (единый OpenAI client layer)
        │
        ▼
PostgreSQL / filesystem / external AI
```

Подробности: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) и [`docs/DEVELOPER_GUIDE.md`](docs/DEVELOPER_GUIDE.md).

## Технологии

- Python 3.9+;
- FastAPI / Uvicorn;
- aiogram 3;
- PostgreSQL / asyncpg;
- OpenAI Python SDK;
- Pydantic / pydantic-settings;
- Jinja2 + vanilla JavaScript;
- PyMuPDF для PDF;
- pytest / pytest-asyncio.

## Требования

- Python 3.9 или новее;
- PostgreSQL;
- рабочий Telegram bot token;
- OpenAI API key;
- для Telegram WebApp в production — публичный HTTPS URL.

## Установка с нуля

```bash
git clone <repository-url> eduai
cd eduai
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

Заполните `.env` реальными значениями. Секреты не должны попадать в Git.

## База данных и миграции

Приложение ожидает существующую базовую схему EduAI. Совместимая idempotent-миграция текущей версии находится в:

```text
migrations/20260819_assignment_sources_gamification.sql
```

Она автоматически применяется при старте через `services/schema_migrations.py` и может быть применена вручную:

```bash
psql "$DATABASE_URL" -f migrations/20260819_assignment_sources_gamification.sql
```

Перед production-обновлением сделайте резервную копию БД.

## Запуск

### API + Telegram bot

```bash
python main.py
```

По умолчанию FastAPI слушает `127.0.0.1:8000`, а Telegram-бот запускается polling-процессом в том же приложении.

### Только backend для разработки

```bash
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

При таком запуске FastAPI lifecycle всё равно подключает БД и worker оцифровки, но polling Telegram из `main()` не запускается.

## WebApp

Основные страницы:

- `/auth` — вход;
- `/student` — кабинет Ученика;
- `/parent` — кабинет Учителя;
- `/admin` — администрирование;
- `/interactive/{app_id}` — интерактивное приложение.

Legacy `.html` URL сохранены как совместимые UI-адаптеры.

Frontend использует единый iOS-inspired design system в `static/css/app.css`: режимы Light/Dark/System с сохранением выбора, компактную top navigation на desktop, bottom navigation на mobile, выдвижные chat/Book Mode panels, сохранение части layout в `localStorage`, единый rich Markdown/Math renderer и `prefers-reduced-motion`. Интерфейс вдохновлён iOS/iPadOS/macOS, но не копирует системные приложения Apple.

## AI и prompts

- единственная точка создания OpenAI клиента: `services/ai/client.py`;
- модель, timeout и retries задаются через environment;
- системные prompt-блоки находятся в `services/prompts/`;
- пользовательский язык не меняется из-за языка prompt;
- Book Mode использует выбранный учебник как основной, но не единственный источник;
- приватные эталонные ответы и AI instructions не должны попадать в Student DTO.

## Вложения

Runtime-файлы хранятся в `storage/attachments/` и не входят в репозиторий. Каталог создаётся автоматически при необходимости. Ограничения типов и ownership проверяются в `services/attachment_storage.py`.

## Тесты

```bash
python -m pytest -q
python -m compileall -q api bot services tests main.py config.py database.py
```

Перед релизом также вручную проверьте регистрацию/авторизацию, роли, AI tutor, Book Mode, задания Учителя и практику, файлы, Telegram, интерактивные приложения, оцифровку, Math rendering, геймификацию и admin pages.

## Структура

```text
api/
  routers/               HTTP endpoints
  schemas/               API/DTO models
bot/
  handlers/              Telegram scenarios
services/
  ai/                    centralized OpenAI access
  prompts/               system prompt blocks
  templates/             trusted interactive shell templates
  *.py                   shared business services
static/
  css/                    design system and responsive styles
  js/                     shared and role-specific frontend logic
templates/                Jinja2 pages
tests/                    automatic tests
migrations/               PostgreSQL migrations
docs/                     user/developer/architecture docs
storage/attachments/      runtime user files (ignored by Git)
```

## Troubleshooting

**`ModuleNotFoundError`** — активируйте созданный `.venv` и повторите `pip install -r requirements.txt`.

**Не подключается PostgreSQL** — проверьте `DATABASE_URL`, доступность сервера и существование базовой схемы EduAI.

**Telegram WebApp не авторизуется** — проверьте `BOT_TOKEN`, `WEBAPP_BASE_URL`, HTTPS и запуск страницы именно внутри Telegram.

**OpenAI timeout / 502** — проверьте ключ, сеть, `OPENAI_TIMEOUT_SECONDS` и `OPENAI_MAX_RETRIES`.

**PDF не обрабатывается** — убедитесь, что файл валиден и меньше 100 МБ; подробная причина должна оставаться в server log, а не показываться пользователю traceback-ом.

## Документация

- [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) — инструкция пользователя;
- [`docs/DEVELOPER_GUIDE.md`](docs/DEVELOPER_GUIDE.md) — руководство разработчика и design system;
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — карта зависимостей и потоков;