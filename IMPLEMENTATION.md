# EduAI: AI Tutor, chat sessions and Book Mode

## Применение

1. Сделайте резервную копию PostgreSQL.
2. Установите зависимости: `.venv/bin/python -m pip install -r requirements.txt`.
3. Убедитесь, что базовые таблицы `users`, `book`, `page` и `chat_messages` уже существуют.
4. Выполните миграцию: `psql "$DATABASE_URL" -f migrations/001_chat_sessions.sql`.
5. Проверьте `BOT_TOKEN`, `OPENAI_API_KEY`, `DATABASE_URL`, `WEBAPP_BASE_URL` и `ADMIN_IDS` в `.env`.
6. Запустите: `.venv/bin/python main.py`.
7. В BotFather укажите HTTPS URL приложения для Telegram Web App.

Миграция идемпотентна. Старые сообщения без `session_id` не теряются: сервис
привязывает их к первой созданной ветке пользователя.

## Карта изменений

- `services/context_resolver.py` — ручное и естественно-языковое разрешение класса, предмета, книги, автора, страницы, параграфа и упражнения; поддерживается транслитерация фамилий.
- `services/tutor.py` — единый сервис Student/Parent Tutor, ветки чатов, история, переименование, Book Mode, OpenAI и сохранение сообщений.
- `services/file_parser.py` — изображения, PDF, DOCX, XLSX, PPTX, ODT/ODS/ODP, EPUB, DjVu, RTF/HTML/XML и текстовые вложения; PDF до 100 МБ, остальные файлы до 15 МБ.
- `services/thinking.py` — Telegram-таймер и typing status.
- `api/routers/tutor.py` — защищённый Web API веток, сообщений, вложений и каскадных фильтров.
- `bot/handlers/ai_chat.py`, `bot/handlers/quests.py`, `bot/media.py` — общий Tutor для всех ролей, файлы, `/new_chat`, `/exit_book`, закрепление контекста и таймер.
- `static/js/chat.js` — общий интерфейс ученика и родителя: sidebar, переключение, новый чат, переименование до 35 символов, файлы и Book Mode.
- `static/js/auth.js` — явная кнопка Telegram WebApp, `ready()/expand()`, чтение `initData`, HMAC endpoint и role redirect.
- `static/js/app.js`, `static/css/app.css` — stopwatch loader и адаптивные компоненты.
- `templates/student.html`, `templates/parent.html`, `templates/auth.html` — новые UI-компоненты.

## Новый API

Все маршруты ниже требуют `Authorization: Bearer <session_token>`.

- `GET/POST /api/v1/tutor/sessions`
- `PATCH/DELETE /api/v1/tutor/sessions/{session_id}`
- `GET /api/v1/tutor/sessions/{session_id}/messages`
- `PUT/DELETE /api/v1/tutor/sessions/{session_id}/context`
- `POST /api/v1/tutor/messages` — `multipart/form-data`: `session_id`, `message_text`, необязательный `attachment` и необязательные поля контекста.
- `GET /api/v1/tutor/context/classes`
- `GET /api/v1/tutor/context/subjects?book_class=6`
- `GET /api/v1/tutor/context/books?book_class=6&book_program=Математика`
- `GET /api/v1/tutor/context/pages?book_id=1`

Явное упоминание книги/автора/страницы в естественном запросе включает Book
Mode автоматически. Ручной выбор можно закрепить кнопкой. Каждый ответ в этом
режиме содержит инструкцию `/exit_book`; Web UI также показывает кнопку выхода.

## Проверка и точный diff

```bash
.venv/bin/python -m compileall -q api bot services tests main.py
.venv/bin/python -m pytest -q
git diff --check
git diff --stat
git diff -- api bot services static templates migrations tests README.md IMPLEMENTATION.md
```

Ручной smoke test:

1. Откройте `/auth.html` внутри Telegram и нажмите кнопку входа.
2. Создайте две ветки, переименуйте одну, переключитесь между ними.
3. Отправьте обычный вопрос, затем изображение и документ.
4. Напишите: `Объясни упражнение 3 из учебника Виленкина для 6 класса`.
5. Проверьте footer Book Mode и выход кнопкой или `/exit_book` в боте.
6. В Parent Mode повторите запрос и создайте задание ребёнку.

## Исправление доставки сообщений Tutor

- Telegram использует `StateFilter(None)` вместо некорректного `F.state == None`,
  поэтому обычный текст, фото и документы действительно попадают в общий handler.
- Фото/документ можно отправить сразу после выбора учебника, не вводя тему отдельным сообщением.
- Web submit полностью обёрнут обработкой ошибок и поддерживает Enter; операции до
  `fetch` больше не могут завершиться молча.
- К статическим ресурсам добавлена версия `v=20260728-1`, чтобы Telegram WebView
  не использовал старый `chat.js` из кэша.
- Реальные smoke tests `/api/v1/tutor/messages` с PNG и PPTX получили HTTP 200 от OpenAI.
- Telegram-тексты с `/exit_book`, `_`, `*` и содержимым AI отправляются без
  небезопасного Markdown entity parsing; длинные ответы автоматически делятся
  на сообщения до 4000 символов.
