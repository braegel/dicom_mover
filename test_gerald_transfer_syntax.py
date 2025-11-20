#!/usr/bin/env python3
"""
Test script to try different transfer syntaxes for Gerald node
"""

import json
import shutil

# Backup current config
shutil.copy('dicom_config.json', 'dicom_config.json.backup_test')

config = {
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
            "name": "Gerald",
            "ae_title": "AYCAN_BMBA_Q",
            "ip_address": "192.168.2.15",
            "port": 7401,
            "transfer_syntax": "ExplicitVRLittleEndian"
        }
    }
}

print("Testing Gerald configuration with different transfer syntaxes\n")
print("=" * 80)

syntaxes_to_test = [
    ("ExplicitVRLittleEndian", "Most common, explicit encoding"),
    ("ImplicitVRLittleEndian", "Legacy format, implicit encoding"),
    ("JPEG2000Lossless", "Compressed lossless")
]

for i, (syntax, description) in enumerate(syntaxes_to_test, 1):
    print(f"\n{i}. {syntax}")
    print(f"   Description: {description}")

print("\n" + "=" * 80)
print("\nCurrent gerald configuration uses: ExplicitVRLittleEndian")
print("\nTo test a different transfer syntax:")
print("1. Edit dicom_config.json")
print("2. Change gerald's transfer_syntax to one of the above")
print("3. Run: python3 dicom_query_compare.py --node gerald")
print("\nThe script now also uses ImplicitVRLittleEndian as automatic fallback")
print("\nBackup saved as: dicom_config.json.backup_test")

# Write current config
with open('dicom_config.json', 'w') as f:
    json.dump(config, f, indent=2)

print("\n✓ Configuration written")
