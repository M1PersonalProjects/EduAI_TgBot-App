# TZ22 installer v3

Эта версия предназначена для ситуации, когда SQL из миграции уже вручную
выполнен в DataGrip, но файл `.sql` не добавлялся в проект.

`migrations/022_textbook_digitization_queue.sql` НЕ требуется.

Перед запуском должны существовать только:

- services/textbook_digitizer.py
- services/digitization_queue.py
- api/routers/digitization.py

Запуск:

```bash
python3 apply_tz22_v3.py
python3 -m compileall -q api services tests main.py
node --check static/js/admin.js
python3 -m pytest -q
```

SQL повторно выполнять не нужно.
