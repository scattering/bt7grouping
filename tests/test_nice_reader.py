"""Regression tests for the NICE-format reader.

The bug these cover shipped because nothing exercised the NICE path at all: a
current-format BT7 file mixes string columns in among the numeric ones, the
reader coerced each row with a single float() inside a bare except, and so
dropped every point while still reporting success.  A reader that returns no
data is not obviously broken to a caller -- it looks like an empty scan -- which
is why this is tested by asserting the values are present and correct, not
merely that read() did not raise.

Every fixture must begin with '# NICE', which is what read() dispatches on.  A
fixture that omits it is parsed by the legacy reader instead and tests nothing
about the code below; _read_nice() asserts the format actually taken so that
mistake fails loudly rather than passing for the wrong reason.
"""

import numpy as np
import pytest

from bt7grouping.reader import read_bt7_file

# Two numeric columns, one string column between them, two data rows.  The
# string columns are what used to poison the whole row: on a real file
# A5.hFocus reads FLAT and filterTrans reads OUT on every single point.
NICE_WITH_STRING_COLUMNS = """# NICE 0.2 : 4 header lines
# date 2026-09-11T11:23:24.128-04:00
# experiment.instrument BT7
# trajectoryData.description "align (100)"
## pt A3(deg) A5.hFocus A4(deg) filterTrans sampleUTilt(deg)
1 17.602 FLAT 35.194 OUT 4.4583
2 107.602 FLAT 35.194 OUT -4.0082
"""

NICE_ALL_NUMERIC = """# NICE 0.2 : 2 header lines
# experiment.instrument BT7
## pt A3(deg) A4(deg)
1 17.602 35.194
2 107.602 35.194
"""

NICE_LITERAL_NAN = """# NICE 0.2 : 2 header lines
# experiment.instrument BT7
## pt A3(deg) temp(K)
1 17.602 nan
2 107.602 300.0
"""

# A short final row: the header promises three columns and the last point
# supplies two.  This is what a file still being written looks like.
NICE_TRUNCATED_LAST_ROW = """# NICE 0.2 : 2 header lines
# experiment.instrument BT7
## pt A3(deg) A4(deg)
1 17.602 35.194
2 107.602 35.194
3 197.602
"""


def _read_nice(tmp_path, name, text):
    """Write a fixture, read it, and confirm the NICE parser is what ran."""
    path = tmp_path / name
    path.write_text(text)
    data = read_bt7_file(str(path))
    assert data.metadata.format_type == "nice", (
        f"fixture routed to the {data.metadata.format_type!r} parser, so this "
        f"test says nothing about the NICE path -- the first line must start "
        f"with '# NICE'"
    )
    return data


def test_string_columns_do_not_discard_the_row(tmp_path):
    """The actual regression: numeric data survives alongside string columns."""
    data = _read_nice(tmp_path, "nice_strings.dat.bt7", NICE_WITH_STRING_COLUMNS)

    assert data.data, "reader returned no columns at all -- every row was dropped"
    np.testing.assert_allclose(data.data["A3(deg)"], [17.602, 107.602])
    np.testing.assert_allclose(data.data["sampleUTilt(deg)"], [4.4583, -4.0082])
    np.testing.assert_allclose(data.data["A4(deg)"], [35.194, 35.194])


def test_string_cells_become_nan_not_dropped_points(tmp_path):
    """A non-numeric cell costs that cell, not the point it sits in."""
    data = _read_nice(tmp_path, "nice_strings2.dat.bt7", NICE_WITH_STRING_COLUMNS)

    assert len(data.data["A5.hFocus"]) == 2
    assert np.all(np.isnan(data.data["A5.hFocus"]))
    # ...and the numeric neighbours in the same rows are untouched.
    assert not np.any(np.isnan(data.data["A3(deg)"]))


def test_npoints_reflects_rows_actually_read(tmp_path):
    """npoints=0 alongside real data was the symptom that hid the bug."""
    data = _read_nice(tmp_path, "nice_numeric.dat.bt7", NICE_ALL_NUMERIC)

    assert data.metadata.npoints == 2
    assert len(data.data["A3(deg)"]) == 2


def test_literal_nan_still_parses(tmp_path):
    """float('nan') handles this natively; guard against a regression."""
    data = _read_nice(tmp_path, "nice_nan.dat.bt7", NICE_LITERAL_NAN)

    assert np.isnan(data.data["temp(K)"][0])
    assert data.data["temp(K)"][1] == pytest.approx(300.0)


def test_truncated_final_row_does_not_cost_the_whole_scan(tmp_path):
    """A short row cannot be assigned to columns, so it is dropped -- but the
    complete points before it are still returned, and np.array() never sees a
    ragged list (which raises ValueError on numpy >= 1.24)."""
    data = _read_nice(tmp_path, "nice_trunc.dat.bt7", NICE_TRUNCATED_LAST_ROW)

    np.testing.assert_allclose(data.data["A3(deg)"], [17.602, 107.602])
    assert data.metadata.npoints == 2
