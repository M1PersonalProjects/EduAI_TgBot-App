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
      : '<p class="text-sm muted">Нет привязанных Учеников</p>';

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
      : empty('Привязанных Учеников пока нет. Создайте приглашение через Telegram-бота.');

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
      cancelled: 'Отменено',
      draft: 'Черновик',
      submitted: 'Отправлено',
      processing: 'Проверяется',
      reviewed: 'Проверено',
      needs_revision: 'Нужна доработка'
    };
    return labels[status] || status || 'Неизвестно';
  }


  function ensureTaskDetailModal() {
    if ($('task-detail-modal')) return;

    const wrapper = document.createElement('div');
    wrapper.innerHTML = `
      <div id="task-detail-modal" class="modal-backdrop" aria-hidden="true">
        <div class="modal-panel glass-strong w-[min(96vw,64rem)] max-w-4xl max-h-[92vh] overflow-y-auto">
          <div class="sticky top-0 z-10 -mx-1 -mt-1 flex items-start justify-between gap-3 rounded-t-2xl bg-slate-950/90 p-1 pb-4 backdrop-blur">
            <div class="min-w-0">
              <p class="text-sm font-bold text-violet-200">Подробное задание</p>
              <h2 id="task-detail-title" class="mt-1 truncate text-xl font-extrabold">Загрузка…</h2>
            </div>
            <button class="icon-btn shrink-0" data-close-modal="task-detail-modal" aria-label="Закрыть" type="button">×</button>
          </div>
          <div id="task-detail-content" class="mt-2"></div>
        </div>
      </div>
    `;
    document.body.appendChild(wrapper.firstElementChild);
  }

  function formatOptionalDate(value) {
    return value ? EduAI.formatDate(value) : '—';
  }

  function boolBadge(value, yesText, noText) {
    return value
      ? `<span class="badge">${EduAI.escapeHtml(yesText)}</span>`
      : `<span class="text-xs muted">${EduAI.escapeHtml(noText)}</span>`;
  }

  function taskContextLabel(context = {}) {
    if (!context?.book_id && !context?.book_title) return 'Без выбранного учебника';

    const book = context.book_title || `Учебник #${context.book_id}`;
    if (context.context_mode === 'single_page' || context.page_id) {
      const page = context.page_number ? `стр. ${context.page_number}` : `page_id ${context.page_id}`;
      const extra = context.page_title || context.page_paragraph;
      return `${book} · ${page}${extra ? ` · ${extra}` : ''}`;
    }

    const used = Array.isArray(context.used_pages) ? context.used_pages : [];
    if (used.length) {
      const pages = used
        .map(item => item?.page_number)
        .filter(value => value !== undefined && value !== null)
        .join(', ');
      return `${book} · весь учебник${pages ? ` · использованы стр. ${pages}` : ''}`;
    }
    return `${book} · весь учебник`;
  }

  function renderTaskDetail(task) {
    const questions = task.questions_json || {};
    const answers = task.student_answers_json || {};
    const context = task.topic_context || {};
    const attachments = Array.isArray(task.attachments) ? task.attachments : [];
    const submissions = Array.isArray(task.submissions) ? task.submissions : [];

    const studentLabel = task.student_username
      ? `@${task.student_username}`
      : `ID ${task.student_id}`;

    const resultText = answers.is_correct === true
      ? 'Ответ принят как правильный'
      : answers.is_correct === false
        ? 'Нужна доработка'
        : 'Итог ещё не определён';

    const attachmentsHtml = attachments.length
      ? attachments.map(file => `
          <div class="rounded-2xl border border-white/10 bg-white/[.035] p-3">
            <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div class="min-w-0">
                <p class="truncate text-sm font-extrabold">📎 ${EduAI.escapeHtml(file.original_name || `Файл #${file.attachment_id}`)}</p>
                <p class="mt-1 text-xs muted">
                  ${EduAI.escapeHtml(file.mime_type || file.extension || 'Файл')} · ${formatFileSize(file.size_bytes)}
                </p>
                <div class="mt-2 flex flex-wrap gap-2">
                  ${boolBadge(file.visible_to_student, 'Виден ученику', 'Скрыт от ученика')}
                  ${boolBadge(file.use_as_ai_context, 'Контекст ИИ', 'Не используется ИИ')}
                </div>
              </div>
              <div class="flex shrink-0 flex-wrap gap-2">
                <button type="button" class="btn-secondary text-sm task-detail-preview" data-url="${EduAI.escapeHtml(file.preview_url || file.download_url || '')}" data-name="${EduAI.escapeHtml(file.original_name || 'attachment')}">Просмотр</button>
                <button type="button" class="btn-secondary text-sm task-detail-download" data-url="${EduAI.escapeHtml(file.download_url || '')}" data-name="${EduAI.escapeHtml(file.original_name || 'attachment')}">Скачать</button>
              </div>
            </div>
          </div>
        `).join('')
      : '<p class="text-sm muted">Вложений нет.</p>';

    const submissionsHtml = submissions.length
      ? submissions.map(item => `
          <article class="rounded-2xl border border-white/10 bg-white/[.035] p-4">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <p class="font-extrabold">Попытка №${Number(item.attempt_number || 0)}</p>
              <span class="badge">${EduAI.escapeHtml(taskStatusLabel(item.status))}</span>
            </div>
            <div class="mt-3 grid gap-3">
              <div>
                <p class="text-xs font-bold uppercase tracking-[.12em] muted">Ответ ученика</p>
                <div class="mt-1 text-sm leading-6 text-slate-200">${EduAI.markdown(item.answer_text || '—')}</div>
              </div>
              ${item.ai_feedback ? `
                <div>
                  <p class="text-xs font-bold uppercase tracking-[.12em] text-violet-200">Обратная связь ИИ</p>
                  <div class="mt-1 text-sm leading-6 text-slate-200">${EduAI.markdown(item.ai_feedback)}</div>
                </div>
              ` : ''}
              <div class="flex flex-wrap gap-x-5 gap-y-1 text-xs muted">
                <span>Балл: ${item.score ?? '—'}</span>
                <span>Отправлено: ${formatOptionalDate(item.submitted_at)}</span>
                <span>Проверено: ${formatOptionalDate(item.reviewed_at)}</span>
              </div>
            </div>
          </article>
        `).join('')
      : '<p class="text-sm muted">Ученик ещё не отправлял попыток.</p>';

    return `
      <div class="grid gap-4">
        <section class="rounded-2xl bg-white/[.035] p-4">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <span class="badge">${EduAI.escapeHtml(taskStatusLabel(task.status))}</span>
            <span class="text-xs muted">task_id: ${task.task_id}</span>
          </div>
          <h3 class="mt-3 text-xl font-extrabold">${EduAI.escapeHtml(task.title || questions.title || `Задание №${task.task_id}`)}</h3>
          <div class="mt-3 grid gap-2 text-sm sm:grid-cols-2">
            <p><span class="muted">Ученик:</span> ${EduAI.escapeHtml(studentLabel)}</p>
            <p><span class="muted">Предмет:</span> ${EduAI.escapeHtml(task.subject || '—')}</p>
            <p><span class="muted">Тема:</span> ${EduAI.escapeHtml(task.topic || '—')}</p>
            <p><span class="muted">Балл:</span> ${task.score ?? '—'}</p>
          </div>
        </section>

        <section class="rounded-2xl bg-white/[.035] p-4">
          <p class="text-xs font-bold uppercase tracking-[.12em] text-violet-200">Полный текст задания</p>
          <div class="mt-3 leading-7 text-slate-200">${EduAI.markdown(questions.question_text || 'Текст задания отсутствует.')}</div>
        </section>

        <div class="grid gap-4 lg:grid-cols-2">
          <section class="rounded-2xl border border-amber-300/15 bg-amber-300/[.04] p-4">
            <p class="text-xs font-bold uppercase tracking-[.12em] text-amber-200">Эталонный ответ · только Учителю</p>
            <div class="mt-2 text-sm leading-6 text-slate-200">${EduAI.markdown(questions.reference_answer || '—')}</div>
          </section>
          <section class="rounded-2xl border border-violet-300/15 bg-violet-300/[.04] p-4">
            <p class="text-xs font-bold uppercase tracking-[.12em] text-violet-200">Инструкции для ИИ · только Учителю</p>
            <p class="mt-2 whitespace-pre-wrap text-sm text-slate-200">${EduAI.escapeHtml(task.ai_instructions || '—')}</p>
          </section>
        </div>

        ${task.parent_comment ? `
          <section class="rounded-2xl border border-emerald-300/15 bg-emerald-300/[.04] p-4">
            <p class="text-xs font-bold uppercase tracking-[.12em] text-emerald-200">Комментарий к заданию · виден Ученику</p>
            <p class="mt-2 whitespace-pre-wrap text-sm text-slate-200">${EduAI.escapeHtml(task.parent_comment)}</p>
          </section>
        ` : ''}

        <section class="rounded-2xl bg-white/[.035] p-4">
          <p class="text-xs font-bold uppercase tracking-[.12em] muted">Учебный контекст</p>
          <p class="mt-2 text-sm text-slate-200">${EduAI.escapeHtml(taskContextLabel(context))}</p>
          ${context.book_program ? `<p class="mt-1 text-xs muted">Программа: ${EduAI.escapeHtml(context.book_program)}${context.book_class ? ` · ${EduAI.escapeHtml(String(context.book_class))} класс` : ''}</p>` : ''}
        </section>

        <section class="rounded-2xl bg-white/[.035] p-4">
          <p class="text-xs font-bold uppercase tracking-[.12em] muted">Даты</p>
          <div class="mt-3 grid gap-2 text-sm sm:grid-cols-2">
            <p><span class="muted">Создано:</span> ${formatOptionalDate(task.created_at)}</p>
            <p><span class="muted">Отправлено:</span> ${formatOptionalDate(task.sent_at)}</p>
            <p><span class="muted">Изменено:</span> ${formatOptionalDate(task.updated_at)}</p>
            <p><span class="muted">Выполнено:</span> ${formatOptionalDate(task.completed_at)}</p>
          </div>
        </section>

        <section class="rounded-2xl bg-white/[.035] p-4">
          <p class="text-xs font-bold uppercase tracking-[.12em] muted">Результат</p>
          <p class="mt-2 font-bold">${EduAI.escapeHtml(resultText)}</p>
          ${answers.provided_answer ? `<div class="mt-3"><p class="text-xs muted">Последний сохранённый ответ</p><div class="mt-1 text-sm text-slate-200">${EduAI.markdown(answers.provided_answer)}</div></div>` : ''}
          ${answers.verification_feedback ? `<div class="mt-3"><p class="text-xs muted">Последняя обратная связь</p><div class="mt-1 text-sm text-slate-200">${EduAI.markdown(answers.verification_feedback)}</div></div>` : ''}
          ${task.cancellation_reason ? `<p class="mt-3 text-sm text-rose-200">Причина отмены: ${EduAI.escapeHtml(task.cancellation_reason)}</p>` : ''}
        </section>

        <section>
          <div class="mb-3 flex items-center justify-between gap-2">
            <h3 class="font-extrabold">Вложения</h3>
            <span class="text-xs muted">${attachments.length}</span>
          </div>
          <div class="grid gap-2">${attachmentsHtml}</div>
        </section>

        <section>
          <div class="mb-3 flex items-center justify-between gap-2">
            <h3 class="font-extrabold">История попыток</h3>
            <span class="text-xs muted">${submissions.length}</span>
          </div>
          <div class="grid gap-3">${submissionsHtml}</div>
        </section>
      </div>
    `;
  }

  async function openTaskDetail(taskId) {
    ensureTaskDetailModal();
    const title = $('task-detail-title');
    const content = $('task-detail-content');
    title.textContent = `Задание №${taskId}`;
    content.innerHTML = `
      <div class="grid min-h-48 place-items-center py-12 text-center">
        <div>
          <div class="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-white/20 border-t-violet-300"></div>
          <p class="mt-3 text-sm muted">Загружаем полную информацию…</p>
        </div>
      </div>
    `;
    EduAI.openModal('task-detail-modal');

    try {
      const task = await EduAI.api(`/api/v1/parent/tasks/${encodeURIComponent(taskId)}`);
      title.textContent = task.title || task.questions_json?.title || `Задание №${taskId}`;
      content.innerHTML = renderTaskDetail(task);
    } catch (error) {
      content.innerHTML = `
        <div class="rounded-2xl border border-rose-300/15 bg-rose-300/[.05] p-5 text-center">
          <p class="font-extrabold text-rose-200">Не удалось открыть задание</p>
          <p class="mt-2 text-sm muted">${EduAI.escapeHtml(error.message || 'Попробуйте ещё раз.')}</p>
          <button type="button" class="btn-secondary mt-4 retry-task-detail" data-id="${taskId}">Повторить</button>
        </div>
      `;
    }
  }

  async function previewProtectedFile(url, filename) {
    if (!url) throw new Error('Ссылка на просмотр недоступна');
    const session = EduAI.readSession();
    const headers = new Headers();
    if (session?.token) headers.set('Authorization', `Bearer ${session.token}`);

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
    const popup = window.open(objectUrl, '_blank', 'noopener,noreferrer');
    if (!popup) {
      URL.revokeObjectURL(objectUrl);
      throw new Error(`Браузер заблокировал просмотр файла «${filename || 'attachment'}»`);
    }
    setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
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
              <article class="glass card task-card cursor-pointer transition hover:bg-white/[.055]" data-task-id="${task.task_id}" tabindex="0" role="button" aria-label="Открыть задание ${task.task_id}">
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
                      <span class="text-[.65rem] muted">Виден Ученику</span>
                    </div>
                    <p class="mt-2 text-sm text-slate-200 whitespace-pre-wrap">${EduAI.escapeHtml(task.parent_comment)}</p>
                  </div>
                ` : ''}

                ${task.ai_instructions ? `
                  <div class="mt-3 rounded-2xl border border-violet-300/15 bg-violet-300/[.06] p-3">
                    <div class="flex items-center justify-between gap-2">
                      <p class="text-xs font-extrabold uppercase tracking-[.12em] text-violet-200">🤖 Инструкции для ИИ</p>
                      <span class="text-[.65rem] muted">Только для Учителя</span>
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
            <div class="rounded-xl bg-white/[.04] p-3" data-attachment-row="${item.attachment_id}">
              <div class="flex items-center justify-between gap-3">
                <div class="min-w-0">
                  <p class="truncate text-sm font-bold">
                    📎 ${EduAI.escapeHtml(item.original_name)}
                  </p>
                  <p class="text-xs muted">${formatFileSize(item.size_bytes)}</p>
                </div>
                <button type="button"
                        class="thread-action remove-task-attachment"
                        data-id="${item.attachment_id}"
                        aria-label="Убрать файл">×</button>
              </div>

              <div class="mt-3 grid gap-2 sm:grid-cols-2">
                <label class="flex items-center gap-2 text-xs">
                  <input type="checkbox"
                         class="task-attachment-ai h-4 w-4"
                         data-id="${item.attachment_id}"
                         ${item.use_as_ai_context !== false ? 'checked' : ''}>
                  Использовать для анализа ИИ
                </label>

                <label class="flex items-center gap-2 text-xs">
                  <input type="checkbox"
                         class="task-attachment-visible h-4 w-4"
                         data-id="${item.attachment_id}"
                         ${item.visible_to_student ? 'checked' : ''}>
                  Отправить Ученику
                </label>
              </div>
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
        state.taskAttachments.push({
          ...attachment,
          use_as_ai_context: true,
          visible_to_student: Boolean($('task-send-files')?.checked)
        });
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
    $('task-history-title').textContent = child ? `Задания ${childName(child)}` : 'Задания Ученика';
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
        return `<article class="task-card cursor-pointer rounded-2xl bg-white/[.04] p-4 transition hover:bg-white/[.07]" data-task-id="${task.task_id}" tabindex="0" role="button" aria-label="Открыть задание ${task.task_id}">
          <div class="flex flex-wrap items-center justify-between gap-2"><span class="badge">${EduAI.escapeHtml(taskStatusLabel(task.status))}</span><span class="text-xs muted">${EduAI.formatDate(task.created_at)}</span></div>
          <h3 class="mt-3 font-extrabold">${EduAI.escapeHtml(task.title || questions.title || `Задание №${task.task_id}`)}</h3>
          <p class="mt-1 text-sm muted">${EduAI.escapeHtml(task.subject || 'Без предмета')}${task.score != null ? ` · Балл: ${task.score}` : ''}</p>
          ${task.parent_comment ? `<div class="mt-3 rounded-xl bg-emerald-300/[.06] p-3"><p class="text-xs font-bold text-emerald-200">💬 Комментарий к заданию · виден Ученику</p><p class="mt-1 text-sm text-slate-200 whitespace-pre-wrap">${EduAI.escapeHtml(task.parent_comment)}</p></div>` : ''}
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
      EduAI.toast('Сначала привяжите Ученика', 'error');
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

  
  $('task-attachments-list').addEventListener('change', event => {
    const aiBox = event.target.closest('.task-attachment-ai');
    const visibleBox = event.target.closest('.task-attachment-visible');
    const box = aiBox || visibleBox;
    if (!box) return;

    const item = state.taskAttachments.find(
      entry => Number(entry.attachment_id) === Number(box.dataset.id)
    );
    if (!item) return;

    if (aiBox) item.use_as_ai_context = aiBox.checked;
    if (visibleBox) item.visible_to_student = visibleBox.checked;

    if (!item.use_as_ai_context && !item.visible_to_student) {
      if (aiBox) item.visible_to_student = true;
      else item.use_as_ai_context = true;

      EduAI.toast(
        'Файл должен использоваться ИИ или быть отправлен Ученику',
        'info'
      );
      renderTaskAttachments();
    }
  });

  $('task-send-files')?.addEventListener('change', event => {
    state.taskAttachments.forEach(item => {
      item.visible_to_student = event.target.checked;
    });
    renderTaskAttachments();
  });

$('task-form').addEventListener('submit', async event => {
    event.preventDefault();

    const button = event.submitter;
    EduAI.setBusy(button, true, 'Создаём…');

    try {
      const studentIds = selectedStudentIds();
      if (!studentIds.length) throw new Error('Выберите хотя бы одного Ученика');
      const description = $('task-description')
        .value
        .trim()
        .replaceAll('$', '');

      if (!description && !state.taskAttachments.length) {
        throw new Error(
          'Добавьте текст задания или прикрепите файл с заданием'
        );
      }

      const payload = {
        student_ids: studentIds,
        subject:
          $('task-subject').value ||
          $('task-topic').value.trim() ||
          'Практика',
        topic: $('task-topic').value.trim(),
        title: $('task-title').value.trim().replaceAll('$', ''),
        description,
        reference_answer: $('task-answer').value
          .trim()
          .replaceAll('$', ''),
        parent_comment: $('task-parent-comment').value
          .trim()
          .replaceAll('$', ''),
        ai_instructions: '',
        book_id: $('task-book').value
          ? Number($('task-book').value)
          : null,
        page_id: $('task-page').value
          ? Number($('task-page').value)
          : null,
        attachment_ids: state.taskAttachments.map(
          item => Number(item.attachment_id)
        ),
        attachment_options: state.taskAttachments.map(item => ({
          attachment_id: Number(item.attachment_id),
          use_as_ai_context: item.use_as_ai_context !== false,
          visible_to_student: Boolean(item.visible_to_student)
        })),
        send_files_to_student: state.taskAttachments.some(
          item => Boolean(item.visible_to_student)
        )
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
    const bookId = $('task-book').value ? Number($('task-book').value) : null;

    if (!topic) {
      EduAI.toast('Укажите тему задания', 'error');
      return;
    }


    const studentIds = selectedStudentIds();
    if (!studentIds.length) {
      EduAI.toast('Выберите хотя бы одного Ученика', 'error');
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

  function taskCardFromEvent(event) {
    const card = event.target.closest('.task-card[data-task-id]');
    if (!card) return null;
    if (event.target.closest('button, a, input, textarea, select, label, [data-no-task-open]')) return null;
    return card;
  }

  $('sent-tasks-list')?.addEventListener('click', event => {
    const card = taskCardFromEvent(event);
    if (card) openTaskDetail(card.dataset.taskId);
  });

  $('sent-tasks-list')?.addEventListener('keydown', event => {
    if (!['Enter', ' '].includes(event.key)) return;
    const card = event.target.closest('.task-card[data-task-id]');
    if (!card || event.target !== card) return;
    event.preventDefault();
    openTaskDetail(card.dataset.taskId);
  });

  $('task-history-list')?.addEventListener('click', event => {
    const card = taskCardFromEvent(event);
    if (card) openTaskDetail(card.dataset.taskId);
  });

  $('task-history-list')?.addEventListener('keydown', event => {
    if (!['Enter', ' '].includes(event.key)) return;
    const card = event.target.closest('.task-card[data-task-id]');
    if (!card || event.target !== card) return;
    event.preventDefault();
    openTaskDetail(card.dataset.taskId);
  });

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && $('task-detail-modal')?.classList.contains('open')) {
      EduAI.closeModal('task-detail-modal');
    }
  });

  document.addEventListener('click', async event => {
    const closeDetail = event.target.closest('[data-close-modal="task-detail-modal"]');
    if (closeDetail) {
      EduAI.closeModal('task-detail-modal');
      return;
    }

    if (event.target?.id === 'task-detail-modal') {
      EduAI.closeModal('task-detail-modal');
      return;
    }

    const retry = event.target.closest('.retry-task-detail');
    if (retry) {
      await openTaskDetail(retry.dataset.id);
      return;
    }

    const preview = event.target.closest('.task-detail-preview');
    if (preview) {
      try {
        await previewProtectedFile(preview.dataset.url, preview.dataset.name);
      } catch (error) {
        EduAI.toast(error.message, 'error');
      }
      return;
    }

    const download = event.target.closest('.task-detail-download');
    if (download) {
      try {
        await downloadProtectedFile(download.dataset.url, download.dataset.name);
      } catch (error) {
        EduAI.toast(error.message, 'error');
      }
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
    welcome: 'Здравствуйте! Я ИИ-тьютор EduAI. Могу помочь с учёбой и обычными вопросами, разобрать вложение, использовать Book Mode или создать интерактивное задание.'
  });

  $('refresh-parent').addEventListener('click', loadAll);

  renderTaskAttachments();
  await Promise.all([
    loadAll(),
    chat.init(),
    loadTaskClasses()
  ]);
});
