#!/usr/bin/env python3
"""
Quick script to update dicom_config.json with gerald node using ExplicitVRLittleEndian
"""

import json
import shutil
from pathlib import Path

CONFIG_FILE = "dicom_config.json"

def main():
    if not Path(CONFIG_FILE).exists():
        print(f"❌ Error: {CONFIG_FILE} not found!")
        return

    # Create backup
    backup_file = f"{CONFIG_FILE}.backup"
    shutil.copy(CONFIG_FILE, backup_file)
    print(f"✓ Backup created: {backup_file}\n")

    # Load config
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)

    print("Original config:")
    print(json.dumps(config, indent=2))
    print("\n" + "=" * 80 + "\n")

    # Migrate to new format if needed
    if "remote" in config and "remotes" not in config:
        print("Migrating old format to new format...")
        remote_node = config["remote"]
        short_name = remote_node["name"].lower().replace(" ", "_")

        # Add transfer_syntax if not present
        if "transfer_syntax" not in remote_node:
            remote_node["transfer_syntax"] = "JPEG2000Lossless"

        config["remotes"] = {
            short_name: remote_node
        }
        del config["remote"]
        print(f"✓ Migrated. Node accessible as '{short_name}'\n")

    # Add transfer_syntax to local if not present
    if "transfer_syntax" not in config["local"]:
        config["local"]["transfer_syntax"] = "JPEG2000Lossless"

    # Add transfer_syntax to existing remotes if not present
    for short_name, node in config["remotes"].items():
        if "transfer_syntax" not in node:
            node["transfer_syntax"] = "JPEG2000Lossless"
            print(f"✓ Added JPEG2000Lossless to '{short_name}'")

    # Example: Add gerald node if not exists
    if "gerald" not in config["remotes"]:
        print("\nAdding 'gerald' node as example...")
        config["remotes"]["gerald"] = {
            "name": "Gerald PACS",
            "ae_title": "GERALD",
            "ip_address": "10.1.15.40",  # Change this to actual IP
            "port": 4051,                  # Change this to actual port
            "transfer_syntax": "ExplicitVRLittleEndian"
        }
        print("✓ 'gerald' node added with ExplicitVRLittleEndian")
        print("⚠ Please update IP address and port in the config file!")

    # Save updated config
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

    print("\n" + "=" * 80)
    print("\n✓ Configuration updated!\n")
    print("Updated config:")
    print(json.dumps(config, indent=2))

    print("\n" + "=" * 80)
    print("\nUsage:")
    for short_name in config["remotes"].keys():
        node = config["remotes"][short_name]
        syntax = node.get("transfer_syntax", "JPEG2000Lossless")
        print(f"  python3 dicom_query_compare.py --node {short_name}  # {syntax}")

if __name__ == "__main__":
    main()
