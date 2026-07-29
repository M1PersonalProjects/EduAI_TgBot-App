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

    $('task-student').innerHTML = state.children.length
      ? state.children
          .map(child => `
            <option value="${child.tg_id}">
              ${EduAI.escapeHtml(childName(child))}
            </option>
          `)
          .join('')
      : '<option value="">Нет привязанных детей</option>';

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

              <button
                class="btn-secondary mt-4 w-full child-task"
                data-child="${child.tg_id}"
                type="button"
              >
                Поставить задание
              </button>
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
      evaluated: 'Выполнено'
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

                ${attachments.length ? `
                  <div class="mt-4 grid gap-2">
                    ${attachments.map(file => `
                      <a
                        class="btn-secondary text-sm"
                        href="${file.download_url}"
                        data-auth-download
                        data-name="${EduAI.escapeHtml(file.original_name)}"
                      >
                        📎 ${EduAI.escapeHtml(file.original_name)}
                      </a>
                    `).join('')}
                  </div>
                ` : ''}
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

    if (childId) {
      $('task-student').value = String(childId);
    }

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
    const button = event.target.closest('.child-task');
    if (button) openTask(button.dataset.child);
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
      const payload = {
        student_id: Number($('task-student').value),
        subject: $('task-subject').value || $('task-topic').value.trim(),
        topic: $('task-topic').value.trim(),
        title: $('task-title').value.trim().replaceAll('$', ''),
        description: $('task-description').value.trim().replaceAll('$', ''),
        reference_answer: $('task-answer').value.trim().replaceAll('$', ''),
        parent_comment: $('task-comment').value.trim().replaceAll('$', ''),
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

      EduAI.toast('Задание отправлено ребёнку', 'success');
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

    const button = event.currentTarget;
    EduAI.setBusy(button, true, 'ИИ создаёт…');

    try {
      const result = await EduAI.api('/api/v1/parent/tasks/generate', {
        method: 'POST',
        body: JSON.stringify({
          student_id: Number($('task-student').value),
          topic,
          instructions: $('task-comment').value.trim().replaceAll('$', ''),
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
