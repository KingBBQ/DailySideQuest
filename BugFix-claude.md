# Analyse

## Vermutung des Users

> Eine "quest" geht von 9 Uhr bis 9 Uhr. Wenn ich um 7 Uhr morgens `/done` mache, wird die neue Quest (noch nicht öffentlich) bereits als erledigt markiert. Die alte ist aber noch aktiv.

**Die Vermutung trifft zu.** Der Bug existiert genau so.

## Ablauf im Detail

Die drei beteiligten Komponenten:

1. **`scheduler.pick_quests_midnight`** läuft täglich um **00:00 Europe/Berlin** und ruft `Database.pick_quest_for_tomorrow` für jede Gruppe auf.
2. **`scheduler.announce_quests_morning`** läuft täglich um **09:00 Europe/Berlin** und postet die Quest, die laut `get_todays_quest` zum heutigen Kalendertag gehört.
3. **`Database.mark_done`** wird durch `/done` getriggert und sucht die Quest über `quest_date = date.today()`.

Spielen wir einen Tag `D` durch (alle Zeiten Berlin):

| Zeit | Aktion | Effekt in `daily_quests` |
|------|--------|--------------------------|
| 00:00 von `D-1` | `pick_quests_midnight` → `pick_quest_for_tomorrow` mit `tomorrow = D-1+1 = D` | Zeile mit `quest_date = D` wird angelegt |
| 09:00 von `D-1` | `announce_quests_morning` postet die Quest mit `quest_date = D-1` | Quest `D-1` wird für die Gruppe sichtbar — sie ist die *aktive* Quest bis 09:00 von `D` |
| 00:00 von `D` | `pick_quests_midnight` legt Quest für `D+1` an | Im DB stehen jetzt: `D-1` (aktive Quest), `D` (vorbereitet), `D+1` (vorbereitet) |
| **07:00 von `D`** | **User schreibt `/done`** | **`mark_done` sucht `quest_date = date.today() = D` und findet die noch nicht angekündigte Quest. Sie wird als erledigt verbucht — die *eigentlich aktive* Quest `D-1` bleibt offen.** |
| 09:00 von `D` | `announce_quests_morning` postet die Quest `D` | Bot kündigt eine Quest an, die für manche User bereits "erledigt" ist |

Genau dasselbe Problem betrifft auch:

- **`get_todays_quest`** (in `database.py`, von `/quest` und `announce_quests_morning` genutzt): liefert zwischen 00:00 und 09:00 die noch nicht angekündigte Quest. Das ist auch der Grund, warum der Hilfetext "Sie wird um 9 Uhr bekannt gegeben" für `/quest` *nicht* mehr ausgelöst wird, sobald die Quest fürs morgen bereits in der DB steht.
- **`get_completions_today`**: Joint nach `quest_date`-Match; Erledigungen, die im Zeitfenster 00:00–09:00 versehentlich angelegt werden, hängen an der falschen Quest.
- **Streak-Berechnung in `mark_done`**: Schreibt `last_completed_date = today` mit demselben verschobenen Verständnis von "today".

## Warum das so passiert

`bot/database.py` verwendet durchgängig `date.today()` als "Quest-Tag". Diese Funktion liefert den **Kalendertag**, nicht den **Quest-Tag** (der laut Produktlogik um 09:00 beginnt). Es fehlt also eine bewusste Modellierung des Quest-Tags. Die `daily_quests`-Zeile für `quest_date = D` existiert bereits ab `00:00 D-1` (Vorabauswahl) bzw. ab `00:00 D` (für die "morgige" Auswahl) — aber als *aktive* Quest gilt sie aus User-Sicht erst ab `09:00 D`.

## Zweiter, verwandter Defekt (Zeitzone)

`date.today()` benutzt die **System-Zeitzone**. Weder `Dockerfile` noch `docker-compose.yml` setzen `TZ`, also läuft der Container in UTC. Der Scheduler triggert zwar Berlin-korrekt um 00:00 Berlin (= 22:00/23:00 UTC), aber `date.today()` innerhalb der Handler liefert dann ggf. den UTC-Tag statt des Berlin-Tags. In den Stunden zwischen 22:00/23:00 UTC und 24:00 UTC ergibt das einen weiteren Off-by-one-Tag-Fehler.

Beispiel: User schreibt um 23:30 Berlin (= 22:30 UTC im Sommer) `/done`. `date.today()` (UTC) liefert noch den alten Tag — also vermutlich passt es zufällig — aber die Konsistenz mit dem Scheduler ist nicht garantiert. Im Winter (CET) verschiebt sich das Fenster.

Dieser TZ-Defekt sollte im selben Aufwasch behoben werden, sonst bleibt das Verhalten an Tagen rund um die Sommerzeitumstellung weiterhin schwer reproduzierbar.

## Wo genau im Code

- `bot/database.py:185` — `get_todays_quest` nutzt `date.today()`
- `bot/database.py:198` — `pick_quest_for_tomorrow` nutzt `date.today()`
- `bot/database.py:276` — `mark_done` nutzt `date.today()`
- `bot/database.py:318` — Streak-Logik in `mark_done` nutzt `date.today()`
- `bot/database.py:344` — `get_completions_today` nutzt `date.today()`

