# BugFix-Analysis

## Bug: Quest wird vorzeitig angekündigt und kann zu früh als "done" markiert werden

### Beobachtung

Der User meldet, dass um 9 Uhr die Quest für den aktuellen Tag angekündigt wird. Wenn man jedoch bereits um 7 Uhr morgens `/done` macht, eine andere Quest als erwartet wird – nämlich bereits die Quest des Folgetages, obwohl diese noch gar nicht öffentlich angekündigt wurde.

---

## #Analyse

### Ablauf in der Zeitlinie

**Montagabend 23:59**:
- Heute ist `date.today() = 2026-04-27` (Montag)
- Es gibt eine Quest für `quest_date = 2026-04-27` in der DB

**Dienstag 00:00:01** – `pick_quest_for_tomorrow` wird ausgeführt:

```python
# scheduler.py:40-50, database.py:196-243
tomorrow = (date.today() + timedelta(days=1)).isoformat()
# date.today() = 2026-04-27 (Dienstag, weil Mitternacht bereits vorbei ist)
# tomorrow = 2026-04-28 (Mittwoch)
```

Die Quest wird mit `quest_date = 2026-04-28` in `daily_quests` eingefügt.

**Dienstag 00:00:01 bis 23:59:59**:
- `quest_date` Wert in der DB ist **2026-04-28** (Mittwoch)

**Dienstag 09:00** – `announce_quests_morning` wird ausgeführt:

```python
# scheduler.py:53-87
quest = await db.get_todays_quest(chat_id)
# get_todays_quest query: WHERE quest_date = date.today()
# date.today() = 2026-04-28 (Dienstag?) — NEIN!
# date.today() = 2026-04-28? ... Moment.
```

**Korrekter Ablauf:**

| Zeit | `date.today()` | `tomorrow` in `pick_quest` | `quest_date` in DB |
|------|----------------|---------------------------|-------------------|
| **Dienstag 00:00:01** | `2026-04-28` (Dienstag!) | `2026-04-29` (Mittwoch) | `2026-04-29` |
| **Dienstag 09:00** | `2026-04-28` | — | Quest: `2026-04-29` |
| **Dienstag 07:00** | `2026-04-28` | — | Quest: `2026-04-29` |

`get_todays_quest` sucht nach `quest_date = 2026-04-28` → **keine Quest gefunden** → "Für heute gibt es noch keine Quest! Sie kommt um 9 Uhr."

Aber warten Sie – das passt so nicht. Wenn es am Montag um 9 Uhr funktioniert, muss die Quest am **Montag um 00:00** für **Montag** eingefügt werden. Dann ist das Datum korrekt.

**Korrekte Zeitlinie (wenn alles richtig läuft):**

| Zeit | `date.today()` | `tomorrow` in `pick_quest` | `quest_date` in DB |
|------|----------------|---------------------------|-------------------|
| **Montag 00:00:01** | `2026-04-27` (Montag!) | `2026-04-28` (Dienstag) | `2026-04-28` |

Hmm, das stimmt auch nicht. `pick_quest_for_tomorrow` wird um 00:00 ausgeführt. Der Scheduler läuft:

```python
# scheduler.py:16-20
jq.run_daily(
    pick_quests_midnight,
    time=time(0, 0, 0, tzinfo=BERLIN),  # Mitternacht
)
```

Die Funktion `pick_quests_midnight` löst bei Mitternacht aus.

**Aber:** Die telegram Job Queue hat ein bekanntes Verhalten. Die Jobs werden **in der lokalen Zeitzone des Servers** ausgeführt, aber `context.bot_data` usw. verwenden `datetime.now()`. 

**Das eigentliche Problem ist in `pick_quest_for_tomorrow`:**

```python
async def pick_quest_for_tomorrow(self, chat_id: int) -> Optional[str]:
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
```

`date.today()` verwendet die **Server-Zeit**, NICHT die Telegram Bot Timezone. Wenn der Server in einer anderen Zeitzone läuft als `Europe/Berlin`, kann es zu einem Versatz kommen.

**Beispiel:**
- Server steht auf UTC (kein Zeitzone-Offset)
- In Berlin ist es 00:00 (27. April)
- Server ist in UTC: 23:00 (26. April)
- `date.today()` = 26. April (Server)
- `tomorrow` = 27. April (Montag) ← korrektes Datum!

**OK, das funktioniert zufällig. Aber was ist mit der 9-Morgen-Schaltung?**

