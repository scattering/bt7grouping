"""BT-7 file reader supporting both legacy and modern ICE formats."""

import os
import re
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import numpy as np


@dataclass
class BT7Metadata:
    """Metadata extracted from BT-7 files."""
    # File info
    filename: str = ""
    filepath: str = ""
    instrument: str = "BT7"

    # Timestamp
    epoch: float = 0.0
    datetime: Optional[datetime] = None
    date_str: str = ""

    # Experiment info (ICE format)
    expt_id: str = ""
    expt_name: str = ""
    expt_participants: str = ""
    user: str = ""
    comment: str = ""

    # Scan info
    scan_type: str = ""
    scan_variable: str = ""
    scan_description: str = ""
    npoints: int = 0

    # Q-space
    h_center: Optional[float] = None
    k_center: Optional[float] = None
    l_center: Optional[float] = None
    e_center: Optional[float] = None

    # Crystal info
    lattice: str = ""
    orient: str = ""

    # Energy configuration
    fixed_e: str = ""
    fixed_e_value: Optional[float] = None

    # Detector mode
    analyzer_detector_mode: str = ""

    # Temperature
    temp_start: Optional[float] = None
    temp_mean: Optional[float] = None
    temp_setpoint: Optional[float] = None

    # Format type
    format_type: str = "unknown"  # "legacy", "ice", "nice"


@dataclass
class BT7Data:
    """Complete BT-7 scan data."""
    metadata: BT7Metadata = field(default_factory=BT7Metadata)
    columns: List[str] = field(default_factory=list)
    data: Dict[str, np.ndarray] = field(default_factory=dict)


def _rows_matching_header(data_rows, columns):
    """Keep the rows we can actually assign to columns, and drop the rest.

    A row whose width disagrees with the header cannot be mapped onto column
    names -- most often it is a final truncated line in a file that is still
    being written.  Dropping it keeps the other points, which beats losing the
    scan; and because a kept row matches the header exactly, no value is ever
    shifted into the wrong column.  Filtering first also keeps np.array() off
    a ragged list, which raises ValueError on numpy >= 1.24.
    """
    return [row for row in data_rows if len(row) == len(columns)]


