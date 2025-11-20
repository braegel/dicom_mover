# Lösung für Gerald C-MOVE Fehler 0xA801

## Problem
Fehlercode `0xA801` bedeutet: **"Move Destination unknown"**

Der Gerald PACS kennt das Ziel (deinen lokalen Server) nicht.

## Ursache
Beim C-MOVE sendet das Script:
- Quell-PACS: **Gerald** (AYCAN_BMBA_Q @ 192.168.2.15:7401)
- Ziel-AE-Title: **"kleditsch"**

Gerald weiß nicht, wohin er Bilder für "kleditsch" senden soll.

## Lösung 1: Gerald PACS konfigurieren (empfohlen)

Im Gerald PACS (AYCAN) musst du einen neuen DICOM-Knoten hinzufügen:

```
AE Title:    kleditsch
IP-Adresse:  192.168.1.178
Port:        11112
```

**Wie man das macht:**
1. Öffne die AYCAN Workstation Administration
2. Gehe zu "DICOM Konfiguration" oder "Netzwerk Knoten"
3. Füge einen neuen Knoten hinzu mit obigen Werten
4. Stelle sicher, dass C-MOVE/C-STORE für diesen Knoten erlaubt ist

## Lösung 2: Anderen AE-Title für lokalen Server verwenden

Falls Gerald nur bestimmte vorkonfigurierte AE-Titles akzeptiert, finde heraus, welche das sind, und ändere deinen lokalen Server entsprechend.

**Mögliche bekannte AE-Titles bei AYCAN:**
- AYCAN_STORE
- PACS_DEST
- WORKSTATION

Du kannst den lokalen AE-Title in der Konfiguration ändern:

```json
{
  "local": {
    "name": "kleditsch",
    "ae_title": "AYCAN_STORE",  // <-- Ändere dies
    "ip_address": "192.168.1.178",
    "port": 11112,
    "transfer_syntax": "JPEG2000Lossless"
  }
}
```

**WICHTIG:** Der lokale DICOM-Server muss dann auch mit diesem AE-Title gestartet werden!

## Lösung 3: Prüfe, ob bereits ein Knoten konfiguriert ist

Möglicherweise ist dein lokaler Server bereits in Gerald konfiguriert, aber mit einem **anderen AE-Title**.

**Test:**
Schaue in der Gerald-Konfiguration nach bereits konfigurierten Knoten mit IP `192.168.1.178` und verwende diesen AE-Title.

## Vergleich mit Telradko

Telradko funktioniert vermutlich, weil:
1. Telradko kennt "kleditsch" als gültiges Ziel, ODER
2. Telradko akzeptiert beliebige AE-Titles (weniger restriktiv)

## Debug-Informationen

Das Script sendet jetzt bei jedem C-MOVE:
```
Using transfer syntax: ExplicitVRLittleEndian (with ImplicitVRLittleEndian fallback)
```

Und bei Fehler:
```
C-MOVE failed with status: 0xA801
```

Weitere DICOM-Statuscodes:
- `0x0000` = Success
- `0xFF00` = Pending (noch in Arbeit)
- `0xA801` = Move Destination unknown
- `0xC000` = Cannot understand
- `0xFE00` = Cancel

## Nächste Schritte

1. **Prüfe Gerald PACS Konfiguration** - suche nach DICOM-Knoten-Einstellungen
2. **Füge "kleditsch" hinzu** oder finde den bereits konfigurierten AE-Title
3. **Teste die Verbindung** mit einem DICOM-Echo:
   ```bash
   # Falls verfügbar:
   echoscu -aec kleditsch 192.168.1.178 11112
   ```
4. **Starte das Script erneut**:
   ```bash
   python3 dicom_query_compare.py --node gerald
   ```

## Zusatzinfo: Transfer-Syntax ist korrekt

Die Transfer-Syntax (`ExplicitVRLittleEndian`) ist **nicht** das Problem. Der Fehler tritt auf, bevor überhaupt Daten übertragen werden - Gerald lehnt die C-MOVE Anfrage ab, weil das Ziel unbekannt ist.
