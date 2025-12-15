#!/usr/bin/env python3
"""
DICOM Automatic Synchronization Tool

This script automatically synchronizes DICOM studies from a remote server to a local server.
It runs continuously, checking every minute for missing studies from today and yesterday,
and automatically transfers series with ≤10 images using C-MOVE with JPEG 2000 Lossless.

Author: DICOM Expert
License: MIT
"""

import argparse
import json
import os
import socket
import sys
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from pydicom.dataset import Dataset
from pydicom.uid import (
    JPEG2000Lossless,
    ExplicitVRLittleEndian,
    ImplicitVRLittleEndian
)
from pynetdicom import AE, debug_logger, evt
from pynetdicom.sop_class import (
    StudyRootQueryRetrieveInformationModelFind,
    StudyRootQueryRetrieveInformationModelMove
)

# Suppress pydicom validation warnings for malformed UIDs from remote PACS
warnings.filterwarnings('ignore', category=UserWarning, module='pydicom.valuerep')


CONFIG_FILE = "dicom_config.json"
STABILITY_TRACKER_FILE = "series_stability.json"

# Transfer syntax mapping
TRANSFER_SYNTAX_MAP = {
    "JPEG2000Lossless": JPEG2000Lossless,
    "ExplicitVRLittleEndian": ExplicitVRLittleEndian,
    "ImplicitVRLittleEndian": ImplicitVRLittleEndian,
}


def get_transfer_syntax_uid(syntax_name: str):
    """Get the UID object for a transfer syntax name"""
    return TRANSFER_SYNTAX_MAP.get(syntax_name, JPEG2000Lossless)


def detect_local_ip() -> Optional[str]:
    """
    Detect the local IP address automatically.
    Returns the most likely local network IP.
    """
    try:
        # Create a socket to determine which interface would be used
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        # Connect to a public DNS server (doesn't actually send data)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip if not local_ip.startswith('127.') else None
    except Exception:
        return None


