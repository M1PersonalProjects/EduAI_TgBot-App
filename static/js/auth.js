document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('browser-login');
  const input = document.getElementById('telegram-id');
  const submit = form.querySelector('button[type="submit"]');
  const telegramBlock = document.getElementById('telegram-progress');
  const telegramEntry = document.getElementById('telegram-entry');
  const telegramButton = document.getElementById('telegram-login');
  const standardBlock = document.getElementById('standard-auth');
  const missingBlock = document.getElementById('not-registered');

  function route(user) { location.replace(EduAI.ROLE_PATH[user.role] || '/auth.html'); }
  function persist(data, source) {
    const telegramPhotoUrl = window.Telegram?.WebApp?.initDataUnsafe?.user?.photo_url || data.telegram_photo_url || '';
    EduAI.saveSession({ token: data.session_token, source, telegram_photo_url: telegramPhotoUrl, user: { tg_id: data.tg_id, username: data.username, role: data.role } });
    route(data);
  }
  async function telegramLogin(initData) {
    if (!initData) {
      EduAI.toast('Откройте эту страницу кнопкой Web App внутри Telegram', 'error');
      return;
    }
    telegramEntry.hidden = true; telegramBlock.hidden = false; standardBlock.hidden = true;
    try {
      const data = await EduAI.api('/api/v1/auth/telegram-webapp', { method: 'POST', body: JSON.stringify({ init_data_raw: initData }) });
      persist(data, 'telegram');
    } catch (error) {
      telegramEntry.hidden = false; telegramBlock.hidden = true; standardBlock.hidden = false;
      EduAI.toast(error.message, 'error');
    }
  }

  form.addEventListener('submit', async event => {
    event.preventDefault(); missingBlock.hidden = true;
    const tgId = Number(input.value);
    if (!Number.isSafeInteger(tgId) || tgId <= 0) { EduAI.toast('Введите корректный Telegram ID', 'error'); return; }
    EduAI.setBusy(submit, true, 'Проверяем…');
    try {
      const data = await EduAI.api('/api/v1/auth/browser-login', { method: 'POST', body: JSON.stringify({ tg_id: tgId }) });
      persist(data, 'browser');
    } catch (error) {
      if (error.status === 404) { form.hidden = true; missingBlock.hidden = false; }
      else EduAI.toast(error.message, 'error');
    } finally { EduAI.setBusy(submit, false); }
  });

  const telegram = window.Telegram?.WebApp;
  if (telegram) {
    telegram.ready();
    telegram.expand();
  }
  telegramButton.addEventListener('click', () => telegramLogin(telegram?.initData || ''));

  const current = EduAI.readSession();
  if (current?.token) {
    EduAI.api('/api/v1/auth/session').then(route).catch(() => {});
    return;
  }
  if (telegram?.initData) telegramLogin(telegram.initData);
});
