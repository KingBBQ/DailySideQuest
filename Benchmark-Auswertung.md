# Benchmark-Auswertung

> Detaillierter Vergleich der Modell-Outputs für `Bug.md` und `Feature.md`, abgeglichen mit dem tatsächlichen Code in `bot/`.
>
> Auswertung erstellt durch: Claude Opus 4.7 (1M context) — eigener Output zur Bug-Aufgabe wurde im Selbstvergleich gleich streng bewertet.

---

## TL;DR — Ranking

### Bug-Aufgabe (Identifikation + Lösung)

| Platz | Modell | Score | Begründung in einem Satz |
|------:|--------|------:|--------------------------|
| 1 | **Claude** | 9.5 / 10 | Vollständige Analyse mit Zeitlinie, exakte Zeilennummern, identifiziert Sekundär-Bug (Container-TZ), saubere & rückwärtskompatible Lösung mit Code. |
| 2 | **Gemini** | 7.0 / 10 | Korrekte Diagnose, korrekter Lösungsansatz (logisches Datum), aber dünn — keine Zeilennummern, keine TZ-Betrachtung, Code-Snippet hat fehlenden Import. |
| 3 | **Gemma** | 6.0 / 10 | Korrekt diagnostiziert und korrekter Lösungsansatz, aber sehr knapp und ohne Code/Zeilennummern. |
| 4 | **Qwen** | 3.5 / 10 | "Thinking out loud" mit mehreren Sackgassen sichtbar im Output; kommt am Ende zur richtigen Diagnose, aber empfiehlt eine Lösung, die das User-Bedürfnis verfehlt (sperrt `/done` vor 9 Uhr, statt es korrekt der Vortags-Quest zuzuordnen). |

### Feature-Aufgabe (Plan)

| Platz | Modell | Score | Begründung in einem Satz |
|------:|--------|------:|--------------------------|
| 1 | **Claude** | 9.0 / 10 | Vollständigster Plan mit klaren Trennungen Streak/Gesamt/Punkte, exakte ALTER-Statements im Projekt-Stil, alle Edge-Cases dokumentiert, "bewusst nicht enthalten"-Sektion. |
| 2 | **Gemini** | 5.5 / 10 | Knapp und sauber strukturiert, aber Streak-Heilung widerspricht "nur halb anrechnen", nur 1-Tage-Fenster, keine konkreten Code-Snippets. |
| 3 | **Gemma** | 4.0 / 10 | Bare-Minimum-Plan, knapp aber funktional, aber mit englischen UI-Strings (Projekt ist deutsch) und ohne `weekly_summary`/`/quest`-Integration. |
| 4 | **Qwen** | 3.0 / 10 | Viel Code, aber broken UX-Flow (mehrstufiger Callback → Photo → /done), undefinierte DB-Methoden, Tippfehler, Markdown-Bug, willkürliche Limits ("max 3 pro Woche", "Streak gecappt auf 10"). |

---

## 1. Aufgaben & Ground Truth

### 1.1 Was sagt der echte Code?

| Komponente | Verhalten |
|------------|-----------|
| `scheduler.pick_quests_midnight` | Läuft täglich 00:00 Berlin, ruft `pick_quest_for_tomorrow` für jede Gruppe auf. |
| `Database.pick_quest_for_tomorrow` (`bot/database.py:196`) | `tomorrow = (date.today() + timedelta(days=1)).isoformat()` → schreibt Zeile in `daily_quests` mit `quest_date = morgen`. |
| `Database.get_todays_quest` (`bot/database.py:184`) | `today = date.today().isoformat()` → sucht Zeile in `daily_quests` mit `quest_date = heute`. |
| `Database.mark_done` (`bot/database.py:272`) | Identische Logik wie `get_todays_quest`. |
| `scheduler.announce_quests_morning` | Läuft 09:00 Berlin, ruft `get_todays_quest` und postet das Ergebnis. |
| `Database.mark_done`, Streak | `gap = (today_date - date.fromisoformat(last_date)).days` → gleiches Problem mit `date.today()`. |
| Container-TZ | Weder `Dockerfile` noch `docker-compose.yml` setzen `TZ`; Container läuft also in UTC. |

### 1.2 Bug — eigene Verifikation

