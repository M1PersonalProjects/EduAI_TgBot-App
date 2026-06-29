import asyncio
import sys
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from aiogram import Bot, Dispatcher
from config import settings
from database import db
from bot.handlers import start, webapp, tasks as bot_tasks, quests

from api.routers.accounts import router as accounts_router
from api.routers.books import router as books_router
from api.routers.tasks import router as tasks_router

from logger_config import logger

app = FastAPI(title="EduAI API Platform", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(accounts_router)
app.include_router(books_router)
app.include_router(tasks_router)

bot = Bot(token=settings.bot_token.get_secret_value())
dp = Dispatcher()

dp.include_router(quests.router)
dp.include_router(start.router)
dp.include_router(webapp.router)
dp.include_router(bot_tasks.router)

templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def serve_home_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

async def run_api():
    config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=8000,
        log_level="info",
        loop="asyncio"
    )
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    await db.connect()
    logger.info(" 🗄  Пул базы данных PostgreSQL успешно инициализирован.")

    asyncio.create_task(run_api())
    logger.info(" 🚀  Веб-сервер FastAPI успешно запущен на http://127.0.0.1:8000")

    try:
        logger.info(" 🤖  Бот EduAI успешно запущен и слушает серверы Telegram...")
        await dp.start_polling(bot)
    finally:
        logger.info(" 🛑  Остановка сервисов...")
        await bot.session.close()
        await db.disconnect()
        logger.info(" 🗄  Пул базы данных закрыт.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())