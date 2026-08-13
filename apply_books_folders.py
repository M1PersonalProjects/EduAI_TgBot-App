from pathlib import Path
import re
import shutil

ROOT = Path.cwd()
JS = ROOT / "static/js/admin.js"
HTML = ROOT / "templates/admin.html"
BACKUP = ROOT / ".books_folders_backup"

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
pattern = re.compile(
    r'async function loadBooks\(\)\s*\{.*?\}(?=\s*function setBookStep\()',
    re.S,
)
js2, count = pattern.subn(lambda m: 'async function loadBooks(){\n    try{\n      state.books=await EduAI.api(\'/api/v1/admin/books\');\n\n      const folderStateKey=\'eduai.admin.bookFolders.v1\';\n      let folderState={};\n      try{\n        folderState=JSON.parse(localStorage.getItem(folderStateKey)||\'{}\');\n      }catch(_){\n        folderState={};\n      }\n\n      const saveFolderState=()=>{\n        localStorage.setItem(folderStateKey,JSON.stringify(folderState));\n      };\n\n      const normalize=value=>String(value??\'\').trim()||\'Без предмета\';\n\n      const grouped=new Map();\n      for(const book of state.books){\n        const classKey=String(book.book_class??\'Без класса\');\n        const subjectKey=normalize(book.book_program);\n\n        if(!grouped.has(classKey)){\n          grouped.set(classKey,new Map());\n        }\n        const subjects=grouped.get(classKey);\n        if(!subjects.has(subjectKey)){\n          subjects.set(subjectKey,[]);\n        }\n        subjects.get(subjectKey).push(book);\n      }\n\n      const classSort=(a,b)=>{\n        const na=Number(a),nb=Number(b);\n        if(Number.isFinite(na)&&Number.isFinite(nb))return na-nb;\n        return String(a).localeCompare(String(b),\'ru\');\n      };\n\n      const renderBookCard=b=>`\n        <article class="glass card flex flex-col">\n          <div class="flex justify-between">\n            <span class="badge">\n              ${b.book_class} класс · ${EduAI.escapeHtml(b.book_program)}\n            </span>\n            <span class="text-xs muted">${b.pages_count} стр.</span>\n          </div>\n          <h3 class="mt-4 font-extrabold">\n            ${EduAI.escapeHtml(b.book_title)}\n          </h3>\n          <p class="mt-2 text-sm muted flex-1">\n            ${EduAI.escapeHtml(b.book_author)}\n          </p>\n          <div class="mt-4 grid grid-cols-3 gap-2">\n            <button class="btn-secondary edit-book" data-id="${b.book_id}">\n              Править\n            </button>\n            <button class="btn-secondary upload-book-action" data-id="${b.book_id}">\n              PDF\n            </button>\n            <button class="btn-danger delete-book" data-id="${b.book_id}">\n              Удалить\n            </button>\n          </div>\n        </article>`;\n\n      const renderSubjectFolder=(classKey,subject,books)=>{\n        const folderKey=`subject:${classKey}:${subject}`;\n        const isOpen=folderState[folderKey]!==false;\n\n        return `\n          <section class="book-subject-folder rounded-2xl bg-white/[.025] border border-white/5">\n            <button\n              type="button"\n              class="book-folder-toggle flex w-full items-center justify-between gap-3 p-4 text-left"\n              data-folder-key="${EduAI.escapeHtml(folderKey)}"\n              aria-expanded="${isOpen?\'true\':\'false\'}"\n            >\n              <span class="flex min-w-0 items-center gap-3">\n                <span class="text-xl">${isOpen?\'📂\':\'📁\'}</span>\n                <span class="min-w-0">\n                  <strong class="block truncate">${EduAI.escapeHtml(subject)}</strong>\n                  <span class="text-xs muted">\n                    ${books.length} ${books.length===1?\'учебник\':\'учебников\'}\n                  </span>\n                </span>\n              </span>\n              <span class="muted">${isOpen?\'▾\':\'▸\'}</span>\n            </button>\n\n            <div\n              class="book-folder-content px-4 pb-4"\n              data-folder-content="${EduAI.escapeHtml(folderKey)}"\n              ${isOpen?\'\':\'hidden\'}\n            >\n              <div class="grid md:grid-cols-2 xl:grid-cols-3 gap-4">\n                ${books\n                  .slice()\n                  .sort((a,b)=>String(a.book_title).localeCompare(String(b.book_title),\'ru\'))\n                  .map(renderBookCard)\n                  .join(\'\')}\n              </div>\n            </div>\n          </section>`;\n      };\n\n      const renderClassFolder=(classKey,subjects)=>{\n        const folderKey=`class:${classKey}`;\n        const isOpen=folderState[folderKey]!==false;\n        const bookCount=Array.from(subjects.values())\n          .reduce((sum,items)=>sum+items.length,0);\n\n        return `\n          <section class="book-class-folder glass overflow-hidden">\n            <button\n              type="button"\n              class="book-folder-toggle flex w-full items-center justify-between gap-3 p-4 sm:p-5 text-left"\n              data-folder-key="${EduAI.escapeHtml(folderKey)}"\n              aria-expanded="${isOpen?\'true\':\'false\'}"\n            >\n              <span class="flex min-w-0 items-center gap-3">\n                <span class="text-2xl">${isOpen?\'📂\':\'📁\'}</span>\n                <span class="min-w-0">\n                  <strong class="block text-lg">\n                    ${EduAI.escapeHtml(classKey)} класс\n                  </strong>\n                  <span class="text-xs muted">\n                    ${subjects.size} предметов · ${bookCount} учебников\n                  </span>\n                </span>\n              </span>\n              <span class="text-lg muted">${isOpen?\'▾\':\'▸\'}</span>\n            </button>\n\n            <div\n              class="book-folder-content border-t border-white/5 p-3 sm:p-4"\n              data-folder-content="${EduAI.escapeHtml(folderKey)}"\n              ${isOpen?\'\':\'hidden\'}\n            >\n              <div class="grid gap-3">\n                ${Array.from(subjects.entries())\n                  .sort(([a],[b])=>a.localeCompare(b,\'ru\'))\n                  .map(([subject,books])=>renderSubjectFolder(classKey,subject,books))\n                  .join(\'\')}\n              </div>\n            </div>\n          </section>`;\n      };\n\n      $(\'books-grid\').className=\'grid gap-4\';\n      $(\'books-grid\').innerHTML=state.books.length\n        ? Array.from(grouped.entries())\n            .sort(([a],[b])=>classSort(a,b))\n            .map(([classKey,subjects])=>renderClassFolder(classKey,subjects))\n            .join(\'\')\n        : empty(\'Учебников пока нет.\');\n\n      if(!$(\'books-grid\').dataset.folderHandler){\n        $(\'books-grid\').dataset.folderHandler=\'1\';\n        $(\'books-grid\').addEventListener(\'click\',event=>{\n          const toggle=event.target.closest(\'.book-folder-toggle\');\n          if(!toggle)return;\n\n          const key=toggle.dataset.folderKey;\n          const content=Array.from(\n            $(\'books-grid\').querySelectorAll(\'[data-folder-content]\')\n          ).find(item=>item.dataset.folderContent===key);\n          if(!content)return;\n\n          const open=content.hidden;\n          content.hidden=!open;\n          toggle.setAttribute(\'aria-expanded\',String(open));\n          folderState[key]=open;\n          saveFolderState();\n\n          const icon=toggle.querySelector(\'.text-2xl, .text-xl\');\n          if(icon)icon.textContent=open?\'📂\':\'📁\';\n\n          const arrow=toggle.lastElementChild;\n          if(arrow)arrow.textContent=open?\'▾\':\'▸\';\n        });\n      }\n\n      const opts=\'<option value="">Выберите учебник</option>\'+\n        state.books\n          .slice()\n          .sort((a,b)=>\n            Number(a.book_class)-Number(b.book_class) ||\n            String(a.book_program).localeCompare(String(b.book_program),\'ru\') ||\n            String(a.book_title).localeCompare(String(b.book_title),\'ru\')\n          )\n          .map(b=>`\n            <option value="${b.book_id}">\n              ${b.book_class} кл. · ${EduAI.escapeHtml(b.book_program)} · ${EduAI.escapeHtml(b.book_title)}\n            </option>`)\n          .join(\'\');\n\n      $(\'upload-book\').innerHTML=opts;\n      $(\'editor-book\').innerHTML=opts;\n    }catch(e){\n      EduAI.toast(e.message,\'error\');\n    }\n  }', js, count=1)
if count != 1:
    raise RuntimeError(
        "Не удалось найти loadBooks() в static/js/admin.js. "
        "Файл отличается от актуального main."
    )
JS.write_text(js2, encoding="utf-8")

html = HTML.read_text(encoding="utf-8")
html = html.replace(
    '<div id="books-grid" class="grid md:grid-cols-2 xl:grid-cols-3 gap-4"></div>',
    '<div id="books-grid" class="grid gap-4"></div>',
    1,
)
html = re.sub(
    r'(/static/js/admin\.js)(?:\?v=[^"\']+)?',
    r'\1?v=20260813-books-folders-1',
    html,
)
HTML.write_text(html, encoding="utf-8")

print("Папки учебников добавлены.")
print("Структура: Класс → Предмет → Учебники")
print("Изменены: static/js/admin.js, templates/admin.html")
print("Backup:", BACKUP)
print("SQL не требуется.")
