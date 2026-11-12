# bt7grouping

Scan grouping and classification toolkit for BT-7 triple-axis spectrometer data.

## Overview

This package provides tools to automatically group related BT-7 neutron scattering data files based on:

- **Experiment ID** (for modern ICE format files, 2009+)
- **Q-space proximity** (H, K, L, E coordinates)
- **Scan type** (VECTOR, ANGLE, Find Peak, ENV, etc.)
- **Temporal proximity** (for mesh scans)
- **Temperature setpoint** (for temperature-dependent studies)

## Installation

```bash
pip install bt7grouping
```

Or install from source:

```bash
git clone https://github.com/scattering/bt7grouping.git
cd bt7grouping
pip install -e .
```

## Usage

### Basic Usage

```python
from bt7grouping import scan_files, group_records, print_groups

# Scan a directory for BT-7 files
records = scan_files(["/path/to/bt7/data"])

# Group the records
groups = group_records(records)

# Print summary
print_groups(groups)
```

### Custom Grouping Configuration

```python
from bt7grouping import scan_files, group_records, GroupingConfig

# Configure grouping behavior
config = GroupingConfig(
    q_tolerance=0.1,           # Q-space tolerance (rlu)
    e_tolerance=0.5,           # Energy tolerance (meV)
    temp_tolerance=1.0,        # Temperature tolerance (K)
    group_by_experiment=True,  # Use experiment IDs
    separate_alignment=True,   # Separate alignment scans
)

records = scan_files(["/path/to/data"])
groups = group_records(records, config=config)
```

### Reading Individual Files

```python
from bt7grouping import read_bt7_file

# Read a single BT-7 file
data = read_bt7_file("/path/to/file.bt7")

# Access metadata
print(f"Experiment: {data.metadata.expt_name}")
print(f"Scan Type: {data.metadata.scan_type}")
print(f"Q Center: ({data.metadata.h_center}, {data.metadata.k_center}, {data.metadata.l_center})")

# Access data columns
if 'Temp' in data.data:
    print(f"Temperature: {data.data['Temp']}")
```

## Supported File Formats

- **Legacy format** (1994-2008): Simple ASCII with quoted header fields
- **ICE format** (2009+): Enhanced ASCII with `#Key Value` headers and 143+ columns
- **NICE format**: Modern NICE instrument control format

## Grouping Logic

Scans are grouped together when they share:

1. **Same experiment ID** (for ICE format files)
2. **Same scan command/description**
3. **Similar Q position** (within configurable tolerance)
4. **Similar energy transfer** (within configurable tolerance)

Special handling for:

- **Alignment scans** (`Find Peak`, `align`, etc.) - separated by default
- **Mesh scans** - grouped by filename pattern and time window
- **Temperature scans** - identified when temperature varies significantly within a group

## Integration with tasreduction

This package is designed to work with the [tasreduction](https://github.com/scattering/tasreduction) toolkit:

```python
from bt7grouping import scan_files, group_records
from tasreduction import translate_ice_file, ReducePipeline

# Find and group related scans
records = scan_files(["/path/to/data"])
groups = group_records(records)

# Process a group through the reduction pipeline
for group in groups:
    if group.group_type == "measurement":
        pipeline = ReducePipeline()
        for record in group.records:
            scan = translate_ice_file(record.path)
            scan.normalize_to_monitor()
            pipeline.add_signal(scan)
        combined = pipeline.sum_signals()
```

## License

BSD 3-Clause License. See [LICENSE](LICENSE) for details.

## Reproducibility Tests

Install the shared contracts from the
[TASCopilot paper repository](https://github.com/scattering/tascopilot-paper)
and this package into a Python 3.11 or newer environment:

```sh
TASCOPILOT_PAPER=/absolute/path/to/tascopilot-paper
python -m pip install -e "$TASCOPILOT_PAPER/packages/tas_copilot_contracts"
python -m pip install -e . pytest
python -m pytest -q -rs
```

Tests use local fixtures. Optional upstream runtimes or explicitly supplied
archive fixtures are reported as skipped when unavailable. No instrument
connection is required. No full papers, private corpus, or development
handoff documents are included.
