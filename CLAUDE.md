# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Telegram bot (German UI) that assigns one daily "side quest" per group chat, tracks completions, streaks and a quest pool. Python 3.12, `python-telegram-bot[job-queue]==21.3`, `aiosqlite`, `pytz`.

## Commands

```bash
# Local dev (requires TELEGRAM_TOKEN)
pip install -r requirements.txt
TELEGRAM_TOKEN=xxx PYTHONUNBUFFERED=1 python bot/main.py

# Containerized (recommended) — reads .env
docker compose up --build
docker compose logs -f bot
```

There are no tests, linter, or build step in this repo.

DB lives at `/data/quests.db` inside the container, mounted from `./data/quests.db` on the host. To inspect/edit:
```bash
sqlite3 ./data/quests.db
```

## Architecture

Single-process polling bot. `bot/main.py` builds the `Application`, registers command handlers, and via `post_init` opens the DB and starts the JobQueue scheduler. The `Database` instance is stashed in `application.bot_data["db"]` and pulled out by every handler — that dict is the only DI mechanism.

**Three layered concepts to keep straight:**

1. **`quest_pool`** — global library of ~30 seeded quests (see `QUEST_POOL` in `bot/database.py`). Used as the fallback source. `used_count` drives "least-used wins" selection. Admins extend it via `/addquest`.
2. **`quest_queue`** — per-group FIFO of user-proposed quests (`/propose`). Drained before the pool.
3. **`daily_quests`** — the actual quest assigned to a group on a given date. One row per `(chat_id, quest_date)`.

**Daily lifecycle (all `Europe/Berlin`, hardcoded):**
- 00:00 — `pick_quests_midnight` writes tomorrow's `daily_quests` row for every group: queue first, else pool (least-used, ties broken randomly), pool's `used_count` incremented.
- 09:00 — `announce_quests_morning` posts the quest to each group.
- Sun 20:00 — `weekly_summary` posts leaderboard + top streaks.

`/start` also calls `pick_quest_for_tomorrow` so a fresh group isn't empty on day one.

**Streaks:** computed inside `Database.mark_done` — gap of >2 days between completions resets to 1, otherwise +1. The first completer of a quest gets `is_first=1` and the 🏆 badge.

**Schema migrations:** `Database.init` runs `CREATE TABLE IF NOT EXISTS` for all tables, then runs `ALTER TABLE … ADD COLUMN` statements wrapped in try/except to add columns to pre-existing databases. New columns must be added the same way — never replace `CREATE TABLE`.

**Categories:** `CATEGORY_EMOJI` in `bot/database.py` is the single source of truth for valid categories and their emojis. Both the scheduler and handlers import from there. `/addquest Mut: …` parses the prefix against `VALID_CATEGORIES`.

## Constraints

- All commands require a group chat. `_require_group` in `bot/handlers/quest.py` and the explicit `chat.type == "private"` check elsewhere short-circuit private DMs.
- `/done` accepts both a plain text command and a photo with `^/done` caption — the photo `MessageHandler` in `main.py` is registered separately.
- `/addquest` checks `chat.get_member(...).status` for `creator`/`administrator`. There is no other auth.
- Scheduler timezone is hardcoded `Europe/Berlin`; changing it deschedules. Date math in `database.py` (`_today_in_berlin`, etc.) must stay aligned.
- User-facing strings are German. Match the existing tone (informal, emoji-heavy) when adding messages.

## Files at a glance

- `bot/main.py` — entrypoint, handler registration, post_init wiring
- `bot/database.py` — all SQL, seed pool, migrations, category constants
- `bot/scheduler.py` — three `run_daily` jobs
- `bot/handlers/{group,quest,stats}.py` — command handlers
- `AGENTS.md` — short overview, kept in sync with this file
