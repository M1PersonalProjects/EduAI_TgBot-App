# Архитектура EduAI

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
          ├─ task_generation + gamification
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
Teacher/manual or AI generation
        │
        ▼
tasks_history (assignment_source='teacher')
        │
        ▼
Student answer → server-side checking → evaluated → reward

Student practice generation
        │
        ▼
tasks_history (assignment_source='tutor_practice')
        │
        ▼
Student answer → checking → completed → reward
```

Student DTO удаляет private answer keys и internal metadata рекурсивно.

## Interactive app flow

```text
chat request
  → structured app spec
  → trusted EduAI shell
  → sanitizer + quality validation
  → sandboxed iframe
  → learner answers
  → server-side grading
```

Correct answers не должны быть встроены в learner HTML.

## Textbook digitization

`services/textbook_digitizer.py` отвечает за PDF → page image/text → Structured Output → сохранение в `page`. И admin API, и platform v1 используют один сервис.

## Gamification

`services/gamification.py` содержит начисления XP/coins, anti-farm коэффициенты, цели и достижения. `gamification_events` имеет уникальный `(user_id, event_key)` для идемпотентности завершения задачи.

## Frontend

`static/css/app.css` — единый design system и layout. `static/js/app.js` — общие API/UI/Markdown/Math utilities. Role-specific JS не должен заново реализовывать common fetch/render helpers.

Breakpoints, используемые layout: mobile ~360–767px, tablet 768–1023px, desktop 1024+; chat sidebar переключается в drawer ниже 1280px.