```python
# scheduler.py:23-27
jq.run_daily(
    announce_quests_morning,
    time=time(9, 0, 0, tzinfo=BERLIN),
    name="announce_quests_morning",
)
```

Wenn der Server UTC ist und das Telegram-Job-System die `tzinfo=BERLIN` berücksichtigt:
- Job feuert um 9:00 Berlin = 7:00 UTC
- Zum Zeitpunkt des Feuerns ist in Berlin 09:00 → `date.today()` = 27. April
- Die Quest wurde um 00:00 Berlin (23:00 UTC) mit `quest_date = 27. April` eingefügt
- `get_todays_quest` sucht nach `27. April` → **Quest gefunden!**

**Das funktioniert also. Dann wo ist das Problem?**

---

### Das Problem: `date.today()` für Quest-Auswahl vs. Ankündigung

Schauen wir uns den genauen Flow an:

**Schritt 1: Mittägliche Quest-Auswahl** (database.py:196-243)

```python
async def pick_quest_for_tomorrow(self, chat_id: int) -> Optional[str]:
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
```

Hier wird `date.today()` verwendet. Die Funktion heißt "für morgen", aber:

- Die Funktion wird von `pick_quests_midnight` aufgerufen, das um **00:00** feuert
- Um 00:00 ist `tomorrow` also tatsächlich der nächste Tag
- **ABER:** Die Quest ist für *morgen*, nicht für heute!

**Schritt 2: Morgendliche Ankündigung** (scheduler.py:53-87)

```python
async def announce_quests_morning(context):
    quest = await db.get_todays_quest(chat_id)
```

`get_todays_quest` sucht nach `quest_date = date.today()`. 

**Beispiel:**
- **Dienstag 09:00**: `announce_quests_morning` sucht `quest_date = '2026-04-28'` (Dienstag)
- Die Quest wurde **Montag 00:00** eingefügt: `date.today()` = Montag → `tomorrow` = Dienstag → `quest_date = '2026-04-28'` (Dienstag) ← **passt!**
- **ODER:** Die Quest wurde **Dienstag 00:00** eingefügt: `date.today()` = Dienstag → `tomorrow` = Mittwoch → `quest_date = '2026-04-29'` (Mittwoch) ← **passt NICHT!**

### Das eigentliche Problem: Timing-Lücke!

Die Quest wird um **00:00** für **einen Tag später** eingefügt. Das bedeutet:
- Montags um 00:00 wird die Quest für dienstag eingefügt
- Dienstdags um 00:00 wird die Quest für donnerstag eingefügt
- Die Quest für donnerstag (eingefügt mittwochs um 00:00) wird donnerstags um 09:00 angekündigt – **korrekt!**

**ABER:** Die Quest für morgen (eingefügt am Vortag um 00:00) wird ebenfalls am nächsten Tag um 09:00 als "heutige" Quest erkannt. Sie ist also **die ganze Zeit über als "done" markierbar, bevor sie offiziell angekündigt wird.**

### Konkreter Bug-Szenario:

| Zeit | Event | `quest_date` in DB |
|------|-------|-------------------|
| **Dienstag 00:00** | `pick_quest_for_tomorrow` wählt Quest für **Mittwoch** aus | `quest_date = '2026-04-29'` |
| **Dienstag 07:00** | User gibt `/done` ein. `mark_done` sucht `quest_date = '2026-04-28'` (Dienstag) | **Keine Quest gefunden!** status = `no_quest` |
| **Dienstag 09:00** | `announce_quests_morning` ruft `get_todays_quest` auf. `get_todays_quest` sucht `quest_date = '2026-04-28'`. **Keine Quest für Dienstag!** | **Keine Quest gefunden!** |

**Warten... das erklärt den Bug nicht. Es würde bedeuten, es gibt KEINE Quest am jeweiligen Tag.**

Lassen Sie mich das nochmal durchdenken. 

**Szenario:**
- **Dienstag 09:00** – Die Quest vom **Montag 00:00** wird angezeigt. Diese Quest hat `quest_date = '2026-04-28'` (Dienstag).
- Der user gibt um 07:00 **Mittwoch** `/done` ein. `mark_done` sucht nach `quest_date = '2026-04-28'` (weil `tomorrow` am Montag = Dienstag = 2026-04-28). **Aber am Mittwoch gibt es eine neue Quest mit `quest_date = '2026-04-29'`!**

**Das ist der Bug!**

