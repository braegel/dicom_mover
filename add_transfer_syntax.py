#!/usr/bin/env python3
"""
Helper script to add transfer_syntax to existing dicom_config.json

This script helps you update your existing configuration to include
transfer syntax specifications for each remote node.
"""

import json
import shutil
import sys
from pathlib import Path

CONFIG_FILE = "dicom_config.json"

def main():
    if not Path(CONFIG_FILE).exists():
        print(f"❌ Error: {CONFIG_FILE} not found!")
        print("Please run dicom_query_compare.py first to create a configuration.")
        sys.exit(1)

    # Create backup
    backup_file = f"{CONFIG_FILE}.backup_transfer_syntax"
    shutil.copy(CONFIG_FILE, backup_file)
    print(f"✓ Backup created: {backup_file}\n")

    # Load config
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)

    print("Current configuration:")
    print(json.dumps(config, indent=2))
    print("\n" + "=" * 80)

    # Check if already has new format
    if "remotes" in config:
        print("\n✓ Configuration already uses 'remotes' format")

        # Check if transfer_syntax is missing
        needs_update = False
        for short_name, node in config["remotes"].items():
            if "transfer_syntax" not in node:
                needs_update = True
                print(f"\n⚠ Node '{short_name}' is missing transfer_syntax")

        if needs_update:
            print("\nAdding transfer_syntax to nodes...\n")

            for short_name, node in config["remotes"].items():
                if "transfer_syntax" not in node:
                    print(f"Node: {short_name} ({node['name']})")
                    print("  1) JPEG2000Lossless (default)")
                    print("  2) ExplicitVRLittleEndian")

                    choice = input(f"  Choose transfer syntax for '{short_name}' (1 or 2): ").strip()

                    if choice == "2":
                        node["transfer_syntax"] = "ExplicitVRLittleEndian"
                        print(f"  ✓ Set to ExplicitVRLittleEndian\n")
                    else:
                        node["transfer_syntax"] = "JPEG2000Lossless"
                        print(f"  ✓ Set to JPEG2000Lossless (default)\n")

            # Add transfer_syntax to local node if missing
            if "transfer_syntax" not in config["local"]:
                config["local"]["transfer_syntax"] = "JPEG2000Lossless"

            # Save updated config
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)

            print("=" * 80)
            print("\n✓ Configuration updated successfully!")
            print("\nUpdated configuration:")
            print(json.dumps(config, indent=2))

        else:
            print("\n✓ All nodes already have transfer_syntax configured!")

    elif "remote" in config:
        print("\n⚠ Old configuration format detected (single 'remote' key)")
        print("Please run the script again to migrate to multi-node format.")

    print("\n" + "=" * 80)
    print("Usage examples:")

    if "remotes" in config:
        for short_name in config["remotes"].keys():
            print(f"  python3 dicom_query_compare.py --node {short_name}")

    print("\n✓ Done!")

if __name__ == "__main__":
    main()
