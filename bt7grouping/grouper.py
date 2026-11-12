"""Scan grouping logic for BT-7 data files."""

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
import numpy as np

from .reader import BT7Reader, BT7Data, BT7Metadata


@dataclass
class GroupingConfig:
    """Configuration for scan grouping behavior."""
    # Q-space tolerance for grouping (in reciprocal lattice units)
    q_tolerance: float = 0.1

    # Energy tolerance (meV)
    e_tolerance: float = 0.5

    # Temperature tolerance (K) for grouping temperature-dependent scans
    temp_tolerance: float = 1.0

    # Time window for mesh scans (seconds)
    mesh_time_window: float = 4 * 3600  # 4 hours

    # Whether to group by experiment ID (for ICE format files)
    group_by_experiment: bool = True

    # Whether to separate alignment scans from measurements
    separate_alignment: bool = True

    # Scan types considered as alignment
    alignment_types: List[str] = field(default_factory=lambda: [
        'Find Peak Scan', 'Find Peak', 'Alignment', 'align', 'findpeak'
    ])


@dataclass
class ScanRecord:
    """Record for a single scan file."""
    path: str
    filename: str
    timestamp: float
    datetime: Optional[datetime] = None

    # Scan identification
    scan_type: str = ""
    scan_variable: str = ""
    scan_description: str = ""

    # Experiment info (ICE format)
    expt_id: str = ""
    expt_name: str = ""

    # Q-space center
    h: Optional[float] = None
    k: Optional[float] = None
    l: Optional[float] = None
    e: Optional[float] = None

    # Temperature
    temp: Optional[float] = None
    temp_setpoint: Optional[float] = None

    # Energy config
    fixed_e: str = ""

    # Detector mode
    detector_mode: str = ""

    # Format
    format_type: str = ""

    # Record type
    record_type: str = "data"  # "data" or "log"

    @classmethod
    def from_bt7_data(cls, data: BT7Data) -> 'ScanRecord':
        """Create a ScanRecord from BT7Data."""
        meta = data.metadata
        return cls(
            path=meta.filepath,
            filename=meta.filename,
            timestamp=meta.epoch,
            datetime=meta.datetime,
            scan_type=meta.scan_type,
            scan_variable=meta.scan_variable,
            scan_description=meta.scan_description,
            expt_id=meta.expt_id,
            expt_name=meta.expt_name,
            h=meta.h_center,
            k=meta.k_center,
            l=meta.l_center,
            e=meta.e_center,
            temp=meta.temp_start,
            temp_setpoint=meta.temp_setpoint,
            fixed_e=meta.fixed_e,
            detector_mode=meta.analyzer_detector_mode,
            format_type=meta.format_type,
        )


@dataclass
class ScanGroup:
    """A group of related scans."""
    records: List[ScanRecord] = field(default_factory=list)
    group_type: str = "measurement"  # "measurement", "alignment", "mesh", "temperature_scan"

    @property
    def expt_id(self) -> str:
        """Get experiment ID from first record."""
        if self.records:
            return self.records[0].expt_id
        return ""

    @property
    def expt_name(self) -> str:
        """Get experiment name from first record."""
        if self.records:
            return self.records[0].expt_name
        return ""

    @property
    def scan_type(self) -> str:
        """Get scan type from first record."""
        if self.records:
            return self.records[0].scan_type
        return ""

    @property
    def q_center(self) -> Dict[str, Optional[float]]:
        """Get Q center from first record."""
        if self.records:
            r = self.records[0]
            return {'h': r.h, 'k': r.k, 'l': r.l, 'e': r.e}
        return {'h': None, 'k': None, 'l': None, 'e': None}

    @property
    def temp_range(self) -> tuple:
        """Get temperature range across all scans in group."""
        temps = [r.temp for r in self.records if r.temp is not None]
        if temps:
            return (min(temps), max(temps))
        return (None, None)

    @property
    def time_range(self) -> tuple:
        """Get time range for the group."""
        if self.records:
            return (self.records[0].timestamp, self.records[-1].timestamp)
        return (0, 0)

    def __len__(self):
        return len(self.records)


def scan_files(root_dirs: List[str], recursive: bool = True,
               file_extensions: List[str] = None) -> List[ScanRecord]:
    """
    Scan directories for BT-7 data files and extract metadata.

    Parameters
    ----------
    root_dirs : list of str
        Directories to scan
    recursive : bool
        Whether to scan subdirectories
    file_extensions : list of str
        File extensions to include (default: ['.bt7'])

    Returns
    -------
    list of ScanRecord
        Records for all found data files
    """
    if file_extensions is None:
        file_extensions = ['.bt7']

    records = []
    reader = BT7Reader()

    for root_dir in root_dirs:
        if not os.path.isdir(root_dir):
            continue

        if recursive:
            for root, dirs, files in os.walk(root_dir):
                for filename in files:
                    if any(filename.endswith(ext) for ext in file_extensions):
                        # Skip NeXus files for now
                        if '.nxs' in filename:
                            continue
                        filepath = os.path.join(root, filename)
                        record = _read_file_to_record(reader, filepath)
                        if record:
                            records.append(record)
        else:
            for filename in os.listdir(root_dir):
                if any(filename.endswith(ext) for ext in file_extensions):
                    if '.nxs' in filename:
                        continue
                    filepath = os.path.join(root_dir, filename)
                    record = _read_file_to_record(reader, filepath)
                    if record:
                        records.append(record)

    return records


def _read_file_to_record(reader: BT7Reader, filepath: str) -> Optional[ScanRecord]:
    """Read a file and convert to ScanRecord."""
    try:
        data = reader.read(filepath)
        return ScanRecord.from_bt7_data(data)
    except Exception as e:
        # Silently skip unreadable files
        return None