class SeriesStabilityTracker:
    """
    Tracks series image counts across sync cycles to detect when series are stable.
    A series is considered stable when its image count hasn't changed between cycles.
    This prevents transferring incomplete series that are still being uploaded.
    """

    def __init__(self, tracker_file: str = STABILITY_TRACKER_FILE):
        self.tracker_file = tracker_file
        self.series_states: Dict[str, Dict] = {}
        self.load()

    def _make_key(self, remote_node_name: str, study_uid: str, series_uid: str) -> str:
        """Create a unique key for a series"""
        return f"{remote_node_name}|{study_uid}|{series_uid}"

    def load(self):
        """Load tracker state from file"""
        if os.path.exists(self.tracker_file):
            try:
                with open(self.tracker_file, 'r') as f:
                    self.series_states = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.series_states = {}

    def save(self):
        """Save tracker state to file"""
        try:
            with open(self.tracker_file, 'w') as f:
                json.dump(self.series_states, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save stability tracker: {e}")

    def update_series(self, remote_node_name: str, study_uid: str, series_uid: str,
                     image_count: int) -> bool:
        """
        Update series state and return whether it's stable for transfer.

        Returns:
            True if series is stable (unchanged from last cycle), False otherwise
        """
        key = self._make_key(remote_node_name, study_uid, series_uid)
        now = datetime.now().isoformat()

        if key in self.series_states:
            old_count = self.series_states[key]['image_count']

            if old_count == image_count:
                # Image count unchanged - series is stable
                self.series_states[key]['last_seen'] = now
                self.series_states[key]['stable_since'] = self.series_states[key].get('stable_since', now)
                return True
            else:
                # Image count changed - series is still growing
                self.series_states[key] = {
                    'image_count': image_count,
                    'last_seen': now,
                    'stable_since': None
                }
                return False
        else:
            # First time seeing this series - wait for next cycle
            self.series_states[key] = {
                'image_count': image_count,
                'last_seen': now,
                'stable_since': None
            }
            return False

    def mark_transferred(self, remote_node_name: str, study_uid: str, series_uid: str):
        """Remove series from tracker after successful transfer"""
        key = self._make_key(remote_node_name, study_uid, series_uid)
        if key in self.series_states:
            del self.series_states[key]

    def cleanup_old_entries(self, max_age_hours: int = 48):
        """Remove series that haven't been seen in max_age_hours"""
        now = datetime.now()
        keys_to_remove = []

        for key, state in self.series_states.items():
            try:
                last_seen = datetime.fromisoformat(state['last_seen'])
                age_hours = (now - last_seen).total_seconds() / 3600
                if age_hours > max_age_hours:
                    keys_to_remove.append(key)
            except (ValueError, KeyError):
                # Invalid timestamp - remove entry
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self.series_states[key]

        if keys_to_remove:
            print(f"Cleaned up {len(keys_to_remove)} old series from stability tracker")


class DicomNode:
    """Represents a DICOM node configuration"""

    def __init__(self, name: str, ae_title: str, ip_address: str, port: int,
                 transfer_syntax: str = "JPEG2000Lossless", local_config: Optional[Dict] = None):
        self.name = name
        self.ae_title = ae_title
        self.ip_address = ip_address
        self.port = port
        self.transfer_syntax = transfer_syntax
        self.local_config = local_config  # How this node sees the local server

    def __repr__(self):
        return f"DicomNode({self.name}, {self.ae_title}@{self.ip_address}:{self.port}, {self.transfer_syntax})"

    def to_dict(self) -> Dict:
        data = {
            "name": self.name,
            "ae_title": self.ae_title,
            "ip_address": self.ip_address,
            "port": self.port,
            "transfer_syntax": self.transfer_syntax
        }
        if self.local_config:
            data["local_config"] = self.local_config
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> 'DicomNode':
        return cls(
            name=data["name"],
            ae_title=data["ae_title"],
            ip_address=data["ip_address"],
            port=data["port"],
            transfer_syntax=data.get("transfer_syntax", "JPEG2000Lossless"),
            local_config=data.get("local_config")  # Optional per-remote local config
        )


class DicomConfig:
    """Manages DICOM configuration"""

    def __init__(self, config_file: str = CONFIG_FILE):
        self.config_file = config_file
        self.local_node: Optional[DicomNode] = None
        self.remote_nodes: Dict[str, DicomNode] = {}  # Dictionary of remote nodes by short name

    def load(self, auto_detect_local_ip: bool = True) -> bool:
        """
        Load configuration from file. Returns True if successful.

        Args:
            auto_detect_local_ip: If True, automatically detect and update local IP address
        """
        if not os.path.exists(self.config_file):
            return False

        try:
            with open(self.config_file, 'r') as f:
                data = json.load(f)

            self.local_node = DicomNode.from_dict(data["local"])

            # Load remote nodes - support both old single 'remote' and new 'remotes' format
            if "remotes" in data:
                # New format: multiple remote nodes
                for short_name, node_data in data["remotes"].items():
                    self.remote_nodes[short_name] = DicomNode.from_dict(node_data)
            elif "remote" in data:
                # Old format: single remote node - migrate to new format with default name
                remote_node = DicomNode.from_dict(data["remote"])
                # Use the node's name as short name, or fallback to "default"
                short_name = remote_node.name.lower().replace(" ", "_") if remote_node.name else "default"
                self.remote_nodes[short_name] = remote_node
                print(f"Migrated old config format: remote node now accessible as '{short_name}'")

            # Auto-detect local IP if enabled
            if auto_detect_local_ip:
                detected_ip = detect_local_ip()
                if detected_ip and detected_ip != self.local_node.ip_address:
                    print(f"📍 Local IP changed: {self.local_node.ip_address} → {detected_ip}")
                    self.local_node.ip_address = detected_ip
                    # Save updated config
                    self.save()
                    print(f"   Configuration automatically updated")

            return True
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error loading config: {e}")
            return False

    def save(self):
        """Save configuration to file"""
        data = {
            "local": self.local_node.to_dict(),
            "remotes": {short_name: node.to_dict() for short_name, node in self.remote_nodes.items()}
        }

        with open(self.config_file, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"Configuration saved to {self.config_file}")

    def interactive_setup(self):
        """Interactively set up configuration"""
        print("\n=== DICOM Configuration Setup ===\n")

        print("Local DICOM Node Configuration:")
        local_name = input("  Name (e.g., 'Local PACS'): ").strip()
        local_ae = input("  AE Title: ").strip()
        local_ip = input("  IP Address: ").strip()
        local_port = int(input("  Port: ").strip())

        self.local_node = DicomNode(local_name, local_ae, local_ip, local_port)

        print("\nRemote DICOM Node Configuration:")
        print("You can configure multiple remote nodes.\n")

        while True:
            short_name = input("  Short name for this remote node (e.g., 'ct', 'mri', 'hospital1'): ").strip().lower()
            if not short_name:
                print("  Short name cannot be empty!")
                continue
            if short_name in self.remote_nodes:
                print(f"  Node '{short_name}' already exists!")
                continue

            remote_name = input("  Full name (e.g., 'CT Scanner PACS'): ").strip()
            remote_ae = input("  AE Title: ").strip()
            remote_ip = input("  IP Address: ").strip()
            remote_port = int(input("  Port: ").strip())

            print("\n  Transfer Syntax:")
            print("    1) JPEG2000Lossless (compressed, default)")
            print("    2) ExplicitVRLittleEndian (most compatible)")
            print("    3) ImplicitVRLittleEndian (legacy)")
            syntax_choice = input("  Choose transfer syntax (1-3, default=1): ").strip()

            if syntax_choice == "2":
                transfer_syntax = "ExplicitVRLittleEndian"
            elif syntax_choice == "3":
                transfer_syntax = "ImplicitVRLittleEndian"
            else:
                transfer_syntax = "JPEG2000Lossless"

            # Ask for remote-specific local configuration
            print("\n  Local Configuration (how this remote knows YOU):")
            use_custom = input("    Does this remote know you differently than default? (y/n, default=n): ").strip().lower()

            local_config = None
            if use_custom == 'y':
                print("    Enter how this remote PACS knows your local server:")
                local_ae = input("      AE Title: ").strip()
                local_ip = input("      IP Address: ").strip()
                local_port = int(input("      Port: ").strip())
                local_config = {
                    "ae_title": local_ae,
                    "ip_address": local_ip,
                    "port": local_port
                }
                print(f"    ✓ Custom local config: {local_ae}@{local_ip}:{local_port}")

            self.remote_nodes[short_name] = DicomNode(remote_name, remote_ae, remote_ip, remote_port,
                                                     transfer_syntax, local_config)
            print(f"  ✓ Remote node '{short_name}' added with {transfer_syntax}")

            add_more = input("\n  Add another remote node? (y/n): ").strip().lower()
            if add_more != 'y':
                break

        print("\nConfiguration complete!")
        self.save()

    def get_remote_node(self, short_name: str) -> Optional[DicomNode]:
        """Get a remote node by its short name"""
        return self.remote_nodes.get(short_name)

    def list_remote_nodes(self) -> List[str]:
        """Get list of all remote node short names"""
        return list(self.remote_nodes.keys())


class DicomSeries:
    """Represents a DICOM series"""

    def __init__(self, series_uid: str, series_number: str, num_images: int,
                 modality: str = "", series_description: str = ""):
        self.series_uid = series_uid
        self.series_number = series_number
        self.num_images = num_images
        self.modality = modality
        self.series_description = series_description

    def __repr__(self):
        return f"Series({self.series_uid}, {self.num_images} images)"


class DicomStudy:
    """Represents a DICOM study"""

    def __init__(self, study_uid: str, study_date: str, patient_id: str,
                 patient_name: str = "", study_description: str = "", study_time: str = "",
                 num_images: int = 0):
        self.study_uid = study_uid
        self.study_date = study_date
        self.patient_id = patient_id
        self.patient_name = patient_name
        self.study_description = study_description
        self.study_time = study_time
        self.num_images = num_images
        self.series: List[DicomSeries] = []

    def __repr__(self):
        return f"Study({self.study_uid}, {self.study_date}, {self.patient_id})"

    def __eq__(self, other):
        return self.study_uid == other.study_uid

    def __hash__(self):
        return hash(self.study_uid)


class DicomQueryClient:
    """Client for querying DICOM servers"""

    def __init__(self, calling_ae_title: str = "QUERY_CLIENT"):
        self.calling_ae_title = calling_ae_title
        self.ae = AE(ae_title=calling_ae_title)
        self.ae.add_requested_context(StudyRootQueryRetrieveInformationModelFind)
        self.ae.add_requested_context(StudyRootQueryRetrieveInformationModelMove)
        # Note: Transfer syntax for C-MOVE is set per-node in move_series() method

    def query_studies(self, node: DicomNode, date_from: str, date_to: str) -> List[DicomStudy]:
        """
        Query studies from a DICOM node for a date range.

        Args:
            node: DicomNode to query
            date_from: Start date in YYYYMMDD format
            date_to: End date in YYYYMMDD format

        Returns:
            List of DicomStudy objects
        """
        print(f"\nQuerying {node.name} ({node.ae_title}@{node.ip_address}:{node.port})...")
        print(f"Date range: {date_from} to {date_to}")

        # Create the C-FIND query dataset
        ds = Dataset()
        ds.QueryRetrieveLevel = 'STUDY'
        ds.StudyDate = f"{date_from}-{date_to}"  # Date range query
        ds.StudyInstanceUID = ''
        ds.PatientID = ''
        ds.PatientName = ''
        ds.StudyDescription = ''
        ds.StudyTime = ''
        ds.NumberOfStudyRelatedInstances = ''

        studies = []

        try:
            # Associate with peer AE
            assoc = self.ae.associate(node.ip_address, node.port, ae_title=node.ae_title)

            if assoc.is_established:
                # Send the C-FIND request
                responses = assoc.send_c_find(ds, StudyRootQueryRetrieveInformationModelFind)

                for (status, identifier) in responses:
                    if status:
                        # If status is pending, we have results
                        if status.Status in (0xFF00, 0xFF01):
                            if identifier:
                                num_images = identifier.get('NumberOfStudyRelatedInstances', '')
                                num_images_int = int(num_images) if num_images and str(num_images).isdigit() else 0

                                study = DicomStudy(
                                    study_uid=str(identifier.get('StudyInstanceUID', '')),
                                    study_date=str(identifier.get('StudyDate', '')),
                                    patient_id=str(identifier.get('PatientID', '')),
                                    patient_name=str(identifier.get('PatientName', '')),
                                    study_description=str(identifier.get('StudyDescription', '')),
                                    study_time=str(identifier.get('StudyTime', '')),
                                    num_images=num_images_int
                                )
                                studies.append(study)
                        else:
                            # Query completed
                            break
                    else:
                        print('Connection timed out, was aborted or received invalid response')

                # Release the association
                assoc.release()

                print(f"Found {len(studies)} studies")
            else:
                print(f"Association rejected, aborted or never connected to {node.name}")

        except Exception as e:
            print(f"Error querying {node.name}: {e}")

        return studies

    def query_series(self, node: DicomNode, study_uid: str) -> List[DicomSeries]:
        """
        Query series for a specific study.

        Args:
            node: DicomNode to query
            study_uid: Study Instance UID

        Returns:
            List of DicomSeries objects
        """
        # Create the C-FIND query dataset for series level
        ds = Dataset()
        ds.QueryRetrieveLevel = 'SERIES'
        ds.StudyInstanceUID = study_uid
        ds.SeriesInstanceUID = ''
        ds.SeriesNumber = ''
        ds.Modality = ''
        ds.SeriesDescription = ''
        ds.NumberOfSeriesRelatedInstances = ''

        series_list = []

        try:
            # Associate with peer AE
            assoc = self.ae.associate(node.ip_address, node.port, ae_title=node.ae_title)

            if assoc.is_established:
                # Send the C-FIND request
                responses = assoc.send_c_find(ds, StudyRootQueryRetrieveInformationModelFind)

                for (status, identifier) in responses:
                    if status:
                        if status.Status in (0xFF00, 0xFF01):
                            if identifier:
                                num_images = identifier.get('NumberOfSeriesRelatedInstances', '')
                                num_images_int = int(num_images) if num_images and str(num_images).isdigit() else 0

                                series = DicomSeries(
                                    series_uid=str(identifier.get('SeriesInstanceUID', '')),
                                    series_number=str(identifier.get('SeriesNumber', '')),
                                    num_images=num_images_int,
                                    modality=str(identifier.get('Modality', '')),
                                    series_description=str(identifier.get('SeriesDescription', ''))
                                )
                                series_list.append(series)
                        else:
                            break

                assoc.release()

        except Exception as e:
            print(f"Error querying series: {e}")

        return series_list

    def query_images(self, node: DicomNode, study_uid: str, series_uid: str) -> List[str]:
        """
        Query all image SOPInstanceUIDs for a specific series.

        Args:
            node: DicomNode to query
            study_uid: Study Instance UID
            series_uid: Series Instance UID

        Returns:
            List of SOPInstanceUIDs
        """
        # Create the C-FIND query dataset for image level
        ds = Dataset()
        ds.QueryRetrieveLevel = 'IMAGE'
        ds.StudyInstanceUID = study_uid
        ds.SeriesInstanceUID = series_uid
        ds.SOPInstanceUID = ''

        image_uids = []

        try:
            # Associate with peer AE
            assoc = self.ae.associate(node.ip_address, node.port, ae_title=node.ae_title)

            if assoc.is_established:
                # Send the C-FIND request
                responses = assoc.send_c_find(ds, StudyRootQueryRetrieveInformationModelFind)

                for (status, identifier) in responses:
                    if status:
                        if status.Status in (0xFF00, 0xFF01):
                            if identifier:
                                sop_uid = str(identifier.get('SOPInstanceUID', ''))
                                if sop_uid:
                                    image_uids.append(sop_uid)
                        else:
                            break

                assoc.release()

        except Exception as e:
            print(f"Error querying images: {e}")

        return image_uids

    def move_series(self, source_node: DicomNode, dest_ae_title: str, dest_ip: str,
                    dest_port: int, study_uid: str, series_uid: str) -> bool:
        """
        Move a series from source to destination using C-MOVE.

        Args:
            source_node: Source DICOM node
            dest_ae_title: Destination AE title (how source knows us)
            dest_ip: Destination IP address (how source knows us)
            dest_port: Destination port (how source knows us)
            study_uid: Study Instance UID
            series_uid: Series Instance UID

        Returns:
            True if successful, False otherwise
        """
        # Create the C-MOVE query dataset
        ds = Dataset()
        ds.QueryRetrieveLevel = 'SERIES'
        ds.StudyInstanceUID = study_uid
        ds.SeriesInstanceUID = series_uid

        try:
            # Create a new AE for this specific C-MOVE with the node's transfer syntax
            move_ae = AE(ae_title=self.calling_ae_title)

            # Add the node-specific transfer syntax as preferred
            transfer_syntax_uid = get_transfer_syntax_uid(source_node.transfer_syntax)

            # Add presentation contexts with multiple transfer syntaxes for better compatibility
            # Primary: node-specific syntax
            move_ae.add_requested_context(StudyRootQueryRetrieveInformationModelMove, [
                transfer_syntax_uid,
                ImplicitVRLittleEndian  # Always add as fallback
            ])

            print(f"  Transfer syntax: {source_node.transfer_syntax}")
            print(f"  C-MOVE destination: {dest_ae_title}@{dest_ip}:{dest_port}")

            # Associate with peer AE
            assoc = move_ae.associate(source_node.ip_address, source_node.port,
                                     ae_title=source_node.ae_title)

            if assoc.is_established:
                # Send the C-MOVE request
                responses = assoc.send_c_move(ds, dest_ae_title, StudyRootQueryRetrieveInformationModelMove)

                # Track if we received a final success status
                success = False

                # Consume ALL responses to ensure C-MOVE completes
                for (status, identifier) in responses:
                    if status:
                        # Pending status
                        if status.Status == 0xFF00:
                            continue
                        # Success status
                        elif status.Status == 0x0000:
                            success = True
                            # Continue to consume remaining responses
                            continue
                        else:
                            # Failed or warning
                            print(f"  C-MOVE failed with status: 0x{status.Status:04X}")
                            if hasattr(status, 'ErrorComment'):
                                print(f"  Error comment: {status.ErrorComment}")
                            return False

                assoc.release()
                return success
            else:
                print(f"  Association rejected or failed to {source_node.name}")
                print(f"  Rejection reason: {assoc.rejected if hasattr(assoc, 'rejected') else 'Unknown'}")
                return False

        except Exception as e:
            print(f"  Exception during C-MOVE: {e}")
            import traceback
            traceback.print_exc()
            return False

    def move_image(self, source_node: DicomNode, dest_ae_title: str, dest_ip: str,
                   dest_port: int, study_uid: str, series_uid: str, sop_instance_uid: str) -> bool:
        """
        Move a single image from source to destination using C-MOVE.

        Args:
            source_node: Source DICOM node
            dest_ae_title: Destination AE title (how source knows us)
            dest_ip: Destination IP address (how source knows us)
            dest_port: Destination port (how source knows us)
            study_uid: Study Instance UID
            series_uid: Series Instance UID
            sop_instance_uid: SOP Instance UID of the image

        Returns:
            True if successful, False otherwise
        """
        # Create the C-MOVE query dataset for image level
        ds = Dataset()
        ds.QueryRetrieveLevel = 'IMAGE'
        ds.StudyInstanceUID = study_uid
        ds.SeriesInstanceUID = series_uid
        ds.SOPInstanceUID = sop_instance_uid

        try:
            # Create a new AE for this specific C-MOVE
            move_ae = AE(ae_title=self.calling_ae_title)

            # Add the node-specific transfer syntax
            transfer_syntax_uid = get_transfer_syntax_uid(source_node.transfer_syntax)

            move_ae.add_requested_context(StudyRootQueryRetrieveInformationModelMove, [
                transfer_syntax_uid,
                ImplicitVRLittleEndian
            ])

            # Associate with peer AE
            assoc = move_ae.associate(source_node.ip_address, source_node.port,
                                     ae_title=source_node.ae_title)

            if assoc.is_established:
                # Send the C-MOVE request
                responses = assoc.send_c_move(ds, dest_ae_title, StudyRootQueryRetrieveInformationModelMove)

                success = False

                # Consume all responses
                for (status, identifier) in responses:
                    if status:
                        if status.Status == 0xFF00:
                            continue
                        elif status.Status == 0x0000:
                            success = True
                            continue
                        else:
                            return False

                assoc.release()
                return success
            else:
                return False

        except Exception as e:
            return False



def get_date_range() -> tuple:
    """Get today and yesterday in YYYYMMDD format"""
    today = datetime.now()
    yesterday = today - timedelta(days=1)

    today_str = today.strftime("%Y%m%d")
    yesterday_str = yesterday.strftime("%Y%m%d")

    return yesterday_str, today_str


def parse_day_keyword(day_keyword: str) -> tuple:
    """
    Parse a day keyword and return date range for that single day.

    Args:
        day_keyword: One of 'today', 'yesterday', or a date in YYYYMMDD format

    Returns:
        Tuple of (date_from, date_to) in YYYYMMDD format (same day for both)
    """
    today = datetime.now()

    if day_keyword.lower() == 'today':
        target_date = today
    elif day_keyword.lower() == 'yesterday':
        target_date = today - timedelta(days=1)
    else:
        # Try to parse as YYYYMMDD format
        try:
            target_date = datetime.strptime(day_keyword, "%Y%m%d")
        except ValueError:
            raise ValueError(f"Invalid day keyword: '{day_keyword}'. Use 'today', 'yesterday', or YYYYMMDD format")

    date_str = target_date.strftime("%Y%m%d")
    return date_str, date_str


def is_within_last_hours(study_date: str, study_time: str, hours: int = 3) -> bool:
    """
    Check if a study is within the last N hours.

    Args:
        study_date: Study date in YYYYMMDD format
        study_time: Study time in HHMMSS format
        hours: Number of hours to look back (default: 3)

    Returns:
        True if study is within last N hours, False otherwise
    """
    if not study_date or len(study_date) < 8:
        return False

    # Parse study time (handle various formats)
    study_time_clean = study_time.replace('.', '').replace(':', '')
    if len(study_time_clean) < 6:
        study_time_clean = study_time_clean.ljust(6, '0')

    try:
        # Create datetime from study date and time
        study_datetime_str = f"{study_date}{study_time_clean[:6]}"
        study_datetime = datetime.strptime(study_datetime_str, "%Y%m%d%H%M%S")

        # Calculate N hours ago
        hours_ago = datetime.now() - timedelta(hours=hours)

        return study_datetime >= hours_ago
    except (ValueError, TypeError):
        # If parsing fails, exclude the study
        return False


def compare_studies(remote_studies: List[DicomStudy], local_studies: List[DicomStudy]) -> List[DicomStudy]:
    """
    Compare remote and local studies, return studies missing on local.

    Args:
        remote_studies: List of studies from remote server
        local_studies: List of studies from local server

    Returns:
        List of studies present on remote but missing on local
    """
    local_uids = {study.study_uid for study in local_studies}
    missing_studies = [study for study in remote_studies if study.study_uid not in local_uids]

    return missing_studies


def compare_series_and_filter(studies: List[DicomStudy], client: DicomQueryClient,
                              remote_node: DicomNode, local_node: DicomNode,
                              stability_tracker: Optional[SeriesStabilityTracker] = None,
                              max_images: Optional[int] = None,
                              all_series: bool = False) -> List[tuple]:
    """
    Query series for each study on both remote and local, then filter incomplete series.

    A series is considered incomplete if:
    - It doesn't exist on local, OR
    - It exists but has fewer images than on remote

    Args:
        studies: List of studies to check
        client: DICOM query client
        remote_node: Remote node to query
        local_node: Local node to query
        stability_tracker: Optional tracker to ensure series are stable before transfer
        max_images: If set, transfer all series with up to this many images
        all_series: If True, transfer all series

    Returns:
        List of tuples (study, remote_series, local_image_count) for series to transfer
    """
    transfer_list = []

    print(f"\nAnalyzing series in {len(studies)} studies...")
    if max_images is not None:
        print(f"  Mode: Transfer series with ≤ {max_images} images")
    else:
        print(f"  Mode: Transfer all incomplete series (default)")

    for i, study in enumerate(studies, 1):
        print(f"  [{i}/{len(studies)}] Checking series for {study.patient_name} ({study.study_date})...")

        # Query series on remote
        print(f"      Querying remote server...")
        remote_series_list = client.query_series(remote_node, study.study_uid)
        study.series = remote_series_list
        print(f"      Found {len(remote_series_list)} series on remote")

        if not remote_series_list:
            continue

        # Query series on local
        print(f"      Querying local server...")
        local_series_list = client.query_series(local_node, study.study_uid)
        local_series_dict = {series.series_uid: series.num_images for series in local_series_list}
        print(f"      Found {len(local_series_list)} series on local")

        # Find incomplete series
        for series in remote_series_list:
            local_image_count = local_series_dict.get(series.series_uid, 0)

            # Skip if series is complete
            if local_image_count >= series.num_images:
                print(f"      Series {series.series_number}: {series.num_images} images - COMPLETE (skip)")
                continue

            # Skip if series has no images
            if series.num_images <= 0:
                print(f"      Series {series.series_number}: 0 images - EMPTY (skip)")
                continue

            # Calculate missing images
            missing_images = series.num_images - local_image_count

            # CRITICAL: Skip if only 1-3 images are missing from larger series (>10 images)
            # Small series (<=10 images) with few missing images are allowed
            if missing_images <= 3 and series.num_images > 10:
                print(f"      Series {series.series_number}: {series.num_images} images ({local_image_count} local) - SKIP (only {missing_images} images missing, series > 10 images)")
                continue

            # Check series stability if tracker is enabled
            if stability_tracker:
                is_stable = stability_tracker.update_series(
                    remote_node.name, study.study_uid, series.series_uid, series.num_images
                )
                if not is_stable:
                    print(f"      Series {series.series_number}: {series.num_images} images ({local_image_count} local) - WAIT (series not yet stable, checking again next cycle)")
                    continue

            # Apply filtering based on selection criteria
            should_transfer = False
            reason = ""

            if max_images is not None:
                # Transfer series with up to N images
                should_transfer = series.num_images <= max_images
                if should_transfer:
                    reason = f"has {series.num_images} ≤ {max_images} images ({missing_images} missing)"
                else:
                    reason = f"has {series.num_images} > {max_images} images"
            else:
                # Default mode: transfer all incomplete series (like --all-series)
                should_transfer = True
                reason = f"incomplete ({missing_images} images missing)"

            status = "→ TRANSFER" if should_transfer else "SKIP"
            print(f"      Series {series.series_number}: {series.num_images} images ({local_image_count} local) - {status} ({reason})")

            if should_transfer:
                transfer_list.append((study, series, local_image_count))

    return transfer_list


def wait_for_series_completion(client: DicomQueryClient, local_node: DicomNode,
                               study_uid: str, series_uid: str, expected_images: int,
                               timeout: int = 60, check_interval: float = 1.5) -> bool:
    """
    Wait for a series to complete transfer by monitoring the local server.

    Args:
        client: DICOM query client
        local_node: Local node to query
        study_uid: Study Instance UID
        series_uid: Series Instance UID
        expected_images: Expected number of images
        timeout: Maximum time to wait in seconds
        check_interval: Time between checks in seconds

    Returns:
        True if series completed successfully, False if timeout
    """
    start_time = time.time()
    last_count = 0
    stable_count = 0

    while time.time() - start_time < timeout:
        # Query local server for this series
        series_list = client.query_series(local_node, study_uid)

        # Find our specific series
        current_count = 0
        for series in series_list:
            if series.series_uid == series_uid:
                current_count = series.num_images
                break

        # Check if we reached expected count
        if current_count >= expected_images:
            print(f"    ✓ Series complete: {current_count}/{expected_images} images arrived")
            return True

        # Check if count is stable (no new images arriving)
        if current_count == last_count:
            stable_count += 1
            # If count hasn't changed for 3 checks (4.5 seconds), consider it done
            if stable_count >= 3:
                if current_count > 0:
                    print(f"    ⚠ Transfer may be incomplete: {current_count}/{expected_images} images (no new images for {stable_count * check_interval:.1f}s)")
                    return True  # Accept partial transfer
                else:
                    # No images arrived at all - likely a failed transfer
                    print(f"    ✗ No images arrived after {stable_count * check_interval:.1f}s - transfer failed")
                    return False
        else:
            # Count changed, reset stable counter
            stable_count = 0
            print(f"    → Receiving: {current_count}/{expected_images} images...")

        last_count = current_count
        time.sleep(check_interval)

    # Timeout reached
    print(f"    ✗ Timeout after {timeout}s: {last_count}/{expected_images} images")
    return False


def transfer_series_sequential(transfer_list: List[tuple], client: DicomQueryClient,
                               remote_node: DicomNode, local_ae_title: str,
                               local_ip: str, local_port: int,
                               local_node: DicomNode,
                               stability_tracker: Optional[SeriesStabilityTracker] = None,
                               use_image_level: bool = False) -> int:
    """
    Transfer series sequentially (one at a time) with detailed status output and live speed tracking.

    Args:
        transfer_list: List of (study, series, local_image_count) tuples to transfer
        client: DICOM query client
        remote_node: Remote node (source)
        local_ae_title: Local AE title (how remote knows us)
        local_ip: Local IP address (how remote knows us)
        local_port: Local port (how remote knows us)
        local_node: Local node to query for completion
        stability_tracker: Optional tracker to mark series as transferred
        use_image_level: If True, use IMAGE-level C-MOVE for partial series

    Returns:
        Number of images transferred
    """
    if not transfer_list:
        print("\nNo series to transfer")
        return 0

    total_series = len(transfer_list)
    total_images = sum(series.num_images for _, series, _ in transfer_list)

    transferred_series = 0
    transferred_images = 0
    failed_series = 0

    overall_start_time = time.time()

    print(f"\nStarting transfer: {total_series} series, {total_images} images")
    print(f"{'=' * 120}\n")

    for i, (study, series, local_count) in enumerate(transfer_list, 1):
        # Format study information
        date_formatted = f"{study.study_date[:4]}-{study.study_date[4:6]}-{study.study_date[6:8]}" if len(study.study_date) == 8 else study.study_date
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Show completeness status
        if local_count == 0:
            status_info = f"New series ({series.num_images} img)"
        else:
            status_info = f"Incomplete ({local_count}/{series.num_images} img)"

        # Print C-MOVE info with timestamp
        print(f"[{timestamp}] [{i}/{total_series}] C-MOVE START")
        print(f"  Patient: {study.patient_name}")
        print(f"  Date: {date_formatted}")
        print(f"  Series: {series.series_number} ({series.modality}) - {status_info}")
        print(f"  Description: {series.series_description[:60]}")

        # Track series transfer time
        series_start_time = time.time()

        # Determine transfer strategy: IMAGE-level for partial series, SERIES-level for new/mostly missing
        missing_images = series.num_images - local_count
        use_image_transfer = False

        if use_image_level and local_count > 0:
            # Calculate percentage of missing images
            missing_percentage = missing_images / series.num_images

            # Use IMAGE-level if less than 30% is missing
            if missing_percentage < 0.3:
                use_image_transfer = True
                print(f"  Strategy: IMAGE-level (only {missing_images} of {series.num_images} images missing, {missing_percentage*100:.1f}%)")
            else:
                print(f"  Strategy: SERIES-level ({missing_images} of {series.num_images} images missing, {missing_percentage*100:.1f}%)")

        # Perform the transfer
        if use_image_transfer:
            # IMAGE-level transfer: Query which images exist, transfer only missing ones
            print(f"  Querying remote for image list...")
            remote_image_uids = client.query_images(remote_node, study.study_uid, series.series_uid)
            print(f"  Found {len(remote_image_uids)} images on remote")

            print(f"  Querying local for image list...")
            local_image_uids = client.query_images(local_node, study.study_uid, series.series_uid)
            local_image_uid_set = set(local_image_uids)
            print(f"  Found {len(local_image_uids)} images on local")

            # Find missing images
            missing_image_uids = [uid for uid in remote_image_uids if uid not in local_image_uid_set]
            print(f"  Transferring {len(missing_image_uids)} missing images...")

            success_count = 0
            for j, image_uid in enumerate(missing_image_uids, 1):
                if j % 10 == 0 or j == len(missing_image_uids):
                    print(f"    Progress: {j}/{len(missing_image_uids)} images")

                img_success = client.move_image(remote_node, local_ae_title, local_ip, local_port,
                                               study.study_uid, series.series_uid, image_uid)
                if img_success:
                    success_count += 1

            success = success_count == len(missing_image_uids)
            if success:
                print(f"  ✓ All {len(missing_image_uids)} images transferred successfully")
            else:
                print(f"  ⚠ Only {success_count}/{len(missing_image_uids)} images transferred")
        else:
            # SERIES-level transfer: Transfer entire series
            success = client.move_series(remote_node, local_ae_title, local_ip, local_port,
                                         study.study_uid, series.series_uid)

        series_end_time = time.time()
        series_duration = series_end_time - series_start_time
        end_timestamp = datetime.now().strftime("%H:%M:%S")

        if success:
            transferred_series += 1
            transferred_images += series.num_images

            # Mark series as transferred in stability tracker
            if stability_tracker:
                stability_tracker.mark_transferred(remote_node.name, study.study_uid, series.series_uid)

            # Calculate speed for this series
            series_speed = series.num_images / series_duration if series_duration > 0 else 0

            # Calculate running average speed
            elapsed_time = series_end_time - overall_start_time
            avg_speed = transferred_images / elapsed_time if elapsed_time > 0 else 0

            print(f"[{end_timestamp}] C-MOVE COMPLETE ✓")
            print(f"  Speed: {series_speed:.1f} img/s (this series) | Average: {avg_speed:.1f} img/s | Time: {series_duration:.1f}s")

            # Wait for images to actually arrive by monitoring local server
            print(f"  Monitoring local server for image arrival...")
            wait_for_series_completion(client, local_node, study.study_uid, series.series_uid,
                                      series.num_images, timeout=60, check_interval=1.5)
        else:
            failed_series += 1
            print(f"[{end_timestamp}] C-MOVE FAILED ✗")

        print()  # Empty line between transfers

    total_time = time.time() - overall_start_time
    final_rate_per_second = transferred_images / total_time if total_time > 0 else 0
    final_rate_per_minute = final_rate_per_second * 60

    print(f"{'=' * 120}")
    print(f"Transfer statistics:")
    print(f"  Successfully transferred: {transferred_series}/{total_series} series ({transferred_images} images)")
    if failed_series > 0:
        print(f"  Failed: {failed_series} series")
    print(f"  Total time: {total_time:.1f} seconds ({total_time/60:.1f} minutes)")
    print(f"  Average transfer rate: {final_rate_per_second:.1f} images/second ({final_rate_per_minute:.1f} images/minute)")

    return transferred_images


def print_study_table(studies: List[DicomStudy], title: str):
    """Print studies in a formatted table"""
    print(f"\n{'=' * 100}")
    print(f"{title}")
    print(f"{'=' * 100}")

    if not studies:
        print("No studies found")
        return

    print(f"{'Study Date':<12} {'Time':<10} {'Patient Name':<25} {'Study Description':<35} {'Images':<8}")
    print(f"{'-' * 100}")

    for study in studies:
        date_formatted = f"{study.study_date[:4]}-{study.study_date[4:6]}-{study.study_date[6:8]}" if len(study.study_date) == 8 else study.study_date
        time_formatted = f"{study.study_time[:2]}:{study.study_time[2:4]}:{study.study_time[4:6]}" if len(study.study_time) >= 6 else study.study_time[:8]
        patient_name = study.patient_name[:22] + "..." if len(study.patient_name) > 25 else study.patient_name
        desc = study.study_description[:32] + "..." if len(study.study_description) > 35 else study.study_description
        print(f"{date_formatted:<12} {time_formatted:<10} {patient_name:<25} {desc:<35} {study.num_images:<8}")


def run_sync_cycle(config: DicomConfig, remote_node: DicomNode, client: DicomQueryClient,
                   stability_tracker: Optional[SeriesStabilityTracker] = None,
                   max_images: Optional[int] = None, all_series: bool = False, hours: int = 3,
                   download_day: Optional[str] = None, use_image_level: bool = False) -> int:
    """
    Run a single synchronization cycle

    Returns:
        Number of images transferred in this cycle
    """
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'=' * 100}")
    print(f"Starting sync cycle at {current_time}")
    print(f"{'=' * 100}")

    # Get date range
    if download_day:
        date_from, date_to = parse_day_keyword(download_day)
        print(f"Searching for ALL studies from day: {date_from}")
        filter_by_hours = False
    else:
        date_from, date_to = get_date_range()
        print(f"Searching for studies from {date_from} to {date_to}")
        print(f"Filtering studies within last {hours} hours")
        filter_by_hours = True

    # Query remote server
    print("\n" + "=" * 80)
    print("Querying Remote Server")
    print("=" * 80)
    remote_studies_all = client.query_studies(remote_node, date_from, date_to)

    # Filter remote studies to last N hours (only if not in download-day mode)
    if filter_by_hours:
        remote_studies = [s for s in remote_studies_all if is_within_last_hours(s.study_date, s.study_time, hours)]
        print(f"Filtered to {len(remote_studies)} studies within last {hours} hours (from {len(remote_studies_all)} total)")
    else:
        remote_studies = remote_studies_all
        print(f"Found {len(remote_studies)} studies on {date_from}")

    if not remote_studies:
        if filter_by_hours:
            print(f"\nNo remote studies found within last {hours} hours")
        else:
            print(f"\nNo remote studies found on {date_from}")
        cycle_end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n{'=' * 100}")
        print(f"Sync cycle completed at {cycle_end_time}")
        print(f"{'=' * 100}")
        return 0

    # Compare series between remote and local for all remote studies
    # This will check which series are missing on local, regardless of whether the study exists locally
    transfer_list = compare_series_and_filter(remote_studies, client, remote_node,
                                             config.local_node, stability_tracker=stability_tracker,
                                             max_images=max_images, all_series=all_series)

    # Print results
    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    print(f"Remote studies found: {len(remote_studies)}")

    if transfer_list:
        if max_images is not None:
            print(f"\nFound {len(transfer_list)} series to transfer (missing series with ≤ {max_images} images)")
        else:
            print(f"\nFound {len(transfer_list)} series to transfer (all incomplete series)")

        # Determine local config to use (remote-specific or default)
        if remote_node.local_config:
            local_ae_title = remote_node.local_config['ae_title']
            local_ip = remote_node.local_config['ip_address']
            local_port = remote_node.local_config['port']
            print(f"\nUsing remote-specific local config: {local_ae_title}@{local_ip}:{local_port}")
        else:
            local_ae_title = config.local_node.ae_title
            local_ip = config.local_node.ip_address
            local_port = config.local_node.port
            print(f"\nUsing default local config: {local_ae_title}@{local_ip}:{local_port}")

        # Start sequential transfer automatically
        transferred_images = transfer_series_sequential(transfer_list, client, remote_node,
                                                        local_ae_title, local_ip, local_port,
                                                        config.local_node,
                                                        stability_tracker=stability_tracker,
                                                        use_image_level=use_image_level)
    else:
        print("\nNo series found to transfer. All relevant series are present on local server!")
        transferred_images = 0

    cycle_end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'=' * 100}")
    print(f"Sync cycle completed at {cycle_end_time}")
    print(f"{'=' * 100}")

    return transferred_images


