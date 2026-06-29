import logging
import sys
from logging.handlers import RotatingFileHandler

# Настраиваем единый формат: Дата Время [УРОВЕНЬ] Компонент: Сообщение
log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
date_format = "%Y-%m-%d %H:%M:%S"

# Создаём главный логер проекта
logger = logging.getLogger("EduAI")
logger.setLevel(logging.INFO)

# 1. Хендлер для файла app.log (автоматом чистит файл, если он больше 5 МБ)
file_handler = RotatingFileHandler("app.log", maxBytes=5242880, backupCount=2, encoding="utf-8")
file_handler.setFormatter(logging.Formatter(log_format, date_format))
file_handler.setLevel(logging.INFO)

# 2. Хендлер для вывода в консоль терминала
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter(log_format, date_format))
console_handler.setLevel(logging.INFO)

# Подключаем их к логеру
if not logger.handlers:
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)