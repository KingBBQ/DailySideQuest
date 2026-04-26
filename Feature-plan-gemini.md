# Feature Plan: Quest Catch-up & XP System

Dieses Feature ermöglicht es Nutzern, verpasste Quests vom Vortag nachzuholen. Dabei wird ein neues "XP" (Erfahrungspunkte) System eingeführt, das pünktliche Erledigungen stärker belohnt als nachgeholte Quests.

## 1. Analyse des Ist-Zustands
- Aktuell können Quests nur am jeweiligen Tag mit `/done` markiert werden.
- Die Streak-Logik (`gap <= 2`) erlaubt bereits das Aussetzen eines Tages, ohne dass der Streak reißt. Allerdings zählt die verpasste Quest dann nicht zum `total_completed` Counter.
- Es gibt keinen Anreiz oder die technische Möglichkeit, eine verpasste Quest "nachzuarbeiten".

## 2. Geplante Änderungen

### A. Datenbank-Erweiterungen (`bot/database.py`)
- **Tabelle `users`**: Neue Spalte `xp` (FLOAT, Default 0.0).
- **Tabelle `completions`**: Neue Spalte `is_redo` (BOOLEAN, Default 0).
- **Migration**: Die `init()` Methode wird erweitert, um diese Spalten bei Bedarf hinzuzufügen.

### B. Neue Logik für Quests
- **XP-Vergabe**:
    - Regulär am selben Tag erledigt: **+1.0 XP**
    - Nachgeholt (vom Vortag): **+0.5 XP**
- **Streak-Heilung**:
    - Wenn ein Nutzer gestern eine Quest verpasst hat und diese heute "nachholt", wird sein Streak so fortgeführt, als hätte er sie gestern gemacht.
    - Beispiel: Streak 3 -> Gestern verpasst -> Heute nachholen -> Streak wird 4. Danach die heutige Quest machen -> Streak wird 5.

### C. Neue Befehle & Handler
- **`/redo` (oder `/nachholen`)**:
    - Prüft, ob es gestern eine Quest gab, die der Nutzer noch nicht erledigt hat.
    - Ermöglicht das Hochladen eines Fotos für diese Quest.
    - Markiert die Quest als `is_redo = 1`.
    - Berechnet den Streak neu und vergibt 0.5 XP.
- **`/done` Update**:
    - Vergibt nun zusätzlich 1.0 XP.
- **`/stats` Update**:
    - Zeigt den neuen XP-Score ("Punkte") in der Rangliste an.
    - Die Rangliste kann optional nach XP sortiert werden.

## 3. Umsetzungsschritte

1.  **Datenbank-Migration**: Update der `Database`-Klasse, um `xp` und `is_redo` zu unterstützen.
2.  **`mark_redo` Methode**: Neue Methode in `Database`, die gezielt die Quest von `date.today() - 1` anspricht.
3.  **Handler `bot/handlers/quest.py`**:
    - Implementierung von `redo_quest` Funktion.
    - Anpassung von `mark_done` für XP-Vergabe.
4.  **Handler `bot/handlers/stats.py`**:
    - Anzeige der XP in der Liste.
    - Beispiel-Format: `🥇 Name | 🔥 5 | ✨ 12.5 XP | ✅ 14`

## 4. Beispiel-Szenario (Nutzer-Wunsch)
1.  Nutzer hat einen **Streak von 3**.
2.  Tag 4: Quest wird **verpasst**.
3.  Tag 5:
    - Nutzer macht `/redo` für Tag 4: Erhält **0.5 XP**. Streak steigt auf **4**.
    - Nutzer macht `/done` für Tag 5: Erhält **1.0 XP**. Streak steigt auf **5**.
    - Gesamt-XP Gewinn: **1.5**.
    - Wenn er Tag 4 *nicht* nachgeholt hätte, wäre er bei Streak 4 (wegen Kulanz-Regel) aber hätte 0.5 XP weniger und 1 Quest weniger in "Gesamt".

Dieses System erfüllt den Wunsch nach einem "zweiten Score" (XP) und dem Anreiz, Übungen (wie Liegestütze) auch dann noch zu machen, wenn der Tag eigentlich schon vorbei ist.
