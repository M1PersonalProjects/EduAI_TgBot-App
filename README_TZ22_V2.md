# EduAI TZ22 installer v2

Исправляет `shutil.SameFileError` из первого установщика.

В вашей текущей ситуации миграция PostgreSQL уже применена — повторно выполнять `022_textbook_digitization_queue.sql` не нужно.

1. Скопируйте `apply_tz22_v2.py` в корень проекта рядом с `main.py`.
2. Убедитесь, что распакованный первый пакет уже добавил файлы:
   - `services/textbook_digitizer.py`
   - `services/digitization_queue.py`
   - `api/routers/digitization.py`
   - `migrations/022_textbook_digitization_queue.sql`
3. Выполните:

```bash
python3 apply_tz22_v2.py
python3 -m compileall -q api services tests main.py
node --check static/js/admin.js
python3 -m pytest -q
```

После успешных проверок перезапустите сервер.

Резервные копии изменяемых production-файлов будут сохранены в `.tz22_backup/`.