class BT7Reader:
    """Reader for BT-7 data files supporting multiple formats."""

    def read(self, filepath: str) -> BT7Data:
        """Read a BT-7 file and return structured data."""
        with open(filepath, 'r', encoding='latin-1') as f:
            first_line = f.readline()
            f.seek(0)
            content = f.read()

        # Detect format
        if first_line.startswith('#ICE') or first_line.startswith('# ICE'):
            return self._read_ice_format(filepath, content)
        elif first_line.startswith('# NICE'):
            return self._read_nice_format(filepath, content)
        else:
            return self._read_legacy_format(filepath, content)

    def _read_ice_format(self, filepath: str, content: str) -> BT7Data:
        """Read modern ICE format BT-7 files (2009+)."""
        result = BT7Data()
        result.metadata.filepath = filepath
        result.metadata.filename = os.path.basename(filepath)
        result.metadata.format_type = "ice"

        lines = content.split('\n')
        header_done = False
        data_rows = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith('#'):
                if line.lower().startswith('#columns'):
                    # '#Columns  QX  QY  QZ  E ...' -- drop the key itself.
                    # This is the only place ICE names its columns, and
                    # without it result.columns stays empty and the data
                    # block below is skipped for every ICE file.
                    result.columns = line[1:].strip().split()[1:]
                self._parse_ice_header(line, result.metadata)
            else:
                if not header_done:
                    header_done = True
                # Data row
                try:
                    values = line.split()
                    # Handle N/A values
                    row = []
                    for v in values:
                        if v.upper() == 'N/A' or v.startswith('['):
                            row.append(np.nan)
                        else:
                            try:
                                row.append(float(v))
                            except ValueError:
                                row.append(np.nan)
                    data_rows.append(row)
                except Exception:
                    pass

        # Convert data to arrays
        if result.columns and data_rows:
            data_rows = _rows_matching_header(data_rows, result.columns)
            data_array = np.array(data_rows)
            if len(data_array.shape) == 2 and data_array.shape[1] == len(result.columns):
                for i, col in enumerate(result.columns):
                    result.data[col] = data_array[:, i]

                # Extract Q center from first point
                self._extract_q_center_from_data(result)
                self._extract_temperature_from_data(result)

        return result

    def _parse_ice_header(self, line: str, meta: BT7Metadata):
        """Parse ICE format header line."""
        # Remove leading #
        line = line[1:].strip()

        # Split on first whitespace
        parts = line.split(None, 1)
        if len(parts) < 1:
            return

        key = parts[0]
        value = parts[1].strip() if len(parts) > 1 else ""

        # Map keys to metadata fields
        key_lower = key.lower()

        if key_lower == 'filename':
            meta.filename = value
        elif key_lower == 'date':
            meta.date_str = value
            try:
                # Parse date like "2010-01-15 15:22:13 EST"
                dt = datetime.strptime(value.split()[0] + ' ' + value.split()[1],
                                       "%Y-%m-%d %H:%M:%S")
                meta.datetime = dt
            except Exception:
                pass
        elif key_lower == 'epoch':
            try:
                meta.epoch = float(value)
                if meta.datetime is None:
                    meta.datetime = datetime.fromtimestamp(meta.epoch)
            except Exception:
                pass
        elif key_lower == 'instrname':
            meta.instrument = value
        elif key_lower == 'exptid':
            meta.expt_id = value
        elif key_lower == 'exptname':
            meta.expt_name = value
        elif key_lower == 'exptparticipants':
            meta.expt_participants = value
        elif key_lower == 'user':
            meta.user = value
        elif key_lower == 'comment':
            meta.comment = value
        elif key_lower == 'scantype':
            meta.scan_type = value
        elif key_lower == 'scan':
            # Format: "12 A3" - extract the scanned variable
            scan_parts = value.split()
            if len(scan_parts) >= 2:
                meta.scan_variable = scan_parts[1]
        elif key_lower == 'scandescr':
            meta.scan_description = value
        elif key_lower == 'npoints':
            try:
                meta.npoints = int(value)
            except Exception:
                pass
        elif key_lower == 'lattice':
            meta.lattice = value
        elif key_lower == 'orient':
            meta.orient = value
        elif key_lower == 'fixede':
            meta.fixed_e = value
            # Parse "Ef 14.7" or "Ei 1"
            fe_parts = value.split()
            if len(fe_parts) >= 2:
                try:
                    meta.fixed_e_value = float(fe_parts[1])
                except Exception:
                    pass
        elif key_lower == 'analyzerdetectormode':
            meta.analyzer_detector_mode = value
        elif key_lower == 'columns':
            # Handled by _read_ice_format, which has the BT7Data to write to.
            pass

    def _read_nice_format(self, filepath: str, content: str) -> BT7Data:
        """Read NICE format files."""
        result = BT7Data()
        result.metadata.filepath = filepath
        result.metadata.filename = os.path.basename(filepath)
        result.metadata.format_type = "nice"

        lines = content.split('\n')
        data_rows = []
        in_data = False

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith('##'):
                # Column header
                result.columns = line[2:].strip().split()
                in_data = True
            elif line.startswith('#'):
                self._parse_nice_header(line, result.metadata)
            elif in_data:
                # Modern NICE files interleave string-valued columns with the
                # numeric ones -- A5.hFocus is FLAT, filterTrans is OUT,
                # sampleState.definition and the sample UUID are free text --
                # so the row has to be coerced one cell at a time.  A single
                # float() over the whole row throws on the first string, and
                # under the bare except that used to sit here the point was
                # discarded without a word.  On a current-format file that is
                # every point, so the reader returned a confident success with
                # no data at all.
                row = []
                for v in line.split():
                    try:
                        row.append(float(v))
                    except ValueError:
                        row.append(np.nan)
                data_rows.append(row)

        if result.columns and data_rows:
            data_rows = _rows_matching_header(data_rows, result.columns)
            data_array = np.array(data_rows, dtype=float)
            if data_array.ndim == 2 and data_array.shape[1] == len(result.columns):
                for i, col in enumerate(result.columns):
                    result.data[col] = data_array[:, i]
                self._extract_q_center_from_data(result)
                self._extract_temperature_from_data(result)
                # The NICE header does not carry npoints, so it sat at 0 next
                # to real data -- which is the symptom that hid the dropped
                # rows.  The rows we actually read are the honest answer.
                if not result.metadata.npoints:
                    result.metadata.npoints = len(data_rows)

        return result

    def _parse_nice_header(self, line: str, meta: BT7Metadata):
        """Parse NICE format header."""
        parts = line[1:].strip().split(None, 1)
        if len(parts) < 2:
            return

        key, value = parts[0], parts[1]

        if key == 'epoch':
            try:
                meta.epoch = float(value)
                meta.datetime = datetime.fromtimestamp(meta.epoch)
            except Exception:
                pass
        elif key == 'date':
            meta.date_str = value
        elif key in ('trajectoryData.description', 'trajectory.description'):
            meta.scan_description = value.strip('"')
        elif key == 'experiment.instrument':
            meta.instrument = value

    def _read_legacy_format(self, filepath: str, content: str) -> BT7Data:
        """Read legacy BT-7 format (pre-2009)."""
        result = BT7Data()
        result.metadata.filepath = filepath
        result.metadata.filename = os.path.basename(filepath)
        result.metadata.format_type = "legacy"

        lines = content.split('\n')

        # First line contains: 'filename' 'date time' 'scantype' ...
        if lines:
            first_line = lines[0]
            # Parse quoted strings
            quoted = re.findall(r"'([^']*)'", first_line)
            if len(quoted) >= 3:
                result.metadata.filename = quoted[0]
                result.metadata.date_str = quoted[1]
                scan_type_char = quoted[2]
                # Map I->Inelastic, B->Bragg, Q->Q-space
                type_map = {'I': 'Inelastic', 'B': 'Bragg', 'Q': 'Q-space', 'T': 'Time'}
                result.metadata.scan_type = type_map.get(scan_type_char, scan_type_char)

                # Try to parse date
                try:
                    dt = datetime.strptime(result.metadata.date_str, "%d-%b-%Y %H:%M")
                    result.metadata.datetime = dt
                    result.metadata.epoch = dt.timestamp()
                except Exception:
                    try:
                        dt = datetime.strptime(result.metadata.date_str, "%b %d %Y %H:%M")
                        result.metadata.datetime = dt
                        result.metadata.epoch = dt.timestamp()
                    except Exception:
                        pass

        return result

    def _extract_q_center_from_data(self, result: BT7Data):
        """Extract Q center from first data point."""
        col_map = {
            'h': ['QX', 'H', 'Qx', 'qx'],
            'k': ['QY', 'K', 'Qy', 'qy'],
            'l': ['QZ', 'L', 'Qz', 'qz'],
            'e': ['E', 'ET', 'Energy', 'e'],
        }

        for target, candidates in col_map.items():
            for col in candidates:
                if col in result.data and len(result.data[col]) > 0:
                    val = result.data[col][0]
                    if not np.isnan(val):
                        setattr(result.metadata, f'{target}_center', val)
                        break

    def _extract_temperature_from_data(self, result: BT7Data):
        """Extract temperature info from data."""
        temp_cols = ['Temp', 'temp', 'Temperature', 'TemperatureControlReading']

        for col in temp_cols:
            if col in result.data and len(result.data[col]) > 0:
                temps = result.data[col]
                valid = temps[~np.isnan(temps)]
                if len(valid) > 0:
                    result.metadata.temp_start = valid[0]
                    result.metadata.temp_mean = np.mean(valid)
                    break

        # Check for setpoint
        if 'TemperatureSetpoint' in result.data:
            setpoints = result.data['TemperatureSetpoint']
            valid = setpoints[~np.isnan(setpoints)]
            if len(valid) > 0:
                result.metadata.temp_setpoint = valid[0]


def read_bt7_file(filepath: str) -> BT7Data:
    """Convenience function to read a BT-7 file."""
    reader = BT7Reader()
    return reader.read(filepath)
