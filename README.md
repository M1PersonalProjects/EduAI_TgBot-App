# EduAI

Telegram-бот и адаптивная web-платформа для ученика, родителя и администратора.

## Локальный запуск

1. Создайте окружение и установите зависимости:

   ```bash
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   ```

2. Скопируйте `.env.example` в `.env` и заполните значения.
3. Создайте схему PostgreSQL безопасным скриптом:

   ```bash
   psql "$DATABASE_URL" -f database_fixes.sql
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

Frontend использует защищённые маршруты `/api/v1/*` и Bearer-сессию. Старые `/api/*` сохранены для совместимости с ботом и существующими тестами.

## Проверка

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q api bot main.py
```

Для Telegram Web App нужен публичный HTTPS-адрес в `WEBAPP_BASE_URL`. В production рекомендуется собирать Tailwind локально вместо CDN и заменить вход только по Telegram ID на подтверждение через Telegram.
