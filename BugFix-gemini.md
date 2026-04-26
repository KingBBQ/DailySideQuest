# Analyse: Quest-Rollover Bug

## Problembeschreibung
Der Nutzer hat festgestellt, dass Quests, die eigentlich von 9:00 Uhr bis 9:00 Uhr am Folgetag laufen sollten, bei einer Erledigung zwischen 00:00 Uhr und 09:00 Uhr fehlerhaft zugeordnet werden. 

Wenn ein Nutzer um 07:00 Uhr morgens `/done` eingibt, wird nicht die aktuell aktive Quest (vom Vortag 09:00 Uhr) als erledigt markiert, sondern bereits die neue Quest des Kalendertages, obwohl diese erst um 09:00 Uhr angekündigt wird.

## Ursachenanalyse
Die Analyse des Codes in `bot/database.py` und `bot/scheduler.py` hat folgende Ursachen ergeben:

1.  **Kalenderdatum vs. Logisches Datum:** Die Methoden `get_todays_quest`, `mark_done` und `get_completions_today` verwenden intern `date.today().isoformat()`. Dieses Datum springt um 00:00 Uhr (Mitternacht) auf den nächsten Tag um.
2.  **Quest-Generierung:** Der Scheduler erzeugt bereits um Mitternacht die Quest für den übernächsten Tag (`pick_quest_for_tomorrow`). Das bedeutet, dass zum Zeitpunkt 07:00 Uhr bereits eine Quest mit dem aktuellen Kalenderdatum in der Datenbank existiert.
3.  **Fehlzuordnung:** Da `mark_done` das aktuelle Kalenderdatum nutzt, greift es auf die Quest zu, die für diesen Kalendertag hinterlegt ist. Da der "Quest-Tag" aber erst um 09:00 Uhr beginnt, ist dies aus Sicht des Nutzers die "zukünftige" Quest. Die eigentlich noch aktive Quest des Vortags (09:00 bis 09:00) wird ignoriert.
4.  **Streak-Logik:** Auch die Berechnung der Streaks basiert auf dem Kalenderdatum, was bei Erledigungen vor 09:00 Uhr zu Inkonsistenzen führen kann.

## Vorgeschlagene Lösung

Die Lösung besteht darin, ein "logisches Quest-Datum" einzuführen. Ein Tag zählt für den Bot erst ab 09:00 Uhr als "neuer Tag". Alles zwischen 00:00 Uhr und 08:59 Uhr gehört logisch noch zum Vortag.

### 1. Zentrale Methode für das logische Datum
In der `Database`-Klasse sollte eine Hilfsmethode eingeführt werden, die das aktuelle Datum unter Berücksichtigung des 9-Uhr-Offsets berechnet:

```python
def get_logical_date(self):
    # Nutzt die Berlin-Zeit für konsistente Ergebnisse
    from datetime import datetime
    import pytz
    berlin = pytz.timezone("Europe/Berlin")
    now = datetime.now(berlin)
    # Wenn es vor 9 Uhr ist, ziehe einen Tag ab
    if now.hour < 9:
        return (now - timedelta(days=1)).date()
    return now.date()
```

### 2. Anpassung der Datenbank-Abfragen
Alle Stellen, die `date.today()` für die Identifizierung der "heutigen" Quest nutzen, müssen auf diese neue Logik umgestellt werden:

*   `get_todays_quest(self, chat_id)`
*   `mark_done(self, chat_id, user_id, ...)`
*   `get_completions_today(self, chat_id)`
*   `get_weekly_stats(self, chat_id)` (hier muss der Zeitraum ggf. auch angepasst werden)

### 3. Anpassung der Streak-Berechnung
In `mark_done` muss der `gap`-Vergleich ebenfalls auf dem logischen Datum basieren, damit eine Quest, die um 07:00 Uhr (logisch gestern) erledigt wurde, korrekt mit einer Quest am nächsten Tag (nach 09:00 Uhr) verknüpft wird.

### 4. Scheduler Konsistenz
Der Scheduler in `bot/scheduler.py` läuft bereits mit der `BERLIN`-Zeitzone. Die Umstellung der Datenbank-Logik auf ein logisches Datum sorgt dafür, dass die um 09:00 Uhr angekündigte Quest exakt diejenige ist, die bis zum nächsten Morgen um 08:59 Uhr über `/done` ansprechbar bleibt.
