# EduAI

Telegram-бот и адаптивная web-платформа для ученика, родителя и администратора.

## Локальный запуск

1. Создайте окружение и установите зависимости:

   ```bash
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   ```

2. Скопируйте `.env.example` в `.env` и заполните значения.
3. После создания базовых таблиц EduAI примените миграцию чатов и Book Mode:

   ```bash
   psql "$DATABASE_URL" -f migrations/001_chat_sessions.sql
   ```

4. Запустите API и Telegram polling:

   ```bash
   .venv/bin/python main.py
   ```

Web-вход: `http://127.0.0.1:8000/auth.html`.

## Страницы

- `/auth.html` — Telegram Web App или вход по Telegram ID;
- `/student.html` — тьютор, задания, прогресс и награды;
- `/parent.html` — дети, ИИ-помощник, задания и магазин;
- `/admin.html` — учебники, страницы, пользователи и аудит.

Frontend использует защищённые маршруты `/api/v1/*` и Bearer-сессию. Старые chat-маршруты `/api/chats/*` сохранены как авторизованные адаптеры к тому же сервису сессий.

ИИ-тьютор поддерживает отдельные ветки диалогов, необязательный выбор учебника,
автоматическое распознавание книги из вопроса и вложения PNG/JPEG/WebP/GIF,
PDF, DOCX, XLSX, PPTX, ODT/ODS/ODP, EPUB, DjVu, RTF, HTML/XML и текстовых
форматов. PDF разрешены до 100 МБ, остальные вложения — до 15 МБ. В Telegram доступны `/new_chat` и
`/exit_book`. Для DjVu, который не открывается через MuPDF, установите системный
пакет `djvulibre` с утилитой `djvutxt`.

## Проверка

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q api bot services tests main.py
```

Для Telegram Web App нужен публичный HTTPS-адрес в `WEBAPP_BASE_URL`. В production рекомендуется собирать Tailwind локально вместо CDN и заменить вход только по Telegram ID на подтверждение через Telegram.

Подробная карта изменений и API находится в [IMPLEMENTATION.md](IMPLEMENTATION.md).
