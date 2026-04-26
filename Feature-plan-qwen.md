# Feature-Plan: Catch-Up Score + Total Scoreboard

## 1. Analyse des bestehenden Systems

### Aktuelle Streak-Logik:
- Streak wird in `users.streak` gespeichert
- Reset wenn Lücke > 2 Tage zwischen zwei Completions (`gap <= 2 else 1`)
- `total_completed` zählt bereits alle abgeschlossenen Challenges global
- `/stats` zeigt bereits: streak, total_completed, total_first

### Problem:
- Nach einem verpassten Tag beginnt der Streak bei 1 – kein Anreiz, verpasste Tage nachzuholen
- total_completed existiert bereits, wird aber im `/done` Feedback nicht gezeigt

---

## 2. Was umgesetzt wird

### Feature 1: `/catchup` — Verpasste Tage nachholen

**Neuer Befehl:** `/catchup [YYYY-MM-DD]`
- User kann bis zu 3 verpasste Tage nachholen
- Nachholung gilt nur für `days 0 bis 7` zurück (1 Woche)
- Für jeden Nachhol-Tag: **Half Point Bonus** (0.5 Punkte) statt normaler Streak-Punkte
- Maximal 3 Nachhol-Tage pro Woche

**Workflow:**
1. User fragt `/catchup` → zeigt verpasste Tage an mit Verfügbarkeit
2. User wählt einen Tag: `/catchup 2024-01-15` oder klickt auf Button im Inline-Keyboard
3. Wenn keine Quest existiert → keine Nachholung möglich ("Für diesen Tag gab es keine Quest" oder "Quest ist bereits abgelaufen")
4. Wenn Quest existiert und nicht completed → User muss `/done` mit Photo für diesen Tag geben
5. Nach erfolgreicher Markierung: **0.5 Punkte** werden dem Catch-Up-Score gutgeschrieben

### Feature 2: Catch-Up Score im Profil

**Neue Datenbank-Spalten:**
```sql
ALTER TABLE users ADD COLUMN catchup_score REAL DEFAULT 0;
ALTER TABLE users ADD COLUMN catchup_max_days INTEGER DEFAULT 0; -- wie viele Tage wurden nachgeholt
```

**Catch-Up Score Berechnung:**
- Für jede nachgeholte Challenge: 0.5 Punkte
- Bei 3 Nachhol-Tagen: 3 × 0.5 = 1.5 Punkte → "Quasi wie ein 15-Tage-Streak!"

### Feature 3: Total Scoreboard in `/stats`

Der Scoreboard zeigt jetzt:
1. **Streak** (aktueller laufender Streak)
2. **Catch-Up Score** (nachgeholte Challenges × 0.5)
3. **Total Score** = Streak + Catch-Up Score
4. **Total Completed** (alle Challenges aller Zeiten)

**Neue Rangliste-Logik:**
Die Rangliste wird primär nach `total_completed` geordnet (nicht nur Streak), um Langzeitmotivation zu fördern.

---

## 3. Umsetzung im Detail

### 3.1 Datenbank-Änderungen

**database.py: `init()` – Neue Spalten hinzufügen**

```python
# Bestehende init() ergänzen:
for stmt in [
    "ALTER TABLE users ADD COLUMN catchup_score REAL DEFAULT 0",
    "ALTER TABLE users ADD COLUMN catchup_max_days INTEGER DEFAULT 0",
    "ALTER TABLE completions ADD COLUMN make_up_quest_date TEXT DEFAULT NULL",  # NULL wenn keine Nachholung
]:
    try:
        await db.execute(stmt)
    except Exception:
        pass
```

**database.py: `make_up_completion()` — Neue Methode**