User behauptet: "/done um 7 Uhr morgens markiert die neue, noch nicht öffentliche Quest als erledigt; die alte ist aber noch aktiv."

**Bestätigt.** Spielen wir den Tag `D` durch (Berlin-Zeit):

| Zeit | Aktion | DB-Effekt |
|------|--------|-----------|
| 00:00 von `D-1` | `pick_quest_for_tomorrow` mit `tomorrow = D` | Zeile mit `quest_date = D` wird angelegt |
| 09:00 von `D-1` | `announce_quests_morning` postet die Zeile mit `quest_date = D-1` | Quest `D-1` ist die *aktive* Quest bis 09:00 von `D` |
| 00:00 von `D` | `pick_quest_for_tomorrow` mit `tomorrow = D+1` | Neue Zeile `D+1`; `D` existiert weiterhin |
| **07:00 von `D`** | `/done` → `mark_done` sucht `quest_date = D` und findet die noch nicht angekündigte Zeile | Erledigung wird auf die *falsche* Quest gebucht |
| 09:00 von `D` | `announce_quests_morning` postet `D` — für manche User bereits "erledigt" | — |

Sekundäres Problem: `date.today()` benutzt die Container-TZ (UTC), nicht Berlin. Im Zeitfenster zwischen 22:00/23:00 UTC und 24:00 UTC liefert das einen weiteren Off-by-one-Tag-Fehler an Tagen rund um die Sommerzeitumstellung.

### 1.3 Feature — Was der User sich wünscht

Aus `Feature.md` extrahiert:

1. **Nachholen** verpasster Quests — Beispiel: 3-Tage-Streak, Tag 4 verpasst, Tag 5 erledigt → Tag 4 nachträglich abhaken können.
2. **Zweiter Score**: entweder ein simpler Gesamtzähler ("wer hat insgesamt am meisten gemacht") und/oder ein gewichteter Score, in dem nachgeholtes "nur halb" zählt.
3. **Motivations-Treiber**: "lohnt sich heute, die Liegestütze noch zu machen" — auch nach dem Quest-Tag soll noch ein Anreiz da sein.

User-Beispielmathe: "die 3 und das nachgeholte nur halb anrechnen … insgesamt bei 4". Die Mathe ist nicht ganz konsistent, aber die Intention ist klar: pünktlich = volle Punkte, nachgeholt = halbe Punkte.

---

## 2. Bug-Auswertung im Detail

### 2.1 Claude — `BugFix-claude.md`

**Stärken**

- Bestätigt den Bug korrekt mit detaillierter Zeitlinien-Tabelle, die `pick_quest_for_tomorrow`-Aufrufe an `D-1` und `D` einzeln zeigt.
- Identifiziert **alle** betroffenen Funktionen — nicht nur `mark_done`, sondern auch `get_todays_quest`, `get_completions_today` und die Streak-Lückenberechnung.
- Findet den **sekundären Bug**: `date.today()` läuft in der Container-Zeitzone (UTC), nicht Berlin. Container hat kein `TZ` gesetzt — gegen den echten Code geprüft, stimmt.
- Liefert konkrete Zeilennummern (`database.py:185, 198, 276, 318, 344`) — alle gegen die echte Datei verifiziert und korrekt.
- Lösung: zwei Helfer `_current_quest_date()` und `_next_quest_date()`, die `Europe/Berlin` benutzen und 09:00 als Tagesgrenze definieren. Sauber und einmal-definiert, kein verstreuter Sonderfall.
- Empfiehlt zusätzlich `TZ=Europe/Berlin` in der `docker-compose.yml` als Defense-in-Depth.
- **Rückwärtskompatibel**: keine Schema-Migration, keine Daten-Backfills.
- "Alternativen verworfen"-Sektion betrachtet explizit `is_announced`-Flag, "Quests erst um 9 Uhr einfügen", Last-announced-Timestamp — und begründet die Ablehnung.

**Schwächen**

- Helfer-Funktionen liegen in `database.py` global statt als Methode der `Database`-Klasse — kosmetisch, kein Bug.
- Geht nicht explizit auf den `/start`-Pfad ein, der `pick_quest_for_tomorrow` aufrufen kann. (Beim Code-Verify: passt trotzdem — die Funktion prüft auf doppelte Einträge, also kein Konflikt.)

**Verifikation gegen Code**

