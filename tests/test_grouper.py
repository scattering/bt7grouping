"""Tests for scan grouping logic."""

import pytest
from bt7grouping.grouper import (
    ScanRecord,
    ScanGroup,
    GroupingConfig,
    group_records,
    _q_match,
)


def test_scan_record_creation():
    """Test ScanRecord creation."""
    record = ScanRecord(
        path="/path/to/file.bt7",
        filename="file.bt7",
        timestamp=1234567890.0,
    )
    assert record.filename == "file.bt7"
    assert record.record_type == "data"


def test_scan_group_properties():
    """Test ScanGroup property accessors."""
    records = [
        ScanRecord(path="a.bt7", filename="a.bt7", timestamp=100, temp=10.0),
        ScanRecord(path="b.bt7", filename="b.bt7", timestamp=200, temp=20.0),
    ]
    group = ScanGroup(records=records)

    assert len(group) == 2
    assert group.temp_range == (10.0, 20.0)
    assert group.time_range == (100, 200)


def test_grouping_config_defaults():
    """Test GroupingConfig has sensible defaults."""
    config = GroupingConfig()
    assert config.q_tolerance == 0.1
    assert config.group_by_experiment is True
    assert config.separate_alignment is True


def test_q_match_same_position():
    """Test Q matching for identical positions."""
    r1 = ScanRecord(path="a.bt7", filename="a.bt7", timestamp=0,
                    h=1.0, k=0.0, l=0.0, e=0.0)
    r2 = ScanRecord(path="b.bt7", filename="b.bt7", timestamp=0,
                    h=1.0, k=0.0, l=0.0, e=0.0)
    assert _q_match(r1, r2, q_tol=0.1, e_tol=0.5) is True


def test_q_match_different_position():
    """Test Q matching for different positions."""
    r1 = ScanRecord(path="a.bt7", filename="a.bt7", timestamp=0,
                    h=1.0, k=0.0, l=0.0, e=0.0)
    r2 = ScanRecord(path="b.bt7", filename="b.bt7", timestamp=0,
                    h=2.0, k=0.0, l=0.0, e=0.0)
    assert _q_match(r1, r2, q_tol=0.1, e_tol=0.5) is False


def test_q_match_missing_q():
    """Test Q matching when Q values are missing."""
    r1 = ScanRecord(path="a.bt7", filename="a.bt7", timestamp=0)
    r2 = ScanRecord(path="b.bt7", filename="b.bt7", timestamp=0)
    # Should return True when Q is missing (rely on other criteria)
    assert _q_match(r1, r2, q_tol=0.1, e_tol=0.5) is True


def test_group_records_empty():
    """Test grouping empty list."""
    groups = group_records([])
    assert groups == []


def test_group_records_single():
    """Test grouping single record."""
    records = [ScanRecord(path="a.bt7", filename="a.bt7", timestamp=100)]
    groups = group_records(records)
    assert len(groups) == 1
    assert len(groups[0]) == 1
