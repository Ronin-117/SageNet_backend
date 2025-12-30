import logging
import os
from logging.handlers import RotatingFileHandler

# Ensure logs directory exists
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

def setup_logger(name: str):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 1. Console Handler (For Docker Logs)
    c_handler = logging.StreamHandler()
    c_handler.setFormatter(formatter)
    logger.addHandler(c_handler)

    # 2. Success/Info Log File (Rotates after 5MB, keeps 3 backups)
    f_handler = RotatingFileHandler(
        f"{LOG_DIR}/application.log", maxBytes=5*1024*1024, backupCount=3
    )
    f_handler.setLevel(logging.INFO)
    f_handler.setFormatter(formatter)
    logger.addHandler(f_handler)

    # 3. Error Log File (Only captures ERROR and CRITICAL)
    e_handler = RotatingFileHandler(
        f"{LOG_DIR}/errors.log", maxBytes=5*1024*1024, backupCount=3
    )
    e_handler.setLevel(logging.ERROR)
    e_handler.setFormatter(formatter)
    logger.addHandler(e_handler)

    return logger