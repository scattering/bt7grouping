"""Regression tests for the ICE-format reader.

ICE is the 2009-2020 BT7 format, so this covers most of the public archive.
_read_ice_format never assigned result.columns -- the only assignment in the
module was in the NICE parser -- so the `if result.columns and data_rows:`
guard was always False and every ICE file came back with a fully populated
metadata block, the right npoints from the header, and no data whatsoever.

Fixtures are trimmed from a real file,
  pub/ncnrdata/bt7/201509/21058/data/testsweep_a4__step_0p25_818584.bt7
(441 points, 139 columns), including its N/A cells and its column-header
spacing.  Each test asserts format_type == "ice" first: a fixture whose first
line does not start with '#ICE' is quietly handled by the legacy parser and
proves nothing about the code here.
"""

import numpy as np
import pytest

from bt7grouping.reader import read_bt7_file

# Leading whitespace on the data rows and the 'N/A' cells are both verbatim
# from the real file: the first point of an a4 sweep has no Q assigned yet.
ICE_BASIC = """#ICE           0.4.0
#ICERepositoryInfo /ice/server/releases/ALL_2014_05_22
#Filename testsweep_a4__step_0p25_818584
#Date 2015-09-14 09:12:03 EDT
#InstrName BT7
#Npoints 3
#FixedE Ef 14.7
#Columns             QX            QY            QZ             E            A4          Time       Monitor      Detector
                    N/A           N/A           N/A           N/A            -0             5             0             0
                    1.0           0.0           0.0           0.0         35.25             5          1000           250
                    1.1           0.0           0.0           0.0          35.50             5          1000           310
"""

# The last row is truncated, which is what a file still being written looks
# like.  The two complete points must survive it.
ICE_TRUNCATED_LAST_ROW = """#ICE           0.4.0
#InstrName BT7
#Npoints 3
#Columns             QX            QY            QZ             E            A4          Time       Monitor      Detector
                    1.0           0.0           0.0           0.0         35.25             5          1000           250
                    1.1           0.0           0.0           0.0          35.50             5          1000           310
                    1.2           0.0           0.0
"""


def _read_ice(tmp_path, name, text):
    """Write a fixture, read it, and confirm the ICE parser is what ran."""
    path = tmp_path / name
    path.write_text(text)
    data = read_bt7_file(str(path))
    assert data.metadata.format_type == "ice", (
        f"fixture routed to the {data.metadata.format_type!r} parser, so this "
        f"test says nothing about the ICE path -- the first line must start "
        f"with '#ICE'"
    )
    return data


def test_columns_header_is_read(tmp_path):
    """The regression: without this, result.columns is empty and no data is
    published no matter how many points the file holds."""
    data = _read_ice(tmp_path, "ice_basic.bt7", ICE_BASIC)

    assert data.columns == ["QX", "QY", "QZ", "E", "A4", "Time", "Monitor", "Detector"]
    assert data.data, "reader returned no data -- the #Columns line was ignored"


def test_data_survives_and_lands_in_the_right_column(tmp_path):
    data = _read_ice(tmp_path, "ice_basic2.bt7", ICE_BASIC)

    np.testing.assert_allclose(data.data["A4"], [-0.0, 35.25, 35.50])
    np.testing.assert_allclose(data.data["Detector"], [0.0, 250.0, 310.0])
    np.testing.assert_allclose(data.data["Monitor"], [0.0, 1000.0, 1000.0])


def test_na_cells_become_nan_without_costing_the_point(tmp_path):
    """'N/A' is how ICE writes an unassigned value; the rest of the row is
    still good data."""
    data = _read_ice(tmp_path, "ice_na.bt7", ICE_BASIC)

    assert np.isnan(data.data["QX"][0])
    assert data.data["QX"][1] == pytest.approx(1.0)
    # The A4 value recorded on the same point as the N/A cells is intact.
    assert data.data["A4"][0] == pytest.approx(-0.0)


def test_header_metadata_is_kept(tmp_path):
    data = _read_ice(tmp_path, "ice_meta.bt7", ICE_BASIC)

    assert data.metadata.instrument == "BT7"
    assert data.metadata.npoints == 3
    assert data.metadata.fixed_e_value == pytest.approx(14.7)


def test_truncated_final_row_does_not_cost_the_whole_scan(tmp_path):
    """A short row cannot be assigned to columns, so it is dropped -- but the
    complete points before it are still returned."""
    data = _read_ice(tmp_path, "ice_trunc.bt7", ICE_TRUNCATED_LAST_ROW)

    np.testing.assert_allclose(data.data["QX"], [1.0, 1.1])
    np.testing.assert_allclose(data.data["Detector"], [250.0, 310.0])
