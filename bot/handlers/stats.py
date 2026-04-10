from telegram import Update
from telegram.ext import ContextTypes


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    db = context.bot_data["db"]

    if chat.type == "private":
        await update.message.reply_text("Diesen Befehl bitte in einer Gruppe verwenden.")
        return

    await db.register_user(user.id, chat.id, user.username or "", user.first_name)

    stats = await db.get_stats(chat.id)

    if not stats:
        await update.message.reply_text(
            "Noch keine Statistiken. Erledigt erst eine Quest mit /done!"
        )
        return

    medals = ["🥇", "🥈", "🥉"]
    text = "📊 *Rangliste*\n\n"

    for i, s in enumerate(stats):
        place = medals[i] if i < 3 else f"{i + 1}\\."
        streak = s["streak"]
        fire = "🔥" * min(streak // 5 + (1 if streak > 0 else 0), 5)

        text += (
            f"{place} *{s['first_name']}*\n"
            f"   🔥 Streak: {streak}  ✅ Gesamt: {s['total_completed']}  🏆 Erster: {s['total_first']}\n"
            f"   {fire}\n\n"
        )

    await update.message.reply_text(text, parse_mode="Markdown")
