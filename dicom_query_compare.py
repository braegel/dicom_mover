#!/usr/bin/env python3
"""
DICOM Automatic Synchronization Tool

This script automatically synchronizes DICOM studies from a remote server to a local server.
It runs continuously, checking every minute for missing studies from today and yesterday,
and automatically transfers series with ≤10 images using C-MOVE with JPEG 2000 Lossless.

Author: DICOM Expert
License: MIT
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from pydicom.dataset import Dataset
from pydicom.uid import JPEG2000Lossless
from pynetdicom import AE, debug_logger, evt
from pynetdicom.sop_class import (
    StudyRootQueryRetrieveInformationModelFind,
    StudyRootQueryRetrieveInformationModelMove
)


CONFIG_FILE = "dicom_config.json"


class DicomNode:
    """Represents a DICOM node configuration"""

    def __init__(self, name: str, ae_title: str, ip_address: str, port: int):
        self.name = name
        self.ae_title = ae_title
        self.ip_address = ip_address
        self.port = port

    def __repr__(self):
        return f"DicomNode({self.name}, {self.ae_title}@{self.ip_address}:{self.port})"

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "ae_title": self.ae_title,
            "ip_address": self.ip_address,
            "port": self.port
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'DicomNode':
        return cls(
            name=data["name"],
            ae_title=data["ae_title"],
            ip_address=data["ip_address"],
            port=data["port"]
        )


class DicomConfig:
    """Manages DICOM configuration"""

    def __init__(self, config_file: str = CONFIG_FILE):
        self.config_file = config_file
        self.local_node: Optional[DicomNode] = None
        self.remote_node: Optional[DicomNode] = None

    def load(self) -> bool:
        """Load configuration from file. Returns True if successful."""
        if not os.path.exists(self.config_file):
            return False

        try:
            with open(self.config_file, 'r') as f:
                data = json.load(f)

            self.local_node = DicomNode.from_dict(data["local"])
            self.remote_node = DicomNode.from_dict(data["remote"])
            return True
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error loading config: {e}")
            return False

    def save(self):
        """Save configuration to file"""
        data = {
            "local": self.local_node.to_dict(),
            "remote": self.remote_node.to_dict()
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
        remote_name = input("  Name (e.g., 'Remote PACS'): ").strip()
        remote_ae = input("  AE Title: ").strip()
        remote_ip = input("  IP Address: ").strip()
        remote_port = int(input("  Port: ").strip())

        self.remote_node = DicomNode(remote_name, remote_ae, remote_ip, remote_port)

        print("\nConfiguration complete!")
        self.save()


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

        # Add JPEG 2000 Lossless as preferred transfer syntax
        self.ae.add_requested_context(StudyRootQueryRetrieveInformationModelMove, JPEG2000Lossless)

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

    def move_series(self, source_node: DicomNode, dest_ae_title: str, study_uid: str,
                    series_uid: str) -> bool:
        """
        Move a series from source to destination using C-MOVE.

        Args:
            source_node: Source DICOM node
            dest_ae_title: Destination AE title
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
            # Associate with peer AE
            assoc = self.ae.associate(source_node.ip_address, source_node.port,
                                     ae_title=source_node.ae_title)

            if assoc.is_established:
                # Send the C-MOVE request
                responses = assoc.send_c_move(ds, dest_ae_title, StudyRootQueryRetrieveInformationModelMove)

                for (status, identifier) in responses:
                    if status:
                        # Success or pending
                        if status.Status in (0xFF00, 0x0000):
                            continue
                        else:
                            # Failed or warning
                            return False

                assoc.release()
                return True
            else:
                return False

        except Exception as e:
            print(f"Error during C-MOVE: {e}")
            return False


def get_date_range() -> tuple:
    """Get today and yesterday in YYYYMMDD format"""
    today = datetime.now()
    yesterday = today - timedelta(days=1)

    today_str = today.strftime("%Y%m%d")
    yesterday_str = yesterday.strftime("%Y%m%d")

    return yesterday_str, today_str


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


def filter_small_series(studies: List[DicomStudy], client: DicomQueryClient,
                        remote_node: DicomNode, max_images: int = 10) -> List[tuple]:
    """
    Query series for each study and filter those with <= max_images.

    Args:
        studies: List of studies to check
        client: DICOM query client
        remote_node: Remote node to query
        max_images: Maximum number of images per series (inclusive)

    Returns:
        List of tuples (study, series) for series to transfer
    """
    transfer_list = []

    print(f"\nAnalyzing series in {len(studies)} studies...")

    for i, study in enumerate(studies, 1):
        print(f"  [{i}/{len(studies)}] Querying series for {study.patient_name}...")

        series_list = client.query_series(remote_node, study.study_uid)
        study.series = series_list

        for series in series_list:
            if 0 < series.num_images <= max_images:
                transfer_list.append((study, series))

    return transfer_list