# Vorgeschlagene Lösung

## Kernidee

Den Begriff "Quest-Tag" explizit modellieren: **Ein Quest-Tag beginnt um 09:00 Europe/Berlin und endet um 08:59:59 am nächsten Kalendertag.**

Daraus folgt: Vor 09:00 Berlin gehört man noch zum Quest-Tag des Vortags.

## Konkrete Änderungen (Patch-Skizze)

### 1. Helfer in `bot/database.py`

Eine zentrale Funktion einführen, die den aktuellen Quest-Tag korrekt liefert:

```python
from datetime import datetime, time, timedelta
import pytz

BERLIN = pytz.timezone("Europe/Berlin")
QUEST_DAY_START = time(9, 0)  # Quest-Tag beginnt um 09:00 Berlin

def _current_quest_date() -> str:
    """Liefert den aktuellen Quest-Tag (ISO).
    Vor 09:00 Berlin: gestriger Kalendertag.
    Ab 09:00 Berlin: heutiger Kalendertag.
    """
    now_berlin = datetime.now(BERLIN)
    if now_berlin.time() < QUEST_DAY_START:
        return (now_berlin.date() - timedelta(days=1)).isoformat()
    return now_berlin.date().isoformat()

def _next_quest_date() -> str:
    """Liefert den nächsten Quest-Tag, also den Tag, für den
    noch keine angekündigte Quest existiert.
    """
    now_berlin = datetime.now(BERLIN)
    if now_berlin.time() < QUEST_DAY_START:
        return now_berlin.date().isoformat()
    return (now_berlin.date() + timedelta(days=1)).isoformat()
```

### 2. `date.today()` an allen relevanten Stellen ersetzen

- `get_todays_quest` → `_current_quest_date()`
- `mark_done` (Quest-Suche und `last_completed_date`) → `_current_quest_date()`
  - die Streak-Lücken-Berechnung (`gap = today_date - last_completed_date`) muss ebenfalls auf das Berlin-Datum umgestellt werden, sonst ist die Lückenmessung an Tageswechseln fehleranfällig
- `get_completions_today` → `_current_quest_date()`
- `pick_quest_for_tomorrow` → `_next_quest_date()`

### 3. Scheduler vereinfachen (optional, aber sauberer)

Der Job `pick_quests_midnight` kann bleiben (er bereitet die nächste Quest vor), wird aber für die Korrektheit nicht mehr gebraucht — `_current_quest_date()` schaut immer auf den richtigen Tag. Empfehlung: Job belassen, weil er die Pool-Auswahl und das Vorab-Schreiben in `daily_quests` deterministisch hält.

`announce_quests_morning` braucht keine Änderung, sobald `get_todays_quest` korrigiert ist — um 09:00 liefert die Funktion automatisch die "neue" Quest des Tages.

### 4. Zeitzone im Container fixieren

`docker-compose.yml`:

```yaml
    environment:
      - PYTHONUNBUFFERED=1
      - TZ=Europe/Berlin
```

Damit ist auch jegliche zukünftige Datums-Logik konsistent. Selbst wenn jemand versehentlich `date.today()` benutzt, läuft es danach in der richtigen Zone.

## Warum diese Lösung die beste ist

- **Minimal-invasiv**: nur `database.py` und `docker-compose.yml` werden angefasst, keine Schemaänderungen, keine Migration nötig.
- **Logisch korrekt**: das Konzept "Quest-Tag startet um 09:00" wird einmal definiert und überall einheitlich verwendet — keine verstreuten Sonderfälle.
- **Robust gegen Zeitzonen-Effekte**: `_current_quest_date()` arbeitet ausschließlich mit `Europe/Berlin`, dazu wird der Container-TZ explizit gesetzt.
- **Rückwärtskompatibel**: bestehende `daily_quests`-Zeilen behalten ihre Bedeutung. Eine bereits für `D` angelegte Zeile wird ab dem 09:00-Cut korrekt als "heute" behandelt — keine Daten verloren, keine Doppelvergabe.
- **Streak-Logik bleibt intuitiv**: `last_completed_date` benutzt denselben Quest-Tag-Begriff, also fließen Erledigungen aus dem 00:00–09:00-Fenster nicht mehr in den falschen Tag und reißen keine Streaks auseinander.

## Alternativen, die ich verworfen habe

- **Quests erst um 09:00 in `daily_quests` einfügen statt um 00:00**: Würde funktionieren, ändert aber den Scheduler stärker und macht den `/start`-Pfad (`pick_quest_for_tomorrow` beim Onboarding) unklar. Weniger sauber.
- **Eine Spalte `is_announced` einführen**: Schemaänderung plus zusätzliche Statusverwaltung. Höherer Aufwand, kein Mehrwert gegenüber der zeitbasierten Lösung.
- **`/done` an die Anwesenheit einer "letzten angekündigten Quest" koppeln (z. B. via Last-announced-Timestamp)**: Komplexer als nötig, weil die Regel "9 Uhr bis 9 Uhr" rein zeitlich entscheidbar ist.
