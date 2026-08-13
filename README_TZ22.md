# EduAI TZ22 — persistent batch textbook digitization

## What changes

- multiple PDF upload;
- one ZIP containing multiple PDFs;
- PostgreSQL-backed queue;
- sequential server-side worker;
- survives closing WebApp;
- pending jobs survive server restart;
- processing jobs are recovered to pending after restart;
- per-job progress and error state;
- retry without re-upload while source file remains on disk;
- SHA-256 duplicate protection;
- safe ZIP reading without `extractall()` / Zip Slip;
- existing single-PDF route is refactored to use the same reusable pipeline.

## Install

1. Copy this whole bundle into the project root, preserving paths.
2. Run:

```bash
python3 apply_tz22.py
psql "$DATABASE_URL" -f migrations/022_textbook_digitization_queue.sql
python3 -m compileall -q api bot services tests main.py
node --check static/js/admin.js
python3 -m pytest -q
```

3. Restart EduAI.

## Important mapping rule

The current EduAI digitizer requires an existing `book_id`; it cannot safely invent grade, subject and author from a PDF filename.

- For several directly selected PDFs, the Admin UI lets you assign an existing book to each PDF before upload.
- For ZIP, the backend auto-matches the PDF basename to an existing `book.book_title`.
- If a ZIP entry cannot be uniquely matched, it is stored as `waiting_for_book`, not lost. In the queue, select the correct textbook; it immediately becomes `pending`.

This avoids creating incorrect textbook metadata while still allowing a ZIP with many books to be uploaded once.
