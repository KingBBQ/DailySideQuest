# Feature-Plan: Nachhol-Funktion + Punkte-Score

> Verfasser: Claude Opus 4.7

## Was der User will (Zusammenfassung)

1. **Nachholen** verpasster Quests (z. B. nach 3 Streak-Tagen Tag 4 verpennen, am Tag 5 sowohl Tag 4 als auch Tag 5 abhaken).
2. **Zweiter Score** zusätzlich zum bestehenden Streak/`total_completed`:
   - Entweder ein simpler **Gesamtzähler** ("wer hat insgesamt am meisten gemacht"),
   - oder eine **gewichtete Punktezahl**, in der nachgeholte Quests **nur halb** zählen.
3. Motivations-Treiber: "so lohnt sich's für mich, heute die Liegestütze noch zu machen". Die heutige Quest soll auch *im Nachhinein* noch belohnt werden — aber nicht so stark, dass das Versäumte gleichwertig zur pünktlichen Erledigung wird.

## Vorhandene Bausteine

- `users.total_completed` zählt bereits jede Erledigung. Das ist der "simple Gesamtzähler" — den können wir direkt nutzen, müssen ihn aber nirgends anzeigen ergänzen.
- `users.streak` und `last_completed_date` werden in `Database.mark_done` gepflegt; Streak bricht bei Lücke > 2 Tagen ab.
- `daily_quests` hat eine Zeile pro `(chat_id, quest_date)` — Nachholen ist also möglich, weil die Quest des verpassten Tages weiterhin im DB steht.
- `completions` referenziert `quest_id`. Der Tag, an dem nachgeholt wird, ist getrennt vom `quest_date` der Quest — das passt strukturell für Nachhol-Logik.

## Vorschlag

### Kern-Idee

**Punkte-Score** als neue, **separate** Metrik einführen:

- Pünktliche Erledigung: **1,0 Punkt**
- Nachgeholte Erledigung (`quest_date` < heute): **0,5 Punkte**
- Streak bleibt **unverändert** — ein Nachholen heilt keinen gebrochenen Streak. Begründung: sonst wird Streak entwertet, und der Nutzer wollte ja explizit, dass das Nachgeholte "nur halb" zählt.
- Der bestehende Zähler `total_completed` bleibt als simple Gesamtzahl ("wie viele Quests hat XY je gemacht") und wird auch bei Nachhol-Erledigungen um 1 hochgezählt.

Damit hat die Statistik künftig drei klar getrennte Größen:

| Anzeige | Was es ist |
|---------|-----------|
| 🔥 Streak | wie heute: aktuelle Lauf-Serie |
| ✅ Gesamt | jede Erledigung zählt als 1, egal ob pünktlich oder nachgeholt |
| ⭐ Punkte | pünktlich = 1,0 / nachgeholt = 0,5 |

### Beispiel des Users durchgespielt

3 Tage hintereinander erledigt → Tag 4 verpasst → Tag 5 erledigt → Tag 4 nachgeholt:

- Streak: bricht bei Tag 4 (Lücke), startet bei Tag 5 mit 1, durchs Nachholen nicht beeinflusst.
- Gesamt: 5 (jede Erledigung = 1).
- Punkte: 1+1+1 (Tag 1–3 pünktlich) + 1 (Tag 5 pünktlich) + 0,5 (Tag 4 nachgeholt) = **4,5**.

Das deckt sich mit dem "ungefähr 4"-Wunsch des Users und ist nachvollziehbar simpel.

### Nachholen — Bedienung

Neuer Befehl: **`/nachholen`** (deutsch, passt zur restlichen UI).

- Aufruf ohne Argument → Bot listet die offenen, nachholbaren Quests der letzten **7 Tage** in der Gruppe als nummerierte Liste:
  ```
  📥 Offene Quests zum Nachholen:
  1. 24.04. — Sing ein ganzes Lied laut durch …
  2. 22.04. — Geh heute 10.000 Schritte
  ```
  Plus Hinweis: `/nachholen <Nummer>` oder `/nachholen <TT.MM.>`