def main():
    """Main function - runs continuous synchronization every minute"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='DICOM Automatic Synchronization Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s --node ct                 # Transfer from remote node 'ct' (default mode, last 3 hours)
  %(prog)s --node mri --hours 6      # Transfer from 'mri' node, last 6 hours
  %(prog)s --node ct --max-images 300  # Transfer from 'ct', series with ≤ 300 images
  %(prog)s --node hospital1 --all-series  # Transfer all series from 'hospital1'
  %(prog)s --node ct --download-day yesterday  # Download ALL series from yesterday
  %(prog)s --node mri --download-day 20231225  # Download ALL series from specific date
        '''
    )

    parser.add_argument(
        '--node',
        type=str,
        required=True,
        metavar='NAME',
        help='Short name of the remote node to sync from (required)'
    )

    parser.add_argument(
        '--hours',
        type=int,
        default=3,
        metavar='N',
        help='Number of hours to look back for studies (default: 3, ignored with --download-day)'
    )

    parser.add_argument(
        '--download-day',
        type=str,
        metavar='DAY',
        help='Download ALL series from a specific day (e.g., "yesterday", "today", or "20231225")'
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--max-images',
        type=int,
        metavar='N',
        help='Transfer all series with up to N images'
    )
    group.add_argument(
        '--all-series',
        action='store_true',
        help='Transfer all series (no image count limit)'
    )

    parser.add_argument(
        '--no-auto-ip',
        action='store_true',
        help='Disable automatic local IP detection'
    )

    parser.add_argument(
        '--image-level',
        action='store_true',
        help='Use IMAGE-level C-MOVE for partial series (transfers only missing images)'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("DICOM Automatic Synchronization Tool")
    print("=" * 80)

    # Display transfer mode and time window
    if args.download_day:
        print(f"\nMode: DOWNLOAD ALL from day '{args.download_day}'")
        if args.all_series:
            print("Transfer mode: ALL SERIES from that day")
        elif args.max_images is not None:
            print(f"Transfer mode: Series with ≤ {args.max_images} images from that day")
        else:
            print("Transfer mode: ALL SERIES from that day (download-day forces all-series)")
            args.all_series = True  # Force all-series mode when downloading a specific day
    else:
        print(f"\nTime window: Last {args.hours} hours")
        if args.max_images is not None:
            print(f"Transfer mode: Series with ≤ {args.max_images} images")
        else:
            print("Transfer mode: All incomplete series (default)")

    # Show IMAGE-level mode if enabled
    if args.image_level:
        print("IMAGE-level mode: Enabled (only missing images transferred for partial series)")

    # Load or create configuration
    config = DicomConfig()

    if not config.load(auto_detect_local_ip=not args.no_auto_ip):
        print("\nNo configuration file found.")
        print("Please run the configuration setup first.")
        config.interactive_setup()

    # Get the selected remote node
    remote_node = config.get_remote_node(args.node)
    if not remote_node:
        print(f"\n❌ Error: Remote node '{args.node}' not found in configuration!")
        print(f"\nAvailable remote nodes:")
        available_nodes = config.list_remote_nodes()
        if available_nodes:
            for node_name in available_nodes:
                node = config.get_remote_node(node_name)
                print(f"  - {node_name}: {node.name} ({node.ae_title}@{node.ip_address}:{node.port})")
        else:
            print("  (no remote nodes configured)")
        print("\nPlease specify a valid remote node with --node <name>")
        sys.exit(1)

    print(f"\nConfiguration loaded:")
    print(f"  Local:  {config.local_node}")
    print(f"  Remote: {remote_node} (selected: '{args.node}')")

    # Create query client
    client = DicomQueryClient()

    # Create series stability tracker (only for continuous sync mode)
    stability_tracker = None
    if not args.download_day:
        stability_tracker = SeriesStabilityTracker()
        print(f"  Stability tracking: Enabled (prevents transferring incomplete series)")

    # If download-day is specified, run once and exit (no continuous sync)
    if args.download_day:
        print("\n" + "=" * 80)
        print("Starting one-time download")
        print("=" * 80)

        try:
            run_sync_cycle(config, remote_node, client, stability_tracker=None,
                          max_images=args.max_images, all_series=args.all_series,
                          hours=args.hours, download_day=args.download_day,
                          use_image_level=args.image_level)
        except ValueError as e:
            print(f"\n❌ Error: {e}")
            sys.exit(1)

        print("\n" + "=" * 80)
        print("Download completed")
        print("=" * 80)
        sys.exit(0)

    # Normal continuous sync mode
    print("\n" + "=" * 80)
    print("Starting automatic synchronization")
    print("Sync will run every 60 seconds (pauses only if <30 images transferred)")
    print("Press Ctrl+C to stop")
    print("=" * 80)

    cycle_count = 0

    try:
        while True:
            cycle_count += 1
            print(f"\n\n{'#' * 100}")
            print(f"{'#' * 100}")
            print(f"CYCLE {cycle_count}")
            print(f"{'#' * 100}")
            print(f"{'#' * 100}")

            # Clean up old entries from stability tracker every 10 cycles
            if stability_tracker and cycle_count % 10 == 0:
                stability_tracker.cleanup_old_entries()

            transferred_images = run_sync_cycle(config, remote_node, client,
                                               stability_tracker=stability_tracker,
                                               max_images=args.max_images,
                                               all_series=args.all_series, hours=args.hours,
                                               download_day=None,
                                               use_image_level=args.image_level)

            # Save stability tracker state after each cycle
            if stability_tracker:
                stability_tracker.save()

            # Wait 60 seconds if fewer than 30 images were transferred
            if transferred_images < 30:
                print(f"\nTransferred {transferred_images} images. Waiting 60 seconds before next sync cycle...")
                time.sleep(60)
            else:
                print(f"\nTransferred {transferred_images} images (≥30). Starting next cycle immediately...")
                time.sleep(1)  # Short pause to prevent tight loop

    except KeyboardInterrupt:
        print("\n\n" + "=" * 80)
        print("Synchronization stopped by user")
        print(f"Total cycles completed: {cycle_count}")
        print("=" * 80)
        sys.exit(0)


if __name__ == "__main__":
    main()