```python
async def check_makeup_availability(
    self, chat_id: int, user_id: int, target_date: str
) -> Dict:
    """
    Prüft, ob eine Quest für `target_date` existiert und nicht completed wurde.
    """
    async with aiosqlite.connect(self.path) as db:
        # Quest existieren?
        async with db.execute(
            "SELECT id, text, category FROM daily_quests WHERE chat_id = ? AND quest_date = ?",
            (chat_id, target_date),
        ) as cursor:
            quest_row = await cursor.fetchone()

        if not quest_row:
            return {"available": False, "reason": "no_quest"}

        quest_id, text, category = quest_row

        # Schon completed?
        async with db.execute(
            "SELECT id FROM completions WHERE quest_id = ? AND user_id = ?",
            (quest_id, user_id),
        ) as cursor:
            if await cursor.fetchone():
                return {"available": False, "reason": "already_done"}

        # Max 3 makeups pro Woche?
        a_week_ago = (date.today() - timedelta(days=7)).isoformat()
        async with db.execute(
            "SELECT COUNT(*) FROM completions WHERE user_id = ? AND chat_id = ? AND make_up_quest_date >= ?",
            (user_id, chat_id, a_week_ago),
        ) as cursor:
            (count,) = await cursor.fetchone()

        if count >= 3:
            return {"available": False, "reason": "max_reached"}

        today = date.today().isoformat()
        days_back = (date.today() - date.fromisoformat(target_date)).days
        if days_back < 1 or days_back > 7:
            return {"available": False, "reason": "outside_range"}

        category_emoji = CATEGORY_EMOJI.get(category, "📋")

        return {
            "available": True,
            "quest": {"id": quest_id, "text": text, "category": category, "category_emoji": category_emoji},
            "target_date": target_date,
        }
```

**database.py: `mark_makeup_done()` — Nachholung abschließen**

```python
async def mark_makeup_done(
    self, chat_id: int, user_id: int, quest_id: int, target_date: str, photo_file_id: Optional[str] = None
) -> Dict:
    """
    Markiert Quest als completed für einen verpassten Tag.
    """
    async with aiosqlite.connect(self.path) as db:
        # Check ob User überhaupt existiert
        async with db.execute(
            "SELECT catchup_score, catchup_max_days, total_completed FROM users WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ) as cursor:
            user_row = await cursor.fetchone()

        if not user_row:
            return {"status": "user_not_found"}

        catchup_score, catchup_max_days, total_completed = user_row

        # Completion eintragen
        await db.execute(
            "INSERT INTO completions (quest_id, user_id, chat_id, photo_file_id, is_first, make_up_quest_date) VALUES (?, ?, ?, ?, 0, ?)",
            (quest_id, user_id, chat_id, photo_file_id, target_date),
        )

        # Catch-up Punkte aktualisieren
        new_catchup_score = catchup_score + 0.5
        new_catchup_max_days = catchup_max_days + 1

        await db.execute(
            "UPDATE users SET catchup_score = ?, catchup_max_days = ?, total_completed = total_completed + 1 WHERE user_id = ? AND chat_id = ?",
            (new_catchup_score, new_catchup_max_days, user_id, chat_id),
        )

        await db.commit()

        # Total Score berechnen (Streak bleibt unverändert — wird bei nächster echter Quest aktualisiert)
        return {
            "status": "ok",
            "catchup_score": new_catchup_score,
            "catchup_max_days": new_catchup_max_days,
            "total_completed": total_completed + 1,
            "is_makeup": True,
        }
```

**database.py: `_calculate_total_score()` — Hilfsfunktion**

```python
@staticmethod
def calculate_total_score(streak: int, catchup_score: float) -> float:
    """
    Kombiniert Streak und Catch-Up Score.
    Formel: Streak (max 10) + Catch-Up Score (max 1.5)
    """
    effective_streak = min(streak, 10) if streak > 0 else 0
    effective_catchup = catchup_score
    return effective_streak + effective_catchup
```

### 3.2 Handler-Änderungen

**handlers/quest.py: `/catchup` Handler**

