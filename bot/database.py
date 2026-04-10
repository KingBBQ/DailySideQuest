import aiosqlite
import logging
from datetime import date, timedelta
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# Emoji pro Kategorie – wird überall verwendet
CATEGORY_EMOJI = {
    "Sozial": "🤝",
    "Körper": "💪",
    "Kreativ": "🎨",
    "Mut": "🦁",
    "Digital": "📵",
    "Spaß": "😄",
    "Abenteuer": "🌍",
    "Allgemein": "📋",
}

VALID_CATEGORIES = list(CATEGORY_EMOJI.keys())

# Vorgefertigte Quests mit Kategorie – direkt in der DB unter quest_pool bearbeitbar
QUEST_POOL = [
    ("Sprich heute eine fremde Person an und frag nach dem Weg – und führe ein kurzes Gespräch", "Sozial"),
    ("Mach jemandem ein ehrliches Kompliment – einem Fremden oder Bekannten", "Sozial"),
    ("Schreib einer Person aus deiner Vergangenheit eine Nachricht", "Sozial"),
    ("Ruf heute jemanden an, dem du sonst nur schreibst", "Sozial"),
    ("Bring jemandem spontan etwas mit (Kaffee, Snack, etc.)", "Sozial"),
    ("Betritt ein Geschäft, das du noch nie betreten hast", "Abenteuer"),
    ("Bestell im Restaurant oder Café, ohne die Karte zu lesen – frag nach einer Empfehlung", "Mut"),
    ("Trag heute etwas, das du sonst nie tragen würdest", "Mut"),
    ("Geh heute einen anderen Weg als sonst (Arbeit, Einkauf, etc.)", "Abenteuer"),
    ("Mach 50 Liegestütze – verteilt über den ganzen Tag", "Körper"),
    ("Geh heute 10.000 Schritte", "Körper"),
    ("Nimm den ganzen Tag die Treppe statt den Aufzug", "Körper"),
    ("Mach 5 Minuten Meditation oder bewusstes Atmen", "Körper"),
    ("Tanz 3 Minuten alleine zu deinem Lieblingssong", "Spaß"),
    ("Zeichne etwas – egal wie schlecht es wird", "Kreativ"),
    ("Schreib ein Haiku über deinen heutigen Tag", "Kreativ"),
    ("Fotografiere etwas Schönes, das du sonst übersehen würdest", "Kreativ"),
    ("Koch heute etwas, das du noch nie gekocht hast", "Kreativ"),
    ("2 Stunden lang kein Social Media", "Digital"),
    ("Stell dein Handy für 1 Stunde komplett auf Flugmodus", "Digital"),
    ("Schick heute 5 Sprachnachrichten statt Texte", "Digital"),
    ("Sing ein ganzes Lied laut durch – alleine oder vor anderen", "Spaß"),
    ("Zähl heute, wie oft du das Wort 'okay' sagst", "Spaß"),
    ("Sag den ganzen Tag 'Danke' auf Italienisch: Grazie!", "Spaß"),
    ("Probiere heute ein Essen, das du normalerweise nie essen würdest", "Abenteuer"),
    ("Schau heute den Sonnenuntergang oder Sonnenaufgang an", "Abenteuer"),
    ("Sitz 10 Minuten alleine in einem Café und beobachte die Menschen um dich herum", "Abenteuer"),
    ("Finde und fotografiere etwas Ungewöhnliches auf deinem heutigen Weg", "Kreativ"),
    ("Kauf etwas in einem Second-Hand-Laden oder auf einem Flohmarkt unter 2 Euro", "Abenteuer"),
    ("Sprich heute eine Person an, die du schon länger ansprechen wolltest", "Mut"),
]


