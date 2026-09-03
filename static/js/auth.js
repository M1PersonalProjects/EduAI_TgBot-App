document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('browser-login');
  const browserSection = document.getElementById('browser-login-section');
  const browserNote = document.getElementById('browser-login-note');
  const input = document.getElementById('telegram-id');
  const submit = form?.querySelector('button[type="submit"]');
  const telegramBlock = document.getElementById('telegram-progress');
  const telegramEntry = document.getElementById('telegram-entry');
  const telegramButton = document.getElementById('telegram-login');
  const standardBlock = document.getElementById('standard-auth');
  const missingBlock = document.getElementById('not-registered');
  const BOT_URL = 'https://t.me/EduAI_platform_bot';
  let browserLoginEnabled = true;

  function route(user) {
    location.replace(EduAI.ROLE_PATH[user.role] || '/auth.html');
  }

  function persist(data, source) {
    const telegramPhotoUrl = window.Telegram?.WebApp?.initDataUnsafe?.user?.photo_url || data.telegram_photo_url || '';
    EduAI.saveSession({
      token: data.session_token,
      source,
      telegram_photo_url: telegramPhotoUrl,
      user: { tg_id: data.tg_id, username: data.username, role: data.role },
    });
    route(data);
  }

  async function telegramLogin(initData) {
    if (!initData) {
      // В обычном мобильном/desktop-браузере сначала открываем бота.
      // После перехода в WebApp Telegram передаст подписанный initData с tg_id.
      window.location.href = BOT_URL;
      return;
    }
    telegramEntry.hidden = true;
    telegramBlock.hidden = false;
    standardBlock.hidden = true;
    try {
      const data = await EduAI.api('/api/v1/auth/telegram-webapp', {
        method: 'POST',
        body: JSON.stringify({ init_data_raw: initData }),
      });
      persist(data, 'telegram');
    } catch (error) {
      telegramEntry.hidden = false;
      telegramBlock.hidden = true;
      standardBlock.hidden = false;
      EduAI.toast(error.message, 'error');
    }
  }

  if (form && input && submit) {
    form.addEventListener('submit', async event => {
      event.preventDefault();
      missingBlock.hidden = true;

      const normalized = String(input.value || '').trim();
      if (!/^\d{1,20}$/.test(normalized)) {
        EduAI.toast('Введите корректный Telegram ID: только цифры', 'error');
        input.focus();
        return;
      }
      const tgId = Number(normalized);
      if (!Number.isSafeInteger(tgId) || tgId <= 0) {
        EduAI.toast('Введите корректный Telegram ID', 'error');
        input.focus();
        return;
      }

      const telegram = window.Telegram?.WebApp;
      const currentTelegramId = Number(telegram?.initDataUnsafe?.user?.id || 0);
      if (telegram?.initData && currentTelegramId === tgId) {
        await telegramLogin(telegram.initData);
        return;
      }

      if (browserLoginEnabled === false) {
        EduAI.toast('Вход только по Telegram ID отключён на сервере. Используйте Telegram WebApp.', 'error');
        return;
      }

      EduAI.setBusy(submit, true, 'Проверяем…');
      try {
        const data = await EduAI.api('/api/v1/auth/browser-login', {
          method: 'POST',
          body: JSON.stringify({ tg_id: tgId }),
        });
        persist(data, 'browser');
      } catch (error) {
        if (error.status === 404) {
          form.hidden = true;
          missingBlock.hidden = false;
        } else if (error.status === 403) {
          browserLoginEnabled = false;
          if (browserNote) browserNote.textContent = 'Вход только по Telegram ID отключён администратором. Используйте Telegram WebApp.';
          EduAI.toast('Вход по Telegram ID отключён. Используйте Telegram WebApp.', 'error');
        } else {
          EduAI.toast(error.message, 'error');
        }
      } finally {
        EduAI.setBusy(submit, false);
      }
    });
  }

  const telegram = window.Telegram?.WebApp;
  if (telegram) {
    telegram.ready();
    telegram.expand();
  }
  telegramButton?.addEventListener('click', () => telegramLogin(telegram?.initData || ''));

  if (browserSection) browserSection.hidden = false;
  EduAI.api('/api/v1/auth/options')
    .then(options => {
      browserLoginEnabled = options.browser_login_enabled !== false;
      if (browserNote && !browserLoginEnabled) {
        browserNote.textContent = 'Вход по ID отображается всегда, но сейчас отключён на сервере. Используйте Telegram WebApp или включите защищённый серверный сценарий входа по ID.';
      }
    })
    .catch(() => {
      browserLoginEnabled = true;
    });

  const current = EduAI.readSession();
  if (current?.token) {
    EduAI.api('/api/v1/auth/session').then(route).catch(() => {});
    return;
  }
  // Не выполняем вход автоматически при загрузке: пользователь видит оба варианта
  // и сам выбирает Telegram ID или защищённый Telegram WebApp.
});
