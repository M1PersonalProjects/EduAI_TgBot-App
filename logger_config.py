import logging
import sys
from logging.handlers import RotatingFileHandler

# 1. Единый формат для всех компонентов проекта
log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
date_format = "%Y-%m-%d %H:%M:%S"
formatter = logging.Formatter(log_format, date_format)

# 2. Создаем хендлер для циклической записи в файл (макс. 5 МБ, храним 2 бэкапа)
file_handler = RotatingFileHandler(
    "app.log", 
    maxBytes=5242880, 
    backupCount=2, 
    encoding="utf-8"
)
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.INFO)

# 3. Создаем хендлер для вывода в стандартный поток терминала
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
console_handler.setLevel(logging.INFO)

# 4. Настраиваем КОРНЕВОЙ (root) логер, который перехватывает всё в системе
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Защита от дублирования хендлеров при повторных импортах
if not root_logger.handlers:
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

# 5. Создаем именной логер для твоего собственного кода приложения
logger = logging.getLogger("EduAI")

logging.getLogger("aiogram").setLevel(logging.INFO)
logging.getLogger("uvicorn").setLevel(logging.INFO)
logging.getLogger("openai").setLevel(logging.WARNING)