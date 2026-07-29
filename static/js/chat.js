(function () {
  class ChatUI {
    constructor(options) {
      this.options = options;
      this.state = { sessions: [], activeId: null };
      this.$ = name => document.getElementById(options[name]);
    }

    async init() {
      this.bind();
      await Promise.all([this.loadSessions(), this.loadClasses()]);
    }

    bind() {
      this.$('newChatId').addEventListener('click', () => this.newChat());
      this.$('threadsId').addEventListener('click', event => this.threadAction(event));
      this.$('formId').addEventListener('submit', event => this.send(event));
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
      this.$('classId').addEventListener('change', () => this.loadSubjects());
      this.$('subjectId').addEventListener('change', () => this.loadBooks());
      this.$('bookId').addEventListener('change', () => this.loadPages());
      this.$('lockId').addEventListener('click', () => this.lockContext());
      this.$('exitId').addEventListener('click', () => this.exitContext());
    }

    async loadSessions(preferredId = null) {
      try {
        this.state.sessions = await EduAI.api('/api/v1/tutor/sessions');
        const available = this.state.sessions.some(item => String(item.session_id) === String(preferredId || this.state.activeId));
        this.state.activeId = available ? String(preferredId || this.state.activeId) : String(this.state.sessions[0]?.session_id || '');
        this.renderThreads();
        if (this.state.activeId) await this.loadMessages();
      } catch (error) { EduAI.toast(error.message, 'error'); }
    }

    renderThreads() {
      this.$('threadsId').innerHTML = this.state.sessions.map(item => {
        const id = String(item.session_id); const active = id === this.state.activeId;
        const context = item.context_locked ? `${item.book_title || 'Book Mode'}${item.page_number ? ', стр. ' + item.page_number : ''}` : `${item.message_count} сообщ.`;
        return `<div class="thread-item ${active ? 'active' : ''}" data-session="${id}"><button class="thread-open"><strong>${EduAI.escapeHtml(item.title)}</strong><small>${EduAI.escapeHtml(context)}</small></button><button class="thread-action" data-rename title="Переименовать">✎</button><button class="thread-action" data-delete title="Удалить чат" aria-label="Удалить чат">🗑</button></div>`;
      }).join('');
      const session = this.state.sessions.find(item => String(item.session_id) === this.state.activeId);
      this.renderContextState(session);
    }

    async threadAction(event) {
      const item = event.target.closest('.thread-item'); if (!item) return;
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
      this.state.activeId = item.dataset.session; this.renderThreads(); await this.loadMessages();
    }

    async newChat() {
      try { const session = await EduAI.api('/api/v1/tutor/sessions', { method: 'POST', body: JSON.stringify({ title: 'Новый чат' }) }); await this.loadSessions(String(session.session_id)); this.$('inputId').focus(); }
      catch (error) { EduAI.toast(error.message, 'error'); }
    }

    append(sender, text, attachmentName = '') {
      const bubble = document.createElement('div'); bubble.className = `message ${sender === 'user' ? 'user' : ''}`;
      bubble.innerHTML = `${attachmentName ? `<small class="block mb-1">📎 ${EduAI.escapeHtml(attachmentName)}</small>` : ''}${EduAI.markdown(text)}`;
      this.$('logId').append(bubble); this.$('logId').scrollTop = this.$('logId').scrollHeight; return bubble;
    }

    async loadMessages() {
      try {
        const messages = await EduAI.api(`/api/v1/tutor/sessions/${this.state.activeId}/messages`);
        this.$('logId').innerHTML = '';
        if (!messages.length) this.append('ai', this.options.welcome);
        else messages.forEach(item => this.append(item.sender, item.message_text, item.attachment_name));
      } catch (error) { EduAI.toast(error.message, 'error'); }
    }

    async send(event) {
      event.preventDefault();
      const button = event.submitter || this.$('formId').querySelector('button[type="submit"], button:not([type])');
      let stopThinking = () => {};
      try {
        if (!this.state.activeId) await this.loadSessions();
        if (!this.state.activeId) throw new Error('Не удалось создать чат. Обновите страницу.');
        const text = this.$('inputId').value.trim().split('$').join('');
        const file = this.$('attachId').files[0];
        if (!text && !file) return;
        const isPdf = file && (file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf'));
        const sizeLimit = isPdf ? 100 * 1024 * 1024 : 15 * 1024 * 1024;
        if (file && file.size > sizeLimit) throw new Error(`Максимальный размер ${isPdf ? 'PDF' : 'файла'} — ${isPdf ? 100 : 15} МБ`);

        this.append('user', text || 'Проанализируй вложение', file ? file.name : '');
        const form = new FormData();
        form.append('session_id', this.state.activeId);
        form.append('message_text', text);
        if (file) form.append('attachment', file);
        const mapping = [['classId','book_class'],['subjectId','book_program'],['bookId','book_id'],['pageId','page_id']];
        mapping.forEach(([id,key]) => {
          const element = this.$(id);
          if (element && element.value) form.append(key, element.value);
        });
        this.$('inputId').value = '';
        this.clearAttachment();
        EduAI.setBusy(button, true, 'Отправляем…');
        stopThinking = EduAI.startThinking(file ? 'ИИ обрабатывает вложение' : 'ИИ формулирует ответ');
        const result = await EduAI.api('/api/v1/tutor/messages', { method: 'POST', body: form });
        this.append('ai', result.message_text); await this.loadSessions(result.session_id);
      } catch (error) {
        console.error('EduAI tutor submit failed', error);
        EduAI.toast(error.message || 'Не удалось отправить сообщение', 'error');
      }
      finally { stopThinking(); EduAI.setBusy(button, false); this.$('inputId').focus(); }
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
      this.$('contextStatusId').textContent = locked ? `🔒 ${session.book_title}${session.page_number ? ', стр. ' + session.page_number : ''}` : 'Автопоиск по тексту вопроса';
      this.$('exitId').hidden = !locked;
    }
  }
  window.EduAIChat = ChatUI;
})();
