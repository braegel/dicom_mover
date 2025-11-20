#!/usr/bin/env python3
"""Test script for configuration migration and multi-node support"""

import json
import sys
import os

# Test 1: Check old format migration
print("=" * 80)
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

    print(f"\nMigrated format (node will be accessible as '{short_name}'):")
    print(json.dumps(new_config, indent=2))

    # Ask if user wants to migrate
    response = input("\nWould you like to migrate to new format? (y/n): ").strip().lower()
    if response == 'y':
        with open('dicom_config.json', 'w') as f:
            json.dump(new_config, f, indent=2)
        print("✓ Configuration migrated successfully!")
    else:
        print("Migration skipped.")

elif "remotes" in config:
    print("\n✓ New format detected (multiple 'remotes' key)")
    print("\nAvailable remote nodes:")
    for short_name, node in config["remotes"].items():
        print(f"  - {short_name}: {node['name']} ({node['ae_title']}@{node['ip_address']}:{node['port']})")

else:
    print("\n❌ Unknown config format!")
    sys.exit(1)

print("\n" + "=" * 80)
print("TEST 2: Command-line usage examples")
print("=" * 80)

if "remotes" in config:
    nodes = list(config["remotes"].keys())
    print(f"\nTo use this configuration, run:")
    for node in nodes:
        print(f"  python3 dicom_query_compare.py --node {node}")
elif "remote" in config:
    remote_node = config["remote"]
    short_name = remote_node["name"].lower().replace(" ", "_")
    print(f"\nAfter migration, you can run:")
    print(f"  python3 dicom_query_compare.py --node {short_name}")

print("\nAll tests completed!")