def group_records(records: List[ScanRecord],
                  config: GroupingConfig = None) -> List[ScanGroup]:
    """
    Group scan records by similarity criteria.

    Grouping is based on:
    1. Experiment ID (for ICE format files)
    2. Q-space proximity
    3. Scan type/command similarity
    4. Temporal proximity for mesh scans

    Parameters
    ----------
    records : list of ScanRecord
        Records to group
    config : GroupingConfig
        Grouping configuration

    Returns
    -------
    list of ScanGroup
        Grouped scans
    """
    if config is None:
        config = GroupingConfig()

    # Sort by timestamp
    records = sorted(records, key=lambda r: r.timestamp)

    groups = []
    current_group = None

    for record in records:
        if current_group is None:
            current_group = ScanGroup(records=[record])
            current_group.group_type = _classify_scan_type(record, config)
            continue

        # Check if record belongs to current group
        if _should_group_together(current_group.records[-1], record, config):
            current_group.records.append(record)
        else:
            # Finalize current group and start new one
            groups.append(current_group)
            current_group = ScanGroup(records=[record])
            current_group.group_type = _classify_scan_type(record, config)

    # Don't forget the last group
    if current_group and current_group.records:
        groups.append(current_group)

    # Post-process: identify temperature scans
    for group in groups:
        if len(group.records) > 1:
            temp_range = group.temp_range
            if temp_range[0] is not None and temp_range[1] is not None:
                if temp_range[1] - temp_range[0] > config.temp_tolerance:
                    group.group_type = "temperature_scan"

    return groups


def _classify_scan_type(record: ScanRecord, config: GroupingConfig) -> str:
    """Classify scan type for grouping purposes."""
    scan_type_lower = record.scan_type.lower()
    scan_desc_lower = record.scan_description.lower()

    # Check for alignment
    if config.separate_alignment:
        for align_type in config.alignment_types:
            if align_type.lower() in scan_type_lower or align_type.lower() in scan_desc_lower:
                return "alignment"

    # Check for mesh
    if 'mesh' in record.filename.lower() or 'mesh' in scan_desc_lower:
        return "mesh"

    return "measurement"


def _should_group_together(last: ScanRecord, current: ScanRecord,
                           config: GroupingConfig) -> bool:
    """Determine if two records should be in the same group."""

    # If grouping by experiment, check experiment ID first
    if config.group_by_experiment and last.expt_id and current.expt_id:
        if last.expt_id != current.expt_id:
            return False

    # Check scan type classification
    last_type = _classify_scan_type(last, config)
    current_type = _classify_scan_type(current, config)

    if config.separate_alignment:
        if last_type != current_type:
            return False

    # Check scan command/description similarity
    if last.scan_description != current.scan_description:
        # Different commands - don't group unless it's a mesh
        if not (_is_mesh(last) and _is_mesh(current)):
            return False

    # Check Q-space proximity
    if not _q_match(last, current, config.q_tolerance, config.e_tolerance):
        return False

    # Special case: mesh scans within time window
    if _is_mesh(last) and _is_mesh(current):
        time_diff = abs(current.timestamp - last.timestamp)
        if time_diff < config.mesh_time_window:
            return True

    return True


def _is_mesh(record: ScanRecord) -> bool:
    """Check if record is a mesh scan."""
    return ('mesh' in record.filename.lower() or
            'mesh' in record.scan_description.lower())


def _q_match(r1: ScanRecord, r2: ScanRecord,
             q_tol: float, e_tol: float) -> bool:
    """Check if two records have similar Q positions."""
    # Build Q vectors
    q1 = np.array([
        r1.h if r1.h is not None else 0,
        r1.k if r1.k is not None else 0,
        r1.l if r1.l is not None else 0,
    ])
    q2 = np.array([
        r2.h if r2.h is not None else 0,
        r2.k if r2.k is not None else 0,
        r2.l if r2.l is not None else 0,
    ])

    # Check if we have valid Q values
    if (r1.h is None and r1.k is None and r1.l is None) or \
       (r2.h is None and r2.k is None and r2.l is None):
        # No Q info - rely on other criteria
        return True

    # Check Q distance
    q_dist = np.linalg.norm(q1 - q2)
    if q_dist > q_tol:
        return False

    # Check energy if both available
    if r1.e is not None and r2.e is not None:
        if abs(r1.e - r2.e) > e_tol:
            return False

    return True


def print_groups(groups: List[ScanGroup], verbose: bool = False):
    """Print summary of scan groups."""
    print(f"Found {len(groups)} groups")
    print("=" * 60)

    for i, group in enumerate(groups):
        if not group.records:
            continue

        first = group.records[0]
        last = group.records[-1]

        print(f"\nGroup {i+1}: {len(group)} files [{group.group_type}]")

        if first.expt_id:
            print(f"  Experiment: {first.expt_id} - {first.expt_name}")

        if first.datetime:
            print(f"  Start: {first.datetime}")
        if last.datetime and len(group) > 1:
            print(f"  End:   {last.datetime}")

        print(f"  Scan Type: {first.scan_type}")
        if first.scan_variable:
            print(f"  Variable: {first.scan_variable}")

        q = group.q_center
        if any(v is not None for v in q.values()):
            print(f"  Q Center: H={q['h']}, K={q['k']}, L={q['l']}, E={q['e']}")

        temp_range = group.temp_range
        if temp_range[0] is not None:
            if abs(temp_range[1] - temp_range[0]) > 1.0:
                print(f"  Temperature: {temp_range[0]:.1f} K -> {temp_range[1]:.1f} K")
            else:
                print(f"  Temperature: {temp_range[0]:.1f} K")

        if verbose:
            print("  Files:")
            for r in group.records:
                print(f"    - {r.filename}")
