document.addEventListener('DOMContentLoaded', async () => {
  EduAI.initShell();

  const user = await EduAI.guard(['parent']);
  if (!user) return;

  window.Telegram?.WebApp?.ready();
  window.Telegram?.WebApp?.expand();

  const $ = id => document.getElementById(id);

  const state = {
    children: [],
    rewards: [],
    sentTasks: [],
    taskAttachments: []
  };

  const empty = text => `
    <div class="empty-state glass col-span-full">
      <p>${EduAI.escapeHtml(text)}</p>
    </div>
  `;

  function childName(child) {
    return child.username ? `@${child.username}` : `ID ${child.tg_id}`;
  }

  function formatFileSize(bytes) {
    const size = Number(bytes || 0);
    if (size < 1024) return `${size} Б`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} КБ`;
    return `${(size / 1024 / 1024).toFixed(1)} МБ`;
  }

  function resetSelect(id, label) {
    const element = $(id);
    if (!element) return;
    element.innerHTML = `<option value="">${EduAI.escapeHtml(label)}</option>`;
  }

  function renderDashboard(data) {
    state.children = data.children || [];

    $('task-students').innerHTML = state.children.length
      ? state.children
          .map(child => `
            <label class="flex items-center gap-3 rounded-xl bg-white/[.04] p-3">
              <input class="task-student-checkbox h-4 w-4" type="checkbox" value="${child.tg_id}">
              <span class="text-sm font-bold">${EduAI.escapeHtml(childName(child))}</span>
            </label>
          `)
          .join('')
      : '<p class="text-sm muted">Нет привязанных детей</p>';

    $('children-grid').innerHTML = state.children.length
      ? state.children
          .map(child => `
            <article class="glass card">
              <div class="flex items-center justify-between">
                <div class="grid h-11 w-11 place-items-center rounded-2xl bg-emerald-300/10 text-xl">
                  👤
                </div>
                <span class="badge">
                  ${child.tasks_done}/${child.tasks_total} заданий
                </span>
              </div>

              <h3 class="mt-4 text-lg font-extrabold">
                ${EduAI.escapeHtml(childName(child))}
              </h3>

              <div class="mt-4 grid grid-cols-3 gap-2 text-center">
                <div class="rounded-xl bg-white/[.04] p-2">
                  <strong class="block">${child.balance_coins}</strong>
                  <span class="text-[.68rem] muted">монет</span>
                </div>
                <div class="rounded-xl bg-white/[.04] p-2">
                  <strong class="block">${child.xp_total}</strong>
                  <span class="text-[.68rem] muted">XP</span>
                </div>
                <div class="rounded-xl bg-white/[.04] p-2">
                  <strong class="block">${child.average_score}</strong>
                  <span class="text-[.68rem] muted">ср. балл</span>
                </div>
              </div>

              <p class="mt-3 text-xs muted">
                Серия: ${child.streak_days} дн. · Покупок: ${child.purchases_total}
              </p>

              <div class="mt-4 grid gap-2">
                <button class="btn-secondary w-full child-task" data-child="${child.tg_id}" type="button">
                  Поставить задание
                </button>
                <button class="btn-secondary w-full child-history" data-child="${child.tg_id}" type="button">
                  История заданий
                </button>
              </div>
            </article>
          `)
          .join('')
      : empty('Привязанных детей пока нет. Создайте приглашение через Telegram-бота.');

    $('family-purchases').innerHTML = data.purchases?.length
      ? data.purchases
          .map(purchase => `
            <div class="flex items-center justify-between gap-3 rounded-xl bg-white/[.035] p-3">
              <div>
                <p class="font-bold">
                  ${EduAI.escapeHtml(purchase.name)}
                </p>
                <p class="text-xs muted">
                  ${EduAI.escapeHtml(
                    purchase.username
                      ? `@${purchase.username}`
                      : `ID ${purchase.student_id}`
                  )}
                  · ${EduAI.formatDate(purchase.purchased_at)}
                </p>
              </div>
              <span class="badge">${purchase.cost_coins} монет</span>
            </div>
          `)
          .join('')
      : '<p class="py-6 text-center muted">Покупок пока нет.</p>';
  }

  function renderRewards(items) {
    state.rewards = items || [];

    $('parent-rewards').innerHTML = state.rewards.length
      ? state.rewards
          .map(reward => `
            <article class="glass card flex flex-col">
              <div class="flex justify-between">
                <span class="text-2xl">🎁</span>
                <span class="badge">${reward.cost_coins} монет</span>
              </div>

              <h3 class="mt-4 font-extrabold">
                ${EduAI.escapeHtml(reward.name)}
              </h3>

              <p class="mt-2 text-sm muted flex-1">
                ${EduAI.escapeHtml(reward.description || 'Без описания')}
              </p>

              <div class="mt-4 flex gap-2">
                <button
                  class="btn-secondary flex-1 edit-reward"
                  data-id="${reward.reward_id}"
                  type="button"
                >
                  Изменить
                </button>
                <button
                  class="btn-danger delete-reward"
                  data-id="${reward.reward_id}"
                  type="button"
                >
                  Удалить
                </button>
              </div>
            </article>
          `)
          .join('')
      : empty('Добавьте первую семейную награду.');
  }

  function taskStatusLabel(status) {
    const labels = {
      created: 'Создано',
      in_progress: 'Выполняется',
      completed: 'Выполнено',
      evaluated: 'Проверено',
      cancelled: 'Отменено'
    };
    return labels[status] || status || 'Неизвестно';
  }

  function renderSentTasks(items) {
    state.sentTasks = items || [];

    const container = $('sent-tasks-list');
    if (!container) return;

    container.innerHTML = state.sentTasks.length
      ? state.sentTasks
          .map(task => {
            const questions = task.questions_json || {};
            const attachments = task.attachments || [];

            return `
              <article class="glass card">
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <span class="badge">${EduAI.escapeHtml(taskStatusLabel(task.status))}</span>
                  <span class="text-xs muted">
                    ${EduAI.formatDate(task.created_at)}
                  </span>
                </div>

                <h3 class="mt-3 text-lg font-extrabold">
                  ${EduAI.escapeHtml(task.title || questions.title || `Задание №${task.task_id}`)}
                </h3>

                <p class="mt-1 text-sm muted">
                  ${EduAI.escapeHtml(
                    task.student_username
                      ? `@${task.student_username}`
                      : `Ученик ${task.student_id}`
                  )}
                  ${task.subject ? ` · ${EduAI.escapeHtml(task.subject)}` : ''}
                </p>

                <div class="mt-3 text-sm leading-6 text-slate-300">
                  ${EduAI.markdown(questions.question_text || '')}
                </div>

                ${task.parent_comment ? `
                  <div class="mt-4 rounded-2xl border border-emerald-300/15 bg-emerald-300/[.06] p-3">
                    <div class="flex items-center justify-between gap-2">
                      <p class="text-xs font-extrabold uppercase tracking-[.12em] text-emerald-200">💬 Комментарий к заданию</p>
                      <span class="text-[.65rem] muted">Виден ребёнку</span>
                    </div>
                    <p class="mt-2 text-sm text-slate-200 whitespace-pre-wrap">${EduAI.escapeHtml(task.parent_comment)}</p>
                  </div>
                ` : ''}

                ${task.ai_instructions ? `
                  <div class="mt-3 rounded-2xl border border-violet-300/15 bg-violet-300/[.06] p-3">
                    <div class="flex items-center justify-between gap-2">
                      <p class="text-xs font-extrabold uppercase tracking-[.12em] text-violet-200">🤖 Инструкции для ИИ</p>
                      <span class="text-[.65rem] muted">Только для Родителя</span>
                    </div>
                    <p class="mt-2 text-sm text-slate-200 whitespace-pre-wrap">${EduAI.escapeHtml(task.ai_instructions)}</p>
                  </div>
                ` : ''}

                ${attachments.length ? `
                  <div class="mt-4 grid gap-2">
                    ${attachments.map(file => `
                      <a class="btn-secondary text-sm" href="${file.download_url}" data-auth-download data-name="${EduAI.escapeHtml(file.original_name)}">
                        📎 ${EduAI.escapeHtml(file.original_name)}
                      </a>
                    `).join('')}
                  </div>
                ` : ''}
                <div class="mt-4 flex flex-wrap gap-2">
                  ${!['cancelled', 'completed', 'evaluated'].includes(task.status) ? `<button type="button" class="btn-secondary cancel-task" data-id="${task.task_id}">Отменить</button>` : ''}
                  ${Number(task.submission_count || 0) === 0 ? `<button type="button" class="btn-danger delete-task" data-id="${task.task_id}">Удалить</button>` : ''}
                </div>
              </article>
            `;
          })
          .join('')
      : empty('Отправленных заданий пока нет.');
  }

  function renderTaskAttachments() {
    const container = $('task-attachments-list');
    if (!container) return;

    container.innerHTML = state.taskAttachments.length
      ? state.taskAttachments
          .map(item => `
            <div class="flex items-center justify-between gap-3 rounded-xl bg-white/[.04] p-3">
              <div class="min-w-0">
                <p class="truncate text-sm font-bold">
                  📎 ${EduAI.escapeHtml(item.original_name)}
                </p>
                <p class="text-xs muted">
                  ${formatFileSize(item.size_bytes)}
                </p>
              </div>
              <button
                type="button"
                class="thread-action remove-task-attachment"
                data-id="${item.attachment_id}"
                aria-label="Убрать файл"
              >
                ×
              </button>
            </div>
          `)
          .join('')
      : '<p class="text-xs muted">Файлы не прикреплены.</p>';
  }

  async function uploadTaskFiles() {
    const input = $('task-attachments');
    const files = Array.from(input?.files || []);

    if (!files.length) {
      return state.taskAttachments;
    }

    if (files.length > 10) {
      throw new Error('Можно прикрепить не более 10 файлов');
    }

    const formData = new FormData();
    files.forEach(file => formData.append('files', file));

    const result = await EduAI.api('/api/v1/attachments', {
      method: 'POST',
      body: formData
    });

    const knownIds = new Set(
      state.taskAttachments.map(item => Number(item.attachment_id))
    );

    for (const attachment of result.attachments || []) {
      if (!knownIds.has(Number(attachment.attachment_id))) {
        state.taskAttachments.push(attachment);
      }
    }

    input.value = '';
    renderTaskAttachments();
    return state.taskAttachments;
  }

  async function loadTaskClasses() {
    resetSelect('task-class', 'Выберите класс');
    resetSelect('task-subject', 'Сначала выберите класс');
    resetSelect('task-book', 'Сначала выберите предмет');
    resetSelect('task-page', 'Страница или параграф');

    try {
      const values = await EduAI.api('/api/v1/tutor/context/classes');
      $('task-class').innerHTML += values
        .map(value => `<option value="${value}">${value} класс</option>`)
        .join('');
    } catch (error) {
      EduAI.toast(error.message, 'error');
    }
  }

  async function loadTaskSubjects() {
    resetSelect('task-subject', 'Выберите предмет');
    resetSelect('task-book', 'Сначала выберите предмет');
    resetSelect('task-page', 'Страница или параграф');

    const bookClass = $('task-class').value;
    if (!bookClass) return;

    try {
      const values = await EduAI.api(
        `/api/v1/tutor/context/subjects?book_class=${encodeURIComponent(bookClass)}`
      );

      $('task-subject').innerHTML += values
        .map(value => `
          <option value="${EduAI.escapeHtml(value)}">
            ${EduAI.escapeHtml(value)}
          </option>
        `)
        .join('');
    } catch (error) {
      EduAI.toast(error.message, 'error');
    }
  }

  async function loadTaskBooks() {
    resetSelect('task-book', 'Выберите учебник');
    resetSelect('task-page', 'Страница или параграф');

    const bookClass = $('task-class').value;
    const subject = $('task-subject').value;
    if (!bookClass || !subject) return;

    try {
      const query = new URLSearchParams({
        book_class: bookClass,
        book_program: subject
      });

      const values = await EduAI.api(
        `/api/v1/tutor/context/books?${query.toString()}`
      );

      $('task-book').innerHTML += values
        .map(book => `
          <option value="${book.book_id}">
            ${EduAI.escapeHtml(book.book_title)} · ${EduAI.escapeHtml(book.book_author)}
          </option>
        `)
        .join('');
    } catch (error) {
      EduAI.toast(error.message, 'error');
    }
  }

  async function loadTaskPages() {
    resetSelect('task-page', 'Весь учебник');

    const bookId = $('task-book').value;
    if (!bookId) return;

    try {
      const values = await EduAI.api(
        `/api/v1/tutor/context/pages?book_id=${encodeURIComponent(bookId)}`
      );

      $('task-page').innerHTML += values
        .map(page => `
          <option value="${page.page_id}">
            стр. ${page.page_number}${
              page.page_paragraph
                ? ` · ${EduAI.escapeHtml(page.page_paragraph)}`
                : page.page_title
                  ? ` · ${EduAI.escapeHtml(page.page_title)}`
                  : ''
            }
          </option>
        `)
        .join('');
    } catch (error) {
      EduAI.toast(error.message, 'error');
    }
  }

  async function loadAll() {
    try {
      const [dashboard, rewards, tasks] = await Promise.all([
        EduAI.api('/api/v1/parent/dashboard'),
        EduAI.api('/api/v1/parent/rewards'),
        EduAI.api('/api/v1/parent/tasks')
      ]);

      renderDashboard(dashboard);
      renderRewards(rewards);
      renderSentTasks(tasks);
    } catch (error) {
      EduAI.toast(error.message, 'error');
    }
  }

  function selectedStudentIds() {
    return Array.from(document.querySelectorAll('.task-student-checkbox:checked'))
      .map(input => Number(input.value))
      .filter(Number.isFinite);
  }

  function setSelectedStudents(ids = []) {
    const selected = new Set(ids.map(Number));
    document.querySelectorAll('.task-student-checkbox').forEach(input => {
      input.checked = selected.has(Number(input.value));
    });
  }

  async function openChildHistory(childId) {
    const child = state.children.find(item => Number(item.tg_id) === Number(childId));
    $('task-history-title').textContent = child ? `Задания ${childName(child)}` : 'Задания ребёнка';
    $('task-history-summary').innerHTML = '<p class="muted col-span-full">Загрузка…</p>';
    $('task-history-list').innerHTML = '';
    EduAI.openModal('task-history-modal');
    try {
      const data = await EduAI.api(`/api/v1/parent/children/${childId}/tasks`);
      const summary = data.summary || {};
      const cells = [
        ['Всего', summary.total || 0], ['Создано', summary.created || 0],
        ['В работе', summary.in_progress || 0], ['Выполнено', summary.completed || 0],
        ['Отменено', summary.cancelled || 0]
      ];
      $('task-history-summary').innerHTML = cells.map(([label, value]) => `
        <div class="rounded-xl bg-white/[.04] p-3 text-center"><strong class="block">${value}</strong><span class="text-xs muted">${label}</span></div>
      `).join('');
      $('task-history-list').innerHTML = (data.tasks || []).length ? data.tasks.map(task => {
        const questions = task.questions_json || {};
        return `<article class="rounded-2xl bg-white/[.04] p-4">
          <div class="flex flex-wrap items-center justify-between gap-2"><span class="badge">${EduAI.escapeHtml(taskStatusLabel(task.status))}</span><span class="text-xs muted">${EduAI.formatDate(task.created_at)}</span></div>
          <h3 class="mt-3 font-extrabold">${EduAI.escapeHtml(task.title || questions.title || `Задание №${task.task_id}`)}</h3>
          <p class="mt-1 text-sm muted">${EduAI.escapeHtml(task.subject || 'Без предмета')}${task.score != null ? ` · Балл: ${task.score}` : ''}</p>
          ${task.parent_comment ? `<div class="mt-3 rounded-xl bg-emerald-300/[.06] p-3"><p class="text-xs font-bold text-emerald-200">💬 Комментарий к заданию · виден ребёнку</p><p class="mt-1 text-sm text-slate-200 whitespace-pre-wrap">${EduAI.escapeHtml(task.parent_comment)}</p></div>` : ''}
          ${task.ai_instructions ? `<div class="mt-2 rounded-xl bg-violet-300/[.06] p-3"><p class="text-xs font-bold text-violet-200">🤖 Инструкции для ИИ · только для Родителя</p><p class="mt-1 text-sm text-slate-200 whitespace-pre-wrap">${EduAI.escapeHtml(task.ai_instructions)}</p></div>` : ''}
          ${task.cancellation_reason ? `<p class="mt-2 text-sm text-rose-200">Причина отмены: ${EduAI.escapeHtml(task.cancellation_reason)}</p>` : ''}
        </article>`;
      }).join('') : empty('История заданий пуста.');
    } catch (error) {
      $('task-history-list').innerHTML = empty(error.message);
    }
  }

  function openTask(childId) {
    if (!state.children.length) {
      EduAI.toast('Сначала привяжите ребёнка', 'error');
      return;
    }

    $('task-form').reset();
    state.taskAttachments = [];
    renderTaskAttachments();

    resetSelect('task-subject', 'Сначала выберите класс');
    resetSelect('task-book', 'Сначала выберите предмет');
    resetSelect('task-page', 'Страница или параграф');

    setSelectedStudents(childId ? [childId] : []);

    EduAI.openModal('task-modal');
  }

  function openReward(item = null) {
    $('reward-form').reset();
    $('reward-id').value = item?.reward_id || '';
    $('reward-modal-title').textContent = item
      ? 'Изменить награду'
      : 'Новая награда';

    if (item) {
      $('reward-name').value = item.name;
      $('reward-description').value = item.description || '';
      $('reward-cost').value = item.cost_coins;
      $('reward-category').value = item.category;
    }

    EduAI.openModal('reward-modal');
  }

  async function downloadProtectedFile(url, filename) {
    const session = EduAI.readSession();
    const headers = new Headers();

    if (session?.token) {
      headers.set('Authorization', `Bearer ${session.token}`);
    }

    const response = await fetch(url, { headers });

    if (!response.ok) {
      let message = `Ошибка ${response.status}`;
      try {
        const body = await response.json();
        message = body.detail || body.message || message;
      } catch (_) {}
      throw new Error(message);
    }

    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');

    link.href = objectUrl;
    link.download = filename || 'attachment';
    document.body.appendChild(link);
    link.click();
    link.remove();

    setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  }

  ['new-task-top', 'new-task-overview', 'new-task'].forEach(id => {
    $(id)?.addEventListener('click', () => openTask());
  });

  $('children-grid').addEventListener('click', event => {
    const taskButton = event.target.closest('.child-task');
    const historyButton = event.target.closest('.child-history');
    if (taskButton) openTask(taskButton.dataset.child);
    if (historyButton) openChildHistory(historyButton.dataset.child);
  });

  $('task-select-all-students')?.addEventListener('click', () => {
    const boxes = Array.from(document.querySelectorAll('.task-student-checkbox'));
    const selectAll = boxes.some(box => !box.checked);
    boxes.forEach(box => { box.checked = selectAll; });
  });

  $('task-class').addEventListener('change', loadTaskSubjects);
  $('task-subject').addEventListener('change', loadTaskBooks);
  $('task-book').addEventListener('change', loadTaskPages);

  $('task-attachments').addEventListener('change', async () => {
    try {
      await uploadTaskFiles();
      EduAI.toast('Файлы загружены', 'success');
    } catch (error) {
      $('task-attachments').value = '';
      EduAI.toast(error.message, 'error');
    }
  });

  $('task-attachments-list').addEventListener('click', event => {
    const button = event.target.closest('.remove-task-attachment');
    if (!button) return;

    state.taskAttachments = state.taskAttachments.filter(
      item => Number(item.attachment_id) !== Number(button.dataset.id)
    );
    renderTaskAttachments();
  });

  $('task-form').addEventListener('submit', async event => {
    event.preventDefault();

    const button = event.submitter;
    EduAI.setBusy(button, true, 'Создаём…');

    try {
      const studentIds = selectedStudentIds();
      if (!studentIds.length) throw new Error('Выберите хотя бы одного ребёнка');
      const payload = {
        student_ids: studentIds,
        subject: $('task-subject').value || $('task-topic').value.trim(),
        topic: $('task-topic').value.trim(),
        title: $('task-title').value.trim().replaceAll('$', ''),
        description: $('task-description').value.trim().replaceAll('$', ''),
        reference_answer: $('task-answer').value.trim().replaceAll('$', ''),
        parent_comment: $('task-parent-comment').value.trim().replaceAll('$', ''),
        book_id: $('task-book').value
          ? Number($('task-book').value)
          : null,
        page_id: $('task-page').value
          ? Number($('task-page').value)
          : null,
        attachment_ids: state.taskAttachments.map(
          item => Number(item.attachment_id)
        ),
        send_files_to_student: $('task-send-files').checked
      };

      await EduAI.api('/api/v1/parent/tasks', {
        method: 'POST',
        body: JSON.stringify(payload)
      });

      EduAI.toast('Задание отправлено выбранным ученикам', 'success');
      EduAI.closeModal('task-modal');
      await loadAll();
    } catch (error) {
      EduAI.toast(error.message, 'error');
    } finally {
      EduAI.setBusy(button, false);
    }
  });

  $('generate-task').addEventListener('click', async event => {
    const topic = $('task-topic').value.trim();
    const bookId = Number($('task-book').value);

    if (!topic) {
      EduAI.toast('Укажите тему задания', 'error');
      return;
    }

    if (!bookId) {
      EduAI.toast('Для генерации ИИ выберите учебник', 'error');
      return;
    }

    const studentIds = selectedStudentIds();
    if (!studentIds.length) {
      EduAI.toast('Выберите хотя бы одного ребёнка', 'error');
      return;
    }

    const button = event.currentTarget;
    EduAI.setBusy(button, true, 'ИИ создаёт…');

    try {
      const result = await EduAI.api('/api/v1/parent/tasks/generate', {
        method: 'POST',
        body: JSON.stringify({
          student_ids: studentIds,
          topic,
          parent_comment: $('task-parent-comment').value.trim().replaceAll('$', ''),
          ai_instructions: $('task-ai-instructions').value.trim().replaceAll('$', ''),
          book_id: bookId,
          page_id: $('task-page').value
            ? Number($('task-page').value)
            : null,
          attachment_ids: state.taskAttachments.map(
            item => Number(item.attachment_id)
          ),
          send_files_to_student: $('task-send-files').checked
        })
      });

      EduAI.toast(
        `Задание «${result.task?.title || topic}» создано и отправлено`,
        'success'
      );
      EduAI.closeModal('task-modal');
      await loadAll();
    } catch (error) {
      EduAI.toast(error.message, 'error');
    } finally {
      EduAI.setBusy(button, false);
    }
  });

  $('new-reward').addEventListener('click', () => openReward());

  $('parent-rewards').addEventListener('click', async event => {
    const edit = event.target.closest('.edit-reward');
    const remove = event.target.closest('.delete-reward');

    if (edit) {
      openReward(
        state.rewards.find(
          reward => reward.reward_id === Number(edit.dataset.id)
        )
      );
    }

    if (remove && confirm('Удалить награду?')) {
      try {
        await EduAI.api(`/api/v1/parent/rewards/${remove.dataset.id}`, {
          method: 'DELETE'
        });
        EduAI.toast('Награда удалена', 'success');
        await loadAll();
      } catch (error) {
        EduAI.toast(error.message, 'error');
      }
    }
  });

  $('reward-form').addEventListener('submit', async event => {
    event.preventDefault();

    const id = $('reward-id').value;
    const button = event.submitter;
    const payload = {
      name: $('reward-name').value.trim(),
      description: $('reward-description').value.trim(),
      cost_coins: Number($('reward-cost').value),
      category: $('reward-category').value
    };

    EduAI.setBusy(button, true, 'Сохраняем…');

    try {
      await EduAI.api(
        id
          ? `/api/v1/parent/rewards/${id}`
          : '/api/v1/parent/rewards',
        {
          method: id ? 'PUT' : 'POST',
          body: JSON.stringify(payload)
        }
      );

      EduAI.closeModal('reward-modal');
      EduAI.toast('Награда сохранена', 'success');
      await loadAll();
    } catch (error) {
      EduAI.toast(error.message, 'error');
    } finally {
      EduAI.setBusy(button, false);
    }
  });

  $('sent-tasks-list')?.addEventListener('click', async event => {
    const cancelButton = event.target.closest('.cancel-task');
    const deleteButton = event.target.closest('.delete-task');
    if (cancelButton) {
      const reason = prompt('Причина отмены (необязательно):', '');
      if (reason === null) return;
      try {
        await EduAI.api(`/api/v1/parent/tasks/${cancelButton.dataset.id}/cancel`, { method: 'POST', body: JSON.stringify({ reason }) });
        EduAI.toast('Задание отменено', 'success');
        await loadAll();
      } catch (error) { EduAI.toast(error.message, 'error'); }
      return;
    }
    if (deleteButton) {
      if (!confirm('Удалить задание без возможности восстановления?')) return;
      try {
        await EduAI.api(`/api/v1/parent/tasks/${deleteButton.dataset.id}`, { method: 'DELETE' });
        EduAI.toast('Задание удалено', 'success');
        await loadAll();
      } catch (error) { EduAI.toast(error.message, 'error'); }
      return;
    }
    const link = event.target.closest('[data-auth-download]');
    if (!link) return;

    event.preventDefault();

    try {
      await downloadProtectedFile(link.href, link.dataset.name);
    } catch (error) {
      EduAI.toast(error.message, 'error');
    }
  });

  document.querySelectorAll('.prompt-chip').forEach(button => {
    button.addEventListener('click', () => {
      $('parent-chat-input').value = button.textContent.trim();
      $('parent-chat-input').focus();
    });
  });

  const chat = new EduAIChat({
    newChatId: 'parent-new-chat',
    threadsId: 'parent-chat-threads',
    formId: 'parent-chat-form',
    inputId: 'parent-chat-input',
    logId: 'parent-chat-log',
    attachId: 'parent-chat-attachment',
    removeAttachId: 'parent-chat-remove-attachment',
    attachmentPreviewId: 'parent-chat-attachment-preview',
    attachmentNameId: 'parent-chat-attachment-name',
    classId: 'parent-chat-class',
    subjectId: 'parent-chat-subject',
    bookId: 'parent-chat-book',
    pageId: 'parent-chat-page',
    lockId: 'parent-chat-lock-context',
    exitId: 'parent-chat-exit-context',
    contextStatusId: 'parent-chat-context-status',
    welcome: 'Здравствуйте! Я учебный ИИ-тьютор. Могу объяснить материал выбранного учебника, разобрать учебное вложение или помочь подготовить задание.'
  });

  $('refresh-parent').addEventListener('click', loadAll);

  renderTaskAttachments();
  await Promise.all([
    loadAll(),
    chat.init(),
    loadTaskClasses()
  ]);
});
