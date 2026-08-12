from pathlib import Path
import re

VERSION = "20260812-5"
TEMPLATES = Path("templates")

if not TEMPLATES.exists():
    raise SystemExit("Run this script from the EduAI project root: templates/ not found")

changed = []
for path in TEMPLATES.glob("*.html"):
    text = path.read_text(encoding="utf-8")
    original = text

    # Force a new URL for the shared renderer so the browser cannot reuse v4/v1.
    text = re.sub(
        r'(/static/js/app\.js)(?:\?v=[^"\']*)?',
        rf'\1?v={VERSION}',
        text,
    )

    # Chat pages can also hold an old JS bundle in cache. Bump only known app bundles.
    text = re.sub(
        r'(/static/js/(?:chat|student|parent)\.js)(?:\?v=[^"\']*)?',
        rf'\1?v={VERSION}',
        text,
    )

    if text != original:
        path.write_text(text, encoding="utf-8")
        changed.append(str(path))

print("TZ19 final cache-bust applied.")
if changed:
    for item in changed:
        print(" updated:", item)
else:
    print(" No template changes were necessary.")

# Show exactly which app.js URLs remain.
for path in TEMPLATES.glob("*.html"):
    text = path.read_text(encoding="utf-8")
    if "/static/js/app.js" in text:
        matches = re.findall(r'/static/js/app\.js[^"\']*', text)
        for match in matches:
            print(f" {path}: {match}")
