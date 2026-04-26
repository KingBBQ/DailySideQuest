# Analyse: Bug bei der Quest-Zuweisung im Zeitfenster 00:00 - 09:00 Uhr

## Problembeschreibung
Der Nutzer hat festgestellt, dass der Befehl `/done` (und potenziell `/quest`) im Zeitraum zwischen Mitternacht (00:00 Uhr) und der offiziellen Bekanntgabe der neuen Quest (09:00 Uhr) bereits die neue Quest des aktuellen Kalendertages als erledigt markiert, anstatt die Quest des Vortages, die laut Geschäftslogik ("9 Uhr bis 9 Uhr") noch aktiv sein sollte.

## Technische Ursache
Die Analyse der Dateien `bot/database.py` und `bot/scheduler.py` zeigt folgende Abläufe:

1. **Quest-Erstellung**: `pick_quests_midnight` läuft täglich um 00:00 Uhr und erstellt über `db.pick_quest_for_tomorrow` eine Quest für den *nächsten* Kalendertag (`date.today() + timedelta(days=1)`). 
   - *Beispiel*: Am Montag um 00:00 Uhr wird die Quest für Dienstag erstellt.
2. **Quest-Bekanntgabe**: `announce_quests_morning` läuft täglich um 09:00 Uhr und ruft `db.get_todays_quest` auf.
3. **Aktuelle Quest-Identifikation**: Die Methoden `get_todays_quest`, `mark_done` und `get_completions_today` in `bot/database.py` verwenden alle hartkodiert `date.today().isoformat()`, um die entsprechende Quest in der Datenbank zu finden.

**Der Bug:**
Wenn ein Nutzer am Dienstag um 07:00 Uhr `/done` aufruft:
- `date.today().isoformat()` liefert den Dienstag.
- Die Datenbank sucht nach der Quest für Dienstag.
- Da diese bereits am Montag um 00:00 Uhr erstellt wurde, existiert sie bereits.
- Die Quest wird als erledigt markiert, obwohl sie erst um 09:00 Uhr bekannt gegeben wird und die Quest vom Montag (aus Sicht des Nutzers) eigentlich noch aktiv ist.

## Vorgeschlagene Lösung

Um die "9 Uhr bis 9 Uhr"-Logik technisch umzusetzen, muss die Bestimmung des "aktiven Quest-Datums" von einem einfachen Kalendertag auf eine zeitabhängige Logik umgestellt werden.

### Detailplan:
1. **Einführung einer Hilfsmethode zur Datumsbestimmung**:
   Es sollte eine Funktion (z.B. `_get_active_quest_date`) implementiert werden, die prüft, ob die aktuelle Uhrzeit (in der Zeitzone `Europe/Berlin`) vor oder nach 09:00 Uhr liegt.
   - Wenn `aktuell < 09:00 Uhr` $\rightarrow$ Aktives Datum = `heute - 1 Tag`.
   - Wenn `aktuell >= 09:00 Uhr` $\rightarrow$ Aktives Datum = `heute`.

2. **Anpassung der Datenbank-Methoden**:
   Die folgenden Methoden in `Database` müssen so geändert werden, dass sie nicht `date.today().isoformat()` verwenden, sondern die neue `_get_active_quest_date()` Logik:
   - `get_todays_quest(self, chat_id)`
   - `mark_done(self, chat_id, user_id, ...)`
   - `get_completions_today(self, chat_id)`

3. **Auswirkung**:
   - Ein Aufruf von `/done` um 07:00 Uhr am Dienstag wird nun mit dem Datum "Montag" an die DB übergeben und markiert die Montag-Quest als erledigt.
   - Ein Aufruf von `/done` um 09:01 Uhr am Dienstag wird mit dem Datum "Dienstag" übergeben und markiert die Dienstag-Quest als erledigt.
   - Die Bekanntgabe um 09:00 Uhr bleibt korrekt, da sie genau zum Zeitpunkt des Wechsels erfolgt.
