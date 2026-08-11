# EduAI — единое форматирование математики

Этот архив содержит готовые файлы для замены/добавления поверх проекта после исправления whole-book context.

## Что заменить
- `services/tutor.py`
- `api/routers/platform.py`
- `api/routers/tasks.py`
- `static/js/app.js`
- `bot/messages.py`
- `requirements.txt`

## Что добавить
- `services/response_formatter.py`
- `tests/test_response_formatter.py`

`services/context_resolver.py` также включён, чтобы сохранить предыдущую правку whole-book context.

## Реализовано
- каноническое хранение Markdown + LaTeX без уничтожения `\\frac`, `\\sqrt`, степеней и систем;
- английские MATHEMATICAL FORMATTING RULES для тьютора и генерации/проверки заданий;
- централизованный KaTeX renderer в `EduAI.markdown()`;
- HTML модели не исполняется: обычный контент сначала экранируется, а HTML создаётся только самим frontend/KaTeX;
- fenced/inline code защищён от математической обработки;
- `/` не заменяется глобально; URL, пути, API-маршруты и код не меняются;
- длинные формулы получают горизонтальную прокрутку;
- Telegram: простая математика остаётся текстом, сложная формула рендерится в PNG через matplotlib;
- при ошибке Telegram renderer отправляется текстовый fallback;
- порядок текста и формул сохраняется;
- отдельного `message_for_web`/`message_for_telegram` нет;
- форматирование не вызывает второй LLM-запрос.

## После замены
```bash
pip install -r requirements.txt
python -m pytest -q
python -m compileall -q api bot services tests main.py
```

KaTeX загружается WebApp централизованно из jsDelivr. Для полностью offline/CSP-strict production его лучше положить в `static/vendor/katex/` и заменить CDN URL в `static/js/app.js`.
