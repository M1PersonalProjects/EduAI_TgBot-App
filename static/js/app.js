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
  function openModal(id) {
    const modal = document.getElementById(id);
    if (!modal) return;
    modal.classList.add('open');
    document.body.classList.add('eduai-modal-open');
  }
  function closeModal(id) {
    document.getElementById(id)?.classList.remove('open');
    if (!document.querySelector('.modal-backdrop.open')) document.body.classList.remove('eduai-modal-open');
  }
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
    document.querySelectorAll('.modal-backdrop').forEach(modal => modal.addEventListener('click', event => { if (event.target === modal) { modal.classList.remove('open'); if (!document.querySelector('.modal-backdrop.open')) document.body.classList.remove('eduai-modal-open'); } }));
    document.querySelectorAll('[data-logout]').forEach(button => button.addEventListener('click', logout));
    const initialSection = document.querySelector('.page-section.active')?.id;
    if (initialSection) document.body.dataset.activeSection = initialSection;
  }


  function syncViewportHeight() {
    const tg = window.Telegram?.WebApp;
    // visualViewport/current Telegram viewport shrink with the mobile keyboard.
    // viewportStableHeight is deliberately last because using it first creates
    // phantom page height while the keyboard is open.
    const height = Number(
      window.visualViewport?.height ||
      tg?.viewportHeight ||
      window.innerHeight ||
      tg?.viewportStableHeight ||
      0
    );
    if (height > 0) {
      document.documentElement.style.setProperty('--eduai-viewport-height', `${Math.round(height)}px`);
    }
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

/* === EduAI unified rich math rendering: 2026-08-16 === */
(function () {
  if (!window.EduAI) return;

  const previousRenderMath = EduAI.renderMath;
  const COMMAND_RE = /\\(?:frac|dfrac|tfrac|sqrt|times|cdot|div|pm|mp|le|leq|ge|geq|ne|neq|approx|equiv|sim|simeq|propto|in|notin|ni|subset|subseteq|supset|supseteq|cap|cup|setminus|emptyset|forall|exists|nabla|partial|sum|prod|int|iint|iiint|oint|lim|min|max|sin|cos|tan|tg|cot|ctg|log|ln|lg|exp|pi|infty|alpha|beta|gamma|delta|epsilon|varepsilon|zeta|eta|theta|vartheta|iota|kappa|lambda|mu|nu|xi|rho|sigma|tau|upsilon|phi|varphi|chi|psi|omega|Gamma|Delta|Theta|Lambda|Xi|Pi|Sigma|Phi|Psi|Omega|quad|qquad|Rightarrow|Leftarrow|Leftrightarrow|rightarrow|leftarrow|to|mapsto|implies|iff|text|textrm|mathrm|mathbf|mathit|mathsf|mathtt|operatorname|begin|end|left|right|overline|underline|vec|hat|bar|dot|ddot|boxed|ldots|cdots|vdots|ddots)(?![A-Za-z])/;
  const DOUBLE_COMMAND_RE = /\\\\(?=(?:\[|\]|\(|\)|frac|dfrac|tfrac|sqrt|times|cdot|div|pm|mp|le|leq|ge|geq|ne|neq|approx|equiv|sim|simeq|propto|in|notin|ni|subset|subseteq|supset|supseteq|cap|cup|setminus|emptyset|forall|exists|nabla|partial|sum|prod|int|iint|iiint|oint|lim|min|max|sin|cos|tan|tg|cot|ctg|log|ln|lg|exp|pi|infty|alpha|beta|gamma|delta|epsilon|varepsilon|zeta|eta|theta|vartheta|iota|kappa|lambda|mu|nu|xi|rho|sigma|tau|upsilon|phi|varphi|chi|psi|omega|Gamma|Delta|Theta|Lambda|Xi|Pi|Sigma|Phi|Psi|Omega|quad|qquad|Rightarrow|Leftarrow|Leftrightarrow|rightarrow|leftarrow|to|mapsto|implies|iff|text|textrm|mathrm|mathbf|mathit|mathsf|mathtt|operatorname|begin|end|left|right|overline|underline|vec|hat|bar|dot|ddot|boxed|ldots|cdots|vdots|ddots)(?![A-Za-z]))/g;
  const WINDOWS_PATH_RE = /\b[A-Za-z]:\\(?:[^\\\s]+\\)+[^\s]*/;

  const encodeMath = value => btoa(unescape(encodeURIComponent(String(value ?? ''))));

  function normalize(value) {
    return String(value ?? '')
      .replace(/\\\\(?=[()[\]])/g, '\\')
      .replace(DOUBLE_COMMAND_RE, '\\');
  }

  function fallback(value) {
    let text = normalize(value).trim();
    let previous = null;

    while (previous !== text) {
      previous = text;
      text = text.replace(/\\(?:frac|dfrac|tfrac)\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, '($1)/($2)');
    }

    text = text
      .replace(/\\sqrt\s*\[([^\]]+)\]\s*\{([^{}]+)\}/g, 'root[$1]($2)')
      .replace(/\\sqrt\s*\{([^{}]+)\}/g, '√($1)');

    previous = null;
    while (previous !== text) {
      previous = text;
      text = text.replace(/\\(?:text|textrm|mathrm|mathbf|mathit|mathsf|mathtt|operatorname|overline|underline|vec|hat|bar|boxed)\s*\{([^{}]*)\}/g, '$1');
    }

    const symbols = {
      times:'×', cdot:'·', div:':', pm:'±', mp:'∓', le:'≤', leq:'≤', ge:'≥', geq:'≥', ne:'≠', neq:'≠',
      approx:'≈', equiv:'≡', sim:'∼', simeq:'≃', propto:'∝', in:'∈', notin:'∉', ni:'∋', subset:'⊂', subseteq:'⊆',
      supset:'⊃', supseteq:'⊇', cap:'∩', cup:'∪', setminus:'∖', emptyset:'∅', forall:'∀', exists:'∃', nabla:'∇', partial:'∂',
      sum:'∑', prod:'∏', int:'∫', iint:'∬', iiint:'∭', oint:'∮', Rightarrow:'⇒', Leftarrow:'⇐', Leftrightarrow:'⇔',
      rightarrow:'→', leftarrow:'←', to:'→', mapsto:'↦', implies:'⇒', iff:'⇔', pi:'π', infty:'∞', alpha:'α', beta:'β', gamma:'γ',
      delta:'δ', epsilon:'ε', varepsilon:'ϵ', zeta:'ζ', eta:'η', theta:'θ', vartheta:'ϑ', iota:'ι', kappa:'κ', lambda:'λ', mu:'μ',
      nu:'ν', xi:'ξ', rho:'ρ', sigma:'σ', tau:'τ', upsilon:'υ', phi:'φ', varphi:'ϕ', chi:'χ', psi:'ψ', omega:'ω', Gamma:'Γ',
      Delta:'Δ', Theta:'Θ', Lambda:'Λ', Xi:'Ξ', Pi:'Π', Sigma:'Σ', Phi:'Φ', Psi:'Ψ', Omega:'Ω', ldots:'…', cdots:'⋯', vdots:'⋮', ddots:'⋱'
    };

    text = text.replace(/\\[,;:]/g, ' ').replace(/\\!/g, '');
    text = text.replace(/\\([A-Za-z]+)\*?/g, (all, name) => {
      if (Object.prototype.hasOwnProperty.call(symbols, name)) return symbols[name];
      if (/^(sin|cos|tan|tg|cot|ctg|log|ln|lg|exp|lim|min|max)$/.test(name)) return name;
      if (/^(quad|qquad|left|right)$/.test(name)) return ' ';
      if (/^(begin|end)$/.test(name)) return '';
      return '';
    });

    const supers = '⁰¹²³⁴⁵⁶⁷⁸⁹';
    const subs = '₀₁₂₃₄₅₆₇₈₉';
    text = text
      .replace(/\\\\/g, '\n')
      .replace(/\\[\[\]()]/g, '')
      .replace(/\^\{([0-9])\}/g, (_, n) => supers[Number(n)])
      .replace(/_\{([0-9])\}/g, (_, n) => subs[Number(n)])
      .replace(/\^([0-9])/g, (_, n) => supers[Number(n)])
      .replace(/_([0-9])/g, (_, n) => subs[Number(n)])
      .replace(/[{}]/g, '')
      .replace(/[ \t]{2,}/g, ' ');
    return text.trim();
  }

  function hasBareLatex(line) {
    if (COMMAND_RE.test(line)) return true;
    if (WINDOWS_PATH_RE.test(line) && !/[{}^_$]/.test(line)) return false;
    return /\\[A-Za-z]+\*?\s*(?:\{|_|\^)/.test(line) || /\\(?:begin|end)\s*\{/.test(line) || /\\[,;:!]/.test(line);
  }

  function renderRichContent(value) {
    const protectedParts = [];
    const protect = html => {
      const token = `@@EDUAI_UNIFIED_${protectedParts.length}@@`;
      protectedParts.push(html);
      return token;
    };

    let text = normalize(value);

    // Programming code is content, not mathematics. Keep it verbatim and safe.
    text = text.replace(/```([\s\S]*?)```/g, (_, code) =>
      protect(`<pre class="eduai-code"><code>${EduAI.escapeHtml(code.replace(/^\n|\n$/g, ''))}</code></pre>`)
    );
    text = text.replace(/`([^`]+)`/g, (_, code) =>
      protect(`<code class="rounded bg-black/20 px-1">${EduAI.escapeHtml(code)}</code>`)
    );

    // Canonical and common legacy math delimiters render through the shared KaTeX renderer.
    text = text.replace(/\\\[([\s\S]+?)\\\]|\$\$([\s\S]+?)\$\$/g, (_, a, b) =>
      protect(`<span class="math-display" data-eduai-math="${encodeMath(a || b || '')}" data-display="1"></span>`)
    );
    text = text.replace(/\\\(([\s\S]+?)\\\)/g, (_, expr) =>
      protect(`<span class="math-inline" data-eduai-math="${encodeMath(expr)}" data-display="0"></span>`)
    );
    text = text.replace(/(?<!\$)\$([^$\n]{1,2000})\$(?!\$)/g, (_, expr) =>
      protect(`<span class="math-inline" data-eduai-math="${encodeMath(expr)}" data-display="0"></span>`)
    );

    // Malformed/legacy bare TeX must never be exposed. Explicitly delimited math
    // above remains beautiful KaTeX; bare commands use a readable Unicode fallback.
    text = text.split('\n').map(line => hasBareLatex(line) ? fallback(line) : line).join('\n');

    let safe = EduAI.escapeHtml(text)
      .replace(/^### (.+)$/gm, '<strong class="block text-base mt-2">$1</strong>')
      .replace(/^## (.+)$/gm, '<strong class="block text-lg mt-2">$1</strong>')
      .replace(/^# (.+)$/gm, '<strong class="block text-xl mt-2">$1</strong>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/^[-•] (.+)$/gm, '<span class="block pl-3">• $1</span>')
      .replace(/\n/g, '<br>');

    protectedParts.forEach((html, index) => {
      safe = safe.replace(`@@EDUAI_UNIFIED_${index}@@`, html);
    });

    queueMicrotask(() => previousRenderMath?.(document));
    return `<div class="rich-content">${safe}</div>`;
  }

  EduAI.renderRichContent = renderRichContent;
  EduAI.markdown = renderRichContent;
  EduAI.latexFallback = fallback;
  EduAI.MATH_RENDERER_VERSION = '20260816-unified-2';
})();
/* === /EduAI unified rich math rendering === */
