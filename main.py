import asyncio
import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler

os.makedirs("logs", exist_ok=True)

_file_handler = RotatingFileHandler(
    "logs/app.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
_error_handler = RotatingFileHandler(
    "logs/errors.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
_error_handler.setLevel(logging.ERROR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        _file_handler,
        _error_handler,
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)


async def heartbeat() -> None:
    while True:
        try:
            with open("logs/heartbeat", "w", encoding="utf-8") as f:
                f.write(datetime.now().isoformat())
        except Exception:
            pass
        await asyncio.sleep(60)


async def main() -> None:
    from database import init_db, load_product_config
    from userbot import run_userbot
    from bot import run_bot
    from scheduler import run_scheduler

    await init_db()
    logger.info("БД инициализирована")

    config = await load_product_config()
    if not config:
        logger.info("Продукт не настроен — запустите бот и используйте /start")
    else:
        logger.info("Конфиг загружен: %s", str(config.get("product_description", ""))[:80])

    await asyncio.gather(
        run_userbot(),
        run_bot(),
        run_scheduler(),
        heartbeat(),
    )


if __name__ == "__main__":
    asyncio.run(main())
