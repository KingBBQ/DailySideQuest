from telegram import Update
from telegram.ext import ContextTypes

HILFE_TEXT = (
    "🎯 *Daily Side Quest – Befehle*\n\n"
    "/quest – Heutige Quest anzeigen + wer schon fertig ist\n"
    "/done – Quest als erledigt markieren (optional Foto dranhängen)\n"
    "/nachholen – Verpasste Quest der letzten 7 Tage nachholen (zählt 0,5 ⭐)\n"
    "/propose [Text] – Quest für morgen vorschlagen\n"
    "/stats – Rangliste der Gruppe\n"
    "/addquest [Kategorie:] Text – Quest dauerhaft zum Pool hinzufügen _(nur Admins)_\n"
    "/hilfe – Diese Übersicht\n\n"
    "Jeden Tag um 9 Uhr wird die Quest bekannt gegeben.\n"
    "Sonntag um 20 Uhr gibt es den Wochenrückblick 📅\n"
    "Wer als Erster fertig ist, bekommt den 🏆 Titel!"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    db = context.bot_data["db"]

    if chat.type == "private":
        await update.message.reply_text(
            "👋 Hey! Füg mich zu einer Gruppe hinzu und schreib dort /start, "
            "um Daily Side Quest zu starten."
        )
        return

    await db.register_group(chat.id, chat.title)
    await db.register_user(user.id, chat.id, user.username or "", user.first_name)

    # Quest für morgen bereits festlegen damit der erste Tag nicht leer ist
    await db.pick_quest_for_tomorrow(chat.id)

    await update.message.reply_text(
        f"🎯 *Daily Side Quest ist aktiv!*\n\n"
        "Jeden Tag um 9 Uhr gibt es eine neue Quest.\n"
        "Die erste Quest kommt morgen früh.\n\n"
        + HILFE_TEXT,
        parse_mode="Markdown",
    )


async def hilfe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HILFE_TEXT, parse_mode="Markdown")
