# Per-Remote Local Configuration

## Problem
Verschiedene PACS-Systeme kennen deinen lokalen Server unter unterschiedlichen Identitäten:
- **Telradko** kennt dich als: `kleditsch@192.168.1.178:11112`
- **Gerald** kennt dich als: `ARZT_4@192.168.222.20:11112`

## Lösung
Jeder Remote-Knoten kann jetzt eine eigene `local_config` haben, die definiert, wie dieser Remote-Knoten den lokalen Server kennt.

## Konfigurationsformat

```json
{
  "local": {
    "name": "kleditsch",
    "ae_title": "kleditsch",
    "ip_address": "192.168.1.178",
    "port": 11112,
    "transfer_syntax": "JPEG2000Lossless"
  },
  "remotes": {
    "telradko": {
      "name": "Telradko",
      "ae_title": "TZK",
      "ip_address": "10.1.15.30",
      "port": 4050,
      "transfer_syntax": "JPEG2000Lossless"
      // Kein local_config = verwendet default local settings
    },
    "gerald": {
      "name": "Gerald",
      "ae_title": "AYCAN_BMBA_Q",
      "ip_address": "192.168.2.15",
      "port": 7401,
      "transfer_syntax": "ExplicitVRLittleEndian",
      "local_config": {
        "ae_title": "ARZT_4",
        "ip_address": "192.168.222.20",
        "port": 11112
      }
    }
  }
}
```

## Wie es funktioniert

### Telradko (ohne local_config):
```bash
python3 dicom_query_compare.py --node telradko
```
- Verwendet **default** local config: `kleditsch@192.168.1.178:11112`
- C-MOVE Ziel: `kleditsch@192.168.1.178:11112`

### Gerald (mit local_config):
```bash
python3 dicom_query_compare.py --node gerald
```
- Verwendet **remote-specific** local config: `ARZT_4@192.168.222.20:11112`
- C-MOVE Ziel: `ARZT_4@192.168.222.20:11112`

## Was das Script ausgibt

### Bei Telradko:
```
Using default local config: kleditsch@192.168.1.178:11112

[06:28:00] [1/5] C-MOVE START
  Patient: Mustermann
  Date: 2025-11-20
  Series: 1 (CT) - New series (150 img)
  Description: CT Thorax
  Transfer syntax: JPEG2000Lossless
  C-MOVE destination: kleditsch@192.168.1.178:11112
```

### Bei Gerald:
```
Using remote-specific local config: ARZT_4@192.168.222.20:11112

[06:28:00] [1/5] C-MOVE START
  Patient: Mustermann
  Date: 2025-11-20
  Series: 1 (CT) - New series (150 img)
  Description: CT Thorax
  Transfer syntax: ExplicitVRLittleEndian
  C-MOVE destination: ARZT_4@192.168.222.20:11112
```

## Wichtig: DICOM-Server Konfiguration

Dein lokaler DICOM-Server muss auf **beiden** Identitäten erreichbar sein:

### Option 1: Mehrere AE-Titles auf einem Server
Konfiguriere deinen lokalen DICOM-Server so, dass er auf:
- AE Title `kleditsch` auf Port `11112` (für Telradko)
- AE Title `ARZT_4` auf Port `11112` (für Gerald)

reagiert.

### Option 2: Verschiedene IPs/Ports
Falls dein Server auf verschiedenen Netzwerk-Interfaces erreichbar ist:
- Interface 1: `192.168.1.178:11112` als `kleditsch`
- Interface 2: `192.168.222.20:11112` als `ARZT_4`

## Interaktives Setup

Beim Hinzufügen eines Remote-Knotens wirst du gefragt:

```
Local Configuration (how this remote knows YOU):
  Does this remote know you differently than default? (y/n, default=n): y
  Enter how this remote PACS knows your local server:
    AE Title: ARZT_4
    IP Address: 192.168.222.20
    Port: 11112
  ✓ Custom local config: ARZT_4@192.168.222.20:11112
```

## Warum ist das nötig?

PACS-Systeme haben Sicherheitseinstellungen, die nur vorkonfigurierte DICOM-Knoten als C-MOVE Ziele akzeptieren:

- **Telradko** hat in seiner Konfiguration: `kleditsch@192.168.1.178:11112`
- **Gerald (AYCAN)** hat in seiner Konfiguration: `ARZT_4@192.168.222.20:11112`

Wenn du den falschen AE-Title/IP verwendest, lehnt der PACS die C-MOVE Anfrage mit Fehler **0xA801** ("Move Destination unknown") ab.

## Fehlerbehebung

### Fehler 0xA801 erscheint immer noch?

1. **Prüfe die PACS-Konfiguration**: Schaue in Gerald nach, wie dein lokaler Server wirklich konfiguriert ist
2. **Teste die Verbindung**: Stelle sicher, dass dein DICOM-Server auf der angegebenen IP/Port/AE-Title erreichbar ist
3. **Prüfe das Netzwerk**: `192.168.222.20` muss von `192.168.2.15` (Gerald) aus erreichbar sein

### Debug-Ausgabe nutzen

Das Script zeigt jetzt bei jedem C-MOVE:
- Welche Transfer-Syntax verwendet wird
- Welches C-MOVE Ziel (AE-Title@IP:Port) verwendet wird
- Bei Fehlern: Den genauen Fehlercode

## Zusammenfassung

Mit dieser Konfiguration kann jeder Remote-PACS dich unter seiner eigenen Identität kennen, und das Script verwendet automatisch die richtige lokale Konfiguration für C-MOVE Operationen.
