import asyncio
import sys
from pathlib import Path
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher
from config import settings
from database import db

from bot.handlers import start, webapp, tasks as bot_tasks, ai_chat, parent, quests

from api.routers.admin import router as admin_router
from api.routers.accounts import router as accounts_router
from api.routers.books import router as books_router
from api.routers.tasks import router as tasks_router
from api.routers.chats import router as chats_router, tutor_router as tutor_chats_router
from api.routers.rewards import router as rewards_router
from api.routers.auth import router as auth_v1_router
from api.routers.platform import router as platform_v1_router

from logger_config import logger

BASE_DIR = Path(__file__).resolve().parent

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    logger.info(" 🗄  Пул базы данных PostgreSQL успешно инициализирован.")
    yield
    await db.disconnect()
    logger.info(" 🗄  Пул базы данных закрыт.")

app = FastAPI(
    title="EduAI API Platform", 
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Монтируем статику (если в папке templates или static лежат стили/скрипты/картинки)
# Это предотвратит 404 ошибки при загрузке картинок и CSS-файлов
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(accounts_router)
app.include_router(books_router)
app.include_router(tasks_router)
app.include_router(admin_router)
app.include_router(chats_router)
app.include_router(tutor_chats_router)
app.include_router(rewards_router)
app.include_router(auth_v1_router)
app.include_router(platform_v1_router)

bot = Bot(token=settings.bot_token.get_secret_value())
dp = Dispatcher()

dp.include_router(bot_tasks.router)
dp.include_router(start.router)
dp.include_router(webapp.router)
dp.include_router(parent.router)
dp.include_router(quests.router)
dp.include_router(ai_chat.router)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ================= РОУТЫ ДЛЯ СТРАНИЦ И ИНТЕРФЕЙСОВ (HTML) =================

@app.get("/auth", response_class=HTMLResponse)
async def serve_auth_page(request: Request):
    return templates.TemplateResponse(request, "auth.html")

@app.get("/admin", response_class=HTMLResponse)
async def serve_admin_page(request: Request):
    return templates.TemplateResponse(request, "admin.html")

@app.get("/student", response_class=HTMLResponse)
async def serve_student_page(request: Request):
    return templates.TemplateResponse(request, "student.html")

@app.get("/parent", response_class=HTMLResponse)
@app.get("/parent/dashboard", response_class=HTMLResponse)
async def parent_dashboard(request: Request):
    return templates.TemplateResponse(request, "parent.html")

@app.get("/parent/create-test", response_class=HTMLResponse)
async def parent_create_test(request: Request):
    return templates.TemplateResponse(request, "parent.html")

@app.get("/parent/auth", response_class=HTMLResponse)
async def parent_auth_page(request: Request):
    return templates.TemplateResponse(request, "auth.html")

@app.get("/", response_class=HTMLResponse)
async def serve_home_page(request: Request):
    return templates.TemplateResponse(request, "auth.html")

# Дополнительный роут-предохранитель: если клиент обратится по старому пути с .html
@app.get("/auth.html", response_class=HTMLResponse)
async def serve_auth_legacy(request: Request):
    return templates.TemplateResponse(request, "auth.html")

@app.get("/parent/auth.html", response_class=HTMLResponse)
async def serve_parent_auth_legacy(request: Request):
    return templates.TemplateResponse(request, "auth.html")

@app.get("/student.html", response_class=HTMLResponse)
async def serve_student_legacy(request: Request):
    return templates.TemplateResponse(request, "student.html")

@app.get("/parent.html", response_class=HTMLResponse)
async def serve_parent_legacy(request: Request):
    return templates.TemplateResponse(request, "parent.html")

@app.get("/admin.html", response_class=HTMLResponse)
async def serve_admin_legacy(request: Request):
    return templates.TemplateResponse(request, "admin.html")


async def run_api():
    # Публичный доступ обычно предоставляет reverse proxy; приложение слушает localhost.
    config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=8000,
        log_config=None,
        loop="asyncio"
    )
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    api_task = asyncio.create_task(run_api())
    logger.info(" 🚀  Веб-сервер FastAPI успешно запущен на http://localhost:8000")

    try:
        logger.info(" 🤖  Бот EduAI успешно запущен и слушает серверы Telegram (Polling)...")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.critical(f" 💥  Критическая ошибка в работе ядра: {e}")
    finally:
        logger.info(" 🛑  Остановка сервисов бота...")
        await bot.session.close()
        api_task.cancel()
        try:
            await api_task
        except asyncio.CancelledError:
            pass
        logger.info(" 👋  Все системы EduAI успешно остановлены.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Программа завершена пользователем.")
