document.addEventListener('DOMContentLoaded', async () => {
  EduAI.initShell(); const user = await EduAI.guard(['admin']); if (!user) return;
  const $=id=>document.getElementById(id); const state={books:[],pages:[],bookStep:1};
  const empty=text=>`<div class="empty-state glass col-span-full"><p>${EduAI.escapeHtml(text)}</p></div>`;
  async function loadOverview(){try{const d=await EduAI.api('/api/v1/admin/overview');['users','books','pages','tasks'].forEach(k=>$(`count-${k}`).textContent=d[k].toLocaleString('ru-RU'));}catch(e){EduAI.toast(e.message,'error');}}
  async function loadBooks(){try{state.books=await EduAI.api('/api/v1/admin/books');$('books-grid').innerHTML=state.books.length?state.books.map(b=>`<article class="glass card flex flex-col"><div class="flex justify-between"><span class="badge">${b.book_class} класс · ${EduAI.escapeHtml(b.book_program)}</span><span class="text-xs muted">${b.pages_count} стр.</span></div><h3 class="mt-4 font-extrabold">${EduAI.escapeHtml(b.book_title)}</h3><p class="mt-2 text-sm muted flex-1">${EduAI.escapeHtml(b.book_author)}</p><div class="mt-4 grid grid-cols-3 gap-2"><button class="btn-secondary edit-book" data-id="${b.book_id}">Править</button><button class="btn-secondary upload-book-action" data-id="${b.book_id}">PDF</button><button class="btn-danger delete-book" data-id="${b.book_id}">Удалить</button></div></article>`).join(''):empty('Учебников пока нет.');const opts='<option value="">Выберите учебник</option>'+state.books.map(b=>`<option value="${b.book_id}">${b.book_class} кл. · ${EduAI.escapeHtml(b.book_title)}</option>`).join('');$('upload-book').innerHTML=opts;$('editor-book').innerHTML=opts;}catch(e){EduAI.toast(e.message,'error');}}
  function setBookStep(n){state.bookStep=Math.max(1,Math.min(4,n));document.querySelectorAll('.book-step').forEach(x=>x.hidden=Number(x.dataset.bookStep)!==state.bookStep);$('book-step-label').textContent=state.bookStep;$('book-progress').style.width=`${state.bookStep*25}%`;$('book-prev').disabled=state.bookStep===1;$('book-next').hidden=state.bookStep===4;$('book-save').hidden=state.bookStep!==4;}
  function openBook(book=null){$('book-form').reset();$('book-id').value=book?.book_id||'';$('book-modal-title').textContent=book?'Изменить учебник':'Новый учебник';if(book){$('book-class').value=book.book_class;$('book-program').value=book.book_program;$('book-author').value=book.book_author;$('book-title').value=book.book_title;}setBookStep(1);EduAI.openModal('book-modal');}
  $('new-book').addEventListener('click',()=>openBook());$('book-prev').addEventListener('click',()=>setBookStep(state.bookStep-1));$('book-next').addEventListener('click',()=>{const ids=['book-class','book-program','book-author'];const field=$(ids[state.bookStep-1]);if(!field.value.trim()){EduAI.toast('Заполните текущий шаг','error');return;}setBookStep(state.bookStep+1);});
  $('book-form').addEventListener('submit',async e=>{e.preventDefault();const id=$('book-id').value;const b=e.submitter;const payload={book_class:Number($('book-class').value),book_program:$('book-program').value.trim(),book_author:$('book-author').value.trim(),book_title:$('book-title').value.trim()};EduAI.setBusy(b,true,'Сохраняем…');try{await EduAI.api(id?`/api/v1/admin/books/${id}`:'/api/v1/admin/books',{method:id?'PUT':'POST',body:JSON.stringify(payload)});EduAI.closeModal('book-modal');EduAI.toast('Учебник сохранён','success');await Promise.all([loadBooks(),loadOverview()]);}catch(err){EduAI.toast(err.message,'error');}finally{EduAI.setBusy(b,false);}});
  $('books-grid').addEventListener('click',async e=>{const edit=e.target.closest('.edit-book');const del=e.target.closest('.delete-book');const upload=e.target.closest('.upload-book-action');if(edit)openBook(state.books.find(b=>b.book_id===Number(edit.dataset.id)));if(upload){$('upload-book').value=upload.dataset.id;document.querySelector('[data-section="digitization"]').click();}if(del&&confirm('Удалить учебник и все его страницы? Это действие нельзя отменить.')){try{await EduAI.api(`/api/v1/admin/books/${del.dataset.id}`,{method:'DELETE'});EduAI.toast('Учебник удалён','success');await Promise.all([loadBooks(),loadOverview()]);}catch(err){EduAI.toast(err.message,'error');}}});

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

async function loadPages(bookId){if(!bookId){state.pages=[];$('editor-page').innerHTML='<option>Выберите учебник</option>';return;}try{state.pages=await EduAI.api(`/api/v1/admin/books/${bookId}/pages`);$('editor-page').innerHTML='<option value="">Выберите страницу</option>'+state.pages.map(p=>`<option value="${p.page_id}">Страница ${p.page_number} · ${EduAI.escapeHtml(p.page_title||'Без заголовка')}</option>`).join('');}catch(e){EduAI.toast(e.message,'error');}}
  $('editor-book').addEventListener('change',e=>loadPages(e.target.value));$('editor-page').addEventListener('change',e=>{const p=state.pages.find(x=>x.page_id===Number(e.target.value));$('editor-empty').hidden=!!p;$('editor-workspace').hidden=!p;if(!p)return;$('page-id').value=p.page_id;$('page-number').value=p.page_number;$('page-title').value=p.page_title||'';$('page-paragraph').value=p.page_paragraph||'';$('page-markdown').value=p.page_markdown||'';$('page-html').value=p.page_html||'';$('page-text').value=p.page_text||'';$('page-image').src=p.page_image||'';});
  document.querySelectorAll('.editor-tab').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('.editor-tab').forEach(x=>x.classList.toggle('btn-primary',x===b));document.querySelectorAll('.editor-pane').forEach(x=>x.hidden=x.dataset.pane!==b.dataset.tab);}));document.querySelector('.editor-tab').click();
  $('page-form').addEventListener('submit',async e=>{e.preventDefault();const b=e.submitter;const payload={page_number:Number($('page-number').value),page_title:$('page-title').value||null,page_paragraph:$('page-paragraph').value||null,page_markdown:$('page-markdown').value.replaceAll('$',''),page_html:$('page-html').value,page_text:$('page-text').value};EduAI.setBusy(b,true,'Сохраняем…');try{await EduAI.api(`/api/v1/admin/pages/${$('page-id').value}`,{method:'PUT',body:JSON.stringify(payload)});EduAI.toast('Страница сохранена','success');await loadPages($('editor-book').value);}catch(err){EduAI.toast(err.message,'error');}finally{EduAI.setBusy(b,false);}});

  async function loadUsers(){const q=new URLSearchParams();if($('user-role').value)q.set('role',$('user-role').value);if($('user-search').value.trim())q.set('search',$('user-search').value.trim());try{const [users,families]=await Promise.all([EduAI.api('/api/v1/admin/users?'+q),EduAI.api('/api/v1/admin/family-tree')]);$('users-body').innerHTML=users.map(u=>`<tr><td>${u.tg_id}</td><td>${EduAI.escapeHtml(u.username?'@'+u.username:'—')}</td><td><span class="badge">${u.role}</span></td><td>${u.parent_id||'—'}</td><td>${EduAI.formatDate(u.created_at)}</td></tr>`).join('')||'<tr><td colspan="5" class="text-center muted">Ничего не найдено</td></tr>';$('family-tree').innerHTML=families.length?families.map(f=>`<article class="glass card"><p class="font-extrabold">${EduAI.escapeHtml(f.parent_username?'@'+f.parent_username:'Родитель '+f.parent_id)}</p><div class="mt-3 grid gap-2">${f.children.length?f.children.map(c=>`<div class="rounded-xl bg-white/[.04] p-2 text-sm">↳ ${EduAI.escapeHtml(c.username?'@'+c.username:'Ученик '+c.tg_id)}</div>`).join(''):'<p class="text-sm muted">Нет привязанных детей</p>'}</div></article>`).join(''):empty('Семейных связей нет.');}catch(e){EduAI.toast(e.message,'error');}}
  $('find-users').addEventListener('click',loadUsers);$('user-search').addEventListener('keydown',e=>{if(e.key==='Enter')loadUsers();});
  async function loadActivity(){try{const items=await EduAI.api('/api/v1/admin/activity');$('activity-list').innerHTML=items.length?items.map(x=>`<article class="glass card flex items-start justify-between gap-3"><div><div class="flex items-center gap-2"><span class="badge">${x.type}</span><span class="text-xs muted">Пользователь ${x.user_id}</span></div><p class="mt-2 text-sm">${EduAI.escapeHtml(String(x.detail).slice(0,260))}</p></div><time class="text-xs muted shrink-0">${EduAI.formatDate(x.created_at)}</time></article>`).join(''):empty('Событий пока нет.');}catch(e){EduAI.toast(e.message,'error');}}
  $('refresh-activity').addEventListener('click',loadActivity);$('refresh-admin').addEventListener('click',()=>Promise.all([loadOverview(),loadBooks()]));document.querySelectorAll('.jump-section').forEach(b=>b.addEventListener('click',()=>document.querySelector(`[data-section="${b.dataset.target}"]`).click()));
  await Promise.all([loadOverview(),loadBooks(),loadUsers(),loadActivity()]);
});
