"""bt7grouping - Scan grouping and classification for BT-7 triple-axis spectrometer data."""

from .grouper import (
    scan_files,
    group_records,
    ScanRecord,
    ScanGroup,
    GroupingConfig,
)
from .reader import BT7Reader, read_bt7_file

__version__ = "0.1.0"

__all__ = [
    "scan_files",
    "group_records",
    "ScanRecord",
    "ScanGroup",
    "GroupingConfig",
    "BT7Reader",
    "read_bt7_file",
]
