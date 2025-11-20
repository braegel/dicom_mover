# Transfer Syntax Konfiguration für DICOM Knoten

## Übersicht

Das Script unterstützt jetzt knotenspezifische Transfer-Syntaxen für C-MOVE Operationen. Jeder Remote-Knoten kann seine eigene bevorzugte Transfer-Syntax haben.

## Unterstützte Transfer Syntaxen

1. **JPEG2000Lossless** - JPEG 2000 verlustfrei (Standard)
2. **ExplicitVRLittleEndian** - Explicit VR Little Endian

## Konfigurationsformat

Jeder Remote-Knoten in der `dicom_config.json` kann ein `transfer_syntax` Feld haben:

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
    },
    "gerald": {
      "name": "Gerald PACS",
      "ae_title": "GERALD",
      "ip_address": "10.1.15.40",
      "port": 4051,
      "transfer_syntax": "ExplicitVRLittleEndian"
    }
  }
}
```

## Verwendung

### Bestehende Konfiguration aktualisieren

Falls du bereits eine `dicom_config.json` hast, kannst du die Transfer-Syntax hinzufügen:

**Option 1: Helper-Script verwenden**
```bash
python3 add_transfer_syntax.py
```

**Option 2: Manuell editieren**
Füge zu jedem Remote-Knoten das Feld `"transfer_syntax"` hinzu:
- `"transfer_syntax": "JPEG2000Lossless"` für Telradko
- `"transfer_syntax": "ExplicitVRLittleEndian"` für Gerald

### Neue Konfiguration erstellen

Bei der interaktiven Einrichtung wirst du nun nach der Transfer-Syntax gefragt:

```bash
python3 dicom_query_compare.py --node <name>
```

Beim ersten Start ohne existierende Konfiguration wirst du nach allen Parametern gefragt, inklusive Transfer-Syntax.

## Verwendungsbeispiele

### Telradko mit JPEG2000Lossless
```bash
python3 dicom_query_compare.py --node telradko
```

### Gerald mit ExplicitVRLittleEndian
```bash
python3 dicom_query_compare.py --node gerald
```

### Mit weiteren Optionen
```bash
python3 dicom_query_compare.py --node gerald --hours 6
python3 dicom_query_compare.py --node telradko --min-images 300
python3 dicom_query_compare.py --node gerald --all-series
```

## Fehlersuche

### C-MOVE schlägt fehl

Wenn C-MOVE Operationen fehlschlagen, kann dies an der falschen Transfer-Syntax liegen:

1. Prüfe die Logs: Das Script zeigt die verwendete Transfer-Syntax an:
   ```
   Using transfer syntax: ExplicitVRLittleEndian
   ```

2. Falls falsch konfiguriert, editiere `dicom_config.json` und ändere die Transfer-Syntax

3. Teste verschiedene Transfer-Syntaxen:
   - Wenn ExplicitVRLittleEndian nicht funktioniert, versuche JPEG2000Lossless
   - Wenn JPEG2000Lossless nicht funktioniert, versuche ExplicitVRLittleEndian

### Kompatibilität mit alten Konfigurationen

- Alte Konfigurationen ohne `transfer_syntax` verwenden automatisch **JPEG2000Lossless** als Standard
- Alte Konfigurationen mit nur einem `"remote"` Knoten werden automatisch migriert

## Technische Details

Die Transfer-Syntax wird für jede C-MOVE Operation dynamisch gesetzt:

```python
# Für jeden Remote-Knoten wird eine neue Association
# mit der spezifischen Transfer-Syntax erstellt
move_ae = AE(ae_title=self.calling_ae_title)
transfer_syntax_uid = get_transfer_syntax_uid(source_node.transfer_syntax)
move_ae.add_requested_context(StudyRootQueryRetrieveInformationModelMove, transfer_syntax_uid)
```

Dies ermöglicht es, verschiedene PACS-Server mit unterschiedlichen Transfer-Syntax-Anforderungen gleichzeitig zu nutzen.
