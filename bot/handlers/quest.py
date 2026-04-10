from telegram import Update
from telegram.ext import ContextTypes


def _require_group(update: Update) -> bool:
    return update.effective_chat.type != "private"


async def show_quest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    db = context.bot_data["db"]

    if not _require_group(update):
        await update.message.reply_text("Diesen Befehl bitte in einer Gruppe verwenden.")
        return

    await db.register_user(user.id, chat.id, user.username or "", user.first_name)

    quest = await db.get_todays_quest(chat.id)
    if not quest:
        await update.message.reply_text(
            "Für heute gibt es noch keine Quest.\n"
            "Sie wird um 9 Uhr bekannt gegeben! ⏰"
        )
        return

    completions = await db.get_completions_today(chat.id)

    text = f"🎯 *Quest des Tages*\n\n_{quest['text']}_"

    if completions:
        text += f"\n\n✅ *Schon erledigt ({len(completions)}):*\n"
        for c in completions:
            badge = " 🏆" if c["is_first"] else ""
            text += f"• {c['first_name']}{badge}\n"
    else:
        text += "\n\n_Noch niemand hat die Quest erledigt – sei der Erste!_ 🚀"

    await update.message.reply_text(text, parse_mode="Markdown")


async def mark_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    db = context.bot_data["db"]

    if not _require_group(update):
        await update.message.reply_text("Diesen Befehl bitte in einer Gruppe verwenden.")
        return

    await db.register_user(user.id, chat.id, user.username or "", user.first_name)

    # Foto optional – entweder direkt oder als Antwort mit /done
    photo_file_id = None
    if update.message.photo:
        photo_file_id = update.message.photo[-1].file_id

    result = await db.mark_done(chat.id, user.id, photo_file_id)

    if result["status"] == "no_quest":
        await update.message.reply_text(
            "Für heute gibt es noch keine Quest! Sie kommt um 9 Uhr. ⏰"
        )
        return

    if result["status"] == "already_done":
        await update.message.reply_text("Du hast die heutige Quest bereits erledigt! ✅")
        return

    streak = result["streak"]
    streak_emoji = "🔥" * min(streak // 3 + 1, 5)
    streak_text = f"{streak_emoji} Streak: {streak} Tag{'e' if streak != 1 else ''}"

    if result["is_first"]:
        await update.message.reply_text(
            f"🏆 *{user.first_name} ist ERSTER!*\n\n"
            f"Quest erledigt – Respekt!\n"
            f"{streak_text}",
            parse_mode="Markdown",
        )
    else:
        position = result["done_count"]
        await update.message.reply_text(
            f"✅ Quest erledigt, {user.first_name}! (Platz {position})\n"
            f"{streak_text}"
        )


async def propose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    db = context.bot_data["db"]

    if not _require_group(update):
        await update.message.reply_text("Diesen Befehl bitte in einer Gruppe verwenden.")
        return

    await db.register_user(user.id, chat.id, user.username or "", user.first_name)

    if not context.args:
        await update.message.reply_text(
            "Bitte gib eine Quest an!\n"
            "Beispiel: /propose Sprich heute eine fremde Person an"
        )
        return

    text = " ".join(context.args)

    if len(text) < 10:
        await update.message.reply_text("Die Quest ist zu kurz. Bitte etwas ausführlicher!")
        return

    if len(text) > 200:
        await update.message.reply_text(
            f"Die Quest ist zu lang ({len(text)}/200 Zeichen). Bitte kürzer fassen."
        )
        return

    queue_size = await db.propose_quest(chat.id, user.id, text)

    await update.message.reply_text(
        f"✨ Quest vorgeschlagen und in der Warteschlange!\n"
        f"_({queue_size} Quest{'s' if queue_size != 1 else ''} warten aktuell)_",
        parse_mode="Markdown",
    )