- Zeilennummern: ✓ alle korrekt
- Logik des Helfers: ✓ wenn `now_berlin.time() < 09:00` → `now_berlin.date() - 1`. Wendet man das auf den 07:00-Fall im Beispiel an, sucht `mark_done` `quest_date = D-1` → trifft die Vortags-Quest, die ja noch aktiv ist. Korrekt.
- Behauptung zu UTC im Container: ✓ verifiziert in `docker-compose.yml`.

**Score: 9.5 / 10**

---

### 2.2 Gemini — `BugFix-gemini.md`

**Stärken**

- Diagnose grundsätzlich korrekt, der Mechanismus ist sauber erklärt.
- Erwähnt Streak-Logik als betroffen — wichtig, weil die meisten oberflächlichen Analysen das übersehen.
- Hinweis auf `get_weekly_stats` ist eine Nuance, die Claude *nicht* explizit benennt (auch wenn die Auswirkung dort gering ist, weil `quest_date`-Aggregate sich nicht durch eine 9-Uhr-Logik verschieben).
- Lösungsansatz "logisches Datum mit 9-Uhr-Cutoff" ist der gleiche wie bei Claude — also der richtige.

**Schwächen**

- Keine Zeilennummern, keine Zeitlinien-Tabelle, keine konkreten Datums-Beispiele mit echten Werten.
- Code-Snippet importiert `datetime` und `pytz` innerhalb der Funktion (Stil-Issue), und benutzt `timedelta(days=1)` ohne dass `timedelta` importiert ist — das Snippet würde so nicht laufen.
- Container-TZ-Problem (UTC vs Berlin) wird **nicht** erwähnt.
- Keine Diskussion von Alternativen, kein "warum diese Lösung".
- Adressiert `pick_quest_for_tomorrow` nicht — bei Claudes Lösung wird sie auf `_next_quest_date()` umgestellt, bei Gemini implizit unverändert. Funktioniert auch (geprüft), wäre aber sauberer wenn alle Stellen einheitlich umgestellt würden.
- Streak-Lücken-Berechnung wird erwähnt, aber nicht im Code gezeigt.

**Verifikation gegen Code**

- Logik des `get_logical_date()`: ✓ korrekt für den 07:00-Fall
- Aber: nutzt `now.hour < 9` statt `now.time() < time(9, 0)` — bei genau 09:00:30 wäre das egal, an der Grenze 09:00:00 funktioniert beides; sauber genug.

**Score: 7.0 / 10**

---

### 2.3 Gemma — `BugFix-gemma.md`

**Stärken**

- Bug korrekt diagnostiziert mit konkretem Beispiel (Montag/Dienstag).
- Lösungsansatz ist der richtige (logisches Datum, 9-Uhr-Cutoff).
- Sehr klare, knappe Sprache — gut lesbar.

**Schwächen**

- Keine Code-Snippets — nur Beschreibung.
- Keine Zeilennummern.
- Kein Wort zu Streak-Logik (übersieht eine relevante Folge-Stelle).
- Kein Wort zu Container-TZ.
- Keine Diskussion von Alternativen.
- Adressiert `pick_quest_for_tomorrow` nicht.

**Verifikation gegen Code**

- Diagnose stimmt
- Vorgeschlagene Logik wäre korrekt, aber unfertig — Streak-Stelle in `mark_done:318` würde übrig bleiben und wäre weiterhin off-by-one bei Erledigungen vor 09:00.

**Score: 6.0 / 10**

---

### 2.4 Qwen — `BugFix-qwen.md`

**Stärken**

- Findet am Ende den richtigen Bug.
- Macht sich Gedanken über Container-TZ (UTC vs Berlin) — auch wenn die Schlussfolgerung daraus nicht ins Endprodukt kommt.

**Schwächen — gravierend**

