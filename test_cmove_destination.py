#!/usr/bin/env python3
"""
Test script to check if Gerald knows the local server as C-MOVE destination
"""

print("=" * 80)
print("C-MOVE Destination Test für Gerald")
print("=" * 80)

print("\nFehler 0xA801 = 'Move Destination unknown'")
print("\nDas bedeutet: Gerald PACS kennt das Ziel nicht.\n")

print("=" * 80)
print("Deine aktuelle Konfiguration:")
print("=" * 80)

print("\nLokaler Server (Ziel):")
print("  AE Title:    kleditsch")
print("  IP-Adresse:  192.168.1.178")
print("  Port:        11112")

print("\nGerald PACS (Quelle):")
print("  AE Title:    AYCAN_BMBA_Q")
print("  IP-Adresse:  192.168.2.15")
print("  Port:        7401")

print("\n" + "=" * 80)
print("Was zu tun ist:")
print("=" * 80)

print("\n1. Öffne die AYCAN Workstation (Gerald PACS)")
print("\n2. Gehe zu den DICOM-Einstellungen / Netzwerk-Konfiguration")
print("\n3. Füge einen neuen DICOM-Knoten hinzu:")
print("   - AE Title:   kleditsch")
print("   - Hostname:   192.168.1.178")
print("   - Port:       11112")
print("   - Erlaubt:    C-MOVE, C-STORE")

print("\n4. Speichere die Konfiguration")

print("\n5. Teste erneut:")
print("   python3 dicom_query_compare.py --node gerald")

print("\n" + "=" * 80)
print("Alternative: Anderen AE-Title verwenden")
print("=" * 80)

print("\nFalls Gerald nur bestimmte vorkonfigurierte AE-Titles akzeptiert:")
print("\n1. Finde heraus, welche AE-Titles in Gerald bereits konfiguriert sind")
print("\n2. Ändere den lokalen AE-Title in dicom_config.json:")
print('   "ae_title": "DER_BEKANNTE_AE_TITLE"')
print("\n3. Starte deinen lokalen DICOM-Server mit diesem AE-Title neu")

print("\n" + "=" * 80)
print("Warum funktioniert Telradko?")
print("=" * 80)

print("\nTelradko funktioniert, weil:")
print("  - Telradko bereits 'kleditsch' als bekanntes Ziel konfiguriert hat, ODER")
print("  - Telradko weniger restriktiv ist und beliebige AE-Titles akzeptiert")

print("\nGerald (AYCAN) ist sicherer konfiguriert und erlaubt nur")
print("vordefinierte Ziele - das ist eine Sicherheitsmaßnahme.")

print("\n" + "=" * 80)
