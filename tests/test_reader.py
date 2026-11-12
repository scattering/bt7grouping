"""Tests for BT-7 file reader."""

import pytest
from bt7grouping.reader import BT7Reader, BT7Metadata


def test_metadata_defaults():
    """Test that metadata has sensible defaults."""
    meta = BT7Metadata()
    assert meta.instrument == "BT7"
    assert meta.format_type == "unknown"
    assert meta.epoch == 0.0


def test_reader_instantiation():
    """Test that reader can be instantiated."""
    reader = BT7Reader()
    assert reader is not None
