(function () {
  const SESSION_KEY = 'eduai.session.v1';
  const ROLE_PATH = { student: '/student.html', parent: '/parent.html', admin: '/admin.html' };
  let katexPromise = null;

  function readSession() { try { return JSON.parse(localStorage.getItem(SESSION_KEY) || 'null'); } catch (_) { localStorage.removeItem(SESSION_KEY); return null; } }
  function saveSession(data) { localStorage.setItem(SESSION_KEY, JSON.stringify(data)); }
  function clearSession() { localStorage.removeItem(SESSION_KEY); }
  async function api(path, options = {}) {
    const session = readSession(); const headers = new Headers(options.headers || {});
    if (session?.token) headers.set('Authorization', `Bearer ${session.token}`);
    if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
    const response = await fetch(path, { ...options, headers });
    if (response.status === 401) { clearSession(); if (!location.pathname.includes('auth')) location.replace('/auth.html'); }
    if (!response.ok) { let message = `Ошибка ${response.status}`; try { const body = await response.json(); message = body.detail || body.message || message; } catch (_) {} const error = new Error(message); error.status = response.status; throw error; }
    if (response.status === 204) return null; return response.json();
  }
  async function guard(allowedRoles) {
    const session = readSession(); if (!session?.token) { location.replace('/auth.html'); return null; }
    try { const user = await api('/api/v1/auth/session'); const allowed = allowedRoles.includes(user.role) || (user.is_admin && allowedRoles.includes('admin')); const adminAsParent = user.is_admin && allowedRoles.includes('parent'); if (!allowed && !adminAsParent) { toast('У вас нет доступа к этой странице', 'error'); setTimeout(() => location.replace(ROLE_PATH[user.role] || '/auth.html'), 500); return null; } saveSession({ ...session, user }); document.querySelectorAll('[data-user-name]').forEach(el => el.textContent = user.username ? `@${user.username}` : `ID ${user.tg_id}`); document.querySelectorAll('[data-admin-only]').forEach(el => el.hidden = !user.is_admin); return user; } catch (error) { return null; }
  }
  function escapeHtml(value) { return String(value ?? '').replace(/[&<>'"]/g, ch => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[ch])); }
  function encodeMath(value) { return btoa(unescape(encodeURIComponent(value))); }
  function decodeMath(value) { return decodeURIComponent(escape(atob(value))); }
  function ensureMathStyles() {
    if (document.getElementById('eduai-math-styles')) return;
    const style = document.createElement('style');
    style.id = 'eduai-math-styles';
    style.textContent = '.math-display{display:block;max-width:100%;overflow-x:auto;overflow-y:hidden;padding:.35rem 0;-webkit-overflow-scrolling:touch}.math-inline{display:inline-block;max-width:100%;vertical-align:middle}.math-display .katex-display{margin:.25rem 0;text-align:left;min-width:max-content}.eduai-code{max-width:100%;overflow-x:auto;margin:.55rem 0;padding:.7rem .8rem;border-radius:.75rem;background:rgba(0,0,0,.22);white-space:pre}';
    document.head.append(style);
  }
  function ensureKatex() {
    if (window.katex) return Promise.resolve(window.katex);
    if (katexPromise) return katexPromise;
    katexPromise = new Promise((resolve, reject) => {
      if (!document.querySelector('link[data-eduai-katex]')) { const link = document.createElement('link'); link.rel = 'stylesheet'; link.dataset.eduaiKatex = '1'; link.href = 'https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.css'; document.head.append(link); }
      const script = document.createElement('script'); script.src = 'https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.js'; script.defer = true; script.onload = () => resolve(window.katex); script.onerror = reject; document.head.append(script);
    });
    return katexPromise;
  }
  function renderMath(root = document) {
    const nodes = root.querySelectorAll ? root.querySelectorAll('[data-eduai-math]') : [];
    if (!nodes.length) return;
    ensureKatex().then(katex => nodes.forEach(node => {
      if (node.dataset.rendered) return;
      const source = decodeMath(node.dataset.eduaiMath || '');
      try { node.innerHTML = katex.renderToString(source, { displayMode: node.dataset.display === '1', throwOnError: false, strict: 'warn', trust: false, output: 'htmlAndMathml' }); node.dataset.rendered = '1'; }
      catch (_) { node.textContent = source; node.dataset.rendered = 'fallback'; }
    })).catch(() => nodes.forEach(node => { if (!node.dataset.rendered) { node.textContent = decodeMath(node.dataset.eduaiMath || ''); node.dataset.rendered = 'fallback'; } }));
  }
  function markdown(value) {
    const raw = String(value ?? ''); const protectedParts = [];
    const protect = html => { const token = `@@EDUAI_${protectedParts.length}@@`; protectedParts.push(html); return token; };
    let text = raw.replace(/```([\s\S]*?)```/g, (_, code) => protect(`<pre class="eduai-code"><code>${escapeHtml(code.replace(/^\n|\n$/g, ''))}</code></pre>`));
    text = text.replace(/`([^`]+)`/g, (_, code) => protect(`<code class="rounded bg-black/20 px-1">${escapeHtml(code)}</code>`));
    text = text.replace(/\\\[([\s\S]+?)\\\]|\$\$([\s\S]+?)\$\$/g, (_, a, b) => protect(`<span class="math-display" data-eduai-math="${encodeMath(a || b || '')}" data-display="1"></span>`));
    text = text.replace(/\\\((.+?)\\\)/g, (_, expr) => protect(`<span class="math-inline" data-eduai-math="${encodeMath(expr)}" data-display="0"></span>`));
    let safe = escapeHtml(text);
    safe = safe.replace(/^### (.+)$/gm, '<strong class="block text-base mt-2">$1</strong>').replace(/^## (.+)$/gm, '<strong class="block text-lg mt-2">$1</strong>').replace(/^# (.+)$/gm, '<strong class="block text-xl mt-2">$1</strong>').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/^[-•] (.+)$/gm, '<span class="block pl-3">• $1</span>').replace(/\n/g, '<br>');
    protectedParts.forEach((html, index) => { safe = safe.replace(`@@EDUAI_${index}@@`, html); });
    queueMicrotask(() => renderMath(document));
    return safe;
  }
  function toast(message, type = 'info') { let stack = document.querySelector('.toast-stack'); if (!stack) { stack = document.createElement('div'); stack.className = 'toast-stack'; document.body.append(stack); } const item = document.createElement('div'); item.className = `toast ${type}`; item.setAttribute('role', 'status'); item.textContent = message; stack.append(item); setTimeout(() => item.remove(), 4200); }
  function formatDate(value) { if (!value) return '—'; return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)); }
  function setBusy(button, busy, label = 'Подождите…') { if (!button) return; if (busy) { button.dataset.label = button.innerHTML; button.disabled = true; button.textContent = label; } else { button.disabled = false; if (button.dataset.label) button.innerHTML = button.dataset.label; } }
  function openModal(id) { document.getElementById(id)?.classList.add('open'); } function closeModal(id) { document.getElementById(id)?.classList.remove('open'); } function logout() { clearSession(); location.replace('/auth.html'); }
  function startThinking(label = 'ИИ обрабатывает запрос') { const widget = document.createElement('div'); widget.className = 'thinking-widget glass-strong'; widget.setAttribute('role', 'status'); widget.innerHTML = `<span class="thinking-orb"></span><div><strong>${escapeHtml(label)}</strong><p class="muted text-xs">Пожалуйста, не закрывайте страницу · <span>00:00</span></p></div>`; document.body.append(widget); const started = Date.now(); const timer = setInterval(() => { const elapsed = Math.floor((Date.now() - started) / 1000); widget.querySelector('span:last-child').textContent = `${String(Math.floor(elapsed / 60)).padStart(2, '0')}:${String(elapsed % 60).padStart(2, '0')}`; }, 1000); return () => { clearInterval(timer); widget.remove(); }; }
  function initShell() { const sidebar = document.querySelector('.sidebar'); const backdrop = document.querySelector('.backdrop'); const close = () => { sidebar?.classList.remove('open'); backdrop?.classList.remove('open'); }; document.querySelector('.menu-toggle')?.addEventListener('click', () => { sidebar?.classList.toggle('open'); backdrop?.classList.toggle('open'); }); backdrop?.addEventListener('click', close); document.querySelectorAll('[data-section]').forEach(link => link.addEventListener('click', () => { const id = link.dataset.section; document.querySelectorAll('[data-section]').forEach(item => item.classList.toggle('active', item === link)); document.querySelectorAll('.page-section').forEach(section => section.classList.toggle('active', section.id === id)); close(); })); document.querySelectorAll('[data-close-modal]').forEach(button => button.addEventListener('click', () => closeModal(button.dataset.closeModal))); document.querySelectorAll('.modal-backdrop').forEach(modal => modal.addEventListener('click', event => { if (event.target === modal) modal.classList.remove('open'); })); document.querySelectorAll('[data-logout]').forEach(button => button.addEventListener('click', logout)); }
  ensureMathStyles();
  ensureKatex().catch(() => {});
  window.EduAI = { api, guard, readSession, saveSession, clearSession, escapeHtml, markdown, renderMath, toast, formatDate, setBusy, openModal, closeModal, logout, startThinking, initShell, ROLE_PATH };
})();