- **Thinking out loud im finalen Output**: enthält wörtlich Sätze wie "Hmm, das stimmt auch nicht", "Aber warten Sie", "Lassen Sie mich das nochmal durchdenken". Die Datei ist eigentlich der Scratchpad, nicht die Analyse.
- Mehrere Tabellen widersprechen sich. Beispiel Z. 156–159: "Dienstag 09:00 announce_quests_morning sucht quest_date = '2026-04-28' → keine Quest gefunden!" — falsch, weil am Montag um 00:00 die Quest mit `quest_date = 2026-04-28` eingefügt wurde.
- Empfohlene Lösung **verfehlt das User-Bedürfnis**:
  - **Option A** (vor 9:00 Berlin gibt es Status `early`): blockiert `/done` zwischen 00:00 und 09:00 komplett. Damit kann der User morgens um 7 Uhr seine **gestrige** Quest *nicht* mehr abhaken — obwohl gerade das das eigentliche Anliegen ist (Quest läuft "von 9 bis 9").
  - **Option B** (`is_published`-Spalte): koppelt Erledigbarkeit an die Ankündigung. Wenn `announce_quests_morning` mal ausfällt, wäre die Quest *gar nicht* mehr erledigbar. Schema-Migration für ein Problem, das rein zeitlich entscheidbar ist.
  - "Empfohlene Lösung: A + B kombiniert" → das Schlechte aus beidem.
- Hinweis "pick_quest_for_tomorrow umbenennen" ist Lärm, das ist nicht Teil des Bugs.

**Verifikation gegen Code**

- Container-TZ-Hinweis: korrekt
- Aber die "Empfohlene Lösung" hätte zur Folge, dass User den Bug *nicht mehr in Form der Symptom-Beschreibung* sehen — aber dafür ein neues Symptom: "ich kann morgens keine Quest abhaken". Das ist eine Verschlimmbesserung gemessen am Anliegen.

**Score: 3.5 / 10** — Diagnose stimmt am Ende; Lösung ist falsch.

---

### 2.5 Bug — Übersichts-Matrix

| Kriterium | Claude | Gemini | Gemma | Qwen |
|-----------|:------:|:------:|:-----:|:----:|
| Bug korrekt diagnostiziert | ✅ | ✅ | ✅ | ✅ (umständlich) |
| Zeitlinien-Tabelle | ✅ | ❌ | teilweise | ✅ (widersprüchlich) |
| Konkrete Zeilennummern | ✅ | ❌ | ❌ | teilweise |
| Streak-Logik miterfasst | ✅ | ✅ | ❌ | ❌ |
| `get_completions_today` miterfasst | ✅ | ✅ | ✅ | ❌ |
| Container-TZ-Sekundärbug | ✅ | ❌ | ❌ | erwähnt, aber nicht gefixt |
| Code-Snippets der Lösung | ✅ | teilweise (kaputt) | ❌ | ✅ (aber falsche Lösung) |
| Alternativen diskutiert | ✅ | ❌ | ❌ | teilweise |
| Lösung bewahrt User-Verhalten | ✅ | ✅ | ✅ | ❌ (blockiert /done vor 9 Uhr) |
| Schema-Migration nötig | nein | nein | nein | ja (Option B) |

---

## 3. Feature-Auswertung im Detail

### 3.1 Claude — `Feature-plan-Claude-Opus-4.7.md`

**Stärken**

- **Klare Begriffstrennung**: drei Metriken nebeneinander — `🔥 Streak` (wie heute), `✅ Gesamt` (jede Erledigung = 1), `⭐ Punkte` (pünktlich 1.0 / nachgeholt 0.5). Beantwortet damit *beide* Wünsche des Users (Counter + gewichteter Score) auf einmal.
- **Streak wird *nicht* geheilt** — Begründung explizit gegeben ("nur halb anrechnen" passt nicht zu "Streak voll fortgesetzt"). Konsistent mit User-Intent.
- User-Beispiel mit echten Zahlen durchgerechnet (3 Tage pünktlich + 1 verpasst + 1 pünktlich + 1 nachgeholt → Punkte = 4.5). Plausibel im Vergleich zu User-Wunsch ("ungefähr 4").
- **`/nachholen`-UX vollständig spezifiziert**: leerer Aufruf zeigt Liste, mit Index oder Datum erledigt, Foto-Variante über `MessageHandler` (matcht den existierenden `/done`-Photo-Handler), Fehler-Status für jede Edge-Case (Datum > 7 Tage, Datum ≥ heute, keine Quest, schon erledigt).
- **Integration in bestehende Flows** durchdacht: `/quest` zeigt Hinweiszeile *nur wenn der anfragende User offene Quests hat* (kein Spam in großen Gruppen), `/stats` erweitert, `weekly_summary` bekommt Top-3-Punkte.
- **Migration matcht Projekt-Konvention** aus `CLAUDE.md`: ALTER-Statements werden in den bestehenden try/except-Block ergänzt.
- Verweist auf `_current_quest_date` aus dem Bug-Fix-Plan und benennt explizit den Fallback, falls noch nicht gemerged. Cross-Feature-Awareness.
- "Bewusst nicht enthalten"-Sektion: streak-Heilung, konfigurierbares Fenster, Erst-Badge fürs Nachholen, Sonderbehandlung `proposed_by` — alle mit Begründung abgelehnt.
- "Offene Punkte ohne Rückfrage entschieden": Befehlsname `/nachholen` (nicht `/done <datum>`), `score` als `REAL`, Streak nicht heilen, `:.1f`-Anzeige — explizite Designentscheidungen mit Rationale.
- Aufwand am Ende beziffert (Anzahl ALTER, Methoden, Handler).