1. **Montag 00:00**: Quest für Dienstag → `quest_date = 2026-04-28` (Dienstag)
2. **Dienstag 09:00**: Quest für Dienstag wird angezeigt
3. **Dienstag 00:00**: Quest für Mittwoch → `quest_date = 2026-04-29` (Mittwoch) 
4. **Mittwoch 07:00**: User gibt `/done` ein. `mark_done` sucht `quest_date = date.today() = 2026-04-29`. Die Quest für Mittwoch existiert bereits! Der User erfüllt die **Mittwoch-Quest**, obwohl sie noch nicht um 9:00 Mittwoch angesagt wurde!

**Der Bug bestätigt sich:** Die Quest wird um Mitternacht automatisch ausgewählt und kann damit **vor der offiziellen Ankündigung um 9:00** als "done" markiert werden!

---

## #Vorgeschlagene Lösung

### Kernproblem

Die Quests werden `daily_quests` mit dem Datum des Ziel-Tages gespeichert, und `mark_done` prüft nur `date.today()`. Eine Quest für morgen existiert also schon bevor sie angekündigt wird.

### Lösungsmöglichkeiten

#### Option A: Quest nur markieren, wenn am aktuellen Datum mindestens 9:00 erreicht ist (Empfohlen)

In `mark_done` wird zusätzlich zur Quest-Existenz geprüft, ob es `09:00 Berlin` oder später ist. Vor 9:00 wird dieselbe Logik wie "no_quest" angewandt.

```python
async def mark_done(self, chat_id: int, user_id: int, photo_file_id: Optional[str] = None) -> Dict:
    today = date.today().isoformat()
    
    # Neu: Vor 9:00 Berlin geht nichts
    now_berlin = datetime.now(BERLIN)
    if now_berlin.hour < 9:
        return {"status": "early", "message": "Quests können erst ab 9:00 Uhr erledigt werden!"}
    
    # ... restliche Logik wie gehabt
```

**Vorteile:** Einfach, direkt am Problem, benötigt keine DB-Änderungen
**Nachteile:** User können am Morgen nicht früher arbeiten (ist aber beabsichtigt)

#### Option B: Quest als "nicht freigeschaltet" markieren

Neuer Spalte `is_published INTEGER DEFAULT 0` in `daily_quests`. Wird im `announce_quests_morning` auf `1` gesetzt.

`mark_done` prüft zusätzlich `AND is_published = 1`.

**Vorteile:** Sauberer, explizit
**Nachteile:** Erfordert DB-Änderung und Migration

#### Option C: Zwei getrennte Felder für "ausgewählt" und "angekündigt"

**Vorteile:** Maximal flexibel
**Nachteile:** Überkompliziert

### Empfohlene Lösung: Option A mit Option B kombiniert

Am besten ist eine Kombination:

1. Datenbank-Migration: Neue Spalte `is_published` in `daily_quests`
2. `announce_quests_morning` setzt `is_published = 1`
3. `mark_done` prüft `AND is_published = 1`

```sql
ALTER TABLE daily_quests ADD COLUMN is_published INTEGER DEFAULT 0;
```

```python
# In announce_quests_morning, nach der Ankündigung:
await db.execute(
    "UPDATE daily_quests SET is_published = 1 WHERE quest_date = ?",
    (today,),
)

# In mark_done, bei der Quest-Suche:
async with db.execute(
    "SELECT id FROM daily_quests WHERE chat_id = ? AND quest_date = ? AND is_published = 1",
    (chat_id, today),
) as cursor:
    ...
```

Dadurch wird verhindert, dass Quests vor ihrer offiziellen Ankündigung (um 9:00) als "done" markiert werden.

### Zusätzliche Verbesserung: pick_quest_for_tomorrow umbenennen

Die Funktion `pick_quest_for_tomorrow` ist verwirrend benannt. Sie wählt eigentlich Quest für `today + 1` (also für `date.today() + 1`). Der Name ist korrekt, aber das Verhalten sollte dokumentiert werden:

```python
async def pick_quest_for_tomorrow(self, chat_id: int) -> Optional[str]:
    """Wählt Quest für den nächsten Tag (wird am nächsten Tag um 9 Uhr angekündigt)."""
    target_date = (date.today() + timedelta(days=1)).isoformat()
    # ...
```

### Migration für existing DB

Für bestehende Datenbanken:
```sql
ALTER TABLE daily_quests ADD COLUMN is_published INTEGER DEFAULT 0;
UPDATE daily_quests SET is_published = 1 WHERE quest_date = date('now');
```
