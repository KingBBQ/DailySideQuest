import logging
from datetime import time
import pytz
from telegram.ext import Application

logger = logging.getLogger(__name__)

BERLIN = pytz.timezone("Europe/Berlin")


def setup_scheduler(app: Application):
    jq = app.job_queue

    # Mitternacht: Quest für morgen festlegen
    jq.run_daily(
        pick_quests_midnight,
        time=time(0, 0, 0, tzinfo=BERLIN),
        name="pick_quests_midnight",
    )

    # 9 Uhr: Quest bekannt geben
    jq.run_daily(
        announce_quests_morning,
        time=time(9, 0, 0, tzinfo=BERLIN),
        name="announce_quests_morning",
    )

    logger.info("Scheduler gestartet: Mitternacht (Quest wählen) + 9 Uhr (Ankündigung)")


async def pick_quests_midnight(context):
    db = context.bot_data["db"]
    groups = await db.get_all_groups()

    for chat_id in groups:
        try:
            text = await db.pick_quest_for_tomorrow(chat_id)
            if text:
                logger.info(f"Quest für Gruppe {chat_id} gewählt: {text[:60]}...")
        except Exception:
            logger.exception(f"Fehler beim Quest-Wählen für Gruppe {chat_id}")


async def announce_quests_morning(context):
    db = context.bot_data["db"]
    bot = context.bot
    groups = await db.get_all_groups()

    for chat_id in groups:
        try:
            quest = await db.get_todays_quest(chat_id)
            if not quest:
                continue

            source = (
                "💡 Von einem Mitglied vorgeschlagen"
                if quest["proposed_by"]
                else "🎲 Automatisch ausgewählt"
            )

            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "🌅 *Guten Morgen! Eure heutige Quest:*\n\n"
                    f"🎯 _{quest['text']}_\n\n"
                    f"{source}\n\n"
                    "Mit /done markieren wenn ihr fertig seid! 💪"
                ),
                parse_mode="Markdown",
            )
        except Exception:
            logger.exception(f"Fehler beim Ankündigen für Gruppe {chat_id}")