class Database:
    def __init__(self, path: str):
        self.path = path

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS groups (
                    chat_id INTEGER PRIMARY KEY,
                    title TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER,
                    chat_id INTEGER,
                    username TEXT,
                    first_name TEXT,
                    streak INTEGER DEFAULT 0,
                    last_completed_date TEXT,
                    total_completed INTEGER DEFAULT 0,
                    total_first INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, chat_id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS daily_quests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    text TEXT,
                    quest_date TEXT,
                    proposed_by INTEGER,
                    category TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS completions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    quest_id INTEGER,
                    user_id INTEGER,
                    chat_id INTEGER,
                    completed_at TEXT DEFAULT (datetime('now')),
                    photo_file_id TEXT,
                    is_first INTEGER DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS quest_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    text TEXT,
                    proposed_by INTEGER,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS quest_pool (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT UNIQUE,
                    category TEXT DEFAULT 'Allgemein',
                    used_count INTEGER DEFAULT 0
                )
            """)

            # Migrationen für bestehende Datenbanken
            for stmt in [
                "ALTER TABLE quest_pool ADD COLUMN category TEXT DEFAULT 'Allgemein'",
                "ALTER TABLE daily_quests ADD COLUMN category TEXT",
            ]:
                try:
                    await db.execute(stmt)
                except Exception:
                    pass  # Spalte existiert bereits

            # Quest-Pool befüllen / Kategorien aktualisieren
            async with db.execute("SELECT COUNT(*) FROM quest_pool") as cursor:
                (count,) = await cursor.fetchone()

            if count == 0:
                await db.executemany(
                    "INSERT OR IGNORE INTO quest_pool (text, category) VALUES (?, ?)",
                    QUEST_POOL,
                )
                logger.info(f"Quest-Pool mit {len(QUEST_POOL)} Quests befüllt")
            else:
                # Kategorien für bestehende Einträge ohne Kategorie setzen
                for text, category in QUEST_POOL:
                    await db.execute(
                        "UPDATE quest_pool SET category = ? WHERE text = ? AND (category IS NULL OR category = 'Allgemein')",
                        (category, text),
                    )

            await db.commit()
        logger.info("Datenbank initialisiert")

    async def register_group(self, chat_id: int, title: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO groups (chat_id, title) VALUES (?, ?)",
                (chat_id, title),
            )
            await db.execute(
                "UPDATE groups SET title = ? WHERE chat_id = ?",
                (title, chat_id),
            )
            await db.commit()

    async def register_user(self, user_id: int, chat_id: int, username: str, first_name: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, chat_id, username, first_name) VALUES (?, ?, ?, ?)",
                (user_id, chat_id, username, first_name),
            )
            await db.execute(
                "UPDATE users SET username = ?, first_name = ? WHERE user_id = ? AND chat_id = ?",
                (username, first_name, user_id, chat_id),
            )
            await db.commit()

    async def get_all_groups(self) -> List[int]:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute("SELECT chat_id FROM groups") as cursor:
                rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def get_todays_quest(self, chat_id: int) -> Optional[Dict]:
        today = date.today().isoformat()
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT id, text, proposed_by, category FROM daily_quests WHERE chat_id = ? AND quest_date = ?",
                (chat_id, today),
            ) as cursor:
                row = await cursor.fetchone()
        if row:
            return {"id": row[0], "text": row[1], "proposed_by": row[2], "category": row[3]}
        return None

    async def pick_quest_for_tomorrow(self, chat_id: int) -> Optional[str]:
        """Wählt die Quest für morgen aus Queue oder Pool."""
        tomorrow = (date.today() + timedelta(days=1)).isoformat()

        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT id FROM daily_quests WHERE chat_id = ? AND quest_date = ?",
                (chat_id, tomorrow),
            ) as cursor:
                if await cursor.fetchone():
                    return None

            # Zuerst aus der Queue (FIFO)
            async with db.execute(
                "SELECT id, text, proposed_by FROM quest_queue WHERE chat_id = ? ORDER BY created_at ASC LIMIT 1",
                (chat_id,),
            ) as cursor:
                queued = await cursor.fetchone()

            if queued:
                queue_id, text, proposed_by = queued
                await db.execute("DELETE FROM quest_queue WHERE id = ?", (queue_id,))
                await db.execute(
                    "INSERT INTO daily_quests (chat_id, text, quest_date, proposed_by, category) VALUES (?, ?, ?, ?, NULL)",
                    (chat_id, text, tomorrow, proposed_by),
                )
            else:
                # Pool: am wenigsten benutzte Quest, zufällig bei Gleichstand
                async with db.execute(
                    "SELECT id, text, category FROM quest_pool ORDER BY used_count ASC, RANDOM() LIMIT 1"
                ) as cursor:
                    pool_row = await cursor.fetchone()

                if pool_row:
                    pool_id, text, category = pool_row
                    await db.execute(
                        "UPDATE quest_pool SET used_count = used_count + 1 WHERE id = ?",
                        (pool_id,),
                    )
                    await db.execute(
                        "INSERT INTO daily_quests (chat_id, text, quest_date, proposed_by, category) VALUES (?, ?, ?, NULL, ?)",
                        (chat_id, text, tomorrow, category),
                    )
                else:
                    text = None

            await db.commit()
        return text

    async def propose_quest(self, chat_id: int, user_id: int, text: str) -> int:
        """Fügt Quest in die Queue ein. Gibt Anzahl wartender Quests zurück."""
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO quest_queue (chat_id, text, proposed_by) VALUES (?, ?, ?)",
                (chat_id, text, user_id),
            )
            await db.commit()
            async with db.execute(
                "SELECT COUNT(*) FROM quest_queue WHERE chat_id = ?", (chat_id,)
            ) as cursor:
                (count,) = await cursor.fetchone()
        return count

    async def add_to_pool(self, text: str, category: str = "Allgemein") -> bool:
        """Fügt Quest zum globalen Pool hinzu. Gibt False zurück wenn bereits vorhanden."""
        async with aiosqlite.connect(self.path) as db:
            try:
                await db.execute(
                    "INSERT INTO quest_pool (text, category) VALUES (?, ?)",
                    (text, category),
                )
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False

    async def mark_done(
        self, chat_id: int, user_id: int, photo_file_id: Optional[str] = None
    ) -> Dict:
        """Markiert Quest als erledigt. Gibt Status und neue Stats zurück."""
        today = date.today().isoformat()

        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT id FROM daily_quests WHERE chat_id = ? AND quest_date = ?",
                (chat_id, today),
            ) as cursor:
                quest_row = await cursor.fetchone()

            if not quest_row:
                return {"status": "no_quest"}

            quest_id = quest_row[0]

            async with db.execute(
                "SELECT id FROM completions WHERE quest_id = ? AND user_id = ?",
                (quest_id, user_id),
            ) as cursor:
                if await cursor.fetchone():
                    return {"status": "already_done"}

            async with db.execute(
                "SELECT COUNT(*) FROM completions WHERE quest_id = ?", (quest_id,)
            ) as cursor:
                (done_count,) = await cursor.fetchone()

            is_first = done_count == 0

            await db.execute(
                "INSERT INTO completions (quest_id, user_id, chat_id, photo_file_id, is_first) VALUES (?, ?, ?, ?, ?)",
                (quest_id, user_id, chat_id, photo_file_id, 1 if is_first else 0),
            )

            # Streak berechnen
            async with db.execute(
                "SELECT streak, last_completed_date FROM users WHERE user_id = ? AND chat_id = ?",
                (user_id, chat_id),
            ) as cursor:
                user_row = await cursor.fetchone()

            streak, last_date = (user_row[0], user_row[1]) if user_row else (0, None)

            today_date = date.today()
            if last_date:
                gap = (today_date - date.fromisoformat(last_date)).days
                new_streak = streak + 1 if gap <= 2 else 1
            else:
                new_streak = 1

            await db.execute(
                """UPDATE users SET
                       streak = ?,
                       last_completed_date = ?,
                       total_completed = total_completed + 1,
                       total_first = total_first + ?
                   WHERE user_id = ? AND chat_id = ?""",
                (new_streak, today, 1 if is_first else 0, user_id, chat_id),
            )
            await db.commit()

        return {
            "status": "ok",
            "is_first": is_first,
            "streak": new_streak,
            "done_count": done_count + 1,
        }

    async def get_completions_today(self, chat_id: int) -> List[Dict]:
        today = date.today().isoformat()
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                """SELECT u.first_name, c.completed_at, c.is_first
                   FROM completions c
                   JOIN users u ON c.user_id = u.user_id AND c.chat_id = u.chat_id
                   JOIN daily_quests dq ON c.quest_id = dq.id
                   WHERE c.chat_id = ? AND dq.quest_date = ?
                   ORDER BY c.completed_at ASC""",
                (chat_id, today),
            ) as cursor:
                rows = await cursor.fetchall()
        return [{"first_name": r[0], "completed_at": r[1], "is_first": r[2]} for r in rows]

    async def get_stats(self, chat_id: int) -> List[Dict]:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                """SELECT first_name, streak, total_completed, total_first
                   FROM users
                   WHERE chat_id = ?
                   ORDER BY streak DESC, total_completed DESC""",
                (chat_id,),
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            {"first_name": r[0], "streak": r[1], "total_completed": r[2], "total_first": r[3]}
            for r in rows
        ]

    async def get_weekly_stats(self, chat_id: int) -> Dict:
        """Statistiken der letzten 7 Tage."""
        async with aiosqlite.connect(self.path) as db:
            # Wer hat diese Woche am meisten erledigt
            async with db.execute(
                """SELECT u.first_name, COUNT(*) as week_count
                   FROM completions c
                   JOIN users u ON c.user_id = u.user_id AND c.chat_id = u.chat_id
                   JOIN daily_quests dq ON c.quest_id = dq.id
                   WHERE c.chat_id = ? AND date(dq.quest_date) >= date('now', '-6 days')
                   GROUP BY c.user_id
                   ORDER BY week_count DESC""",
                (chat_id,),
            ) as cursor:
                completions = await cursor.fetchall()

            # Wie viele Quests gab es diese Woche
            async with db.execute(
                """SELECT COUNT(DISTINCT quest_date)
                   FROM daily_quests
                   WHERE chat_id = ? AND date(quest_date) >= date('now', '-6 days')""",
                (chat_id,),
            ) as cursor:
                (total_quests,) = await cursor.fetchone()

            # Top-Streaks aktuell
            async with db.execute(
                """SELECT first_name, streak
                   FROM users
                   WHERE chat_id = ? AND streak > 0
                   ORDER BY streak DESC
                   LIMIT 3""",
                (chat_id,),
            ) as cursor:
                streaks = await cursor.fetchall()

        return {
            "completions": [{"first_name": r[0], "count": r[1]} for r in completions],
            "total_quests": total_quests,
            "streaks": [{"first_name": r[0], "streak": r[1]} for r in streaks],
        }
