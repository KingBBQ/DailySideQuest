from telegram import Update
from telegram.ext import ContextTypes
from database import CATEGORY_EMOJI, VALID_CATEGORIES


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

    category_line = ""
    if quest["category"]:
        emoji = CATEGORY_EMOJI.get(quest["category"], "📋")
        category_line = f"\n{emoji} _{quest['category']}_"

    text = f"🎯 *Quest des Tages*\n\n_{quest['text']}_{category_line}"

    completions = await db.get_completions_today(chat.id)
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
        await update.message.reply_text(
            f"✅ Quest erledigt, {user.first_name}! (Platz {result['done_count']})\n"
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


async def add_quest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nur für Gruppen-Admins: Quest dauerhaft zum Pool hinzufügen."""
    chat = update.effective_chat
    user = update.effective_user
    db = context.bot_data["db"]

    if not _require_group(update):
        await update.message.reply_text("Diesen Befehl bitte in einer Gruppe verwenden.")
        return

    # Admin-Check
    member = await chat.get_member(user.id)
    if member.status not in ("creator", "administrator"):
        await update.message.reply_text(
            "Nur Gruppen-Admins können Quests dauerhaft zum Pool hinzufügen.\n"
            "Für eigene Vorschläge: /propose"
        )
        return

    if not context.args:
        cats = ", ".join(VALID_CATEGORIES[:-1])  # ohne "Allgemein"
        await update.message.reply_text(
            "Syntax: /addquest [Kategorie:] Text\n\n"
            f"Kategorien: {cats}\n\n"
            "Beispiele:\n"
            "/addquest Geh heute barfuß durch Gras\n"
            "/addquest Mut: Sing laut in der U-Bahn"
        )
        return

    full_text = " ".join(context.args)
    category = "Allgemein"

    # Optionalen Kategorie-Prefix erkennen: "Mut: Text"
    for cat in VALID_CATEGORIES:
        if full_text.lower().startswith(cat.lower() + ":"):
            category = cat
            full_text = full_text[len(cat) + 1:].strip()
            break

    if len(full_text) < 10:
        await update.message.reply_text("Die Quest ist zu kurz (min. 10 Zeichen).")
        return

    if len(full_text) > 200:
        await update.message.reply_text(
            f"Die Quest ist zu lang ({len(full_text)}/200 Zeichen)."
        )
        return

    success = await db.add_to_pool(full_text, category)

    if success:
        emoji = CATEGORY_EMOJI.get(category, "📋")
        await update.message.reply_text(
            f"✅ Quest dauerhaft zum Pool hinzugefügt!\n\n"
            f"{emoji} *{category}*\n"
            f"_{full_text}_",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text("Diese Quest ist bereits im Pool.")
