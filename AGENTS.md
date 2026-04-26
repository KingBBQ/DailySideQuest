# Daily Side Quest

Telegram bot that assigns daily quests to groups. Python 3.12 + `python-telegram-bot` + aiosqlite.

## Setup

```
cp .env.example .env
# add TELEGRAM_TOKEN to .env
docker compose up
```

Or locally: `pip install -r requirements.txt && TELEGRAM_TOKEN=xxx python bot/main.py`

Database file: `/data/quests.db` (mounted as `./data/quests.db` via docker compose).

## Running locally

```
PYTHONUNBUFFERED=1 python bot/main.py
```

## Architecture

- `bot/main.py` – entrypoint, registers command handlers, builds app, runs polling
- `bot/database.py` – all persistence (aiosqlite), seed `QUEST_POOL`, migrations
- `bot/scheduler.py` – three cron jobs (all `Europe/Berlin`):
  - 00:00 – picks tomorrow's quest (queue-first, then random from pool)
  - 09:00 – announces the quest to all groups
  - Sunday 20:00 – weekly summary with leaderboard + streaks
- `bot/handlers/group.py` – `/start`, `/hilfe`
- `bot/handlers/quest.py` – `/quest`, `/done`, `/propose`, `/addquest`
- `bot/handlers/stats.py` – `/stats`

All commands require a group chat (not private). Quest pool editing is admin-only.

## Gotchas

- Quest pool seeds into `quest_pool` on first run. Edit via `/addquest` or directly in the DB.
- Streaks reset if gap > 2 days between completions.
- First completer of the day gets 🏆 badge.
- `/done` works via text command or photo caption matching `^/done`.
- Scheduler timezone is hardcoded `Europe/Berlin` — changes will deschedule.