- Aufruf mit Nummer (`/nachholen 1`) oder Datum (`/nachholen 24.04.`) → Erledigung wird mit `is_retroactive=1` gebucht, Score +0,5, Gesamt +1, Streak unangetastet.
- Foto-Variante analog `/done`: `MessageHandler` mit `CaptionRegex(r"^/nachholen")` registrieren.
- Nicht nachholbar:
  - Datum > 7 Tage zurück (Fenster fest)
  - Datum ≥ heute (dafür gibt's `/done`)
  - Quest existiert nicht (Gruppe war an dem Tag noch nicht registriert)
  - User hat *diese* Quest schon erledigt (egal ob pünktlich oder nachgeholt)
- Erfolgs-Antwort: `📥 Quest vom 24.04. nachgeholt — +0,5 ⭐` (kein Streak, keine 🏆-Vergabe; der Erst-Badge bleibt für Pünktliche reserviert).

### `/quest` Erweiterung

Wenn der User noch offene nachholbare Quests hat, am Ende der `/quest`-Antwort eine kleine Zeile:

```
📥 _Du hast 2 offene Quests aus den letzten Tagen — /nachholen_
```

Nur einblenden, wenn es *für den anfragenden User* tatsächlich was nachzuholen gibt. Verhindert Spam-Anzeige in großen Gruppen.

### `/stats` Erweiterung

Bestehende Rangliste um eine Punkte-Zeile ergänzen:

```
🥇 *Anna*
   🔥 Streak: 7  ✅ Gesamt: 24  ⭐ Punkte: 21,5  🏆 Erster: 5
   🔥🔥
```

Sortier-Reihenfolge: weiterhin nach `streak DESC, total_completed DESC`. Kein zweiter Befehl, keine Tab-Trennung — alles in einer Übersicht. Wer den Punkte-Wettbewerb will, sieht die Zahl direkt.

### `weekly_summary` Erweiterung

Im Wochenrückblick zusätzlich die Top-3 nach **Wochenpunkten** (also pünktlich/nachgeholt der letzten 7 Tage). Damit hat der zweite Score auch wöchentliche Sichtbarkeit.

## Umsetzungs-Plan im Code

### 1. Schema-Migration (`bot/database.py`)

In `Database.init`, in den bestehenden `try/except`-ALTER-Block ergänzen:

```python
"ALTER TABLE completions ADD COLUMN is_retroactive INTEGER DEFAULT 0",
"ALTER TABLE completions ADD COLUMN quest_date_completed TEXT",  # speichert das quest_date der nachgeholten Quest
"ALTER TABLE users ADD COLUMN score REAL DEFAULT 0",
```

`quest_date_completed` ist redundant zu `daily_quests.quest_date` über den Join, vereinfacht aber Streak/Wochen-Auswertungen ohne Join — pragmatisch.

Migration ist additiv, keine Datenlöschung, bestehende Zeilen bekommen Defaults.

### 2. `Database.mark_done` anpassen

Score +1,0 bei pünktlicher Erledigung; `total_completed` wird wie heute +1 hochgezählt:

```python
"""UPDATE users SET
       streak = ?,
       last_completed_date = ?,
       total_completed = total_completed + 1,
       total_first = total_first + ?,
       score = score + 1.0
   WHERE user_id = ? AND chat_id = ?"""
```

### 3. Neue Methode `Database.mark_retroactive`

```python
async def mark_retroactive(
    self, chat_id: int, user_id: int, quest_date: str,
    photo_file_id: Optional[str] = None,
) -> Dict
```

- Validiert: `quest_date` zwischen `_current_quest_date() - 7 Tage` (exklusive heute) und `_current_quest_date() - 1`.
  *(Hinweis: `_current_quest_date` ist der Helfer aus dem Bug-Fix-Plan — falls noch nicht gemerged, hier `date.today()` als Fallback bis dahin.)*
- Lädt `daily_quests` für `(chat_id, quest_date)`. Existiert nicht → Status `no_quest_for_date`.
- Prüft, ob User schon Erledigung hat → Status `already_done`.
- Insert in `completions` mit `is_retroactive=1`, `is_first=0` (nie Erst-Badge bei Nachholen), `quest_date_completed=quest_date`.
- `users.total_completed += 1`, `users.score += 0.5`. **Kein** Update von `streak` und `last_completed_date`.
- Rückgabe: `{"status": "ok", "score_added": 0.5}`.

### 4. Neue Methode `Database.list_retroactive_candidates`

```python
async def list_retroactive_candidates(self, chat_id: int, user_id: int) -> List[Dict]
```

- Holt alle `daily_quests` mit `quest_date` in `[heute-7, heute-1]` für `chat_id`.
- LEFT JOIN auf `completions` für genau diesen User; nur Zeilen ohne Completion.
- Rückgabe: `[{"quest_date": "...", "text": "...", "category": "..."}]`, sortiert absteigend nach Datum.

### 5. Neuer Handler `bot/handlers/quest.py::nachholen`

- Gruppen-Pflicht via `_require_group`.
- `register_user`.
- Ohne Argument → `list_retroactive_candidates` aufrufen, Liste rendern. Leer → "Keine offenen Quests aus den letzten 7 Tagen 🎉".
- Mit Argument:
  - Reine Zahl 1–7 → Index in die Kandidatenliste.
  - Datumsformat `TT.MM.` oder `TT.MM.JJJJ` → ISO konvertieren.
  - Sonst → Hilfetext.
- `mark_retroactive` aufrufen, Status auswerten:
  - `ok` → `📥 Quest vom {datum} nachgeholt! +0,5 ⭐`
  - `already_done` → `Du hast diese Quest schon erledigt.`
  - `no_quest_for_date` → `Für den {datum} gibt es keine Quest in dieser Gruppe.`
  - `out_of_window` → `Du kannst nur Quests der letzten 7 Tage nachholen.`

### 6. Registrierung in `bot/main.py`

```python
app.add_handler(CommandHandler("nachholen", nachholen))
app.add_handler(
    MessageHandler(filters.PHOTO & filters.CaptionRegex(r"^/nachholen"), nachholen)
)
```

### 7. `/quest`-Hinweiszeile

In `show_quest`: nach dem bestehenden Body einmal `list_retroactive_candidates(chat_id, user.id)` aufrufen. Wenn `len > 0`, eine Zeile anhängen mit Anzahl. Kosten: ein zusätzlicher kleiner Query pro `/quest`-Aufruf — vertretbar.

### 8. `/stats` erweitern

`Database.get_stats` SELECT um `score` ergänzen, im Handler-Renderer `⭐ Punkte: {score:.1f}` einfügen. Sortierung lassen wie sie ist.

### 9. `weekly_summary` erweitern

`Database.get_weekly_stats` um eine neue Liste `weekly_score` ergänzen (Summe aus `completions.is_retroactive`-Gewichtung der letzten 7 Tage je User). Im Scheduler-Output als zusätzliche Top-3-Sektion zeigen, falls nicht leer:

```
⭐ *Top-Punkte diese Woche:*
🥇 Anna: 4,5
🥈 Ben: 3,0
```

### 10. `bot/handlers/group.py::HILFE_TEXT`

Neue Zeile zwischen `/done` und `/propose`:

```
/nachholen [Nr|TT.MM.] – Verpasste Quest der letzten 7 Tage nachholen (zählt 0,5 ⭐)
```

## Bewusst nicht enthalten

- **Streak heilen durchs Nachholen**: technisch machbar (Streak neu durchrechnen aus completion-Historie), aber widerspricht dem User-Ansatz "nur halb anrechnen". Streak bleibt der "Pünktlichkeits-Score", Punkte sind der "Fleiß-Score". Klare Trennung.
- **Konfigurierbares Nachhol-Fenster pro Gruppe**: 7 Tage hartcodiert, analog zum Konstantenstil im Repo (`CATEGORY_EMOJI`, Berlin-Zeitzone).
- **Erst-Badge fürs Nachholen**: würde den 🏆-Wettbewerb verwässern. Ausgeschlossen.
- **Nachhol-Punkte für `proposed_by`**: keine Sonderbehandlung — eine vorgeschlagene Quest ist beim Nachholen genauso 0,5 wie eine Pool-Quest.

## Aufwand / Umfang

- 1 Migration (3 ALTER-Statements)
- 2 neue DB-Methoden + 2 angepasste DB-Methoden
- 1 neuer Handler + 2 leichte Handler-Erweiterungen (`show_quest`, `show_stats`)
- 1 Scheduler-Erweiterung (`weekly_summary`)
- 1 neuer `CommandHandler` + 1 neuer `MessageHandler` in `main.py`
- Hilfe-Text-Update

Keine Schema-Brüche, keine Backfills nötig, alle Tests (gibt's eh nicht) bleiben grün. Roll-out per Container-Restart, beim ersten `init`-Lauf greifen die Migrationen.

## Offene Punkte, die ich bewusst ohne Rückfrage entschieden habe

- **Befehlsname**: `/nachholen` statt `/done <datum>`. Begründung: weniger Risiko, dass jemand das Datum verschluckt und eine pünktliche Erledigung in Richtung Vergangenheit verbucht.
- **Punkte als `REAL`** in der DB (statt Integer mit Faktor 2). Spart Sonder-Anzeigelogik und ist für die Größenordnung der App völlig ausreichend.
- **Streak nicht heilen**. Wenn sich später herausstellt, dass das doch gewünscht ist, lässt sich das in `mark_retroactive` nachträglich aktivieren — Schema bleibt gleich.
- **Score wird in der Anzeige auf eine Nachkommastelle gerundet** (`{:.1f}`), in der DB präzise gespeichert.
