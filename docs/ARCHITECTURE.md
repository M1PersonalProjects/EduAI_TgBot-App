# Архитектура Umnix

## Главный поток зависимостей

```text
WebApp                     Telegram
  │                           │
  ▼                           ▼
FastAPI routers          bot/handlers
        \                 /
         \               /
          ▼             ▼
          Shared service layer
          ├─ tutor + tutor_policy
          ├─ context_resolver + educational_context
          ├─ conversation_context + chat_memory
          ├─ task_generation + assignment_source
          ├─ attachment_storage + file_parser
          ├─ interactive_apps
          ├─ textbook_digitizer + digitization_queue
          ├─ response_formatter
          └─ ai + prompts
                    │
                    ▼
       PostgreSQL / filesystem / OpenAI
```

Главное правило: routers/handlers принимают транспортный запрос и проверяют доступ, а бизнес-логика должна находиться в `services/`. Router не должен импортировать другой router.

## API layer

`api/routers/` содержит HTTP endpoints. DTO находятся в `api/schemas/`. Авторизация и проверка Telegram WebApp вынесены в `api/security.py`.

Legacy routes сохранены только там, где они нужны существующим клиентам. Новые операции, изменяющие состояние, должны использовать POST/PATCH/PUT/DELETE, а не GET.

## Telegram layer

`bot/handlers/` обрабатывает Telegram updates и делегирует общую предметную логику тем же сервисам, что использует WebApp. Это предотвращает появление второй реализации AI tutor, генерации задач или Book Mode.

## AI layer

```text
feature service / router / handler
            │
            ▼
services/ai/client.py
  - model
  - timeout
  - retries
  - logging
  - upstream error normalization
            │
            ▼
OpenAI SDK
```

Все system prompt blocks находятся в `services/prompts/`. Сборка prompt выполняется через `services/tutor_policy.py` и feature-specific правила.

## Context flow

```text
user message
  ├─ active Book Mode?
  ├─ explicit file reference?
  ├─ active attachments?
  └─ general query
          │
          ▼
context_resolver / conversation_context
          │
          ▼
educational_context ranking
          │
          ▼
tutor prompt + response
```

Выбранный учебник — основной источник, но не единственный. Supplement допускается, если материала недостаточно.

## Attachment flow

```text
upload → ownership metadata → storage path
                    │
                    ├─ chat message link
                    ├─ task attachment link
                    └─ interactive/context use
```

Доступ к preview/download/delete должен всегда проверять владельца или разрешённую связь Учитель–Ученик.

## Task flow

```text
Students page / Teacher AI message
        ↓
persistent task_drafts
        ↓
Teacher edit + preview + student/file selection
        ↓
explicit Send
        ↓
tasks_history (assignment_source='teacher')
        ↓
Student answer → pending_review
        ↓
optional AI suggestion → final Teacher score/comment → evaluated

Telegram Quest-test (Student only)
        ↓
temporary FSM state
        ↓
choice checking in Telegram → state.clear()
(no tasks_history persistence)

Interactive assignment
        ↓
interactive_assignments + tasks_history
        ↓
server-side interactive grading → evaluated/completed
```

Student DTO удаляет private answer keys и internal metadata рекурсивно. Полный Teacher reference остаётся только в защищённых Teacher endpoints/DB.

## Interactive app flow

```text
explicit Interactive App mode + chat request/materials
  → AI returns one COMPLETE HTML document
  → sanitizer + technical/security validation
  → immutable app version (version_id + parent_version_id)
  → sandboxed iframe / version-specific URL
  → learner answers
  → server-side grading
```

Correct answers не должны быть встроены в learner HTML.

## Textbook digitization

`services/textbook_digitizer.py` отвечает за PDF → page image/text → Structured Output → сохранение в `page`. И admin API, и platform v1 используют один сервис.

## Frontend

`static/css/app.css` — единый design system и layout. `static/js/app.js` — общие API/UI/Markdown/Math utilities. Role-specific JS не должен заново реализовывать common fetch/render helpers.

Breakpoints, используемые layout: mobile ~360–767px, tablet 768–1023px, desktop 1024+; chat sidebar переключается в drawer ниже 1280px.

## Chat identity / profile flow

```text
users.username (fallback tg_id)
        ↓
Tutor message DTO sender_name
        ↓
shared ChatUI message header

/api/v1/tutor/profile
        ├─ username/tg_id
        └─ /profile/avatar → Telegram Bot API proxy/cache
```

Новый пустой chat отображает UI-only greeting и не дублирует его в `chat_messages`.
