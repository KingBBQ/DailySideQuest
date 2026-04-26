# Analyse

## Ergebnis

Die Vermutung stimmt: Der Bug existiert.

Wenn ein User zwischen `00:00` und `08:59` `/done` ausführt, markiert der Bot aktuell nicht die noch aktive Quest vom Vortag, sondern die bereits vorbereitete Quest des neuen Kalendertags. Das widerspricht der Produktlogik aus dem Repo, nach der eine Quest faktisch von `09:00` bis `09:00` läuft.

## Bestehender Ablauf im Code

### Scheduler

- In [bot/scheduler.py](/home/kingbbq/src/DailySideQuest/bot/scheduler.py:15) wird um `00:00 Europe/Berlin` `pick_quests_midnight` ausgeführt.
- Diese Funktion ruft `Database.pick_quest_for_tomorrow()` auf und legt die Quest für den nächsten Kalendertag in `daily_quests` an.
- Um `09:00 Europe/Berlin` ruft [bot/scheduler.py](/home/kingbbq/src/DailySideQuest/bot/scheduler.py:22) `announce_quests_morning` auf und veröffentlicht die Quest.

### Quest-Anzeige und `/done`

- `/quest` ruft in [bot/handlers/quest.py](/home/kingbbq/src/DailySideQuest/bot/handlers/quest.py:21) `db.get_todays_quest(chat.id)` auf.
- `/done` ruft in [bot/handlers/quest.py](/home/kingbbq/src/DailySideQuest/bot/handlers/quest.py:63) `db.mark_done(chat.id, user.id, photo_file_id)` auf.

### Datenbanklogik

- [bot/database.py](/home/kingbbq/src/DailySideQuest/bot/database.py:184) `get_todays_quest()` sucht immer nach `quest_date = date.today()`.
- [bot/database.py](/home/kingbbq/src/DailySideQuest/bot/database.py:196) `pick_quest_for_tomorrow()` legt immer `quest_date = date.today() + 1` an.
- [bot/database.py](/home/kingbbq/src/DailySideQuest/bot/database.py:272) `mark_done()` sucht ebenfalls immer nach `quest_date = date.today()`.
- [bot/database.py](/home/kingbbq/src/DailySideQuest/bot/database.py:343) `get_completions_today()` filtert auch über `quest_date = date.today()`.

## Warum der Bug entsteht

Der Bot verwendet überall den Kalendertag als "heute". Die echte Fachlogik ist aber anders:

- Quest-Auswahl: nachts vorbereiten
- Quest-Ankündigung: morgens um 09:00
- Gültigkeit für User: von 09:00 bis zum nächsten Tag 09:00

Der aktuelle Code modelliert dieses `09:00`-Fenster aber nirgends explizit.

### Konkretes Beispiel

Angenommen, heute ist der `26.04.`:

1. Um `00:00` wird bereits die Quest mit `quest_date = 2026-04-27` vorbereitet.
2. Die Quest mit `quest_date = 2026-04-26` ist für User aber noch bis `09:00` aktiv.
3. Ein User sendet am `27.04. um 07:00` `/done`.
4. `mark_done()` verwendet `date.today() == 2026-04-27`.
5. Dadurch wird die Quest für `2026-04-27` als erledigt markiert, obwohl sie erst um `09:00` angekündigt wird.

Damit ist die Diagnose klar: Der Bot kennt keinen "aktiven Quest-Tag", sondern nur einen Kalendertag.

## Zusätzliche Auswirkungen

Das Problem betrifft nicht nur `/done`.

### `/quest`

Auch `get_todays_quest()` ist davon betroffen. Zwischen Mitternacht und 09:00 liefert `/quest` potenziell schon die neue Quest statt der noch aktiven alten.

### Anzeigen der Erledigungen

`get_completions_today()` hängt Erledigungen an denselben falschen Kalendertag. Dadurch können in der Quest-Anzeige die falschen Completion-Einträge auftauchen.

### Streak-Logik

`mark_done()` schreibt `last_completed_date = today` und berechnet die Lücke ebenfalls relativ zu `date.today()`. Wenn ein Completion im falschen Quest-Tag landet, ist auch die Streak semantisch falsch zugeordnet.

## Root Cause

Die eigentliche Ursache ist eine fehlende zentrale Zeitlogik:

- Der Scheduler arbeitet mit `Europe/Berlin`.
- Die Fachlogik sagt "Quest-Tag startet um 09:00".
- Die Datenbankmethoden arbeiten trotzdem nur mit `date.today()`.

Damit sind Scheduler-Zeitpunkt und Business-Logik nicht sauber mit den Lese- und Schreiboperationen in der DB verbunden.

# Vorgeschlagene Lösung

## Ziel

Den "aktiven Quest-Tag" zentral definieren und alle relevanten DB-Methoden darauf umstellen.

## Beste Lösung

In `bot/database.py` sollte eine zentrale Hilfsfunktion eingeführt werden, die den aktiven Quest-Tag in `Europe/Berlin` bestimmt:

- Vor `09:00` gilt noch der Vortag als aktiver Quest-Tag.
- Ab `09:00` gilt der aktuelle Kalendertag.

Zusätzlich sollte es eine zweite Hilfsfunktion geben, die den nächsten vorzubereitenden Quest-Tag liefert.

## Konkret betroffene Stellen

Diese Methoden sollten nicht mehr direkt `date.today()` verwenden:

- `get_todays_quest()`
- `mark_done()`
- `get_completions_today()`
- `pick_quest_for_tomorrow()`

## Erwartete Logik nach dem Fix

- `07:00` morgens: `/done` zählt noch auf die Quest vom Vortag.
- `09:00` morgens: `/quest` und `/done` beziehen sich ab dann auf die neue Quest.
- Die vorbereitete Quest darf schon in der DB existieren, aber erst ab dem Quest-Tageswechsel aktiv werden.

## Umsetzungsskizze

1. In `bot/database.py` einen zentralen Helper für den aktiven Quest-Tag auf Basis von `datetime.now(Europe/Berlin)` einführen.
2. Einen zweiten Helper für den "nächsten vorzubereitenden Quest-Tag" ergänzen.
3. Alle DB-Zugriffe auf Quests und Completions auf diese Helper umstellen.
4. Die Streak-Berechnung mit demselben Quest-Tag-Konzept synchronisieren.

## Warum diese Lösung die beste ist

- Sie behebt den Bug an der Ursache statt nur `/done` punktuell zu patchen.
- Sie hält die bestehende Datenstruktur intakt.
- Sie ist klein genug für einen gezielten Fix.
- Sie stellt sicher, dass `/quest`, `/done`, Completion-Anzeige und Streaks dieselbe Tagesdefinition verwenden.

## Nicht empfohlene Alternativen

- Nur `/done` anzupassen: würde `/quest` und die Completion-Anzeige weiter inkonsistent lassen.
- Die Quest erst um `09:00` in die Datenbank zu schreiben: unnötig invasiv, obwohl die vorhandene Vorab-Planung grundsätzlich brauchbar ist.
- Zusätzliche Statusfelder wie `is_active` oder `is_announced`: möglich, aber für dieses Problem komplizierter als nötig.
