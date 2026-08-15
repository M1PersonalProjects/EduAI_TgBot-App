(function () {
  const SESSION_KEY = 'eduai.session.v1';
  const ROLE_PATH = { student: '/student.html', parent: '/parent.html', admin: '/admin.html' };
  const ROLE_LABELS = { student: 'Ученик', parent: 'Учитель', admin: 'Администратор' };
  const roleLabel = role => ROLE_LABELS[role] || role || '';
  const MATH_RENDERER_VERSION = '20260812-5';
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
    } catch (_) { return null; }
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, ch => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[ch]));
  }

  function encodeMath(value) { return btoa(unescape(encodeURIComponent(value))); }
  function decodeMath(value) { return decodeURIComponent(escape(atob(value))); }

  function ensureMathStyles() {
    if (document.getElementById('eduai-math-styles')) return;
    const style = document.createElement('style');
    style.id = 'eduai-math-styles';
    style.textContent = [
      '.math-display{display:block;max-width:100%;overflow-x:auto;overflow-y:hidden;padding:.35rem 0;-webkit-overflow-scrolling:touch}',
      '.math-inline{display:inline-block;max-width:100%;vertical-align:middle}',
      '.math-display .katex-display{margin:.25rem 0;text-align:left;min-width:max-content}',
      '.eduai-code{max-width:100%;overflow-x:auto;margin:.55rem 0;padding:.7rem .8rem;border-radius:.75rem;background:rgba(0,0,0,.22);white-space:pre}',
      '.math-fallback{font-family:inherit;white-space:pre-wrap}'
    ].join('');
    document.head.append(style);
  }

  function ensureKatex() {
    if (window.katex) return Promise.resolve(window.katex);
    if (katexPromise) return katexPromise;
    katexPromise = new Promise((resolve, reject) => {
      if (!document.querySelector('link[data-eduai-katex]')) {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.dataset.eduaiKatex = '1';
        link.href = 'https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.css';
        document.head.append(link);
      }
      const existing = document.querySelector('script[data-eduai-katex]');
      if (existing) {
        existing.addEventListener('load', () => resolve(window.katex), { once: true });
        existing.addEventListener('error', reject, { once: true });
        return;
      }
      const script = document.createElement('script');
      script.dataset.eduaiKatex = '1';
      script.src = 'https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.js';
      script.defer = true;
      script.onload = () => resolve(window.katex);
      script.onerror = reject;
      document.head.append(script);
    });
    return katexPromise;
  }

  function normalizeLatexTransport(value) {
    let text = String(value ?? '');
    // JSON/LLM transport occasionally leaves doubled TeX backslashes.
    // Collapse them only before known TeX delimiters/commands, never globally.
    text = text.replace(/\\\\(?=[()[\]])/g, '\\');
    text = text.replace(/\\\\(?=(?:frac|sqrt|times|cdot|div|text|begin|end|quad|qquad|Rightarrow|Leftarrow|rightarrow|leftarrow|pm|leq?|geq?|neq?|pi|infty|left|right)\b)/g, '\\');
    return text;
  }

  function latexFallback(expr) {
    let text = normalizeLatexTransport(expr).trim();
    let previous = null;

    // Resolve nested simple fractions from inside out.
    while (previous !== text) {
      previous = text;
      text = text.replace(/\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, '($1)/($2)');
    }

    text = text
      .replace(/\\sqrt\s*\[([^\]]+)\]\s*\{([^{}]+)\}/g, 'root[$1]($2)')
      .replace(/\\sqrt\s*\{([^{}]+)\}/g, '√($1)')
      .replace(/\\text\s*\{([^{}]*)\}/g, '$1')
      .replace(/\\(?:quad|qquad)\b/g, ' ')
      .replace(/\\Rightarrow\b/g, ' ⇒ ')
      .replace(/\\Leftarrow\b/g, ' ⇐ ')
      .replace(/\\rightarrow\b/g, ' → ')
      .replace(/\\leftarrow\b/g, ' ← ')
      .replace(/\\times\b/g, '×')
      .replace(/\\cdot\b/g, '·')
      .replace(/\\div\b/g, ':')
      .replace(/\\pm\b/g, '±')
      .replace(/\\leq?\b/g, '≤')
      .replace(/\\geq?\b/g, '≥')
      .replace(/\\neq?\b/g, '≠')
      .replace(/\\pi\b/g, 'π')
      .replace(/\\infty\b/g, '∞')
      .replace(/\\begin\{cases\}|\\end\{cases\}/g, '')
      .replace(/\\(?:left|right)\b/g, '')
      .replace(/\\\\/g, '\n')
      .replace(/[{}]/g, '');

    // Never expose remaining TeX command names in fallback.
    text = text.replace(/\\[A-Za-z]+/g, '');
    return text.replace(/[ \t]{2,}/g, ' ').trim();
  }

  function renderMath(root = document) {
    const nodes = [];
    if (root?.matches?.('[data-eduai-math]')) nodes.push(root);
    if (root?.querySelectorAll) nodes.push(...root.querySelectorAll('[data-eduai-math]'));
    if (!nodes.length) return;

    ensureKatex().then(katex => {
      nodes.forEach(node => {
        if (node.dataset.rendered === '1') return;
        const source = decodeMath(node.dataset.eduaiMath || '');
        try {
          node.innerHTML = katex.renderToString(source, {
            displayMode: node.dataset.display === '1',
            throwOnError: true,
            strict: 'warn',
            trust: false,
            output: 'htmlAndMathml'
          });
          node.dataset.rendered = '1';
        } catch (_) {
          node.textContent = latexFallback(source);
          node.classList.add('math-fallback');
          node.dataset.rendered = 'fallback';
        }
      });
    }).catch(() => {
      nodes.forEach(node => {
        if (node.dataset.rendered) return;
        node.textContent = latexFallback(decodeMath(node.dataset.eduaiMath || ''));
        node.classList.add('math-fallback');
        node.dataset.rendered = 'fallback';
      });
    });
  }

  function protectBareLatex(text, protect) {
    // Handle legacy/model output where TeX commands were emitted without delimiters.
    // Process line by line so normal prose/URLs remain untouched.
    return text.split('\n').map(line => {
      if (!/\\(?:frac|sqrt|times|cdot|div|text|begin|end|quad|qquad|Rightarrow|Leftarrow|rightarrow|leftarrow|pm|leq?|geq?|neq?)\b/.test(line)) {
        return line;
      }
      // If a line contains a TeX command, treat the mathematical tail as inline math.
      // This is intentionally conservative and does not touch URLs or code (already protected).
      const first = line.search(/\\(?:frac|sqrt|times|cdot|div|text|begin|end|quad|qquad|Rightarrow|Leftarrow|rightarrow|leftarrow|pm|leq?|geq?|neq?)\b/);
      let start = first;
      while (start > 0 && !/[,:;.!?]\s/.test(line.slice(start - 2, start + 1))) start--;
      const prefix = line.slice(0, start);
      const expr = line.slice(start).trim();
      return prefix + protect(`<span class="math-inline" data-eduai-math="${encodeMath(expr)}" data-display="0"></span>`);
    }).join('\n');
  }

  function markdown(value) {
    const raw = normalizeLatexTransport(String(value ?? ''));
    const protectedParts = [];
    const protect = html => {
      const token = `@@EDUAI_${protectedParts.length}@@`;
      protectedParts.push(html);
      return token;
    };

    // Protect code before any mathematical processing.
    let text = raw.replace(/```([\s\S]*?)```/g, (_, code) =>
      protect(`<pre class="eduai-code"><code>${escapeHtml(code.replace(/^\n|\n$/g, ''))}</code></pre>`)
    );
    text = text.replace(/`([^`]+)`/g, (_, code) =>
      protect(`<code class="rounded bg-black/20 px-1">${escapeHtml(code)}</code>`)
    );

    // Explicit display and inline math.
    text = text.replace(/\\\[([\s\S]+?)\\\]|\$\$([\s\S]+?)\$\$/g, (_, a, b) =>
      protect(`<span class="math-display" data-eduai-math="${encodeMath(a || b || '')}" data-display="1"></span>`)
    );
    text = text.replace(/\\\(([\s\S]+?)\\\)/g, (_, expr) =>
      protect(`<span class="math-inline" data-eduai-math="${encodeMath(expr)}" data-display="0"></span>`)
    );

    // Legacy/bare TeX.
    text = protectBareLatex(text, protect);

    let safe = escapeHtml(text);
    safe = safe
      .replace(/^### (.+)$/gm, '<strong class="block text-base mt-2">$1</strong>')
      .replace(/^## (.+)$/gm, '<strong class="block text-lg mt-2">$1</strong>')
      .replace(/^# (.+)$/gm, '<strong class="block text-xl mt-2">$1</strong>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/^[-•] (.+)$/gm, '<span class="block pl-3">• $1</span>')
      .replace(/\n/g, '<br>');

    protectedParts.forEach((html, index) => {
      safe = safe.replace(`@@EDUAI_${index}@@`, html);
    });

    queueMicrotask(() => renderMath(document));
    return safe;
  }

  function installMathObserver() {
    if (!document.body || window.__eduaiMathObserver) return;
    const observer = new MutationObserver(mutations => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (node.nodeType === Node.ELEMENT_NODE) renderMath(node);
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    window.__eduaiMathObserver = observer;
    renderMath(document);
  }

  function toast(message, type = 'info') {
    let stack = document.querySelector('.toast-stack');
    if (!stack) { stack = document.createElement('div'); stack.className = 'toast-stack'; document.body.append(stack); }
    const item = document.createElement('div'); item.className = `toast ${type}`; item.setAttribute('role', 'status'); item.textContent = message;
    stack.append(item); setTimeout(() => item.remove(), 4200);
  }

  function formatDate(value) { if (!value) return '—'; return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)); }
  function setBusy(button, busy, label = 'Подождите…') { if (!button) return; if (busy) { button.dataset.label = button.innerHTML; button.disabled = true; button.textContent = label; } else { button.disabled = false; if (button.dataset.label) button.innerHTML = button.dataset.label; } }
  function openModal(id) { document.getElementById(id)?.classList.add('open'); }
  function closeModal(id) { document.getElementById(id)?.classList.remove('open'); }
  function logout() { clearSession(); location.replace('/auth.html'); }

  function startThinking(label = 'ИИ обрабатывает запрос') {
    const widget = document.createElement('div'); widget.className = 'thinking-widget glass-strong'; widget.setAttribute('role', 'status');
    widget.innerHTML = `<span class="thinking-orb"></span><div><strong>${escapeHtml(label)}</strong><p class="muted text-xs">Пожалуйста, не закрывайте страницу · <span>00:00</span></p></div>`;
    document.body.append(widget);
    const started = Date.now();
    const timer = setInterval(() => {
      const elapsed = Math.floor((Date.now() - started) / 1000);
      widget.querySelector('span:last-child').textContent = `${String(Math.floor(elapsed / 60)).padStart(2, '0')}:${String(elapsed % 60).padStart(2, '0')}`;
    }, 1000);
    return () => { clearInterval(timer); widget.remove(); };
  }

  function initShell() {
    const sidebar = document.querySelector('.sidebar'); const backdrop = document.querySelector('.backdrop');
    const close = () => { sidebar?.classList.remove('open'); backdrop?.classList.remove('open'); };
    document.querySelector('.menu-toggle')?.addEventListener('click', () => { sidebar?.classList.toggle('open'); backdrop?.classList.toggle('open'); });
    backdrop?.addEventListener('click', close);
    document.querySelectorAll('[data-section]').forEach(link => link.addEventListener('click', () => {
      const id = link.dataset.section;
      document.body.dataset.activeSection = id;
      document.querySelectorAll('[data-section]').forEach(item => item.classList.toggle('active', item === link));
      document.querySelectorAll('.page-section').forEach(section => section.classList.toggle('active', section.id === id));
      close();
    }));
    document.querySelectorAll('[data-close-modal]').forEach(button => button.addEventListener('click', () => closeModal(button.dataset.closeModal)));
    document.querySelectorAll('.modal-backdrop').forEach(modal => modal.addEventListener('click', event => { if (event.target === modal) modal.classList.remove('open'); }));
    document.querySelectorAll('[data-logout]').forEach(button => button.addEventListener('click', logout));
    const initialSection = document.querySelector('.page-section.active')?.id;
    if (initialSection) document.body.dataset.activeSection = initialSection;
  }


  function syncViewportHeight() {
    const tg = window.Telegram?.WebApp;
    const height = Number(tg?.viewportStableHeight || tg?.viewportHeight || window.visualViewport?.height || window.innerHeight || 0);
    if (height > 0) document.documentElement.style.setProperty('--eduai-viewport-height', `${Math.round(height)}px`);
  }
  syncViewportHeight();
  window.addEventListener('resize', syncViewportHeight, { passive: true });
  window.visualViewport?.addEventListener('resize', syncViewportHeight, { passive: true });
  window.Telegram?.WebApp?.onEvent?.('viewportChanged', syncViewportHeight);

  ensureMathStyles();
  ensureKatex().catch(() => {});
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', installMathObserver, { once: true });
  } else {
    installMathObserver();
  }

  window.EduAI = {
    api, guard, readSession, saveSession, clearSession, escapeHtml,
    markdown, renderMath, toast, formatDate, setBusy, openModal, closeModal,
    logout, startThinking, initShell, ROLE_PATH, ROLE_LABELS, roleLabel, MATH_RENDERER_VERSION,
    mathDebug: { normalizeLatexTransport, latexFallback }
  };
})();

/* === TZ23 RICH CONTENT START === */
(function () {
  if (!window.EduAI) return;

  const oldInitShell = EduAI.initShell;
  let katexPromise = null;

  function encodeMath(value) {
    return btoa(unescape(encodeURIComponent(String(value ?? ''))));
  }

  function decodeMath(value) {
    return decodeURIComponent(escape(atob(value || '')));
  }

  function normalizeLatexTransport(value) {
    let text = String(value ?? '');
    text = text.replace(/\\\\(?=[()[\]])/g, '\\');
    text = text.replace(
      /\\\\(?=(?:frac|sqrt|times|cdot|div|text|begin|end|quad|qquad|Rightarrow|Leftarrow|rightarrow|leftarrow|pm|leq?|geq?|neq?|pi|infty|left|right)\b)/g,
      '\\'
    );
    return text;
  }

  function latexFallback(value) {
    let text = normalizeLatexTransport(value).trim();
    let previous = null;

    while (text !== previous) {
      previous = text;
      text = text.replace(
        /\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g,
        '($1) / ($2)'
      );
    }

    text = text
      .replace(/\\sqrt\s*\{([^{}]+)\}/g, '√($1)')
      .replace(/\\text\s*\{([^{}]*)\}/g, '$1')
      .replace(/\\(?:quad|qquad)\b/g, ' ')
      .replace(/\\Rightarrow\b/g, ' ⇒ ')
      .replace(/\\Leftarrow\b/g, ' ⇐ ')
      .replace(/\\rightarrow\b/g, ' → ')
      .replace(/\\leftarrow\b/g, ' ← ')
      .replace(/\\times\b/g, ' × ')
      .replace(/\\cdot\b/g, ' · ')
      .replace(/\\div\b/g, ' : ')
      .replace(/\\pm\b/g, ' ± ')
      .replace(/\\leq?\b/g, ' ≤ ')
      .replace(/\\geq?\b/g, ' ≥ ')
      .replace(/\\neq?\b/g, ' ≠ ')
      .replace(/\\pi\b/g, 'π')
      .replace(/\\infty\b/g, '∞')
      .replace(/\\begin\{cases\}|\\end\{cases\}/g, '')
      .replace(/\\(?:left|right)\b/g, '')
      .replace(/\\\\/g, '\n')
      .replace(/\\\[|\\\]|\\\(|\\\)/g, '')
      .replace(/\\[A-Za-z]+/g, '')
      .replace(/[{}]/g, '');

    return text.replace(/[ \t]{2,}/g, ' ').trim();
  }

  function ensureKatex() {
    if (window.katex) return Promise.resolve(window.katex);
    if (katexPromise) return katexPromise;

    katexPromise = new Promise((resolve, reject) => {
      if (!document.querySelector('link[data-eduai-katex]')) {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.dataset.eduaiKatex = '1';
        link.href = 'https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.css';
        document.head.append(link);
      }

      const existing = document.querySelector('script[data-eduai-katex]');
      if (existing) {
        if (window.katex) resolve(window.katex);
        else {
          existing.addEventListener('load', () => resolve(window.katex), { once: true });
          existing.addEventListener('error', reject, { once: true });
        }
        return;
      }

      const script = document.createElement('script');
      script.dataset.eduaiKatex = '1';
      script.src = 'https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.js';
      script.defer = true;
      script.onload = () => resolve(window.katex);
      script.onerror = reject;
      document.head.append(script);
    });

    return katexPromise;
  }

  function mathNodes(root) {
    const result = [];
    if (root?.matches?.('[data-eduai-math]')) result.push(root);
    if (root?.querySelectorAll) {
      result.push(...root.querySelectorAll('[data-eduai-math]'));
    }
    return result;
  }

  function renderMath(root = document) {
    const nodes = mathNodes(root).filter(node => !node.dataset.rendered);
    if (!nodes.length) return;

    ensureKatex()
      .then(katex => {
        nodes.forEach(node => {
          const source = decodeMath(node.dataset.eduaiMath || '');
          try {
            node.innerHTML = katex.renderToString(source, {
              displayMode: node.dataset.display === '1',
              throwOnError: true,
              strict: 'warn',
              trust: false,
              output: 'htmlAndMathml'
            });
            node.dataset.rendered = '1';
          } catch (_) {
            node.textContent = latexFallback(source);
            node.classList.add('math-fallback');
            node.dataset.rendered = 'fallback';
          }
        });
      })
      .catch(() => {
        nodes.forEach(node => {
          node.textContent = latexFallback(
            decodeMath(node.dataset.eduaiMath || '')
          );
          node.classList.add('math-fallback');
          node.dataset.rendered = 'fallback';
        });
      });
  }

  function hasBareLatex(line) {
    return /\\(?:frac|sqrt|times|cdot|div|text|begin|end|quad|qquad|Rightarrow|Leftarrow|rightarrow|leftarrow|pm|leq?|geq?|neq?)\b/.test(line);
  }

  function renderRichContent(value) {
    const raw = normalizeLatexTransport(value);
    const protectedParts = [];
    const protect = html => {
      const token = `@@EDUAI_RICH_${protectedParts.length}@@`;
      protectedParts.push(html);
      return token;
    };

    // Code must be protected before math processing. URLs are not touched by
    // the fallback because it only reacts to TeX commands beginning with '\\'.
    let text = raw.replace(/```([\s\S]*?)```/g, (_, code) =>
      protect(
        `<pre class="eduai-code"><code>${EduAI.escapeHtml(
          code.replace(/^\n|\n$/g, '')
        )}</code></pre>`
      )
    );
    text = text.replace(/`([^`]+)`/g, (_, code) =>
      protect(
        `<code class="rounded bg-black/20 px-1">${EduAI.escapeHtml(code)}</code>`
      )
    );

    // Canonical display and inline math.
    text = text.replace(
      /\\\[([\s\S]+?)\\\]|\$\$([\s\S]+?)\$\$/g,
      (_, a, b) => protect(
        `<span class="math-display" data-eduai-math="${encodeMath(a || b || '')}" data-display="1"></span>`
      )
    );
    text = text.replace(/\\\(([\s\S]+?)\\\)/g, (_, expr) =>
      protect(
        `<span class="math-inline" data-eduai-math="${encodeMath(expr)}" data-display="0"></span>`
      )
    );

    // Legacy messages sometimes contain bare TeX without delimiters. Do not
    // show technical commands to the user: convert such lines to a readable
    // fallback while preserving normal prose around them.
    text = text
      .split('\n')
      .map(line => hasBareLatex(line) ? latexFallback(line) : line)
      .join('\n');

    let safe = EduAI.escapeHtml(text);
    safe = safe
      .replace(/^### (.+)$/gm, '<strong class="block text-base mt-2">$1</strong>')
      .replace(/^## (.+)$/gm, '<strong class="block text-lg mt-2">$1</strong>')
      .replace(/^# (.+)$/gm, '<strong class="block text-xl mt-2">$1</strong>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/^[-•] (.+)$/gm, '<span class="block pl-3">• $1</span>')
      .replace(/\n/g, '<br>');

    protectedParts.forEach((html, index) => {
      safe = safe.replace(`@@EDUAI_RICH_${index}@@`, html);
    });

    queueMicrotask(() => renderMath(document));
    return `<div class="rich-content">${safe}</div>`;
  }

  function setActiveSection() {
    const active = document.querySelector('.page-section.active');
    if (active?.id) document.body.dataset.activeSection = active.id;
  }

  EduAI.initShell = function (...args) {
    const result = oldInitShell.apply(this, args);
    setActiveSection();
    document.querySelectorAll('[data-section]').forEach(button => {
      button.addEventListener('click', () => {
        requestAnimationFrame(setActiveSection);
      });
    });
    return result;
  };

  EduAI.renderRichContent = renderRichContent;
  EduAI.markdown = renderRichContent; // backward compatibility
  EduAI.renderMath = renderMath;
  EduAI.latexFallback = latexFallback;
  EduAI.MATH_RENDERER_VERSION = '20260813-tz23-1';

  const installObserver = () => {
    if (!document.body || window.__eduaiMathObserver) return;
    const observer = new MutationObserver(mutations => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (node.nodeType === Node.ELEMENT_NODE) renderMath(node);
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    window.__eduaiMathObserver = observer;
    renderMath(document);
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', installObserver, { once: true });
  } else {
    installObserver();
  }
})();
/* === TZ23 RICH CONTENT END === */
