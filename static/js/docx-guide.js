document.addEventListener('DOMContentLoaded', async () => {
  const documentUrl = '/static/docs/telegram_id_guide.docx';
  const viewer = document.getElementById('doc-guide-viewer');
  const empty = document.getElementById('doc-guide-empty');
  const status = document.getElementById('doc-guide-status');
  const download = document.getElementById('doc-guide-download');

  function showUnavailable(message) {
    viewer.hidden = true;
    empty.hidden = false;
    download.hidden = true;
    status.textContent = message;
  }

  try {
    const response = await fetch(documentUrl, { cache: 'no-store', credentials: 'same-origin' });
    if (!response.ok) {
      showUnavailable('Инструкция пока не опубликована.');
      return;
    }

    const blob = await response.blob();
    if (!blob.size) {
      showUnavailable('Файл инструкции пуст.');
      return;
    }
    if (!window.docx?.renderAsync) {
      showUnavailable('Модуль просмотра документа не загрузился. Попробуйте обновить страницу.');
      return;
    }

    viewer.hidden = false;
    empty.hidden = true;
    await window.docx.renderAsync(blob, viewer, viewer, {
      inWrapper: true,
      breakPages: true,
      ignoreLastRenderedPageBreak: false,
      useBase64URL: true,
    });
    download.hidden = false;
    status.textContent = 'Документ открыт в режиме просмотра. Скачивание выполняется только по отдельной кнопке.';
  } catch (error) {
    console.error('Telegram ID guide preview failed', error);
    showUnavailable('Не удалось открыть инструкцию для просмотра. Попробуйте позже.');
  }
});
