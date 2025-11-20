# DICOM Mover - Quick Reference

## Verwendung

### Telradko synchronisieren
```bash
python3 dicom_query_compare.py --node telradko
```
- Verwendet: `kleditsch@192.168.1.178:11112` (default)
- Transfer-Syntax: JPEG2000Lossless

### Gerald synchronisieren
```bash
python3 dicom_query_compare.py --node gerald
```
- Verwendet: `ARZT_4@192.168.222.20:11112` (custom)
- Transfer-Syntax: ExplicitVRLittleEndian

## Optionen

```bash
# Nur letzte 6 Stunden
python3 dicom_query_compare.py --node gerald --hours 6

# Alle Serien mit < 300 Bildern
python3 dicom_query_compare.py --node telradko --min-images 300

# Alle Serien übertragen
python3 dicom_query_compare.py --node gerald --all-series
```

## Konfiguration anzeigen

```bash
python3 -c "
import json
config = json.load(open('dicom_config.json'))
for name, node in config['remotes'].items():
    print(f'{name}: {node[\"ae_title\"]}@{node[\"ip_address\"]}:{node[\"port\"]}')
    if 'local_config' in node:
        lc = node['local_config']
        print(f'  -> Local: {lc[\"ae_title\"]}@{lc[\"ip_address\"]}:{lc[\"port\"]}')
"
```

## Wichtige Dateien

- `dicom_config.json` - Hauptkonfiguration
- `dicom_query_compare.py` - Haupt-Script
- `PER_REMOTE_LOCAL_CONFIG.md` - Dokumentation für lokale Konfigurationen
- `TRANSFER_SYNTAX_README.md` - Dokumentation für Transfer-Syntaxe

## Fehlersuche

### 0xA801 - Move Destination unknown
Das Remote-PACS kennt dein lokales Ziel nicht. Prüfe:
1. `local_config` in `dicom_config.json` korrekt?
2. PACS-Konfiguration auf Remote-Seite korrekt?
3. Netzwerk erreichbar?

### Keine Bilder werden übertragen
1. Prüfe C-MOVE Destination im Log
2. Stelle sicher, dass dein DICOM-Server läuft
3. Prüfe Firewall-Einstellungen

## Aktuelle Konfiguration

### Telradko
- **Remote**: TZK@10.1.15.30:4050
- **Local**: kleditsch@192.168.1.178:11112 (default)
- **Transfer**: JPEG2000Lossless

### Gerald
- **Remote**: AYCAN_BMBA_Q@192.168.2.15:7401
- **Local**: ARZT_4@192.168.222.20:11112 (custom!)
- **Transfer**: ExplicitVRLittleEndian