**Schwächen**

- `quest_date_completed` als zweite Spalte in `completions` ist eine bewusst genannte Redundanz (statt Join über `daily_quests`). Pragmatisch, aber stilistisch nicht jedermanns Sache.
- Keine ausgeschriebenen Handler-Bodies — nur Signaturen + Verhalten. Das ist für einen *Plan* OK, wird aber bei der Umsetzung nochmal Detail erfordern.
- `score`-Spalte auf `users` ist denormalisiert (könnte aus `completions` aggregiert werden). Matcht aber den existierenden Stil von `total_completed` und `total_first` — also intern konsistent.

**Verifikation gegen Code**

- ALTER-Pattern: ✓ matcht `database.py:124-131`
- `MessageHandler(filters.PHOTO & filters.CaptionRegex(r"^/nachholen"), …)`: ✓ matcht `main.py:48-50` für `/done`
- `_require_group`, `register_user`: ✓ matchen `handlers/quest.py` Konventionen
- `total_first`, `total_completed`, `streak`, `last_completed_date`: ✓ alle Spalten existieren
- `pick_quest_for_tomorrow` wird nicht angefasst: ✓ vom Feature unberührt

**Score: 9.0 / 10**

---

### 3.2 Gemini — `Feature-plan-gemini.md`

**Stärken**

- Knapp, gut strukturiert.
- Erkennt, dass die existierende Streak-Logik (`gap <= 2`) bereits einen Tag-Aussetzer toleriert — kontextuell nützlich.
- Unterscheidet sauber zwischen `xp` (gewichtet) und `total_completed` (Counter).

**Schwächen — inhaltlich**

- **Streak-Heilung widerspricht "nur halb anrechnen"**: Geminis Plan setzt nach Nachholen den Streak fort, als wäre der Tag pünktlich erledigt worden. Damit zählt die nachgeholte Quest *für den Streak* voll und *für XP* halb. Designerisch inkonsistent, weil der User im Originaltext explizit sagt: "die 3 und das nachgeholte nur halb anrechnen".
- Das eigene Schluss-Beispiel zerlegt sich selbst: "Wenn er Tag 4 *nicht* nachgeholt hätte, wäre er bei Streak 4 (wegen Kulanz-Regel)". Wenn die Kulanz-Regel den Streak ohnehin trägt, wozu dann Streak-Heilung?
- **Nachhol-Fenster auf 1 Tag begrenzt** (nur `date.today() - 1`). User-Wunsch klingt nach mehr Flexibilität ("lohnt sich heute die Liegestütze noch zu machen" suggeriert auch ältere Quests).
- Befehlsname schwankt zwischen `/redo` (englisch) und `/nachholen` (deutsch) — nicht entschieden.
- Kein Foto-Handler erwähnt — Inkonsistenz mit `/done`.
- Keine konkreten ALTER-Statements, kein Migration-Pattern.
- Keine Erweiterung von `weekly_summary` oder `/quest`.
- Keine Diskussion von Alternativen oder bewusst Nicht-Eingebautem.

**Verifikation gegen Code**

- Schema-Vorschlag (`xp` REAL, `is_redo` Boolean) ist additiv und würde funktionieren.
- Streak-Heilung wäre umsetzbar, würde aber `gap <= 2` und die `users.last_completed_date`-Logik komplizierter machen, weil dann Nachholen rückwirkend `last_completed_date` setzen müsste.

