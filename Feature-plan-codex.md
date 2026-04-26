# Feature-Plan

## Zielbild

Ich schlage vor, den Wunsch in zwei klar getrennte Features zu zerlegen:

1. Nachholen verpasster Quests
2. Zusätzliche Wertung für alle erledigten Quests, damit Nachholen messbar belohnt wird

Die bestehende Streak bleibt dabei erhalten und behält ihre heutige Bedeutung: Sie misst pünktliche Regelmäßigkeit. Das Nachholen sollte diese Streak nicht nachträglich "reparieren", sonst verliert sie ihre Aussagekraft.

## Bestehender Stand im Code

### Bereits vorhanden

- In [bot/database.py](/home/kingbbq/src/DailySideQuest/bot/database.py:75) gibt es in `users` bereits `streak`, `last_completed_date`, `total_completed` und `total_first`.
- `total_completed` zählt schon heute jede erfolgreiche `/done`-Aktion.
- `completions` referenziert über `quest_id` eine konkrete Quest in `daily_quests`.
- Dadurch ist die Historie pro Quest grundsätzlich vorhanden und Nachholen ist strukturell möglich.

### Aktuelle Grenzen

- Es gibt nur `mark_done()` für die aktive Quest des Tages.
- Es gibt keinen Befehl, um eine ältere Quest gezielt abzuhaken.
- Es gibt keine getrennte Punktelogik für pünktige vs. nachgeholte Erledigungen.
- `/stats` zeigt nur `streak`, `total_completed` und `total_first`.

## Mein Umsetzungsvorschlag

## 1. Neuer Score zusätzlich zur Streak

Ich würde einen zweiten Score einführen, statt die bestehende Streak umzudefinieren.

### Vorschlag für die Wertung

- Pünktlich erledigte Quest: `1.0` Punkt
- Nachgeholte Quest: `0.5` Punkte

Zusätzlich bleibt:

- `total_completed`: zählt jede erledigte Quest als Ganzzahl
- `streak`: nur für aktuelle Regelmäßigkeit

Damit bekommt der Bot drei unterschiedliche Metriken:

- `streak`: Wer ist gerade konstant dran
- `total_completed`: Wer hat insgesamt wie viele Quests gemacht
- `score`: Wie wertvoll waren diese Erledigungen im Spielsystem

Das passt inhaltlich gut zu deinem Beispiel: Wer eine Quest verpasst, soll fürs Nachholen noch belohnt werden, aber weniger als für pünktiges Abschließen.

## 2. Nachholen als eigener Befehl

Ich würde keinen komplizierten Sondermodus in `/done` einbauen, sondern einen eigenen Befehl ergänzen:

- `/nachholen`

Das ist für User verständlicher und reduziert Spezialfälle in der bestehenden `/done`-Logik.

### Verhalten von `/nachholen`

- Ohne Argument: zeigt offene nachholbare Quests an
- Mit Auswahl: markiert eine ältere Quest als erledigt

Beispiel:

- `/nachholen`
- `/nachholen 1`
- optional später auch `/nachholen 24.04.`

## 3. Nachholfenster begrenzen

Ich würde das Nachholen bewusst auf die letzten `7` Quest-Tage begrenzen.

Warum:

- verhindert unendliches Altdaten-Abhaken
- hält die UI überschaubar
- motiviert trotzdem noch kurzfristiges Nachholen

## Datenmodell

## Bestehendes Modell nutzen

Die vorhandenen Tabellen reichen fast aus, aber für die neue Logik würde ich kleine additive Erweiterungen vorsehen.

### `users`

Neue Spalte:

- `score REAL DEFAULT 0`

Damit kann der gewichtete Gesamtwert direkt gespeichert und schnell in `/stats` angezeigt werden.

### `completions`

Neue Spalte:

- `is_retroactive INTEGER DEFAULT 0`

Damit ist pro Completion eindeutig sichtbar, ob sie pünktlich oder nachgeholt war.

Optional sinnvoll:

- `credited_score REAL DEFAULT 1.0`

Das wäre robuster als die Punkte immer wieder indirekt herzuleiten. Dann ist pro Eintrag exakt gespeichert, wie viel diese Erledigung gezählt hat.

Ich würde `credited_score` tatsächlich mit aufnehmen, weil das spätere Auswertungen vereinfacht und Ranking-Logik stabil hält.

## Konkreter Ablauf

