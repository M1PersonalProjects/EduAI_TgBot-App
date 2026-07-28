document.addEventListener('DOMContentLoaded', async () => {
  EduAI.initShell();
  const user = await EduAI.guard(['student']);
  if (!user) return;
  window.Telegram?.WebApp?.ready(); window.Telegram?.WebApp?.expand();
  const state = { dashboard: null };
  const byId = id => document.getElementById(id);

  function empty(text) { return `<div class="empty-state glass col-span-full"><div><div class="text-3xl mb-3">○</div><p>${EduAI.escapeHtml(text)}</p></div></div>`; }
  function renderDashboard(data) {
    state.dashboard = data;
    byId('coins').textContent = data.profile.balance_coins.toLocaleString('ru-RU');
    byId('xp').textContent = data.profile.xp_total.toLocaleString('ru-RU');
    byId('streak').textContent = `${data.profile.streak_days}`;
    byId('task-count-badge').textContent = data.tasks.length;
    byId('tasks-list').innerHTML = data.tasks.length ? data.tasks.map(task => {
      const q = task.questions_json || {}; const topic = task.topic_context || {};
      return `<article class="glass card" data-task-card="${task.task_id}">
        <div class="flex items-center justify-between gap-2"><span class="badge">${task.parent_id ? 'От родителя' : 'ИИ-практика'}</span><span class="text-xs muted">${EduAI.escapeHtml(topic.subject || 'Задание')}</span></div>
        <h3 class="mt-4 text-lg font-extrabold">${EduAI.escapeHtml(q.title || `Задание №${task.task_id}`)}</h3>
        <div class="mt-2 text-sm leading-6 text-slate-300">${EduAI.markdown(q.question_text || '')}</div>
        ${task.student_answers_json?.verification_feedback ? `<p class="mt-3 rounded-xl bg-white/[.04] p-3 text-sm muted">${EduAI.escapeHtml(task.student_answers_json.verification_feedback)}</p>` : ''}
        <form class="task-form mt-4 grid gap-2" data-task-id="${task.task_id}"><label class="text-xs font-bold muted" for="answer-${task.task_id}">Ваш ответ</label><div class="flex gap-2"><input id="answer-${task.task_id}" class="input" maxlength="4000" required placeholder="Введите ответ"><button class="btn-primary shrink-0" type="submit">Проверить</button></div></form>
      </article>`;
    }).join('') : empty('Активных заданий пока нет. Можно посвятить время тьютору.');

    byId('rewards-list').innerHTML = data.rewards.length ? data.rewards.map(reward => `<article class="glass card flex flex-col"><div class="flex items-center justify-between"><span class="text-2xl">${reward.category === 'activity' ? '🚲' : reward.category === 'screen' ? '🎮' : '🎁'}</span><span class="badge">${reward.cost_coins} монет</span></div><h3 class="mt-4 font-extrabold">${EduAI.escapeHtml(reward.name)}</h3><p class="mt-2 text-sm muted flex-1">${EduAI.escapeHtml(reward.description || 'Семейная награда')}</p><button class="btn-primary mt-5 reward-buy" data-reward-id="${reward.reward_id}" ${data.profile.balance_coins < reward.cost_coins ? 'disabled' : ''}>${data.profile.balance_coins < reward.cost_coins ? 'Нужно больше монет' : 'Получить награду'}</button></article>`).join('') : empty('Родитель пока не добавил награды.');
    byId('purchases-list').innerHTML = data.purchases.length ? data.purchases.map(item => `<article class="glass card flex items-center justify-between gap-3"><div><p class="font-bold">${EduAI.escapeHtml(item.name)}</p><p class="mt-1 text-xs muted">${EduAI.formatDate(item.purchased_at)}</p></div><span class="badge">−${item.cost_coins} монет</span></article>`).join('') : empty('Покупок ещё не было.');
  }
  async function loadDashboard() {
    try { renderDashboard(await EduAI.api('/api/v1/student/dashboard')); }
    catch (error) { EduAI.toast(error.message, 'error'); }
  }
  byId('tasks-list').addEventListener('submit', async event => {
    const form = event.target.closest('.task-form'); if (!form) return; event.preventDefault(); const button = form.querySelector('button'); const answer = form.querySelector('input').value.trim(); EduAI.setBusy(button, true, 'Проверяем…');
    try { const result = await EduAI.api(`/api/v1/student/tasks/${form.dataset.taskId}/submit`, { method: 'POST', body: JSON.stringify({ student_answer: answer }) }); EduAI.toast(result.success ? `Верно! +${result.earned_coins} монет и +${result.earned_xp} XP` : result.message, result.success ? 'success' : 'error'); await loadDashboard(); }
    catch (error) { EduAI.toast(error.message, 'error'); } finally { EduAI.setBusy(button, false); }
  });
  byId('rewards-list').addEventListener('click', async event => { const button = event.target.closest('.reward-buy'); if (!button) return; if (!confirm('Обменять монеты на эту награду?')) return; EduAI.setBusy(button, true, 'Покупаем…'); try { const result = await EduAI.api(`/api/v1/student/rewards/${button.dataset.rewardId}/buy`, { method: 'POST' }); EduAI.toast(`Награда «${result.reward_name}» получена!`, 'success'); await loadDashboard(); } catch (e) { EduAI.toast(e.message, 'error'); } finally { EduAI.setBusy(button, false); } });
  byId('refresh-dashboard').addEventListener('click', loadDashboard); byId('refresh-tasks').addEventListener('click', loadDashboard);
  const chat = new EduAIChat({
    newChatId: 'new-chat', threadsId: 'chat-threads', formId: 'chat-form', inputId: 'chat-input',
    logId: 'chat-log', attachId: 'chat-attachment', removeAttachId: 'chat-remove-attachment',
    attachmentPreviewId: 'chat-attachment-preview', attachmentNameId: 'chat-attachment-name',
    classId: 'chat-class', subjectId: 'chat-subject', bookId: 'chat-book', pageId: 'chat-page',
    lockId: 'chat-lock-context', exitId: 'chat-exit-context', contextStatusId: 'chat-context-status',
    welcome: 'Привет! Я твой ИИ-тьютор. Можно сразу задать вопрос или выбрать учебник справа.'
  });
  await Promise.all([loadDashboard(), chat.init()]);
});
