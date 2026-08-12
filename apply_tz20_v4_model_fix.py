from pathlib import Path
import re
import shutil

path = Path("api/routers/platform.py")
if not path.exists():
    raise SystemExit("Не найден api/routers/platform.py")

backup_dir = Path(".tz20_v4_backup")
backup_dir.mkdir(exist_ok=True)
shutil.copy2(path, backup_dir / "platform.py")

text = path.read_text(encoding="utf-8")

if "class TaskAttachmentOption(BaseModel):" not in text:
    marker = "class ParentTaskRequest(BaseModel):"
    if marker not in text:
        raise RuntimeError("Не найден class ParentTaskRequest(BaseModel)")

    model = '''class TaskAttachmentOption(BaseModel):
    attachment_id: int
    use_as_ai_context: bool = True
    visible_to_student: bool = False


'''
    text = text.replace(marker, model + marker, 1)

text, count = re.subn(
    r'attachment_options:\s*List\[Dict\[str,\s*Any\]\]\s*=\s*Field\(default_factory=list,\s*max_length=10\)',
    'attachment_options: List[TaskAttachmentOption] = Field(default_factory=list, max_length=10)',
    text,
    count=1,
)

if count == 0 and "attachment_options: List[TaskAttachmentOption]" not in text:
    raise RuntimeError("Не удалось обновить тип attachment_options")

old = '''    for item in payload.attachment_options or []:
        try:
            result[int(item.get("attachment_id"))] = item
        except (TypeError, ValueError):
            continue
'''
new = '''    for item in payload.attachment_options or []:
        data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        try:
            result[int(data.get("attachment_id"))] = data
        except (TypeError, ValueError):
            continue
'''
if old in text:
    text = text.replace(old, new, 1)

old2 = '''    for item in attachment_options or []:
        try:
            option_map[int(item.get("attachment_id"))] = item
        except (TypeError, ValueError):
            continue
'''
new2 = '''    for item in attachment_options or []:
        data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        try:
            option_map[int(data.get("attachment_id"))] = data
        except (TypeError, ValueError):
            continue
'''
if old2 in text:
    text = text.replace(old2, new2, 1)

path.write_text(text, encoding="utf-8")

print("TZ20 v4 model fix applied.")
print("Added/restored: TaskAttachmentOption")
print("Updated: ParentTaskRequest.attachment_options")
print("Backup: .tz20_v4_backup/platform.py")
