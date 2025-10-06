# DICOM Automatic Synchronization Tool

A Python tool that automatically synchronizes DICOM studies from a remote PACS server to a local PACS server. The tool continuously monitors for new and incomplete studies and automatically transfers series based on configurable image count criteria using DICOM C-MOVE operations.

## Features

- **Automatic Monitoring**: Runs continuously, checking every 60 seconds for new and incomplete studies
- **Completeness Checking**: Detects and re-transfers incomplete series (verifies image count remote vs. local)
- **Flexible Series Selection**:
  - Transfer only the smallest series per study (default)
  - Transfer all series with fewer than N images (configurable)
  - Transfer all series (no limit)
- **Configurable Time Window**: Only processes studies from the last N hours (default: 3 hours)
- **Sequential Transfer**: One C-MOVE at a time to avoid network overload
- **Detailed Logging**: Timestamp for each C-MOVE with status information
- **JPEG 2000 Lossless**: Supports JPEG 2000 Lossless transfer syntax
- **Progress Tracking**: Real-time transfer statistics and progress updates
- **Easy Configuration**: Interactive configuration setup for DICOM nodes

## Requirements

- Python 3.7 or higher
- Network access to both DICOM servers
- DICOM servers must support:
  - C-FIND (Study/Series level queries)
  - C-MOVE (for transfers)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/braegel/dicom_mover.git
cd dicom_mover
```

2. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install pydicom pynetdicom
```

## Configuration

On first run, the tool will prompt you to configure both DICOM nodes:

```bash
python3 dicom_query_compare.py
```

You'll be asked to provide:
- **Local PACS**:
  - Name (e.g., "Local PACS")
  - AE Title
  - IP Address
  - Port
- **Remote PACS**:
  - Name (e.g., "Remote PACS")
  - AE Title
  - IP Address
  - Port

Configuration is saved to `dicom_config.json` (excluded from git for security).

## Usage

### Basic Usage

Run the script with different transfer modes and time windows:

**Default Mode** - Transfer only the smallest series per study from last 3 hours:
```bash
python3 dicom_query_compare.py
```

**Custom Time Window** - Transfer from last 6 hours:
```bash
python3 dicom_query_compare.py --hours 6
```

**Custom Image Limit** - Transfer all series with fewer than N images:
```bash
python3 dicom_query_compare.py --min-images 300
```

**Transfer All Series** - Transfer all series without any limit:
```bash
python3 dicom_query_compare.py --all-series
```

**Combined Options** - Transfer all series < 300 images from last 12 hours:
```bash
python3 dicom_query_compare.py --hours 12 --min-images 300
```

**Help** - Display all available options:
```bash
python3 dicom_query_compare.py --help
```

### How It Works

The tool will:
1. Query both remote and local PACS for studies from yesterday and today
2. Filter studies to only those within the specified time window (default: last 3 hours)
3. For each study, query series information on both remote and local
4. Identify incomplete series (missing or fewer images on local than remote)
5. Automatically transfer incomplete series based on selected mode (one C-MOVE at a time)
6. Display detailed transfer status with timestamps
7. Wait 60 seconds and repeat

Press `Ctrl+C` to stop the synchronization.

**Note:** The completeness check (comparing image counts) is performed at the beginning of each sync cycle, not after each individual C-MOVE transfer.

## Options Explained

### Time Window (`--hours`)
```bash
python3 dicom_query_compare.py --hours 6
```
Specifies how many hours to look back for studies. Default is 3 hours. Only studies from the remote server that were created within this time window will be considered for synchronization. This helps focus on recent studies and reduces unnecessary transfers.

### Transfer Modes

#### Default Mode (Smallest Series Only)
```bash
python3 dicom_query_compare.py
```
For each missing study, only the series with the smallest number of images is transferred. This is useful for transferring scout/localizer images or small preview series.

#### Custom Image Limit
```bash
python3 dicom_query_compare.py --min-images 300
```
Transfers all series that have fewer than the specified number of images. For example, `--min-images 300` will transfer all series with 1-299 images. This is useful when you want to transfer multiple small series per study.

#### All Series
```bash
python3 dicom_query_compare.py --all-series
```
Transfers all series from missing studies without any image count restriction. Use this when you want complete studies transferred.

## Technical Details

1. **Query Phase**:
   - Queries remote PACS for studies (yesterday + today)
   - Filters to only studies within the specified time window (default: 3 hours)

2. **Completeness Check Phase**:
   - For each study, queries series information on both remote and local
   - Compares image counts for each series (remote vs. local)
   - Identifies incomplete series where local has fewer images than remote
   - Applies the selected filter mode (smallest/min-images/all)

3. **Transfer Phase**:
   - Uses DICOM C-MOVE to transfer incomplete series sequentially
   - **One C-MOVE at a time** to prevent network overload
   - Displays timestamp, patient info, and status for each transfer
   - Shows whether series is new or being completed
   - Provides detailed statistics after all transfers complete

## Output Example

```
================================================================================
DICOM Automatic Synchronization Tool
================================================================================

Time window: Last 3 hours
Transfer mode: Series with < 300 images

Configuration loaded:
  Local:  DicomNode(Local PACS, LOCAL@192.168.1.100:11112)
  Remote: DicomNode(Remote PACS, REMOTE@192.168.1.200:11112)

====================================================================================================
Starting sync cycle at 2025-10-06 14:30:00
====================================================================================================
Searching for studies from 20251005 to 20251006
Filtering studies within last 3 hours

Analyzing series in 5 studies...
  [1/5] Checking series for Doe^John...
  [2/5] Checking series for Smith^Jane...

Found 4 series to transfer (missing series with < 300 images)

Starting transfer: 4 series, 387 images
========================================================================================================================

[14:30:15] [1/4] C-MOVE START
  Patient: Doe^John
  Date: 2025-10-06
  Series: 1 (CT) - New series (120 images)
  Description: Thorax native
[14:31:42] C-MOVE COMPLETE ✓

[14:31:43] [2/4] C-MOVE START
  Patient: Doe^John
  Date: 2025-10-06
  Series: 2 (CT) - Incomplete (45/267 images)
  Description: Thorax arterial
[14:34:18] C-MOVE COMPLETE ✓

========================================================================================================================
Transfer statistics:
  Successfully transferred: 4/4 series (387 images)
  Total time: 4.2 minutes
  Transfer rate: 92.1 images/minute
```

## Security Notes

- The configuration file (`dicom_config.json`) contains sensitive server information and is excluded from version control
- Ensure proper network security and access controls on your DICOM servers
- Consider using VPN or secure network connections for remote PACS access

## License

MIT License

## Author

DICOM Expert

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.
