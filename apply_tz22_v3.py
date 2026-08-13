from pathlib import Path
import re
import shutil

ROOT = Path.cwd()
BACKUP = ROOT / ".tz22_v3_backup"
BACKUP.mkdir(exist_ok=True)

# SQL migration is intentionally NOT required here.
# The database migration may already have been applied manually via DataGrip.
REQUIRED_CODE_FILES = (
    ROOT / "services/textbook_digitizer.py",
    ROOT / "services/digitization_queue.py",
    ROOT / "api/routers/digitization.py",
)

for path in REQUIRED_CODE_FILES:
    if not path.exists():
        raise SystemExit(
            f"Не найден обязательный файл TZ22: {path.relative_to(ROOT)}. "
            "Распакуйте исходный пакет TZ22 в корень проекта и повторите запуск."
        )


def backup(path: Path) -> None:
    if not path.exists():
        raise RuntimeError(f"Не найден файл: {path}")
    rel = path.relative_to(ROOT)
    dest = BACKUP / rel
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)


def update_file(path: Path, text: str) -> None:
    old = path.read_text(encoding="utf-8")
    if old == text:
        print(f"already OK: {path.relative_to(ROOT)}")
        return
    backup(path)
    path.write_text(text, encoding="utf-8")
    print(f"updated: {path.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# main.py
# ---------------------------------------------------------------------------
main_path = ROOT / "main.py"
if not main_path.exists():
    raise SystemExit("Не найден main.py")

main = main_path.read_text(encoding="utf-8")

if "from api.routers.digitization import router as digitization_router" not in main:
    candidates = [
        "from api.routers.tutor import router as tutor_v1_router\n",
        "from api.routers.attachments import router as attachments_v1_router\n",
    ]
    anchor = next((x for x in candidates if x in main), None)
    if not anchor:
        raise RuntimeError("main.py: не найдена точка для импорта digitization_router")
    main = main.replace(
        anchor,
        anchor
        + "from api.routers.digitization import router as digitization_router\n"
        + "from services.digitization_queue import "
          "start_digitization_worker, stop_digitization_worker\n",
        1,
    )

# Add worker calls to existing lifespan instead of replacing the whole function.
if "await start_digitization_worker()" not in main:
    marker = "    await db.connect()\n"
    if marker not in main:
        raise RuntimeError("main.py: не найден await db.connect() в lifespan")
    main = main.replace(
        marker,
        marker + "    await start_digitization_worker()\n",
        1,
    )

if "await stop_digitization_worker()" not in main:
    # Put shutdown immediately before db.disconnect if present.
    marker = "        await db.disconnect()\n"
    if marker in main:
        main = main.replace(
            marker,
            "        await stop_digitization_worker()\n" + marker,
            1,
        )
    else:
        marker = "    await db.disconnect()\n"
        if marker not in main:
            raise RuntimeError("main.py: не найден await db.disconnect()")
        main = main.replace(
            marker,
            "    await stop_digitization_worker()\n" + marker,
            1,
        )

if "app.include_router(digitization_router)" not in main:
    include_candidates = [
        "app.include_router(attachments_v1_router)\n",
        "app.include_router(tutor_v1_router)\n",
    ]
    anchor = next((x for x in include_candidates if x in main), None)
    if not anchor:
        raise RuntimeError("main.py: не найдена точка include_router")
    main = main.replace(
        anchor,
        anchor + "app.include_router(digitization_router)\n",
        1,
    )

update_file(main_path, main)


# ---------------------------------------------------------------------------
# templates/admin.html
# ---------------------------------------------------------------------------
html_path = ROOT / "templates/admin.html"
if not html_path.exists():
    raise SystemExit("Не найден templates/admin.html")

html = html_path.read_text(encoding="utf-8")

# Make the file input accept multiple PDFs and ZIPs.
html = re.sub(
    r'(<input[^>]+id=["\']pdf-file["\'][^>]*)(>)',
    lambda m: (
        re.sub(r'\s+multiple\b', '', m.group(1))
        .replace(
            'accept=".pdf"',
            'accept=".pdf,.zip,application/pdf,application/zip"'
        )
        .replace(
            'accept="application/pdf"',
            'accept=".pdf,.zip,application/pdf,application/zip"'
        )
        + ' multiple'
        + m.group(2)
    ),
    html,
    count=1,
    flags=re.S,
)

html = html.replace("Перетащите PDF сюда", "Перетащите PDF-файлы или ZIP сюда")
html = html.replace(
    "или нажмите, чтобы выбрать файл до 100 МБ",
    "или выберите несколько PDF или один ZIP"
)

html = re.sub(
    r'(/static/js/admin\.js)(?:\?v=[^"\']+)?',
    r'\1?v=20260813-22-3',
    html,
)

update_file(html_path, html)


# ---------------------------------------------------------------------------
# static/js/admin.js
# ---------------------------------------------------------------------------
js_path = ROOT / "static/js/admin.js"
if not js_path.exists():
    raise SystemExit("Не найден static/js/admin.js")

js = js_path.read_text(encoding="utf-8")

# If the queue UI code from TZ22 is already present, leave it intact.
queue_present = (
    "/api/v1/admin/digitization/jobs" in js
    and "/api/v1/admin/digitization/upload" in js
)

if not queue_present:
    old_start = js.find("const file=$('pdf-file'),zone=$('drop-zone');")
    if old_start < 0:
        old_start = js.find("  const file=$('pdf-file'),zone=$('drop-zone');")

    old_end = js.find("async function loadPages(bookId)", old_start)
    if old_end < 0:
        old_end = js.find("  async function loadPages(bookId)", old_start)

    if old_start < 0 or old_end < 0:
        raise RuntimeError(
            "admin.js: не удалось найти старый блок одиночной загрузки PDF. "
            "Пришлите static/js/admin.js, если файл уже сильно изменён."
        )

    indent = "  " if js[old_start:old_start+2] == "  " else ""

    queue_code = r"""
  const file=$('pdf-file'),zone=$('drop-zone');

  const digitizationSection=$('digitization');
  const queuePanel=document.createElement('div');
  queuePanel.className='glass card mt-4';
  queuePanel.innerHTML=`
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h3 class="font-extrabold">Очередь оцифровки</h3>
        <p class="mt-1 text-sm muted">
          Очередь работает на сервере. После загрузки страницу можно закрыть.
        </p>
      </div>
      <button id="refresh-digitization-queue" class="btn-secondary" type="button">
        Обновить
      </button>
    </div>
    <div id="digitization-upload-map" class="mt-4 grid gap-2"></div>
    <div id="digitization-queue" class="mt-4 grid gap-3">
      <p class="muted">Загрузка…</p>
    </div>`;
  digitizationSection.append(queuePanel);

  function selectedDigitizationFiles(){
    return Array.from(file.files||[]);
  }

  function renderDigitizationUploadMap(){
    const files=selectedDigitizationFiles();
    $('file-label').textContent=files.length
      ? files.map(item=>item.name).join(', ')
      : 'или выберите несколько PDF или один ZIP';

    $('upload-pdf').disabled=!files.length;

    const map=$('digitization-upload-map');
    if(
      files.length>1 &&
      files.every(item=>item.name.toLowerCase().endsWith('.pdf'))
    ){
      map.innerHTML=`
        <p class="text-xs muted">
          Для каждого PDF можно выбрать учебник. Пустое значение —
          попробовать сопоставить автоматически по имени.
        </p>
        ${files.map(item=>`
          <div class="grid sm:grid-cols-[minmax(0,1fr)_18rem] gap-2 items-center">
            <span class="truncate text-sm">${EduAI.escapeHtml(item.name)}</span>
            <select
              class="select digitization-book-map"
              data-name="${EduAI.escapeHtml(item.name)}"
            >
              <option value="">Автосопоставление</option>
              ${state.books.map(book=>`
                <option value="${book.book_id}">
                  ${book.book_class} кл. · ${EduAI.escapeHtml(book.book_title)}
                </option>`).join('')}
            </select>
          </div>`).join('')}`;
    }else{
      map.innerHTML='';
    }
  }

  file.addEventListener('change',renderDigitizationUploadMap);

  ['dragenter','dragover'].forEach(type=>zone.addEventListener(type,event=>{
    event.preventDefault();
    zone.classList.add('dragging');
  }));

  ['dragleave','drop'].forEach(type=>zone.addEventListener(type,event=>{
    event.preventDefault();
    zone.classList.remove('dragging');
  }));

  zone.addEventListener('drop',event=>{
    const transfer=new DataTransfer();
    Array.from(event.dataTransfer.files||[]).forEach(item=>transfer.items.add(item));
    file.files=transfer.files;
    file.dispatchEvent(new Event('change'));
  });

  function digitizationStatusText(value){
    return {
      waiting_for_book:'Нужно выбрать учебник',
      pending:'Ожидает',
      processing:'Обрабатывается',
      completed:'Завершено',
      failed:'Ошибка'
    }[value]||value;
  }

  function digitizationStatusIcon(value){
    return {
      waiting_for_book:'⚠️',
      pending:'🕓',
      processing:'⚙️',
      completed:'✅',
      failed:'❌'
    }[value]||'•';
  }

  async function loadDigitizationQueue(){
    try{
      const items=await EduAI.api('/api/v1/admin/digitization/jobs');
      $('digitization-queue').innerHTML=items.length
        ? items.map(job=>`
          <article class="rounded-2xl bg-white/[.04] p-4">
            <div class="flex flex-wrap justify-between gap-3">
              <div class="min-w-0">
                <p class="font-bold truncate">
                  ${digitizationStatusIcon(job.status)}
                  ${EduAI.escapeHtml(job.original_name)}
                </p>
                <p class="mt-1 text-xs muted">
                  ${digitizationStatusText(job.status)}
                  ${job.book_title?' · '+EduAI.escapeHtml(job.book_title):''}
                  ${job.total_pages
                    ? ` · ${job.processed_pages}/${job.total_pages} стр.`
                    : ''}
                </p>
                ${job.stage?`
                  <p class="mt-1 text-xs muted">
                    Этап: ${EduAI.escapeHtml(job.stage)}
                  </p>`:''}
                ${job.error_text?`
                  <p class="mt-2 text-sm text-rose-200">
                    ${EduAI.escapeHtml(job.error_text)}
                  </p>`:''}
              </div>

              <div class="flex flex-wrap gap-2">
                ${job.status==='failed'?`
                  <button
                    class="btn-secondary retry-digitization"
                    data-id="${job.job_id}"
                    type="button"
                  >Повторить</button>`:''}

                ${job.status==='waiting_for_book'||job.status==='failed'?`
                  <select
                    class="select assign-digitization-book"
                    data-id="${job.job_id}"
                  >
                    <option value="">Выбрать учебник…</option>
                    ${state.books.map(book=>`
                      <option value="${book.book_id}">
                        ${book.book_class} кл. · ${EduAI.escapeHtml(book.book_title)}
                      </option>`).join('')}
                  </select>`:''}
              </div>
            </div>
          </article>`).join('')
        : '<p class="muted">Очередь пока пуста.</p>';
    }catch(error){
      EduAI.toast(error.message,'error');
    }
  }

  $('refresh-digitization-queue').addEventListener(
    'click',
    loadDigitizationQueue
  );

  $('digitization-queue').addEventListener('click',async event=>{
    const retry=event.target.closest('.retry-digitization');
    if(!retry)return;

    try{
      await EduAI.api(
        `/api/v1/admin/digitization/jobs/${retry.dataset.id}/retry`,
        {method:'POST'}
      );
      await loadDigitizationQueue();
    }catch(error){
      EduAI.toast(error.message,'error');
    }
  });

  $('digitization-queue').addEventListener('change',async event=>{
    const select=event.target.closest('.assign-digitization-book');
    if(!select||!select.value)return;

    try{
      await EduAI.api(
        `/api/v1/admin/digitization/jobs/${select.dataset.id}/assign/${select.value}`,
        {method:'POST'}
      );
      await loadDigitizationQueue();
    }catch(error){
      EduAI.toast(error.message,'error');
    }
  });

  $('upload-pdf').addEventListener('click',async event=>{
    const files=selectedDigitizationFiles();
    if(!files.length)return;

    const button=event.currentTarget;
    const form=new FormData();

    files.forEach(item=>form.append('files',item));

    const map={};
    document.querySelectorAll('.digitization-book-map').forEach(select=>{
      if(select.value){
        map[select.dataset.name]=Number(select.value);
      }
    });

    form.append('book_map_json',JSON.stringify(map));

    if(
      files.length===1 &&
      files[0].name.toLowerCase().endsWith('.pdf') &&
      $('upload-book').value
    ){
      form.append('default_book_id',$('upload-book').value);
    }

    EduAI.setBusy(button,true,'Добавляем в очередь…');

    try{
      const result=await EduAI.api(
        '/api/v1/admin/digitization/upload',
        {method:'POST',body:form}
      );

      const created=(result.jobs||[]).filter(item=>!item.duplicate).length;
      const duplicates=(result.jobs||[]).filter(item=>item.duplicate).length;

      EduAI.toast(
        duplicates
          ? `Добавлено: ${created}. Дубликатов: ${duplicates}.`
          : `Добавлено задач: ${created}`,
        'success'
      );

      file.value='';
      renderDigitizationUploadMap();
      await loadDigitizationQueue();
    }catch(error){
      EduAI.toast(error.message,'error');
    }finally{
      EduAI.setBusy(button,false);
    }
  });

  await loadDigitizationQueue();
  setInterval(loadDigitizationQueue,4000);

"""

    # Preserve indentation exactly as the surrounding file expects.
    queue_code = queue_code.lstrip("\n")
    if not indent and queue_code.startswith("  "):
        queue_code = "\n".join(
            line[2:] if line.startswith("  ") else line
            for line in queue_code.splitlines()
        ) + "\n"

    js = js[:old_start] + queue_code + js[old_end:]

update_file(js_path, js)


print()
print("TZ22 v3 успешно применён.")
print("SQL-файл в проекте НЕ требуется.")
print("SQL повторно выполнять НЕ нужно.")
print("Backup:", BACKUP)
print()
print("Проверка:")
print("  python3 -m compileall -q api services tests main.py")
print("  node --check static/js/admin.js")
print("  python3 -m pytest -q")
