(function () {
  const appId = document.body.dataset.interactiveAppId;
  const frame = document.getElementById('interactive-frame');
  const loading = document.getElementById('interactive-loading');
  const title = document.getElementById('interactive-title');
  const version = document.getElementById('interactive-version');
  const resultBox = document.getElementById('interactive-result');
  const downloadButton = document.getElementById('interactive-download');
  const backButton = document.getElementById('interactive-back');
  let app = null;

  async function fetchProtectedBlob(url) {
    const session = EduAI.readSession?.();
    const headers = new Headers();
    if (session?.token) headers.set('Authorization', `Bearer ${session.token}`);
    const response = await fetch(url, { headers, credentials: 'same-origin' });
    if (!response.ok) {
      let message = `Ошибка ${response.status}`;
      try { const body = await response.json(); message = body.detail || message; } catch (_) {}
      throw new Error(message);
    }
    return response.blob();
  }

  async function load() {
    try {
      app = await EduAI.api(`/api/v1/interactive/${encodeURIComponent(appId)}`);
      title.innerHTML = EduAI.markdown(app.title || 'Интерактивное задание');
      EduAI.renderMath?.(title);
      version.textContent = `Версия v${app.current_version || 1}${app.question_count ? ` · ${app.question_count} вопросов` : ''}`;
      frame.hidden = true;
      loading.hidden = false;
      loading.textContent = 'Подготавливаем интерактивное задание…';
      const reveal = () => {
        loading.hidden = true;
        frame.hidden = false;
      };
      frame.addEventListener('load', reveal, { once: true });
      frame.srcdoc = app.html_document || '<!doctype html><p>Нет содержимого</p>';
      // Safety fallback for unusual WebView implementations that do not emit load for srcdoc.
      setTimeout(() => { if (frame.hidden) reveal(); }, 1800);
    } catch (error) {
      loading.textContent = error.message || 'Не удалось загрузить интерактивное задание';
    }
  }

  window.addEventListener('message', async event => {
    if (event.source !== frame.contentWindow) return;
    if (!event.data || event.data.type !== 'eduai-interactive-result') return;
    const payload = event.data.payload || {};
    const safe = {
      score: Number.isFinite(Number(payload.score)) ? Number(payload.score) : 0,
      max_score: Number.isFinite(Number(payload.max_score)) ? Math.max(0, Number(payload.max_score)) : 0,
      completed: Boolean(payload.completed),
      answers: payload.answers && typeof payload.answers === 'object' ? payload.answers : {}
    };
    try {
      const saved = await EduAI.api(`/api/v1/interactive/${encodeURIComponent(appId)}/result`, {
        method: 'POST', body: JSON.stringify(safe)
      });
      resultBox.hidden = false;
      resultBox.textContent = safe.max_score > 0
        ? `Результат сохранён: ${safe.score} из ${safe.max_score} (${saved.percent}%).`
        : 'Результат интерактивного задания сохранён.';
    } catch (error) {
      // Owners/Teachers can preview apps without having an assignment; this is expected.
      const session = EduAI.readSession?.();
      if (session?.user?.role === 'student') EduAI.toast(error.message, 'error');
    }
  });

  downloadButton.addEventListener('click', async () => {
    try {
      const blob = await fetchProtectedBlob(`/api/v1/interactive/${encodeURIComponent(appId)}/download`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${(app?.title || 'interactive').replace(/[^\p{L}\p{N}._-]+/gu, '_')}.html`;
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { EduAI.toast(error.message, 'error'); }
  });

  backButton.addEventListener('click', () => {
    if (history.length > 1) history.back();
    else location.href = '/';
  });

  load();
})();