```python
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


async def catchup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    db = context.bot_data["db"]

    if not _require_group(update):
        await update.message.reply_text("Diesen Befehl bitte in einer Gruppe verwenden.")
        return

    await db.register_user(user.id, chat.id, user.username or "", user.first_name)

    args = context.args
    if not args:
        # Zeige Übersicht verpasster Tage
        await show_catchup_overview(update, user, chat, db)
        return

    # Datum parsen: /catchup 2024-01-15
    try:
        target_date = date.fromisoformat(args[0])
    except ValueError:
        await update.message.reply_text("Format: /catchup YYYY-MM-DD")
        return

    availability = await db.check_makeup_availability(chat.id, user.id, target_date.isoformat())
    if not availability["available"]:
        reasons = {
            "no_quest": "❌ Für diesen Tag gab es keine Quest.",
            "already_done": "✅ Du hast diese Quest bereits erledigt.",
            "max_reached": "🔒 Du hast bereits 3 Nachhol-Tage diese Woche genutzt.",
            "outside_range": "⏰ Du kannst nur die letzten 7 Tage nachholen.",
        }
        await update.message.reply_text(reasons.get(availability["reason"], "❌ Leider nicht möglich."))
        return

    # Zeige Quest und Frage nach Bestätigung
    quest = availability["quest"]
    emoji = availability["quest"]["category_emoji"]
    target = availability["target_date"]

    keyboard = [
        [InlineKeyboardButton(f"✅ Jetzt {target} nachholen", callback_data=f"makeup:{target}")],
        [InlineKeyboardButton("❌ Abbrechen", callback_data="cancel")]
    ]

    await update.message.reply_text(
        f"🎯 *Quest für {target} nachholen*\n\n"
        f"{emoji} _{quest['text']}_\n\n"
        f"Nachholen gibt dir **0.5 Punkte**.\n"
        f"Du kannst bis zu 3 Tage nachholen.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
```

**Callback Handler für `/catchup` Bestätigung:**

```python
async def catchup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback für /catchup Buttons."""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text("❌ Abgebrochen.")
        return

    if query.data.startswith("makeup:"):
        target_date = query.data.split(":")[1]
        user = query.from_user
        chat = query.message.chat
        db = context.bot_data["db"]

        availability = await db.check_makeup_availability(chat.id, user.id, target_date)
        if not availability["available"]:
            await query.edit_message_text("❌ Leider nicht mehr möglich.")
            return

        quest = availability["quest"]

        # Hier kommt die Logik: User muss das Photo für diesen Tag schicken
        await query.edit_message_text(
            f"📸 *Photos für {target_date}*:\n\n"
            f"Jetzt ein Photo schicken, das zur Quest passt:\n"
            f"{quest['category_emoji']} _{quest['text']}_\n\n"
            f"Nach dem Photo: /done mit dem Bild für {target_date}.\n\n"
            f"_Alternativ:_ /done im normalen Modus wenn du die Quest heute schon erledigt hast.",
            parse_mode="Markdown"
        )

        # Speichere temporär das Ziel-Datum
        context.user_data[f"makeup_target_{user.id}"] = target_date

        # User wird jetzt aufgefordert, ein Photo zu schicken
        # ... (siehe unten: Photo Handler Logik)
```

**handlers/quest.py: Photo Handler für Makeups**

```python
async def handle_makeup_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handelt Photo wenn makeup_target im user_data gesetzt ist."""
    user = update.effective_user
    chat = update.effective_chat

    makeup_target = context.user_data.get(f"makeup_target_{user.id}")
    if not makeup_target:
        return  # Kein makeup-Mode

    photo_file_id = update.message.photo[-1].file_id

    quest = await db.get_quest_by_date(chat.id, makeup_target)  # Neue Methode
    if not quest:
        await update.message.reply_text("Quest für diesen Tag nicht gefunden.")
        context.user_data.pop(f"makeup_target_{user.id}")
        return

    result = await db.mark_makeup_done(chat.id, user.id, quest["id"], makeup_target, photo_file_id)
    if result["status"] == "ok":
        await update.message.reply_text(
            f"✅ Quest für {makeup_target} nachgeholt!\n"
            f"📊 Catch-Up Score: {result['catchup_score']} (von max. 1.5)\n"
            f"🔥 Bonus: Du hast dich selbst nicht aufggeben!"
        )
    context.user_data.pop(f"makeup_target_{user.id}")
```

### 3.3 Stats-Handler-Änderung

**handlers/stats.py: Erweiterte Stats**

