# DICOM Automatic Synchronization Tool

A Python tool that automatically synchronizes DICOM studies from a remote PACS server to a local PACS server. The tool continuously monitors for new studies and automatically transfers small series (≤10 images) using DICOM C-MOVE operations.

## Features

- **Automatic Monitoring**: Runs continuously, checking every 60 seconds for new studies
- **Smart Filtering**: Only transfers series with 10 or fewer images
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

Simply run the script:

```bash
python3 dicom_query_compare.py
```

The tool will:
1. Query both remote and local PACS for studies from yesterday and today
2. Identify studies present on remote but missing on local
3. Query series information for missing studies
4. Automatically transfer series with ≤10 images
5. Wait 60 seconds and repeat

Press `Ctrl+C` to stop the synchronization.

## How It Works

1. **Query Phase**:
   - Queries remote PACS for studies (yesterday + today)
   - Queries local PACS for studies (same date range)
   - Compares to find missing studies

2. **Analysis Phase**:
   - For each missing study, queries series information
   - Filters series with ≤10 images

3. **Transfer Phase**:
   - Uses DICOM C-MOVE to transfer filtered series
   - Transfers one series at a time
   - Displays progress and statistics

## Output Example

```
Starting sync cycle at 2025-10-04 14:30:00
========================================
Searching for studies from 20251003 to 20251004

Remote studies found: 15
Local studies found:  12
Missing on local:     3

Found 5 series with ≤10 images to transfer

Starting transfer: 5 series, 28 images

Transfer statistics:
  Successfully transferred: 5/5 series (28 images)
  Total time: 2.3 minutes
  Transfer rate: 12.2 images/minute
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