def transfer_series_sequential(transfer_list: List[tuple], client: DicomQueryClient,
                               remote_node: DicomNode, local_ae_title: str):
    """
    Transfer series sequentially (one at a time) with minimal status output.

    Args:
        transfer_list: List of (study, series) tuples to transfer
        client: DICOM query client
        remote_node: Remote node (source)
        local_ae_title: Local AE title (destination)
    """
    if not transfer_list:
        print("\nNo series to transfer (all series have > 10 images)")
        return

    total_series = len(transfer_list)
    total_images = sum(series.num_images for _, series in transfer_list)

    transferred_series = 0
    transferred_images = 0
    failed_series = 0

    start_time = time.time()

    print(f"\nStarting transfer: {total_series} series, {total_images} images\n")

    for i, (study, series) in enumerate(transfer_list, 1):
        # Format study information
        date_formatted = f"{study.study_date[:4]}-{study.study_date[4:6]}-{study.study_date[6:8]}" if len(study.study_date) == 8 else study.study_date

        # Single line output with carriage return for updating
        status_line = f"[{i}/{total_series}] {study.patient_name} | {date_formatted} | Series {series.series_number} ({series.num_images} img)"
        print(f"\r{status_line:<100}", end='', flush=True)

        # Perform the transfer
        success = client.move_series(remote_node, local_ae_title, study.study_uid, series.series_uid)

        if success:
            transferred_series += 1
            transferred_images += series.num_images
        else:
            failed_series += 1
            # Print failed transfers on a new line
            print(f"\r{status_line} - FAILED{' ' * 20}")

    # Clear the line and print final summary
    print(f"\r{' ' * 100}\r", end='')

    total_time = time.time() - start_time
    final_rate = (transferred_images / total_time * 60) if total_time > 0 else 0

    print(f"\nTransfer statistics:")
    print(f"  Successfully transferred: {transferred_series}/{total_series} series ({transferred_images} images)")
    if failed_series > 0:
        print(f"  Failed: {failed_series} series")
    print(f"  Total time: {total_time/60:.1f} minutes")
    print(f"  Transfer rate: {final_rate:.1f} images/minute")


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


def run_sync_cycle(config: DicomConfig, client: DicomQueryClient):
    """Run a single synchronization cycle"""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'=' * 100}")
    print(f"Starting sync cycle at {current_time}")
    print(f"{'=' * 100}")

    # Get date range (yesterday and today)
    date_from, date_to = get_date_range()
    print(f"Searching for studies from {date_from} to {date_to}")

    # Query remote server
    print("\n" + "=" * 80)
    print("Querying Remote Server")
    print("=" * 80)
    remote_studies = client.query_studies(config.remote_node, date_from, date_to)

    # Query local server
    print("\n" + "=" * 80)
    print("Querying Local Server")
    print("=" * 80)
    local_studies = client.query_studies(config.local_node, date_from, date_to)

    # Compare studies
    missing_studies = compare_studies(remote_studies, local_studies)

    # Print results
    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    print(f"Remote studies found: {len(remote_studies)}")
    print(f"Local studies found:  {len(local_studies)}")
    print(f"Missing on local:     {len(missing_studies)}")

    if missing_studies:
        print_study_table(missing_studies, "Studies Missing on Local Server")

        # Filter for small series
        transfer_list = filter_small_series(missing_studies, client, config.remote_node, max_images=10)

        if transfer_list:
            print(f"\nFound {len(transfer_list)} series with ≤10 images to transfer")

            # Start sequential transfer automatically
            transfer_series_sequential(transfer_list, client, config.remote_node,
                                      config.local_node.ae_title)
        else:
            print("\nNo series with ≤10 images found.")
    else:
        print("\nAll remote studies are present on the local server!")

    cycle_end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'=' * 100}")
    print(f"Sync cycle completed at {cycle_end_time}")
    print(f"{'=' * 100}")


def main():
    """Main function - runs continuous synchronization every minute"""
    print("=" * 80)
    print("DICOM Automatic Synchronization Tool")
    print("=" * 80)

    # Load or create configuration
    config = DicomConfig()

    if not config.load():
        print("\nNo configuration file found.")
        print("Please run the configuration setup first.")
        config.interactive_setup()

    print(f"\nConfiguration loaded:")
    print(f"  Local:  {config.local_node}")
    print(f"  Remote: {config.remote_node}")

    # Create query client
    client = DicomQueryClient()

    print("\n" + "=" * 80)
    print("Starting automatic synchronization")
    print("Sync will run every 60 seconds")
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

            run_sync_cycle(config, client)

            # Wait 60 seconds before next cycle
            print(f"\nWaiting 60 seconds before next sync cycle...")
            time.sleep(60)

    except KeyboardInterrupt:
        print("\n\n" + "=" * 80)
        print("Synchronization stopped by user")
        print(f"Total cycles completed: {cycle_count}")
        print("=" * 80)
        sys.exit(0)


if __name__ == "__main__":
    main()
