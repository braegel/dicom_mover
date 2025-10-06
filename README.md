# DICOM Automatic Synchronization Tool

A Python tool that automatically synchronizes DICOM studies from a remote PACS server to a local PACS server. The tool continuously monitors for new studies and automatically transfers series based on configurable image count criteria using DICOM C-MOVE operations.

## Features

- **Automatic Monitoring**: Runs continuously, checking every 60 seconds for new studies
- **Flexible Series Selection**:
  - Transfer only the smallest series per study (default)
  - Transfer all series with fewer than N images (configurable)
  - Transfer all series (no limit)
- **Time-based Filtering**: Only processes studies from the last 12 hours
- **Date Range Query**: Searches for studies from yesterday and today
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

Run the script with different transfer modes:

**Default Mode** - Transfer only the smallest series per study:
```bash
python3 dicom_query_compare.py
```

**Custom Image Limit** - Transfer all series with fewer than N images:
```bash
python3 dicom_query_compare.py --min-images 300
```

**Transfer All Series** - Transfer all series without any limit:
```bash
python3 dicom_query_compare.py --all-series
```

**Help** - Display all available options:
```bash
python3 dicom_query_compare.py --help
```

### How It Works

The tool will:
1. Query both remote and local PACS for studies from yesterday and today
2. Filter studies to only those within the last 12 hours
3. Identify studies present on remote but missing on local
4. Query series information for missing studies
5. Automatically transfer series based on selected mode
6. Wait 60 seconds and repeat

Press `Ctrl+C` to stop the synchronization.

## Transfer Modes Explained

### Default Mode (Smallest Series Only)
```bash
python3 dicom_query_compare.py
```
For each missing study, only the series with the smallest number of images is transferred. This is useful for transferring scout/localizer images or small preview series.

### Custom Image Limit
```bash
python3 dicom_query_compare.py --min-images 300
```
Transfers all series that have fewer than the specified number of images. For example, `--min-images 300` will transfer all series with 1-299 images. This is useful when you want to transfer multiple small series per study.

### All Series
```bash
python3 dicom_query_compare.py --all-series
```
Transfers all series from missing studies without any image count restriction. Use this when you want complete studies transferred.

## How It Works

1. **Query Phase**:
   - Queries remote PACS for studies (yesterday + today)
   - Filters to only studies within the last 12 hours
   - Queries local PACS for studies (same date range)
   - Compares to find missing studies

2. **Analysis Phase**:
   - For each missing study, queries series information
   - Applies the selected filter mode (smallest/min-images/all)

3. **Transfer Phase**:
   - Uses DICOM C-MOVE to transfer filtered series
   - Transfers one series at a time
   - Displays progress and statistics

## Output Example

```
================================================================================
DICOM Automatic Synchronization Tool
================================================================================

Transfer mode: Series with < 300 images

Configuration loaded:
  Local:  DicomNode(Local PACS, LOCAL@192.168.1.100:11112)
  Remote: DicomNode(Remote PACS, REMOTE@192.168.1.200:11112)

====================================================================================================
Starting sync cycle at 2025-10-06 14:30:00
====================================================================================================
Searching for studies from 20251005 to 20251006
Filtering studies within last 12 hours

Querying Remote Server
Filtered to 8 studies within last 12 hours (from 15 total)

Querying Local Server
Filtered to 5 studies within last 12 hours (from 12 total)

RESULTS SUMMARY
Remote studies found: 8
Local studies found:  5
Missing on local:     3

Analyzing series in 3 studies...

Found 7 series to transfer (with < 300 images)

Starting transfer: 7 series, 156 images

Transfer statistics:
  Successfully transferred: 7/7 series (156 images)
  Total time: 3.2 minutes
  Transfer rate: 48.8 images/minute
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