## Pünktliche Erledigung

`mark_done()` bleibt der Einstieg für die aktive Quest.

Zusätzlich zur aktuellen Logik würde der Bot:

- `total_completed += 1`
- `score += 1.0`
- Completion mit `is_retroactive = 0`
- Completion mit `credited_score = 1.0`

## Nachgeholte Erledigung

Neue Methode, z. B. `mark_quest_retroactive(chat_id, user_id, quest_date, photo_file_id=None)`.

Sie würde:

1. prüfen, ob es für dieses Datum in der Gruppe eine Quest gibt
2. prüfen, ob sie innerhalb des Nachholfensters liegt
3. prüfen, ob der User diese Quest noch nicht erledigt hat
4. einen Completion-Eintrag anlegen
5. `total_completed += 1`
6. `score += 0.5`
7. `streak` nicht verändern
8. `total_first` nicht verändern

Das halte ich für die sauberste Trennung.

## UI-Vorschlag

## `/stats`

`/stats` sollte den neuen Score sichtbar machen.

Beispiel:

`🔥 Streak: 3  ✅ Gesamt: 5  ⭐ Score: 4.5  🏆 Erster: 1`

Damit sind sowohl "alles erledigt" als auch "pünktlich erledigt" sichtbar.

## `/quest`

Optional würde ich am Ende von `/quest` einen kleinen Hinweis ergänzen, wenn der User offene Nachhol-Quests hat:

`📥 Du hast noch 2 nachholbare Quests. Nutze /nachholen`

Das erhöht die Sichtbarkeit des Features stark.

## `/nachholen`

Ohne Parameter sollte der Bot eine kurze Liste offener Quests anzeigen, z. B.:

1. `25.04. – Mach 50 Liegestütze`
2. `24.04. – Geh 10.000 Schritte`

Danach kann der User per Nummer auswählen.

Das ist einfacher als sofort Datumseingaben zu erzwingen.

## Wöchentliche Zusammenfassung

In [bot/scheduler.py](/home/kingbbq/src/DailySideQuest/bot/scheduler.py:90) würde ich den Wochenrückblick ebenfalls ergänzen.

Aktuell zeigt er:

- meiste Quests der Woche
- aktuelle Top-Streaks

Zusätzlich sinnvoll:

- Top-Scores der Woche oder Gesamt-Score-Ranking

So wird das Nachholen auch im Gruppenerlebnis sichtbar.

## Warum ich diese Variante vorschlage

### Vorteile

- minimale, additive Schemaänderung
- bestehende Streak-Logik bleibt verständlich
- Nachholen wird belohnt, aber nicht gleich stark wie pünktliche Erledigung
- `total_completed` deckt bereits deinen Wunsch nach einem einfachen Gesamtzähler ab
- eigener Score löst den Wunsch nach einer Mischwertung sauberer als ein Umbau der Streak

### Bewusste Entscheidung

Ich würde die Streak nicht rückwirkend durch Nachholen heilen.

Begründung:

- Streak soll Pünktlichkeit messen
- Nachholen soll Fleiß messen
- zwei getrennte Metriken sind verständlicher als eine künstlich gemischte Kennzahl

## Technischer Plan

1. In `Database.init()` Migrationen für `users.score`, `completions.is_retroactive` und `completions.credited_score` ergänzen.
2. `mark_done()` erweitern, damit pünktliche Erledigungen auch Score verbuchen.
3. Neue DB-Methode für nachgeholte Erledigungen ergänzen.
4. Neue DB-Methode bauen, die nachholbare Quests der letzten 7 Tage liefert.
5. In `bot/handlers/quest.py` einen neuen Handler für `/nachholen` ergänzen.
6. In `bot/main.py` den neuen Command registrieren.
7. `/stats` um den Score erweitern.
8. Optional `/quest` um einen Nachhol-Hinweis ergänzen.
9. Optional den Wochenrückblick um Score-Auswertung ergänzen.

## Fazit

Die sinnvollste Umsetzung ist aus meiner Sicht:

- Streak unverändert lassen
- Nachholen als eigenen Befehl einführen
- `total_completed` weiter nutzen
- zusätzlich einen gewichteten `score` einführen, bei dem nachgeholte Quests nur halb zählen

Damit bekommt der Bot genau den Anreiz, den du beschrieben hast: Nachholen lohnt sich, aber pünktiges Erledigen bleibt mehr wert.
