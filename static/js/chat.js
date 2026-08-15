(function () {
  class ChatUI {
    constructor(options) {
      this.options = options;
      this.state = { sessions: [], activeId: null, editingInteractiveId: null, interactiveAction: null };
      this.$ = name => document.getElementById(options[name]);
      this.layout = null;
      this.jumpButton = null;
    }

    async init() {
      this.bind();
      await Promise.all([this.loadSessions(), this.loadClasses()]);
    }

    bind() {
      this.$('newChatId').addEventListener('click', () => this.newChat());
      this.$('threadsId').addEventListener('click', event => this.threadAction(event));
      this.$('formId').addEventListener('submit', event => this.send(event));
      this.$('logId').addEventListener('click', event => this.messageAction(event));
      this.$('logId').addEventListener('scroll', () => this.updateJumpButton(), { passive: true });
      this.installChatChrome();
      this.$('inputId').addEventListener('input', () => this.resizeComposer());
      this.$('inputId').addEventListener('keydown', event => {
        if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
          event.preventDefault();
          const form = this.$('formId');
          if (typeof form.requestSubmit === 'function') form.requestSubmit();
          else form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
        }
      });
      this.$('attachId').addEventListener('change', () => this.previewAttachment());
      this.$('removeAttachId').addEventListener('click', () => this.clearAttachment());
      this.bindPlusMenu();
      this.$('classId').addEventListener('change', () => this.loadSubjects());
      this.$('subjectId').addEventListener('change', () => this.loadBooks());
      this.$('bookId').addEventListener('change', () => this.loadPages());
      this.$('lockId').addEventListener('click', () => this.lockContext());
      this.$('exitId').addEventListener('click', () => this.exitContext());
    }

    installChatChrome() {
      const section = this.$('formId')?.closest('.page-section');
      this.layout = section?.querySelector('[data-chat-layout]') || null;
      this.jumpButton = section?.querySelector('[data-chat-jump-bottom]') || null;
      this.jumpButton?.addEventListener('click', () => this.scrollToBottom('smooth'));
      this.layout?.querySelectorAll('[data-chat-sidebar-toggle]').forEach(button => {
        button.addEventListener('click', () => this.toggleThreadsPanel());
      });
      this.layout?.querySelector('[data-chat-sidebar-backdrop]')?.addEventListener('click', () => this.closeThreadsDrawer());
      window.addEventListener('resize', () => {
        this.closeThreadsDrawer();
        this.updateSidebarButtons();
        this.resizeComposer();
      }, { passive: true });
      this.updateSidebarButtons();
      this.resizeComposer();
      queueMicrotask(() => this.updateJumpButton());
    }

    isThreadsDrawerMode() {
      return window.matchMedia('(max-width: 1279px)').matches;
    }

    toggleThreadsPanel() {
      if (!this.layout) return;
      if (this.isThreadsDrawerMode()) {
        this.layout.classList.toggle('threads-drawer-open');
      } else {
        this.layout.classList.toggle('threads-collapsed');
      }
      this.updateSidebarButtons();
    }

    closeThreadsDrawer() {
      if (!this.layout) return;
      this.layout.classList.remove('threads-drawer-open');
      this.updateSidebarButtons();
    }

    updateSidebarButtons() {
      if (!this.layout) return;
      const drawer = this.isThreadsDrawerMode();
      const open = drawer
        ? this.layout.classList.contains('threads-drawer-open')
        : !this.layout.classList.contains('threads-collapsed');
      this.layout.querySelectorAll('[data-chat-sidebar-toggle]').forEach(button => {
        button.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
    }

    isNearBottom(threshold = 72) {
      const log = this.$('logId');
      if (!log) return true;
      return (log.scrollHeight - log.scrollTop - log.clientHeight) <= threshold;
    }

    scrollToBottom(behavior = 'smooth') {
      const log = this.$('logId');
      if (!log) return;
      if (typeof log.scrollTo === 'function') log.scrollTo({ top: log.scrollHeight, behavior });
      else log.scrollTop = log.scrollHeight;
      if (this.jumpButton) this.jumpButton.hidden = true;
    }

    updateJumpButton() {
      if (!this.jumpButton) return;
      this.jumpButton.hidden = this.isNearBottom();
    }

    resizeComposer() {
      const input = this.$('inputId');
      if (!input) return;
      input.style.height = 'auto';
      const maxHeight = window.matchMedia('(max-width: 639px)').matches ? 128 : 160;
      input.style.height = `${Math.min(Math.max(input.scrollHeight, 48), maxHeight)}px`;
      input.style.overflowY = input.scrollHeight > maxHeight ? 'auto' : 'hidden';
    }

    bindPlusMenu() {
      const form = this.$('formId');
      if (!form) return;
      const wrap = form.querySelector('.chat-plus-wrap');
      const plus = form.querySelector('[data-chat-plus]');
      const menu = form.querySelector('[data-chat-plus-menu]');
      const attachTrigger = form.querySelector('[data-chat-attach-trigger]');
      const interactiveTrigger = form.querySelector('[data-chat-interactive-trigger]');
      const modePreview = form.parentElement?.querySelector('[data-chat-compose-mode]');
      const modeClear = modePreview?.querySelector('[data-chat-compose-mode-clear]');

      const closeMenu = () => {
        if (!menu || !plus) return;
        menu.hidden = true;
        plus.setAttribute('aria-expanded', 'false');
      };
      const toggleMenu = () => {
        if (!menu || !plus) return;
        menu.hidden = !menu.hidden;
        plus.setAttribute('aria-expanded', menu.hidden ? 'false' : 'true');
      };

      plus?.addEventListener('click', event => { event.stopPropagation(); toggleMenu(); });
      attachTrigger?.addEventListener('click', () => { closeMenu(); this.$('attachId').click(); });
      interactiveTrigger?.addEventListener('click', () => {
        closeMenu();
        this.startInteractiveCompose('create');
      });
      modeClear?.addEventListener('click', () => this.clearInteractiveCompose());
      document.addEventListener('click', event => {
        if (wrap && !wrap.contains(event.target)) closeMenu();
      });
      document.addEventListener('keydown', event => {
        if (event.key === 'Escape') closeMenu();
      });
    }

    interactiveActionInput() {
      return this.$('formId')?.querySelector('[data-chat-interactive-action]') || null;
    }

    startInteractiveCompose(action = 'create', appId = null) {
      this.state.interactiveAction = action;
      this.state.editingInteractiveId = appId || null;
      const hidden = this.interactiveActionInput();
      if (hidden) hidden.value = action;
      const preview = this.$('formId')?.parentElement?.querySelector('[data-chat-compose-mode]');
      const label = preview?.querySelector('[data-chat-compose-mode-label]');
      if (preview) preview.hidden = false;
      if (label) label.textContent = action === 'edit' ? '🧩 Редактирование интерактивного приложения' : '🧩 Создание интерактивного приложения';
      const input = this.$('inputId');
      if (input) {
        if (!input.dataset.defaultPlaceholder) input.dataset.defaultPlaceholder = input.placeholder || '';
        input.placeholder = action === 'edit'
          ? 'Опишите, что изменить: добавить вопросы, таймер, оформление…'
          : 'Опишите приложение: тема, количество вопросов, сложность, оформление…';
        input.focus();
      }
    }

    clearInteractiveCompose() {
      this.state.interactiveAction = null;
      this.state.editingInteractiveId = null;
      const hidden = this.interactiveActionInput();
      if (hidden) hidden.value = '';
      const preview = this.$('formId')?.parentElement?.querySelector('[data-chat-compose-mode]');
      if (preview) preview.hidden = true;
      const input = this.$('inputId');
      if (input?.dataset.defaultPlaceholder) input.placeholder = input.dataset.defaultPlaceholder;
    }

    async loadSessions(preferredId = null, { loadMessages = true } = {}) {
      try {
        this.state.sessions = await EduAI.api('/api/v1/tutor/sessions');
        const available = this.state.sessions.some(item => String(item.session_id) === String(preferredId || this.state.activeId));
        this.state.activeId = available ? String(preferredId || this.state.activeId) : String(this.state.sessions[0]?.session_id || '');
        this.renderThreads();
        if (this.state.activeId && loadMessages) await this.loadMessages();
      } catch (error) { EduAI.toast(error.message, 'error'); }
    }

    renderThreads() {
      this.$('threadsId').innerHTML = this.state.sessions.map(item => {
        const id = String(item.session_id);
        const active = id === this.state.activeId;
        const telegramDefault = item.chat_type === 'telegram_default';
        const context = item.context_locked
          ? `${item.book_title || 'Book Mode'}${item.page_number ? ', стр. ' + item.page_number : ''}`
          : item.active_context_mode === 'attachment'
            ? 'Файловый контекст'
            : `${item.message_count} сообщ.`;
        const meta = telegramDefault ? `Telegram · ${context}` : context;
        const deleteButton = telegramDefault
          ? ''
          : '<button type="button" data-delete>Удалить чат</button>';
        return `<div class="thread-item ${active ? 'active' : ''}" data-session="${id}">
          <button class="thread-open" title="${EduAI.escapeHtml(item.title)}">
            <strong>${EduAI.escapeHtml(item.title)}</strong>
            <small>${EduAI.escapeHtml(meta)}</small>
          </button>
          <details class="thread-menu">
            <summary class="thread-menu-toggle" title="Действия с чатом" aria-label="Действия с чатом">⋮</summary>
            <div class="thread-menu-panel">
              <button type="button" data-rename>Переименовать</button>
              ${deleteButton}
            </div>
          </details>
        </div>`;
      }).join('');
      const session = this.state.sessions.find(item => String(item.session_id) === this.state.activeId);
      this.renderContextState(session);
    }

    async threadAction(event) {
      const item = event.target.closest('.thread-item'); if (!item) return;
      const menu = event.target.closest('.thread-menu');
      if (menu && !event.target.closest('[data-delete], [data-rename]')) return;
      if (event.target.closest('[data-delete]')) {
        const current = this.state.sessions.find(x => String(x.session_id) === item.dataset.session);
        if (!confirm(`Удалить чат «${current?.title || 'Новый чат'}» и всю его историю?`)) return;
        try {
          await EduAI.api(`/api/v1/tutor/sessions/${item.dataset.session}`, { method: 'DELETE' });
          if (String(this.state.activeId) === String(item.dataset.session)) this.state.activeId = null;
          await this.loadSessions();
          EduAI.toast('Чат удалён', 'success');
        } catch (error) { EduAI.toast(error.message, 'error'); }
        return;
      }
      if (event.target.closest('[data-rename]')) {
        const current = this.state.sessions.find(x => String(x.session_id) === item.dataset.session);
        const title = prompt('Название чата (до 35 символов):', current?.title || '');
        if (title === null) return;
        const clean = title.trim();
        if (!clean || clean.length > 35) { EduAI.toast('Название должно содержать от 1 до 35 символов', 'error'); return; }
        try { await EduAI.api(`/api/v1/tutor/sessions/${item.dataset.session}`, { method: 'PATCH', body: JSON.stringify({ title: clean }) }); await this.loadSessions(item.dataset.session); }
        catch (error) { EduAI.toast(error.message, 'error'); }
        return;
      }
      this.state.activeId = item.dataset.session; this.renderThreads(); this.closeThreadsDrawer(); await this.loadMessages();
    }

    async newChat() {
      try { const session = await EduAI.api('/api/v1/tutor/sessions', { method: 'POST', body: JSON.stringify({ title: 'Новый чат' }) }); await this.loadSessions(String(session.session_id)); this.closeThreadsDrawer(); this.$('inputId').focus(); }
      catch (error) { EduAI.toast(error.message, 'error'); }
    }

    formatBytes(value) {
      const bytes = Number(value || 0);
      if (!bytes) return '';
      if (bytes < 1024) return `${bytes} Б`;
      if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} КБ`;
      return `${(bytes / 1048576).toFixed(1)} МБ`;
    }

    attachmentHtml(attachment) {
      const name = attachment.original_name || attachment.name || 'Вложение';
      const meta = [attachment.mime_type || attachment.type, this.formatBytes(attachment.size_bytes || attachment.size)].filter(Boolean).join(' · ');
      if (!attachment.download_url && !attachment.preview_url) {
        return `<div class="mt-2 rounded-xl bg-white/[.05] px-3 py-2 text-xs"><strong>📎 ${EduAI.escapeHtml(name)}</strong>${meta ? `<span class="ml-2 muted">${EduAI.escapeHtml(meta)}</span>` : ''}</div>`;
      }
      return `<div class="mt-2 flex flex-wrap items-center gap-2 rounded-xl bg-white/[.05] px-3 py-2 text-xs">
        <span class="min-w-0 flex-1"><strong class="break-all">📎 ${EduAI.escapeHtml(name)}</strong>${meta ? `<span class="ml-2 muted">${EduAI.escapeHtml(meta)}</span>` : ''}</span>
        ${attachment.preview_url ? `<button type="button" class="attachment-action" data-chat-attachment="preview" data-url="${EduAI.escapeHtml(attachment.preview_url)}" data-name="${EduAI.escapeHtml(name)}">Просмотр</button>` : ''}
        ${attachment.download_url ? `<button type="button" class="attachment-action" data-chat-attachment="download" data-url="${EduAI.escapeHtml(attachment.download_url)}" data-name="${EduAI.escapeHtml(name)}">Скачать</button>` : ''}
      </div>`;
    }

    append(sender, text, attachments = [], source = null, interactiveApp = null, options = {}) {
      if (typeof attachments === 'string') attachments = attachments ? [{ original_name: attachments }] : [];
      const follow = options.forceScroll === true || (options.forceScroll !== false && this.isNearBottom());
      const bubble = document.createElement('div');
      bubble.className = `message ${sender === 'user' ? 'user' : ''}`;
      const sourceBadge = source === 'telegram' ? '<div class="mb-1 text-[.65rem] muted">📱 Telegram</div>' : '';
      bubble.innerHTML = `${sourceBadge}${EduAI.markdown(text)}${(attachments || []).map(item => this.attachmentHtml(item)).join('')}${this.interactiveCardHtml(interactiveApp)}`;
      this.$('logId').append(bubble);
      EduAI.renderMath?.(bubble);
      if (follow) this.scrollToBottom(options.behavior || 'smooth');
      else this.updateJumpButton();
      return bubble;
    }

    async loadMessages() {
      try {
        const messages = await EduAI.api(`/api/v1/tutor/sessions/${this.state.activeId}/messages`);
        this.$('logId').innerHTML = '';
        if (!messages.length) {
          this.append('ai', this.options.welcome, [], null, null, { forceScroll: false });
        } else {
          messages.forEach(item => this.append(
            item.sender,
            item.message_text,
            item.attachments?.length ? item.attachments : (item.attachment_name || ''),
            item.message_source,
            item.interactive_app || null,
            { forceScroll: false, behavior: 'auto' }
          ));
        }
        requestAnimationFrame(() => this.scrollToBottom('auto'));
      } catch (error) { EduAI.toast(error.message, 'error'); }
    }

    async fetchProtected(url) {
      const session = EduAI.readSession?.();
      const headers = new Headers();
      if (session?.token) headers.set('Authorization', `Bearer ${session.token}`);
      const response = await fetch(url, { headers });
      if (!response.ok) {
        let message = `Ошибка ${response.status}`;
        try { const body = await response.json(); message = body.detail || body.message || message; } catch (_) {}
        throw new Error(message);
      }
      return response.blob();
    }


    interactiveCardHtml(app) {
      if (!app?.app_id) return '';
      const session = EduAI.readSession?.();
      const canAssign = ['parent', 'admin'].includes(session?.user?.role);
      return `<div class="interactive-chat-card mt-3" data-interactive-app="${EduAI.escapeHtml(app.app_id)}">
        <div class="interactive-card-head min-w-0">
          <strong class="interactive-card-title">🧩 ${EduAI.markdown(app.title || 'Интерактивное задание')}</strong>
          <div class="text-xs muted">v${Number(app.current_version || 1)}${app.question_count ? ` · ${Number(app.question_count)} вопросов` : ''}</div>
        </div>
        <div class="interactive-card-actions">
          <button type="button" class="interactive-card-action" data-interactive-open>Открыть</button>
          <button type="button" class="interactive-card-action" data-interactive-edit>Изменить</button>
          <button type="button" class="interactive-card-action" data-interactive-download>Скачать HTML</button>
          ${canAssign ? '<button type="button" class="interactive-card-action" data-interactive-assign>Отправить Ученику</button>' : ''}
        </div>
      </div>`;
    }

    async messageAction(event) {
      const card = event.target.closest('[data-interactive-app]');
      if (card) {
        const appId = card.dataset.interactiveApp;
        if (event.target.closest('[data-interactive-open]')) {
          window.open(`/interactive/${encodeURIComponent(appId)}`, '_blank', 'noopener,noreferrer'); return;
        }
        if (event.target.closest('[data-interactive-edit]')) {
          this.startInteractiveCompose('edit', appId);
          this.$('inputId').value = '';
          EduAI.toast('Опишите изменение и отправьте сообщение', 'success'); return;
        }
        if (event.target.closest('[data-interactive-download]')) {
          try {
            const blob = await this.fetchProtected(`/api/v1/interactive/${encodeURIComponent(appId)}/download`);
            const url = URL.createObjectURL(blob); const link = document.createElement('a');
            link.href = url; link.download = 'interactive.html'; document.body.appendChild(link); link.click(); link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          } catch (error) { EduAI.toast(error.message, 'error'); }
          return;
        }
        if (event.target.closest('[data-interactive-assign]')) { await this.assignInteractive(appId); return; }
      }
      await this.attachmentAction(event);
    }
    async assignInteractive(appId) {
      try {
        const students = await EduAI.api('/api/v1/interactive/students');
        if (!students.length) { EduAI.toast('Нет привязанных Учеников', 'error'); return; }
        const menu = students.map((item, index) => `${index + 1}. ${item.username ? '@' + item.username : 'ID ' + item.tg_id}`).join('\n');
        const choice = prompt(`Выберите Ученика:\n${menu}\n\nВведите номер:`);
        if (choice === null) return;
        const student = students[Number(choice) - 1];
        if (!student) { EduAI.toast('Некорректный выбор Ученика', 'error'); return; }
        await EduAI.api(`/api/v1/interactive/${encodeURIComponent(appId)}/assign`, {
          method: 'POST', body: JSON.stringify({ student_ids: [student.tg_id] })
        });
        EduAI.toast('Интерактивное задание назначено Ученику', 'success');
      } catch (error) { EduAI.toast(error.message, 'error'); }
    }
    async attachmentAction(event) {
      const button = event.target.closest('[data-chat-attachment]');
      if (!button) return;
      try {
        const blob = await this.fetchProtected(button.dataset.url);
        const objectUrl = URL.createObjectURL(blob);
        if (button.dataset.chatAttachment === 'preview') {
          window.open(objectUrl, '_blank', 'noopener,noreferrer');
          setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
        } else {
          const link = document.createElement('a');
          link.href = objectUrl; link.download = button.dataset.name || 'attachment';
          document.body.appendChild(link); link.click(); link.remove();
          setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
        }
      } catch (error) { EduAI.toast(error.message, 'error'); }
    }

    async send(event) {
      event.preventDefault();
      const button = event.submitter || this.$('formId').querySelector('button[type="submit"], button:not([type])');
      let stopThinking = () => {};
      const input = this.$('inputId');
      const originalText = input.value;
      const text = originalText.trim().split('$').join('');
      const file = this.$('attachId').files[0];
      const interactiveAction = this.interactiveActionInput()?.value || this.state.interactiveAction || '';
      try {
        if (!this.state.activeId) await this.loadSessions();
        if (!this.state.activeId) throw new Error('Не удалось создать чат. Обновите страницу.');
        if (!text && !file) {
          if (interactiveAction) EduAI.toast('Сначала опишите, какое интерактивное приложение нужно создать или изменить', 'error');
          return;
        }
        const isPdf = file && (file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf'));
        const sizeLimit = isPdf ? 100 * 1024 * 1024 : 15 * 1024 * 1024;
        if (file && file.size > sizeLimit) throw new Error(`Максимальный размер ${isPdf ? 'PDF' : 'файла'} — ${isPdf ? 100 : 15} МБ`);
        this.append('user', text || 'Проанализируй вложение', file ? [{ original_name: file.name, mime_type: file.type, size_bytes: file.size }] : [], null, null, { forceScroll: true });
        const form = new FormData();
        form.append('session_id', this.state.activeId);
        form.append('message_text', text);
        if (interactiveAction) form.append('interactive_action', interactiveAction);
        if (this.state.editingInteractiveId) form.append('interactive_app_id', this.state.editingInteractiveId);
        if (file) form.append('attachment', file);
        const mapping = [['classId','book_class'],['subjectId','book_program'],['bookId','book_id'],['pageId','page_id']];
        mapping.forEach(([id,key]) => { const element = this.$(id); if (element && element.value) form.append(key, element.value); });
        EduAI.setBusy(button, true, interactiveAction ? 'Создаём…' : 'Отправляем…');
        stopThinking = EduAI.startThinking(
          interactiveAction === 'edit' ? 'ИИ изменяет интерактивное приложение' :
          interactiveAction === 'create' ? 'ИИ создаёт интерактивное приложение' :
          file ? 'ИИ обрабатывает вложение' : 'ИИ формулирует ответ'
        );
        const result = await EduAI.api('/api/v1/tutor/messages', { method: 'POST', body: form });
        this.append('ai', result.message_text, [], null, result.interactive_app || null);
        if (!result.interactive_error) {
          input.value = '';
          this.resizeComposer();
          this.clearAttachment();
          this.clearInteractiveCompose();
        } else {
          input.value = originalText;
          this.resizeComposer();
          EduAI.toast('Интерактивное приложение не создано. Запрос оставлен в поле — можно повторить.', 'error');
        }
        this.resizeComposer();
        await this.loadSessions(result.session_id, { loadMessages: false });
      } catch (error) {
        console.error('EduAI tutor submit failed', error);
        input.value = originalText;
        this.resizeComposer();
        EduAI.toast(error.message || 'Не удалось отправить сообщение', 'error');
      } finally { stopThinking(); EduAI.setBusy(button, false); input.focus(); }
    }

    previewAttachment() {
      const file = this.$('attachId').files[0];
      this.$('attachmentPreviewId').hidden = !file;
      this.$('attachmentNameId').textContent = file ? `📎 ${file.name} · ${(file.size / 1048576).toFixed(1)} МБ` : '';
    }
    clearAttachment() { this.$('attachId').value = ''; this.$('attachmentPreviewId').hidden = true; }

    async loadClasses() {
      try { const values = await EduAI.api('/api/v1/tutor/context/classes'); this.$('classId').innerHTML = '<option value="">Класс (необязательно)</option>' + values.map(x => `<option value="${x}">${x} класс</option>`).join(''); }
      catch (error) { EduAI.toast(error.message, 'error'); }
    }
    async loadSubjects() {
      this.resetSelect('subjectId', 'Предмет (необязательно)'); this.resetSelect('bookId', 'Учебник (необязательно)'); this.resetSelect('pageId', 'Страница / параграф');
      if (!this.$('classId').value) return;
      const values = await EduAI.api(`/api/v1/tutor/context/subjects?book_class=${this.$('classId').value}`);
      this.$('subjectId').innerHTML += values.map(x => `<option value="${EduAI.escapeHtml(x)}">${EduAI.escapeHtml(x)}</option>`).join('');
    }
    async loadBooks() {
      this.resetSelect('bookId', 'Учебник (необязательно)'); this.resetSelect('pageId', 'Страница / параграф');
      if (!this.$('subjectId').value) return;
      const query = new URLSearchParams({ book_class: this.$('classId').value, book_program: this.$('subjectId').value });
      const values = await EduAI.api(`/api/v1/tutor/context/books?${query}`);
      this.$('bookId').innerHTML += values.map(x => `<option value="${x.book_id}">${EduAI.escapeHtml(x.book_title)} · ${EduAI.escapeHtml(x.book_author)}</option>`).join('');
    }
    async loadPages() {
      this.resetSelect('pageId', 'Страница / параграф'); if (!this.$('bookId').value) return;
      const values = await EduAI.api(`/api/v1/tutor/context/pages?book_id=${this.$('bookId').value}`);
      this.$('pageId').innerHTML += values.map(x => `<option value="${x.page_id}">стр. ${x.page_number}${x.page_paragraph ? ' · ' + EduAI.escapeHtml(x.page_paragraph) : ''}</option>`).join('');
    }
    resetSelect(id, label) { this.$(id).innerHTML = `<option value="">${label}</option>`; }
    async lockContext() {
      if (!this.$('bookId').value) { EduAI.toast('Выберите учебник', 'error'); return; }
      const payload = { book_id: Number(this.$('bookId').value) };
      if (this.$('pageId').value) payload.page_id = Number(this.$('pageId').value);
      try { await EduAI.api(`/api/v1/tutor/sessions/${this.state.activeId}/context`, { method: 'PUT', body: JSON.stringify(payload) }); EduAI.toast('Book Mode включён', 'success'); await this.loadSessions(this.state.activeId); }
      catch (error) { EduAI.toast(error.message, 'error'); }
    }
    async exitContext() {
      try { await EduAI.api(`/api/v1/tutor/sessions/${this.state.activeId}/context`, { method: 'DELETE' }); EduAI.toast('Book Mode выключен', 'success'); await this.loadSessions(this.state.activeId); }
      catch (error) { EduAI.toast(error.message, 'error'); }
    }
    renderContextState(session) {
      const locked = Boolean(session?.context_locked);
      const mode = session?.active_context_mode || (locked ? 'book' : 'general');
      this.$('contextStatusId').textContent = locked ? `🔒 ${session.book_title}${session.page_number ? ', стр. ' + session.page_number : ''}` : mode === 'attachment' ? '📎 Активен файловый контекст' : 'Автопоиск по тексту вопроса';
      this.$('exitId').hidden = !locked;
    }
  }
  window.EduAIChat = ChatUI;
})();