**Score: 5.5 / 10**

---

### 3.3 Gemma — `Feature-plan-gemma4:31b.md`

**Stärken**

- Sehr knapp, gut lesbar.
- Korrekte Grundkonzepte: `weighted_score`-Spalte, `mark_catchup_done`-Methode, 7-Tage-Fenster.
- Hat Verification-Schritte am Ende (welche Sequenzen man testen würde).

**Schwächen**

- **Englische UI-Strings** (`"You are all caught up! 🌟"`) — verletzt explizit die Projekt-Konvention aus `CLAUDE.md`: "User-facing strings are German".
- Plant `/catchup <quest_id>` als User-Interface — User sollten keine internen DB-IDs sehen.
- Keine konkreten ALTER-Statements, kein Migration-Pattern (try/except).
- Keine Foto-Handler-Integration.
- Keine `weekly_summary`-Erweiterung.
- Keine `/quest`-Hinweisintegration.
- Keine Diskussion von Streak-Wechselwirkung — bleibt offen.
- Keine User-Beispiel-Mathe.
- Keine Edge-Case-Behandlung über die Basis hinaus.

**Verifikation gegen Code**

- Schema-Vorschlag würde funktionieren, der einzelne `weighted_score`-Spalte ist minimal-invasiv.
- Die Methode `mark_catchup_done(user_id, chat_id, quest_id)` würde existieren — Implementierung ist aber nicht beschrieben.

**Score: 4.0 / 10**

---

### 3.4 Qwen — `Feature-plan-qwen.md`

**Stärken**

- Sehr ausführlich (über 500 Zeilen).
- Inline-Keyboard-UX als zusätzliche Dimension.
- Versucht, die User-Mathe zu erklären.

**Schwächen — gravierend**

- **Broken UX-Flow**: User ruft `/catchup 2024-01-15` → Bot zeigt Confirm-Dialog mit Buttons → User klickt "✅ Jetzt nachholen" → Bot fordert ein Foto an "mit `/done` für {target_date}". Aber `/done` akzeptiert in der bestehenden Code-Basis kein Datums-Argument. Der Flow setzt also einen Refactor von `/done` voraus, der nicht beschrieben ist.
- **Nicht-existente Methoden**: `db.get_quest_by_date(...)` und `db.get_user_profile(...)` werden aufgerufen, aber sind weder im Plan definiert noch im echten Code vorhanden.
- **`context.user_data` als State-Speicher** für den Foto-Modus — geht beim Bot-Restart verloren und kann mit dem normalen Foto-Handler kollidieren.
- **Markdown-Bug**: `f"📊 *Dein Gesamt-Score:\n\n"` — der `*` wird nicht geschlossen, würde Markdown brechen.
- **Tippfehler**: "aufggeben" statt "aufgegeben".
- **Willkürliche Limits ohne User-Bezug**:
  - "Max 3 Nachhol-Tage pro Woche" — User hat das nicht gefordert.
  - "Streak gecappt bei 10" in `calculate_total_score` — User hat das nicht gefordert.
- Mehrere Befehle (`/catchup`, `/makeup`, `/total`) plus Callback-Handler plus Photo-Handler — Feature-Creep für eine Aufgabe, die ein Befehl löst.
- **Sortierung umgestellt**: `ORDER BY total_completed DESC, streak DESC` — bricht das bestehende `/stats`-Verhalten ohne Begründung.
- Der `/makeup`-Keyboard-Builder ist verwirrend: in derselben Zeile werden Buttons "🕐 +1 Tag", "🕐 -1 Tag", "📸 Foto", "❌ Abbrechen" pro Tag *angefügt*, mit `callback_data="skip"` für sowohl +1 als auch -1 → mehrdeutig und nicht funktional.
- CallbackQueryHandler wird nicht in `main.py` registriert. Auch der Photo-Handler ist nicht ordentlich verdrahtet.

**Verifikation gegen Code**

- ALTER-Pattern matcht ✓.
- `mark_makeup_done` INSERT-Logik wäre korrekt.
- Aber: `db.get_quest_by_date` und `db.get_user_profile` existieren nicht und werden auch nicht definiert → der Code würde nicht laufen.
- `query.message.chat` in einer CallbackQueryHandler-Antwort ist OK, aber `_require_group` wird im Callback-Pfad nicht angewendet → Privatchat-Schutz fehlt.

