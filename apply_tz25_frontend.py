from pathlib import Path
import re
import shutil

ROOT = Path.cwd()
JS = ROOT / "static/js/admin.js"
HTML = ROOT / "templates/admin.html"
BACKUP = ROOT / ".tz25_backup"

for path in (JS, HTML):
    if not path.exists():
        raise SystemExit(f"Не найден {path}")

BACKUP.mkdir(exist_ok=True)

def backup(path):
    dest = BACKUP / path.relative_to(ROOT)
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)

backup(JS)
backup(HTML)

js = JS.read_text(encoding="utf-8")

start = js.find("const file=$('pdf-file'),zone=$('drop-zone');")
if start < 0:
    start = js.find("  const file=$('pdf-file'),zone=$('drop-zone');")

end = js.find("async function loadPages(bookId)", start)
if end < 0:
    end = js.find("  async function loadPages(bookId)", start)

if start < 0 or end < 0:
    raise RuntimeError(
        "Не удалось найти блок пакетной оцифровки TZ22 в admin.js"
    )

block = r'''const file=$('pdf-file'),zone=$('drop-zone');
  const digitizationSection=$('digitization');
  const queuePanel=document.createElement('div');
  queuePanel.className='glass card mt-4';
  queuePanel.innerHTML=`
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h3 class="font-extrabold">Сопоставление и очередь оцифровки</h3>
        <p class="mt-1 text-sm muted">
          Сначала сопоставьте каждый PDF с заранее созданным пустым учебником.
          OCR начнётся только после подтверждения всего пакета.
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <button id="refresh-digitization-books" class="btn-secondary" type="button">
          Обновить учебники
        </button>
        <button id="refresh-digitization-queue" class="btn-secondary" type="button">
          Обновить очередь
        </button>
      </div>
    </div>

    <div id="digitization-match-summary" class="mt-4"></div>
    <div id="digitization-queue" class="mt-4 grid gap-4">
      <p class="muted">Загрузка…</p>
    </div>`;
  digitizationSection.append(queuePanel);

  let emptyDigitizationBooks=[];

  function selectedDigitizationFiles(){
    return Array.from(file.files||[]);
  }

  function bookOptionLabel(book){
    return `${book.book_title} — ${book.book_program} — ${book.book_class} класс — ${book.book_author} — ID ${book.book_id}`;
  }

  async function loadEmptyDigitizationBooks(){
    emptyDigitizationBooks=await EduAI.api(
      '/api/v1/admin/digitization/empty-books'
    );
  }

  function renderSelectedUploadFiles(){
    const files=selectedDigitizationFiles();
    $('file-label').textContent=files.length
      ? files.map(item=>item.name).join(', ')
      : 'или выберите несколько PDF или один ZIP';
    $('upload-pdf').disabled=!files.length;
  }

  file.addEventListener('change',renderSelectedUploadFiles);

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
    Array.from(event.dataTransfer.files||[]).forEach(item=>{
      transfer.items.add(item);
    });
    file.files=transfer.files;
    file.dispatchEvent(new Event('change'));
  });

  function statusText(value){
    return {
      matching:'Сопоставление',
      pending:'Ожидает',
      processing:'Обрабатывается',
      completed:'Завершено',
      failed:'Ошибка'
    }[value]||value;
  }

  function statusIcon(value){
    return {
      matching:'🔗',
      pending:'🕓',
      processing:'⚙️',
      completed:'✅',
      failed:'❌'
    }[value]||'•';
  }

  function matchText(job){
    if(job.match_type==='automatic')return 'Автоматически';
    if(job.match_type==='manual')return 'Вручную';
    if(job.stage==='ambiguous_match')return 'Несколько точных совпадений';
    return 'Учебник не найден';
  }

  function matchingBookIds(batchJobs){
    return new Set(
      batchJobs
        .filter(job=>job.book_id)
        .map(job=>Number(job.book_id))
    );
  }

  function renderBookSelect(job,batchJobs){
    const used=matchingBookIds(
      batchJobs.filter(item=>item.job_id!==job.job_id)
    );

    return `
      <select
        class="select assign-digitization-book w-full"
        data-id="${job.job_id}"
      >
        <option value="">Выберите пустой учебник…</option>
        ${emptyDigitizationBooks.map(book=>`
          <option
            value="${book.book_id}"
            ${Number(job.book_id)===Number(book.book_id)?'selected':''}
            ${used.has(Number(book.book_id))?'disabled':''}
          >
            ${EduAI.escapeHtml(bookOptionLabel(book))}
          </option>`).join('')}
      </select>`;
  }

  function renderMatchingBatch(batchId,jobs){
    const matched=jobs.filter(job=>job.book_id).length;
    const ready=matched===jobs.length && jobs.length>0;

    return `
      <section class="rounded-2xl border border-white/10 bg-white/[.025] p-4">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h4 class="font-extrabold">Сопоставление учебников</h4>
            <p class="mt-1 text-sm ${ready?'text-emerald-200':'muted'}">
              ${matched} / ${jobs.length} файлов сопоставлены
            </p>
          </div>
          <button
            class="btn-primary confirm-digitization-batch"
            data-batch="${batchId}"
            type="button"
            ${ready?'':'disabled'}
          >
            Начать оцифровку
          </button>
        </div>

        <div class="mt-4 grid gap-3">
          ${jobs.map(job=>`
            <article class="rounded-xl bg-white/[.04] p-3">
              <div class="flex flex-col gap-3 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(18rem,28rem)] lg:items-center">
                <div class="min-w-0">
                  <p class="font-bold break-words">
                    ${job.book_id?'✅':'⚠️'}
                    ${EduAI.escapeHtml(job.original_name)}
                  </p>
                  <p class="mt-1 text-xs muted">
                    ${EduAI.escapeHtml(matchText(job))}
                    ${job.book_title
                      ? ` · → ${EduAI.escapeHtml(job.book_title)}`
                      : ''}
                  </p>
                </div>
                ${renderBookSelect(job,jobs)}
              </div>
            </article>`).join('')}
        </div>

        <p class="mt-3 text-xs muted">
          Если нужного учебника нет, создайте его в разделе «Учебники»,
          затем нажмите «Обновить учебники».
        </p>
      </section>`;
  }

  function renderQueueJob(job){
    return `
      <article class="rounded-2xl bg-white/[.04] p-4">
        <div class="flex flex-wrap justify-between gap-3">
          <div class="min-w-0">
            <p class="font-bold break-words">
              ${statusIcon(job.status)}
              ${EduAI.escapeHtml(job.original_name)}
            </p>
            <p class="mt-1 text-xs muted">
              ${statusText(job.status)}
              ${job.book_title?` · ${EduAI.escapeHtml(job.book_title)}`:''}
              ${job.match_type?` · ${job.match_type==='automatic'?'авто':'вручную'}`:''}
              ${job.total_pages?` · ${job.processed_pages}/${job.total_pages} стр.`:''}
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

          ${job.status==='failed'?`
            <button
              class="btn-secondary retry-digitization"
              data-id="${job.job_id}"
              type="button"
            >
              Повторить
            </button>`:''}
        </div>
      </article>`;
  }

  async function loadDigitizationQueue(){
    try{
      const items=await EduAI.api('/api/v1/admin/digitization/jobs');
      const matching=items.filter(job=>job.status==='matching');
      const queue=items.filter(job=>job.status!=='matching');

      const batches=new Map();
      matching.forEach(job=>{
        const key=String(job.batch_id);
        if(!batches.has(key))batches.set(key,[]);
        batches.get(key).push(job);
      });

      $('digitization-match-summary').innerHTML=batches.size
        ? `
          <div class="rounded-xl bg-violet-300/[.06] p-3 text-sm">
            Есть ${batches.size} пакет(а), ожидающих подтверждения сопоставления.
            Пока они здесь, worker их не обрабатывает.
          </div>`
        : '';

      $('digitization-queue').innerHTML=[
        ...Array.from(batches.entries()).map(
          ([batchId,jobs])=>renderMatchingBatch(batchId,jobs)
        ),
        ...queue.map(renderQueueJob)
      ].join('') || '<p class="muted">Очередь пока пуста.</p>';
    }catch(error){
      EduAI.toast(error.message,'error');
    }
  }

  $('refresh-digitization-books').addEventListener('click',async()=>{
    try{
      await Promise.all([loadBooks(),loadEmptyDigitizationBooks()]);
      await loadDigitizationQueue();
      EduAI.toast('Список пустых учебников обновлён','success');
    }catch(error){
      EduAI.toast(error.message,'error');
    }
  });

  $('refresh-digitization-queue').addEventListener('click',loadDigitizationQueue);

  $('digitization-queue').addEventListener('change',async event=>{
    const select=event.target.closest('.assign-digitization-book');
    if(!select||!select.value)return;

    try{
      await EduAI.api(
        `/api/v1/admin/digitization/jobs/${select.dataset.id}/assign/${select.value}`,
        {method:'POST'}
      );
      await Promise.all([
        loadEmptyDigitizationBooks(),
        loadDigitizationQueue()
      ]);
    }catch(error){
      EduAI.toast(error.message,'error');
      await loadDigitizationQueue();
    }
  });

  $('digitization-queue').addEventListener('click',async event=>{
    const confirmButton=event.target.closest('.confirm-digitization-batch');
    if(confirmButton){
      EduAI.setBusy(confirmButton,true,'Проверяем…');
      try{
        await EduAI.api(
          `/api/v1/admin/digitization/batches/${confirmButton.dataset.batch}/confirm`,
          {method:'POST'}
        );
        EduAI.toast(
          'Сопоставление подтверждено. Пакет добавлен в очередь.',
          'success'
        );
        await Promise.all([
          loadEmptyDigitizationBooks(),
          loadDigitizationQueue()
        ]);
      }catch(error){
        EduAI.toast(error.message,'error');
      }finally{
        EduAI.setBusy(confirmButton,false);
      }
      return;
    }

    const retry=event.target.closest('.retry-digitization');
    if(!retry)return;

    try{
      await EduAI.api(
        `/api/v1/admin/digitization/jobs/${retry.dataset.id}/retry`,
        {method:'POST'}
      );
      EduAI.toast('Задача повторно поставлена в очередь','success');
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

    EduAI.setBusy(button,true,'Загружаем и сопоставляем…');

    try{
      const result=await EduAI.api(
        '/api/v1/admin/digitization/upload',
        {method:'POST',body:form}
      );

      const created=(result.jobs||[]).filter(item=>!item.duplicate).length;
      const duplicates=(result.jobs||[]).filter(item=>item.duplicate).length;

      EduAI.toast(
        duplicates
          ? `Загружено: ${created}. Дубликатов: ${duplicates}. Проверьте сопоставление.`
          : `Загружено файлов: ${created}. Проверьте сопоставление.`,
        'success'
      );

      file.value='';
      renderSelectedUploadFiles();

      await Promise.all([
        loadEmptyDigitizationBooks(),
        loadDigitizationQueue()
      ]);
    }catch(error){
      EduAI.toast(error.message,'error');
    }finally{
      EduAI.setBusy(button,false);
    }
  });

  await loadEmptyDigitizationBooks();
  await loadDigitizationQueue();
  setInterval(loadDigitizationQueue,4000);
  '''

js = js[:start] + block + js[end:]
JS.write_text(js, encoding="utf-8")

html = HTML.read_text(encoding="utf-8")
html = html.replace(
    'Перетащите PDF-файлы или ZIP сюда',
    'Загрузите PDF-файлы или ZIP для сопоставления'
)
html = re.sub(
    r'(/static/js/admin\.js)(?:\?v=[^"\']+)?',
    r'\1?v=20260813-tz25-1',
    html,
)
HTML.write_text(html, encoding="utf-8")

print("TZ25 frontend applied.")
print("Changed: static/js/admin.js, templates/admin.html")
print("Backup:", BACKUP)
