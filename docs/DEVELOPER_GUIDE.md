# Руководство разработчика EduAI

## 1. Принципы

- один модуль — одна понятная ответственность;
- `routers/handlers → services → storage/DB/external clients`;
- не импортировать router из router;
- не создавать OpenAI client в feature-модулях;
- system prompts — только в `services/prompts/` и на английском;
- новые/изменённые комментарии и docstrings — на русском;
- пользовательский язык определяется запросом, а не языком system prompt;
- не раскрывать private answer keys, AI instructions, prompts и внутренние metadata.

## 2. Основные модули

- `services/tutor.py` — оркестрация tutor sessions/messages;
- `services/tutor_policy.py` — сборка prompt policy;
- `services/context_resolver.py` — Book Mode и поиск выбранного контекста;
- `services/educational_context.py` — ранжирование учебных источников;
- `services/chat_memory.py` / `conversation_context.py` — память и активный контекст;
- `services/task_generation.py` — общий structured task generation;
- `services/assignment_source.py` — источник задания (`teacher` / `tutor_practice`) и нормализация сложности;
- `services/attachment_storage.py` — ownership/storage/linking файлов;
- `GET /api/v1/attachments/library` — библиотека вложений текущего пользователя по чатам WebApp/Telegram;
- `DELETE /api/v1/attachments/{attachment_id}/memory` — удаление связи вложения с памятью/историей чата с сохранением файла, если он ещё нужен заданию;
- `services/interactive_apps.py` — безопасные интерактивные приложения;
- `services/textbook_digitizer.py` / `digitization_queue.py` — оцифровка;
- `services/response_formatter.py` — canonical Markdown/Math и Telegram fallback;
- `services/ai/client.py` — единственный OpenAI client layer.

## 3. OpenAI

Конфигурация:

```env
OPENAI_MODEL=gpt-4o
OPENAI_TIMEOUT_SECONDS=45
OPENAI_MAX_RETRIES=2
```

Feature-код получает общий `openai_client` и вызывает `create_chat_completion()` или `parse_chat_completion()`. Это сохраняет единые timeout/retry/logging правила и позволяет тестам подменять client.

## 4. Prompts

Prompt состоит из повторно используемых блоков:

```text
BASE RULES
+ ROLE RULES
+ ACTIVE CONTEXT
+ FEATURE-SPECIFIC RULES
+ OUTPUT FORMAT RULES
```

Новые feature rules добавляйте в `services/prompts/`, экспортируйте через `services/prompts/__init__.py` и собирайте в `tutor_policy.py` или конкретном service.

## 5. API и DTO

- GET — чтение;
- POST — создание/запуск операции;
- PATCH — частичное изменение;
- PUT — полная замена/обновление ресурса;
- DELETE — удаление.

Legacy GET `/api/tasks/generate/{tg_id}` пока сохранён для обратной совместимости; новые клиенты должны использовать POST-версию.

При добавлении Student response убедитесь, что рекурсивно исключены `reference_answer`, `correct_answer`, `ai_instructions`, system prompts и private verification metadata.

## 6. Task workflow и privacy

Обычное Teacher assignment никогда не отправляется сразу из генератора. `POST /api/v1/parent/task-drafts` создаёт persistent draft; `PATCH` редактирует; `/send` является единственным UI-финализатором. `POST /api/v1/parent/tasks/generate` также возвращает `status=draft`.

После ответа обычного задания статус становится `pending_review`. `POST /api/v1/parent/tasks/{task_id}/review-suggestion` возвращает только рекомендацию AI, а `POST /api/v1/parent/tasks/{task_id}/review` фиксирует решение Учителя. Legacy `/api/tasks/submit` и Telegram handler обязаны соблюдать ту же ручную проверку для `assignment_source=teacher`.

`student_safe_task_payload()` рекурсивно удаляет private answer fields. Никогда не передавайте `reference_answer`, `correct_answer`, `ai_instructions` или hidden criteria в Student DOM/state/download/Telegram. Интерактивные приложения проверяются через backend `grade_interactive_submission`; learner HTML проходит проверку `contains_embedded_solution_data`.

## 7. База данных

Все multi-step изменения, способные оставить частичное состояние, выполняйте внутри `async with conn.transaction()`. Совместимая схема, необходимая текущей версии приложения, централизована в `services/schema_migrations.py` и должна оставаться идемпотентной.

Перед удалением колонок или таблиц проверьте модели, SQL в services/routers и тестовые fixtures. Одноразовые SQL-файлы не являются runtime-зависимостью проекта.

## 8. Async

Не выполняйте тяжёлые синхронные операции в event loop без необходимости. PDF/OCR/file parsing должны либо быть короткими, либо выноситься в worker/thread. Долгие сетевые операции обязаны иметь timeout.

## 9. Errors и logging

Пользователь видит короткое безопасное сообщение. Полная ошибка остаётся в server log. Не логируйте tokens, passwords, API keys и полный текст приватных документов без необходимости.

## 10. Тесты

