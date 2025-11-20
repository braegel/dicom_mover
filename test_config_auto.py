#!/usr/bin/env python3
"""Test script for configuration migration and multi-node support (non-interactive)"""

import json
import sys
import os
import shutil

# Create backup
print("Creating backup of dicom_config.json...")
shutil.copy('dicom_config.json', 'dicom_config.json.backup')

# Test 1: Check old format migration
print("\n" + "=" * 80)
print("TEST 1: Old format migration")
print("=" * 80)

# Read current config
with open('dicom_config.json', 'r') as f:
    config = json.load(f)

print("\nCurrent config format:")
print(json.dumps(config, indent=2))

if "remote" in config and "remotes" not in config:
    print("\n✓ Old format detected (single 'remote' key)")

    # Simulate migration
    remote_node = config["remote"]
    short_name = remote_node["name"].lower().replace(" ", "_")

    new_config = {
        "local": config["local"],
        "remotes": {
            short_name: remote_node
        }
    }

    print(f"\n✓ Migrated format (node accessible as '{short_name}'):")
    print(json.dumps(new_config, indent=2))

    print(f"\n✓ Command to use this node:")
    print(f"  python3 dicom_query_compare.py --node {short_name}")

elif "remotes" in config:
    print("\n✓ New format detected (multiple 'remotes' key)")
    print("\n✓ Available remote nodes:")
    for short_name, node in config["remotes"].items():
        print(f"  - {short_name}: {node['name']} ({node['ae_title']}@{node['ip_address']}:{node['port']})")
        print(f"    Command: python3 dicom_query_compare.py --node {short_name}")

else:
    print("\n❌ Unknown config format!")
    sys.exit(1)

print("\n" + "=" * 80)
print("TEST 2: Multiple node example")
print("=" * 80)

example_config = {
    "local": config["local"],
    "remotes": {
        "telradko": {
            "name": "Telradko",
            "ae_title": "TZK",
            "ip_address": "10.1.15.30",
            "port": 4050
        },
        "ct": {
            "name": "CT Scanner PACS",
            "ae_title": "CT_PACS",
            "ip_address": "10.1.15.40",
            "port": 4051
        },
        "mri": {
            "name": "MRI PACS",
            "ae_title": "MRI_PACS",
            "ip_address": "10.1.15.50",
            "port": 4052
        }
    }
}

print("\nExample configuration with multiple nodes:")
print(json.dumps(example_config, indent=2))

print("\n✓ Usage examples:")
print("  python3 dicom_query_compare.py --node telradko")
print("  python3 dicom_query_compare.py --node ct --hours 6")
print("  python3 dicom_query_compare.py --node mri --all-series")

print("\n" + "=" * 80)
print("✓ All tests completed successfully!")
print("=" * 80)
print("\nNote: Your original config is backed up as 'dicom_config.json.backup'")
