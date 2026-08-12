from pathlib import Path
import re

VERSION = "20260812-4"
for rel in ("templates/student.html", "templates/parent.html"):
    path = Path(rel)
    if not path.exists():
        print(f"skip: {rel} not found")
        continue
    text = path.read_text(encoding="utf-8")
    text, count = re.subn(
        r'(/static/js/app\.js)\?v=[^"\']+',
        rf'\1?v={VERSION}',
        text,
    )
    if not count:
        text = text.replace('/static/js/app.js"', f'/static/js/app.js?v={VERSION}"')
    path.write_text(text, encoding="utf-8")
    print(f"updated cache key: {rel}")

# Also bump chat/student/parent JS cache keys so an old page bundle cannot mask the fix.
for rel in ("templates/student.html", "templates/parent.html"):
    path = Path(rel)
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'(/static/js/(?:chat|student|parent)\.js)\?v=[^"\']+', rf'\1?v={VERSION}', text)
    path.write_text(text, encoding="utf-8")
