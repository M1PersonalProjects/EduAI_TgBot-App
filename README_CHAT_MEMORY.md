# EduAI — память контекста и файлов внутри chat_session

Пакет подготовлен для актуальной структуры EduAI_TgBot-App.

## Что заменить / добавить

Скопируйте содержимое архива в корень проекта с сохранением путей:

- `services/tutor.py` — заменить;
- `services/chat_memory.py` — новый файл;
- `api/routers/tutor.py` — заменить;
- `bot/media.py` — заменить;
- `static/js/chat.js` — заменить;
- `tests/services/test_chat_memory.py` — новый тест;
- `migrations/003_chat_memory_and_attachments.sql` — SQL-миграция.

`services/attachment_storage.py` не заменяется: новая логика специально использует существующий `save_upload`, `get_attachment` и `load_attachment_for_ai`.

## Порядок установки

1. Остановите приложение.
2. Сделайте резервную копию БД и перечисленных файлов.
3. Выполните `migrations/003_chat_memory_and_attachments.sql` целиком в DataGrip/psql.
4. Замените/добавьте файлы из ZIP.
5. Запустите:

```bash
python3 -m pytest -q
python3 -m compileall -q api bot services tests main.py
```

6. Перезапустите приложение. Для WebApp сделайте hard reload (Cmd+Shift+R), потому что `chat.js` мог остаться в браузерном кэше.

## Основная логика

- WebApp-вложение сначала сохраняется через существующий `attachment_storage`.
- Telegram-вложение также сохраняется через тот же `attachment_storage`.
- После создания `chat_messages.message_id` создаётся связь в `chat_message_attachments`, включая `session_id`.
- История API возвращает `attachments: []` у каждого сообщения.
- Short-term memory: до 24 последних сообщений плюс важные закреплённые ранние сообщения.
- Long-term memory: `chat_sessions.memory_state` + `memory_summary`.
- Большие блоки и наборы задач закрепляются по `message_id`, а не исчезают после 16 сообщений.
- По старой истории выполняется keyword retrieval при ссылках на прошлый контекст.
- Вложения выбираются по имени, типу, тексту, давности и активному attachment state; все файлы сессии в каждый prompt не добавляются.
- Релевантное старое изображение повторно читается из оригинального файла и отправляется мультимодальной модели.
- Book Mode остаётся связан с `chat_session` существующим механизмом.
- Новый чат имеет отдельный `memory_state` и не наследует память другого session_id.

## Важно

Миграция добавляет FK `chat_messages.session_id -> chat_sessions.session_id` как `NOT VALID`: новые записи контролируются сразу, но старые потенциально осиротевшие сообщения не удаляются. В конце SQL есть проверка. Если она возвращает 0, можно выполнить предложенные `VALIDATE CONSTRAINT`.