```bash
python -m pytest -q
python -m compileall -q api bot services tests main.py config.py database.py
```

Не подменяйте production modules глобально через `sys.modules`, если можно monkeypatch конкретную зависимость. Это загрязняет collection state других тестов.

## 11. Изменения схемы

Если текущей версии приложения требуется новое поле, индекс или служебная таблица, добавляйте минимальный идемпотентный DDL в `services/schema_migrations.py` и покрывайте именно требуемый runtime-контракт тестом. Не добавляйте тесты, которые проверяют наличие исторического отчёта или уже выполненного одноразового SQL-файла.

## 12. Добавление функции

1. Определите transport contracts/schema.
2. Добавьте business logic в service.
3. Добавьте endpoint/handler как тонкий adapter.
4. Если нужен AI — добавьте English prompt block и используйте `services.ai`.
5. Добавьте tests на business logic, permissions/privacy и transport.
6. Проверьте desktop/mobile UI.
7. Обновите документацию при изменении architecture/UX.

# Frontend Design System

## Общий принцип

Интерфейс — iOS-inspired, но с собственной идентичностью EduAI: контент важнее декора, панели компактны, постоянное занятие пространства сведено к минимуму. Основная реализация находится в `static/css/app.css`, а адаптивное UI-поведение — в `static/js/app.js`.

## Theme tokens

Базовые токены имеют префикс `--ios-*` (`--ios-bg`, `--ios-surface`, `--ios-text`, `--ios-accent`, `--ios-separator`, radius/shadow/control-height). Старые `--color-*` сохранены как совместимые алиасы.

Поддерживаются три режима: `light`, `dark`, `system`. Выбор хранится в `localStorage` по ключу `eduai.ui.theme`; для `system` используется `prefers-color-scheme`. Новые компоненты не должны содержать собственную независимую палитру.

## Typography

Основной stack — Inter с системными fallback. Используйте ограниченную иерархию H1/H2/H3/body/caption/button и не вводите отдельный размер для каждой карточки.

## Navigation

На desktop постоянная sidebar не занимает колонку: она открывается как navigation sheet, а основные разделы дублируются в компактной `.desktop-quick-nav`. На телефоне создаётся `.mobile-bottom-nav` с четырьмя основными разделами и кнопкой «Ещё». Активный раздел синхронизируется через `data-active-section`, последний открытый раздел сохраняется по pathname.

## AI Tutor panels

На desktop список чатов — компактный collapsible sidebar с поиском и профилем внизу; на mobile — off-canvas swipe-drawer с обычными кнопками открытия/закрытия для accessibility. Book Mode превращается в `.chat-context-panel`/sheet; после Apply панель закрывается. Центральный `.chat-center-card` остаётся главным содержимым.

Имя отправителя приходит в message DTO как `sender_name`. Профиль загружается один раз через `/api/v1/tutor/profile`; Telegram avatar отдаётся безопасным server-side proxy. Не делайте отдельный profile request на каждое сообщение.

Mobile keyboard определяется через `visualViewport` и focus: bottom navigation скрывается, composer остаётся над клавиатурой, layout не создаёт бесконечный vertical scroll.

## Layout customization

Часть dashboard widgets (`student-dashboard-stats`, admin stats) поддерживает drag-and-drop на desktop/tablet. Порядок хранится под ключами `eduai.ui.layout:*`. Кнопка «Сбросить расположение» удаляет layout/section state, но не сбрасывает выбранную тему. На mobile drag-and-drop отключён, чтобы не конфликтовать с touch scrolling.

## Cards, buttons, forms

Карточки используют radius 18–24px, мягкие shadows и умеренный blur. `.btn-primary` — одно главное действие; `.btn-secondary` — вторичное; `.btn-danger` — опасное. `.icon-btn` обязан иметь понятный context или `aria-label`. Формы используют `.field`, `.input`, `.select`, `.textarea`.

## Modal / sheet

Desktop использует floating modal/popover. На ширине до 767px `.modal-panel` становится bottom sheet с safe-area padding. Blur имеет `@supports` fallback на solid surface.

## Scroll control

Одна `.global-scroll-control` появляется только после фактического scroll, выбирает реальный scroll container и автоматически меняет направление `↓/↑` в зависимости от положения. Прежняя chat-only кнопка скрыта CSS, чтобы не дублировать управление.

## Breakpoints и accessibility

Обязательная ручная проверка: 1920×1080, 1366×768, 1024×768, 768px, 390px и 360px. Проверяйте keyboard focus, `aria-label`, touch target около 44px, contrast, отсутствие horizontal overflow и работу screen reader там, где control не имеет текстовой подписи.

## Motion и performance

Основные transition — 150–300ms. `prefers-reduced-motion: reduce` отключает animation/transition. Не добавляйте WebGL, постоянные JS-анимации или большое количество blur-слоёв. Тематический background остаётся почти незаметным и CSS-only.

## Math

Не реализуйте новый renderer в role-specific JS. Используйте `EduAI.renderRichContent` / `EduAI.markdown` и общий Math pipeline из `static/js/app.js`.