```python
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    db = context.bot_data["db"]

    if chat.type == "private":
        await update.message.reply_text("Diesen Befehl bitte in einer Gruppe verwenden.")
        return

    await db.register_user(user.id, chat.id, user.username or "", user.first_name)

    # Hole Stats mit catchup_info
    stats_list = await db.get_stats(chat.id, include_catchup=True)  # Neue Methode
    my_index = None
    for i, s in enumerate(stats_list):
        if s["user_id"] == user.id:
            my_index = i
            break

    if not stats_list:
        await update.message.reply_text(
            "Noch keine Statistiken. Erledigt erst eine Quest mit /done!"
        )
        return

    medals = ["🥇", "🥈", "🥉"]
    text = "📊 *Rangliste*\n\n"

    # Sortiere nach total_completed, dann nach total_score
    sorted_stats = sorted(stats_list, key=lambda x: x["total_completed"], reverse=True)

    for i, s in enumerate(sorted_stats):
        place = medals[i] if i < 3 else f"{i + 1}\\."
        streak = s["streak"]
        total_completed = s["total_completed"]
        total_score = Database.calculate_total_score(streak, s["catchup_score"])
        catchup_max = s["catchup_max_days"]

        fire = "🔥" * min(streak // 5 + (1 if streak > 0 else 0), 5)

        user_marker = " 👈 Du" if my_index is not None and sorted_stats[i]["user_id"] == user.id else ""

        text += (
            f"{place} *{s['first_name']}*\n"
            f"   🔥 Streak: {streak}  ✅ Gesamt: {total_completed}  🏆 Erster: {s['total_first']}\n"
            f"   📈 Score: {total_score:.1f} (Streak {streak} + CatchUp {s['catchup_score']:.1f})\n"
            f"   🔙 CatchUp: {catchup_max}/3 Tage nachgeholt\n"
            f"   {fire}{user_marker}\n\n"
        )

    await update.message.reply_text(text, parse_mode="Markdown")
```

**database.py: `get_stats()` mit catchup_info**

```python
async def get_stats(self, chat_id: int, include_catchup: bool = False) -> List[Dict]:
    async with aiosqlite.connect(self.path) as db:
        if include_catchup:
            query = """
                SELECT first_name, streak, total_completed, total_first,
                       catchup_score, catchup_max_days, user_id
                FROM users
                WHERE chat_id = ?
                ORDER BY total_completed DESC, streak DESC
            """
        else:
            query = """
                SELECT first_name, streak, total_completed, total_first
                FROM users
                WHERE chat_id = ?
                ORDER BY total_completed DESC, streak DESC
            """
        async with db.execute(query, (chat_id,)) as cursor:
            rows = await cursor.fetchall()
    
    if include_catchup:
        return [
            {
                "first_name": r[0],
                "streak": r[1],
                "total_completed": r[2],
                "total_first": r[3],
                "catchup_score": r[4],
                "catchup_max_days": r[5],
                "user_id": r[6],
            }
            for r in rows
        ]
    else:
        return [
            {"first_name": r[0], "streak": r[1], "total_completed": r[2], "total_first": r[3]}
            for r in rows
        ]
```

### 3.4 Neuer Befehl `/makeup` (Alternative zu `/catchup`)

**handlers/quest.py: `/makeup` — Schneller Nachhol-Modus**