**Score: 3.0 / 10** — viel Output, viel Code, viel kaputt.

---

### 3.5 Feature — Übersichts-Matrix

| Kriterium | Claude | Gemini | Gemma | Qwen |
|-----------|:------:|:------:|:-----:|:----:|
| Beide User-Wünsche (Counter + Score) bedient | ✅ | teilweise | teilweise | teilweise |
| Pünktlich 1.0 / Nachgeholt 0.5 | ✅ | ✅ | ✅ | ✅ |
| User-Beispielmathe nachgerechnet | ✅ | ✅ | ❌ | teilweise |
| Streak-Wechselwirkung explizit entschieden | ✅ (nicht heilen) | ✅ (heilen) | ❌ | teilweise |
| Streak-Entscheidung kohärent mit User-Intent | ✅ | ❌ | — | — |
| Foto-Variante (analog `/done`) | ✅ | ❌ | ❌ | ja, aber broken |
| `/quest`-Integration | ✅ | ❌ | ❌ | ❌ |
| `weekly_summary`-Integration | ✅ | ❌ | ❌ | ❌ |
| `/stats`-Erweiterung | ✅ | ✅ | ✅ | ✅ |
| Konkrete ALTER-Statements (Projekt-Pattern) | ✅ | ❌ | teilweise | ✅ |
| Hilfetext-Update | ✅ | ❌ | ❌ | ❌ |
| Edge-Cases (kein Quest am Datum, schon erledigt, …) | ✅ | ❌ | teilweise | teilweise |
| Alternativen / "bewusst nicht eingebaut" | ✅ | ❌ | ❌ | ❌ |
| Konsistente UI-Sprache (Deutsch) | ✅ | gemischt | ❌ (englisch) | gemischt |
| Referenziert nicht-existente Methoden | nein | nein | nein | **ja** |
| Tippfehler / Markdown-Bugs | nein | nein | nein | **ja** |
| Plan ist umsetzbar wie geschrieben | ✅ | mit Lücken | mit Lücken | ❌ |

---

## 4. Querbetrachtungen

### 4.1 Output-Qualität / Schreibstil

- **Claude** schreibt strukturierte, hierarchische Dokumente mit Tabellen, expliziten Code-Blöcken, klaren "Warum"-Sektionen und einer "bewusst nicht enthalten"-Tradition. Liest sich wie ein technischer Plan, den ein Engineer in Review verteidigen würde.
- **Gemini** ist sauber, knapp, korrekt — fühlt sich wie eine ausgedünnte Variante des Claude-Outputs an. Keine groben Fehler, aber wenig Tiefe.
- **Gemma** ist *sehr* knapp. Macht meistens das Richtige, aber lässt vieles unbeantwortet. Englische Strings im deutschen Projekt sind ein klares Negativ-Signal — das Modell hat das Projekt-Konvention-Signal aus `CLAUDE.md` nicht aufgegriffen, obwohl es im Kontext steht.
- **Qwen** liefert *Volumen*, aber nicht *Substanz*. Der Bug-Output ist Scratchpad-artig und nicht für Konsum bestimmt; der Feature-Output ist Code-lastig, aber der Code referenziert nicht-existente Methoden, hat Tippfehler und einen kaputten Markdown-String. Das deutet darauf hin, dass das Modell viel produziert, aber nicht selbst gegen den echten Code abgleicht.

### 4.2 Code-Awareness

| Modell | hat den echten Code wirklich gelesen? |
|--------|---------------------------------------|
| Claude | Ja — exakte Zeilennummern, korrekte Migrationspatterns, korrekte Handler-Signaturen, Verweis auf `_current_quest_date` als Cross-Feature-Abhängigkeit. |
| Gemini | Vermutlich ja — referenziert die richtigen Methoden, aber ohne Zeilennummern. Tiefe spricht eher für Überflug. |
| Gemma | Ja, aber oberflächlich — kennt die Spalten, aber übergeht Migrationspattern und Sprach-Konvention. |
| Qwen | Nur teilweise — referenziert nicht-existente Methoden (`get_quest_by_date`, `get_user_profile`), was zeigt, dass nicht jede Methode im Plan tatsächlich gegen den Code abgeglichen wurde. |

