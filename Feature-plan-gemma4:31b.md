# Feature Plan: Catch-up & Weighted Scoring System
**Model**: gemma4:31b

## Overview
This feature introduces a way for users to retrospectively complete missed quests and a new scoring metric that rewards consistency over raw completion.

## Technical Specifications

### 1. Database Changes (`bot/database.py`)
- **Migration**: Add `weighted_score` column to `users` table.
  ```sql
  ALTER TABLE users ADD COLUMN weighted_score REAL DEFAULT 0;
  ```
- **Modified `mark_done`**: 
  - Update it to increment `weighted_score` by `1.0` for the daily quest.
- **New Method `mark_catchup_done`**:
  - Takes `user_id`, `chat_id`, and `quest_id`.
  - Verifies the quest exists and was not already completed by the user.
  - Increments `total_completed` by 1.
  - Increments `weighted_score` by `0.5`.
  - Inserts record into `completions`.

### 2. New Handler: `/catchup` (`bot/handlers/quest.py`)
- **Logic**:
  1. Fetch all `daily_quests` for the group from the last 7 days.
  2. Fetch all `completions` for the current user within that timeframe.
  3. Calculate the set difference to find missed quests.
  4. If no quests are missed, inform the user: "You are all caught up! 🌟"
  5. If quests are missed, list them and provide a way to mark them as done. 
     - *Note*: To keep it simple for a CLI-based bot, I will implement this as `/catchup <quest_id>` or a list where the user can respond with the ID.
- **Workflow**:
  - User runs `/catchup` -> Bot lists missed quests with IDs.
  - User runs `/catchup <id>` -> Bot marks quest as done and updates score.

### 3. Update Statistics (`bot/handlers/stats.py`)
- Update the `/stats` output to include the new score.
- **Format**:
  `🔥 Streak: {streak} | ✅ Gesamt: {total_completed} | 📈 Score: {weighted_score} | 🏆 Erster: {total_first}`

## Implementation Steps
1. **DB Migration**: Add the `weighted_score` column.
2. **DB Logic**: Implement `mark_catchup_done` and update `mark_done`.
3. **Command Handler**: Create the `/catchup` logic and register the command in `bot/main.py`.
4. **UI Update**: Update `/stats` to display the new metric.
5. **Verification**: 
   - Test a normal `/done` sequence (Score should be 1.0, 2.0...).
   - Test missing a day, then doing `/done` today (Score: X + 1.0).
   - Test `/catchup` for the missed day (Score: X + 1.0 + 0.5).
   - Verify `/stats` shows the correct weighted total.