```python
async def makeup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Zeigt die aktuell verfügbaren Tage zum Nachholen."""
    chat = update.effective_chat
    user = update.effective_user
    db = context.bot_data["db"]

    if not _require_group(update):
        await update.message.reply_text("Diesen Befehl bitte in einer Gruppe verwenden.")
        return

    await db.register_user(user.id, chat.id, user.username or "", user.first_name)

    available_dates = []
    for days_back in range(1, 8):  # 1 bis 7 Tage zurück
        target_date = (date.today() - timedelta(days=days_back)).isoformat()
        avail = await db.check_makeup_availability(chat.id, user.id, target_date)
        if avail["available"]:
            available_dates.append(avail)

    if not available_dates:
        await update.message.reply_text(
            "😴 Es gibt keine Quests zum Nachholen.\n"
            "Entweder sind alle Quests bereits erledigt,\n"
            "oder es gab keine Quest für die letzten 7 Tage."
        )
        return

    keyboard = []
    for avail in available_dates:
        quest = avail["quest"]
        emoji = avail["quest"]["category_emoji"]
        target = avail["target_date"]
        # Max 3 Buttons pro Zeile
        keyboard.append([InlineKeyboardButton(f"{emoji} {target}", callback_data=f"makeup:{target}")])
        # 4 buttons in a row
        if len(keyboard) > 0:
            keyboard[-1].extend([
                InlineKeyboardButton("🕐 +1 Tag", callback_data="skip"),
                InlineKeyboardButton("❌ Abbrechen", callback_data="cancel"),
            ])
            keyboard[-1].extend([
                InlineKeyboardButton("🕐 -1 Tag", callback_data="skip"),
                InlineKeyboardButton("📸 Foto", callback_data="photo"),
            ])

    await update.message.reply_text(
        f"📅 *Verfügbare Tage zum Nachholen:*\n\n"
        f"💡 Du kannst bis zu 3 Tage nachholen (½ Punkte pro Tag).\n"
        f"🎯 Wähle einen Tag:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
```

---

## 4. Zusammenfassung der Änderungen

### Datenbank:
1. Neue Spalten: `users.catchup_score REAL`, `users.catchup_max_days INTEGER`, `completions.make_up_quest_date TEXT`
2. Migration-Spalten in `init()` hinzufügen

### Neue Funktionen in `database.py`:
1. `check_makeup_availability(chat_id, user_id, target_date)`
2. `mark_makeup_done(chat_id, user_id, quest_id, target_date, photo)`
3. `get_stats(include_catchup=True)` — erweiterte Stats
4. `calculate_total_score(streak, catchup)` — Hilfsfunktion

### Neuer Befehle in `handlers/quest.py`:
1. `/catchup [YYYY-MM-DD]` — Detail-Nachholung
2. `/makeup` — Schnellauswahl verfügbarer Tage
3. Photo-Handler für Makeups

### Erweiterte Befehle:
1. `/stats` zeigt jetzt: Catch-Up Score, Total Score, CatchUp-Counter

### Integration in `main.py`:
1. Neue Handler registrieren für `/catchup` und `/makeup`
2. Photo-Handler für Makeups


### Bonus: `/total` Befehl

```python
async def show_total_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    db = context.bot_data["db"]

    if chat.type == "private":
        await update.message.reply_text("Diesen Befehl bitte in einer Gruppe verwenden.")
        return

    await db.register_user(user.id, chat.id, user.username or "", user.first_name)

    stats = await db.get_user_profile(chat.id, user.id)
    total = Database.calculate_total_score(stats["streak"], stats["catchup_score"])
    
    await update.message.reply_text(
        f"📊 *Dein Gesamt-Score:\n\n"
        f"🔥 Streak: {stats['streak']}\n"
        f"📈 Catch-Up Score: {stats['catchup_score']:.1f}\n"
        f"💯 Total Score: {total:.1f}\n\n"
        f"_Dein Streak + CatchUp Score._\n"
        f"_Jeder Schritt zählt – auch der nachgeholte!_"
    )
```

---

## 5. Vorteile dieses Systems

1. **Motivation bleibt erhalten:** Nach einem missratenen Streak kann man trotzdem punkten
2. **Fairness:** 0.5 Punkte pro Nachhol-Challenge belohnen den Einsatz, ohne den Streak zu brechen
3. **Transparenz:** Der Score zeigt klar, wie viel man durch Nachholung erreicht hat
4. **Langzeit-Motivation:** Die Rangliste nach `total_completed` belohnert regelmäßige Teilnehmer
5. **Flexibilität:** Bis zu 3 Nachhol-Tage pro Woche erlauben Puffer für echte Ausfälle

---

## 6. Implementation Order

1. Datenbank-Migration (Spalten hinzufügen)
2. Neue DB-Methoden (`check_makeup_availability`, `mark_makeup_done`, `get_stats` erweitert)
3. Neue Handler `/catchup`, `/makeup`
4. `/stats` erweitern
5. Photo-Handler für Makeups
6. Testen und Feinschliff