### 4.3 Selbstkritisches: Wie streng war ich mit Claude?

Da der Claude-Output von mir selbst zu evaluieren ist, habe ich besonders auf folgende potenzielle Schwächen geachtet:

- **Denormalisierung** (`score`-Spalte auf `users`, `quest_date_completed` redundant zu `daily_quests.quest_date`): real existente Trade-offs, im Score-Abzug berücksichtigt.
- **Komplexität**: 10-Punkte-Plan ist nicht trivial. Aber jeder Punkt löst ein konkretes User-Bedürfnis (`/quest`-Hinweis, `weekly_summary`, etc.). Kein offensichtlicher Feature-Creep — habe ich nicht zusätzlich abgewertet.
- **Cross-Feature-Verweis** auf den Bug-Fix: ist klug, könnte aber als Zwiebelschälen wirken, wenn der Bug noch nicht gemergt ist. Claude erwähnt einen Fallback — ausreichend abgesichert.
- **`/stats`-Sortierung**: bleibt unverändert. Habe ich gegenüber Qwens "neue Sortierung nach total_completed" als Plus für Claude gewertet, weil Claude die Änderung *nicht* macht und damit bestehende User-Erwartungen schont.

Im Ergebnis 9.0 / 10 für den Feature-Plan und 9.5 / 10 für den Bug-Plan — beide wären 10, wenn der Plan auch noch eine ausgeschriebene Test-Strategie enthielte, was bei einem Repo ohne Tests aber pragmatisch entfallen darf.

---

## 5. Konkrete Empfehlungen

1. **Bug umsetzen nach Claude-Vorlage** — `_current_quest_date()` + `_next_quest_date()` Helfer, alle `date.today()`-Stellen ersetzen, `TZ=Europe/Berlin` in `docker-compose.yml` ergänzen. Keine Schema-Migration nötig.

2. **Feature umsetzen nach Claude-Vorlage**, mit zwei kleinen Anpassungen, die ich beim Self-Review noch sehen würde:
   - Den `score`-Wert *nicht* in `users` denormalisieren, sondern bei `/stats`-Aufruf aus `completions` mit `SUM(CASE WHEN is_retroactive THEN 0.5 ELSE 1.0 END)` berechnen. Spart eine Spalte und ist robuster gegen Inkonsistenzen.
   - `quest_date_completed` weglassen — Join über `daily_quests` reicht, gerade bei nur einer Erledigung pro Tag.
   - Sonst Plan 1:1 übernehmen.

3. **Wenn Reihenfolge wichtig ist**: erst Bug-Fix mergen, *dann* Feature — weil das Feature den Bug-Fix-Helfer (`_current_quest_date`) referenziert. Andernfalls den Fallback (`date.today()`) im Feature-Code temporär lassen und nach Bug-Fix entfernen.

4. **Aus den schwächeren Outputs übernehmen**:
   - **Gemini** — sein Hinweis auf `get_weekly_stats` als potentiell betroffene Stelle ist es wert, im Bug-Fix nochmal kurz zu prüfen (Aggregat-Effekt an Tag-Grenzen).
   - **Qwen** — die Inline-Keyboard-Idee für `/nachholen` ist als spätere UX-Verbesserung interessant, sobald der Basis-Flow steht. Nicht als Erstes umsetzen.

---

## 6. Methodik

- Kontext für die Auswertung: Vollständiges Lesen von `bot/database.py`, `bot/main.py`, `bot/scheduler.py`, allen `bot/handlers/*.py` und `CLAUDE.md`.
- Jeder Modell-Output wurde gegen den echten Code geprüft (existieren referenzierte Funktionen? Stimmen Zeilennummern? Funktioniert der vorgeschlagene Code-Snippet, wenn man ihn ausführt?).
- Bei Lösungsvorschlägen wurde die Bug-Reproduktion mental "abgespielt" mit dem Vorschlag eingebaut, um sicherzustellen, dass das Symptom verschwindet *und keine neuen Symptome entstehen*.
- Score 1–10, wobei 10 = "exakt, vollständig, projekt-konform, wäre ohne Edits umsetzbar".
- Die Bewertung des Claude-Outputs ist von mir selbst — ich habe versucht, sie nicht freundlich zu drücken, aber bin mir bewusst, dass eine externe Drittperson hier den fairsten Urteil hätte.
