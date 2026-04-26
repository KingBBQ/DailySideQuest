import logging
from datetime import time
import pytz
from telegram.ext import Application
from database import CATEGORY_EMOJI

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

    # Sonntag 20 Uhr: Wochenrückblick
    jq.run_daily(
        weekly_summary,
        time=time(20, 0, 0, tzinfo=BERLIN),
        days=(6,),  # 0=Montag, 6=Sonntag
        name="weekly_summary",
    )

    logger.info("Scheduler gestartet: Mitternacht + 9 Uhr + Sonntag 20 Uhr")


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

            category_line = ""
            if quest["category"]:
                emoji = CATEGORY_EMOJI.get(quest["category"], "📋")
                category_line = f"{emoji} _{quest['category']}_\n\n"

            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "🌅 *Guten Morgen! Eure heutige Quest:*\n\n"
                    f"🎯 _{quest['text']}_\n\n"
                    f"{category_line}"
                    f"{source}\n\n"
                    "Mit /done markieren wenn ihr fertig seid! 💪"
                ),
                parse_mode="Markdown",
            )
        except Exception:
            logger.exception(f"Fehler beim Ankündigen für Gruppe {chat_id}")


async def weekly_summary(context):
    db = context.bot_data["db"]
    bot = context.bot
    groups = await db.get_all_groups()

    for chat_id in groups:
        try:
            stats = await db.get_weekly_stats(chat_id)

            if not stats["completions"] and stats["total_quests"] == 0:
                continue

            text = "📅 *Wochenrückblick*\n\n"

            if stats["completions"]:
                text += "🏅 *Meiste Quests diese Woche:*\n"
                medals = ["🥇", "🥈", "🥉"]
                for i, c in enumerate(stats["completions"][:3]):
                    medal = medals[i] if i < 3 else "•"
                    n = c["count"]
                    text += f"{medal} {c['first_name']}: {n} Quest{'s' if n != 1 else ''}\n"
                text += "\n"

            if stats["streaks"]:
                text += "🔥 *Aktuelle Top-Streaks:*\n"
                for s in stats["streaks"]:
                    fire = "🔥" * min(s["streak"] // 5 + 1, 5)
                    text += f"• {s['first_name']}: {s['streak']} Tage {fire}\n"
                text += "\n"

            if stats.get("scores"):
                text += "⭐ *Top-Punkte diese Woche:*\n"
                medals = ["🥇", "🥈", "🥉"]
                for i, sc in enumerate(stats["scores"][:3]):
                    medal = medals[i] if i < 3 else "•"
                    text += f"{medal} {sc['first_name']}: {sc['score']:.1f}\n"
                text += "\n"

            n = stats["total_quests"]
            text += f"_Insgesamt {n} Quest{'s' if n != 1 else ''} diese Woche. Weiter so! 💪_"

            await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        except Exception:
            logger.exception(f"Fehler beim Wochenrückblick für Gruppe {chat_id}")
