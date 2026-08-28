# Umnix

Umnix — единая образовательная платформа с WebApp, FastAPI backend, Telegram-ботом и AI-тьютором. Проект поддерживает роли **Ученик**, **Учитель**, **Родитель** и **Администратор**. Учитель и Родитель имеют одинаковый функционал наставника; в БД/API обе публичные роли используют техническую роль `parent`, а различие интерфейса хранится в `mentor_kind`, работу с учебниками и Book Mode, задания, интерактивные приложения, вложения и учебный прогресс.

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
  ├─ assignment source / task workflow
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
git clone <repository-url> umnix
cd umnix
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
# Создайте .env вручную или скопируйте .env.example, если используете шаблон
```

Минимально задайте `BOT_TOKEN`, `OPENAI_API_KEY` и `DATABASE_URL`. Секреты не должны попадать в Git.

## База данных и актуализация схемы

Приложение ожидает существующую базовую схему Umnix. Минимальные совместимые изменения, необходимые текущему коду (`assignment_source`, draft-first задания и `pending_review`), проверяются и идемпотентно применяются при старте через `services/schema_migrations.py`. Runtime не зависит от одноразовых `.sql`-файлов.

Перед любыми ручными изменениями production-БД делайте резервную копию.

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

Frontend использует единый iOS-inspired design system в `static/css/app.css`: режимы Light/Dark/System, мягкий Umnix glow, glass-панели, компактную desktop navigation, compact mobile section sheet, swipe-drawer списка чатов, Book Mode sheet, `visualViewport` для экранной клавиатуры, сохранение layout/theme в `localStorage`, единый Markdown/Math renderer и `prefers-reduced-motion`. Интерфейс вдохновлён iOS/iPadOS/macOS, но не копирует системные приложения Apple.

### Задания Учителя

Обычное задание всегда проходит путь `черновик → редактирование/preview → выбор Ученика → отправка`. Черновик можно начать со страницы «Ученики» или из конкретного ответа AI Tutor. Ответ Ученика переводит обычное задание в `pending_review`; окончательную оценку и комментарий выставляет Учитель. AI может дать Учителю подсказку, но не принимает финальное решение. Интерактивные приложения остаются отдельным типом задания с автоматической серверной проверкой.


## AI и prompts

- единственная точка создания OpenAI клиента: `services/ai/client.py`;
- модель, timeout и retries задаются через environment;
- системные prompt-блоки находятся в `services/prompts/`;
- пользовательский язык не меняется из-за языка prompt;
- Book Mode использует выбранный учебник как основной, но не единственный источник;
- приватные эталонные ответы и AI instructions не должны попадать в Student DTO.

## Вложения

Runtime-файлы хранятся в `storage/attachments/` и не входят в репозиторий. Каталог создаётся автоматически при необходимости. Ограничения типов и ownership проверяются в `services/attachment_storage.py`.

Страница `/files` показывает единое хранилище вложений WebApp и Telegram, сгруппированное по чатам. Пользователь может просмотреть или скачать файл, а действие «Удалить из памяти» удаляет связь с историей чата и AI-контекстом; физический файл удаляется только если он не нужен заданию или другой активной ссылке.

## Тесты

```bash
python -m pytest -q
python -m compileall -q api bot services tests main.py config.py database.py
```

Перед релизом также вручную проверьте регистрацию/авторизацию, роли, AI Tutor, sender names и greeting нового чата, Book Mode, draft/send/manual-review flow заданий, файлы, Telegram, интерактивные приложения и их server-side grading, оцифровку, Math rendering и admin pages.

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
docs/                     user/developer/architecture docs
storage/attachments/      runtime user files (ignored by Git)
```

## Troubleshooting

**`ModuleNotFoundError`** — активируйте созданный `.venv` и повторите `pip install -r requirements.txt`.

**Не подключается PostgreSQL** — проверьте `DATABASE_URL`, доступность сервера и существование базовой схемы Umnix.

**Telegram WebApp не авторизуется** — проверьте `BOT_TOKEN`, `WEBAPP_BASE_URL`, HTTPS и запуск страницы именно внутри Telegram.

**OpenAI timeout / 502** — проверьте ключ, сеть, `OPENAI_TIMEOUT_SECONDS` и `OPENAI_MAX_RETRIES`.

**PDF не обрабатывается** — убедитесь, что файл валиден и меньше 100 МБ; подробная причина должна оставаться в server log, а не показываться пользователю traceback-ом.

## Документация

- [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) — инструкция пользователя;
- [`docs/DEVELOPER_GUIDE.md`](docs/DEVELOPER_GUIDE.md) — руководство разработчика и design system;
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — карта зависимостей и потоков;
## Reference UI (Фон_ИИ.html)

Актуальный WebApp использует единый iOS-like visual layer по мотивам предоставленного `Фон_ИИ.html`:

- Light/Dark/System темы;
- полупрозрачные glass-панели;
- лёгкий `Matrix Formula Stream` на Canvas на всех страницах;
- blue/violet/pink top glow только во время реальной обработки AI-запроса;
- компактный desktop rail и off-canvas список чатов;
- полноширинный ответ ИИ и пользовательская плашка не шире 75% рабочей области;
- pill-shaped composer;
- mobile drawer для чатов и bottom sheet для Book Mode.

