(function () {
  const SESSION_KEY = 'eduai.session.v1';
  const ROLE_PATH = { student: '/student.html', parent: '/parent.html', admin: '/admin.html' };

  function readSession() {
    try { return JSON.parse(localStorage.getItem(SESSION_KEY) || 'null'); }
    catch (_) { localStorage.removeItem(SESSION_KEY); return null; }
  }
  function saveSession(data) { localStorage.setItem(SESSION_KEY, JSON.stringify(data)); }
  function clearSession() { localStorage.removeItem(SESSION_KEY); }

  async function api(path, options = {}) {
    const session = readSession();
    const headers = new Headers(options.headers || {});
    if (session?.token) headers.set('Authorization', `Bearer ${session.token}`);
    if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
    const response = await fetch(path, { ...options, headers });
    if (response.status === 401) {
      clearSession();
      if (!location.pathname.includes('auth')) location.replace('/auth.html');
    }
    if (!response.ok) {
      let message = `Ошибка ${response.status}`;
      try { const body = await response.json(); message = body.detail || body.message || message; } catch (_) {}
      const error = new Error(message); error.status = response.status; throw error;
    }
    if (response.status === 204) return null;
    return response.json();
  }

  async function guard(allowedRoles) {
    const session = readSession();
    if (!session?.token) { location.replace('/auth.html'); return null; }
    try {
      const user = await api('/api/v1/auth/session');
      const allowed = allowedRoles.includes(user.role) || (user.is_admin && allowedRoles.includes('admin'));
      const adminAsParent = user.is_admin && allowedRoles.includes('parent');
      if (!allowed && !adminAsParent) {
        toast('У вас нет доступа к этой странице', 'error');
        setTimeout(() => location.replace(ROLE_PATH[user.role] || '/auth.html'), 500);
        return null;
      }
      saveSession({ ...session, user });
      document.querySelectorAll('[data-user-name]').forEach(el => el.textContent = user.username ? `@${user.username}` : `ID ${user.tg_id}`);
      document.querySelectorAll('[data-admin-only]').forEach(el => el.hidden = !user.is_admin);
      return user;
    } catch (error) { return null; }
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, ch => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[ch]));
  }
  function markdown(value) {
    let safe = escapeHtml(String(value ?? '').replaceAll('$', ''));
    safe = safe.replace(/^### (.+)$/gm, '<strong class="block text-base mt-2">$1</strong>')
      .replace(/^## (.+)$/gm, '<strong class="block text-lg mt-2">$1</strong>')
      .replace(/^# (.+)$/gm, '<strong class="block text-xl mt-2">$1</strong>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+)`/g, '<code class="rounded bg-black\/20 px-1">$1</code>')
      .replace(/^[-•] (.+)$/gm, '<span class="block pl-3">• $1</span>')
      .replace(/\n/g, '<br>');
    return safe;
  }
  function toast(message, type = 'info') {
    let stack = document.querySelector('.toast-stack');
    if (!stack) { stack = document.createElement('div'); stack.className = 'toast-stack'; document.body.append(stack); }
    const item = document.createElement('div'); item.className = `toast ${type}`; item.setAttribute('role', 'status'); item.textContent = message;
    stack.append(item); setTimeout(() => item.remove(), 4200);
  }
  function formatDate(value) {
    if (!value) return '—';
    return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
  }
  function setBusy(button, busy, label = 'Подождите…') {
    if (!button) return;
    if (busy) { button.dataset.label = button.innerHTML; button.disabled = true; button.textContent = label; }
    else { button.disabled = false; if (button.dataset.label) button.innerHTML = button.dataset.label; }
  }
  function openModal(id) { document.getElementById(id)?.classList.add('open'); }
  function closeModal(id) { document.getElementById(id)?.classList.remove('open'); }
  function logout() { clearSession(); location.replace('/auth.html'); }

  function initShell() {
    const sidebar = document.querySelector('.sidebar'); const backdrop = document.querySelector('.backdrop');
    const close = () => { sidebar?.classList.remove('open'); backdrop?.classList.remove('open'); };
    document.querySelector('.menu-toggle')?.addEventListener('click', () => { sidebar?.classList.toggle('open'); backdrop?.classList.toggle('open'); });
    backdrop?.addEventListener('click', close);
    document.querySelectorAll('[data-section]').forEach(link => link.addEventListener('click', () => {
      const id = link.dataset.section;
      document.querySelectorAll('[data-section]').forEach(item => item.classList.toggle('active', item === link));
      document.querySelectorAll('.page-section').forEach(section => section.classList.toggle('active', section.id === id));
      close();
    }));
    document.querySelectorAll('[data-close-modal]').forEach(button => button.addEventListener('click', () => closeModal(button.dataset.closeModal)));
    document.querySelectorAll('.modal-backdrop').forEach(modal => modal.addEventListener('click', event => { if (event.target === modal) modal.classList.remove('open'); }));
    document.querySelectorAll('[data-logout]').forEach(button => button.addEventListener('click', logout));
  }

  window.EduAI = { api, guard, readSession, saveSession, clearSession, escapeHtml, markdown, toast, formatDate, setBusy, openModal, closeModal, logout, initShell, ROLE_PATH };
})();
