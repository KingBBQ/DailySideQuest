import logging
import os

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from database import Database
from scheduler import setup_scheduler
from handlers.group import start, hilfe
from handlers.quest import (
    add_quest,
    mark_done,
    nachholen,
    nachholen_callback,
    propose,
    show_quest,
)
from handlers.stats import show_stats

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(application: Application):
    db = Database("/data/quests.db")
    await db.init()
    application.bot_data["db"] = db
    setup_scheduler(application)
    logger.info("Bot bereit")


def main():
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN ist nicht gesetzt")

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("quest", show_quest))
    app.add_handler(CommandHandler("done", mark_done))
    app.add_handler(CommandHandler("propose", propose))
    app.add_handler(CommandHandler("stats", show_stats))
    app.add_handler(CommandHandler("addquest", add_quest))
    app.add_handler(CommandHandler("nachholen", nachholen))
    app.add_handler(CommandHandler("hilfe", hilfe))

    # Foto mit /done als Bildunterschrift
    app.add_handler(
        MessageHandler(filters.PHOTO & filters.CaptionRegex(r"^/done"), mark_done)
    )

    # Klicks auf die Nachhol-Buttons
    app.add_handler(CallbackQueryHandler(nachholen_callback, pattern=r"^nachholen:"))

    logger.info("Bot startet...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
