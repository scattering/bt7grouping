from bt7grouping.copilot_plugin import get_tool_specs, run_tool
from tas_copilot_contracts import ToolCall, ToolResultStatus


def test_copilot_plugin_specs():
    specs = get_tool_specs()
    names = {(spec.namespace, spec.name) for spec in specs}
    assert ("tas.data_reader", "read_bt7_file") in names
    assert ("tas.scan_grouping", "group_bt7_scans") in names
    assert all(spec.enabled_by_default for spec in specs)


def test_copilot_read_bt7_file(tmp_path):
    data_file = tmp_path / "legacy.bt7"
    data_file.write_text("'legacy.bt7' '01-Jan-2020 12:00' 'I'\n", encoding="latin-1")

    result = run_tool(
        ToolCall(
            tool_namespace="tas.data_reader",
            tool_name="read_bt7_file",
            arguments={"path": str(data_file)},
        )
    )

    assert result.status == ToolResultStatus.success
    assert result.output["metadata"]["filename"] == "legacy.bt7"
    assert result.output["metadata"]["format_type"] == "legacy"


def test_copilot_read_bt7_file_exposes_partial_psd_map(tmp_path):
    data_file = tmp_path / "psd.bt7"
    data_file.write_text(
        "\n".join(
            [
                "#ICE",
                "#Filename    psd",
                "#AnalyzerDetectorMode 4 PSDDiff",
                "#Columns QX A4 Temp PSDC00 PSDC01 TemperatureControlReading timestamp",
                "N/A 29.5 10.0 1 2 10.1 1",
                "N/A 29.5 20.0 3 4 20.2 2",
            ]
        ),
        encoding="latin-1",
    )

    result = run_tool(
        ToolCall(
            tool_namespace="tas.data_reader",
            tool_name="read_bt7_file",
            arguments={"path": str(data_file)},
        )
    )

    assert result.status == ToolResultStatus.success
    assert result.output["row_count"] == 2
    assert result.output["psd_map"]["status"] == "partial"
    assert result.output["psd_map"]["psd_channel_axis"] == [0, 1]
    assert result.output["psd_map"]["two_theta_axis"] == {"type": "constant", "value": 29.5}
    assert result.output["psd_map"]["two_theta_axis_source"] == "A4"
    assert result.output["psd_map"]["temperature_axis"] == [10.1, 20.2]
    assert result.output["psd_map"]["intensity"] == [[1.0, 2.0], [3.0, 4.0]]
    assert result.output["psd_map"]["q_axis"] is None


def test_copilot_read_bt7_file_exposes_single_detector_line_scan(tmp_path):
    data_file = tmp_path / "line.bt7"
    data_file.write_text(
        "\n".join(
            [
                "#ICE",
                "#Filename    line",
                "#AnalyzerDetectorMode 3 SingDetHFoc",
                "#Columns QX E Temp Monitor Detector timestamp",
                "1.20 3.0 50.0 100 10 1",
                "1.25 3.0 50.0 100 20 2",
                "1.30 3.0 50.0 100 15 3",
            ]
        ),
        encoding="latin-1",
    )

    result = run_tool(
        ToolCall(
            tool_namespace="tas.data_reader",
            tool_name="read_bt7_file",
            arguments={"path": str(data_file)},
        )
    )

    assert result.status == ToolResultStatus.success
    assert result.output["line_scan"]["q_axis"] == [1.2, 1.25, 1.3]
    assert result.output["line_scan"]["energy_transfer_meV"] == 3.0
    assert result.output["line_scan"]["temperature_K"] == 50.0
    assert result.output["line_scan"]["intensity"] == [0.1, 0.2, 0.15]
    assert result.output["line_scan"]["intensity_source"] == "Detector/Monitor"


def test_copilot_group_bt7_scans(tmp_path):
    for index in range(2):
        (tmp_path / f"scan{index}.bt7").write_text(
            f"'scan{index}.bt7' '01-Jan-2020 12:0{index}' 'I'\n",
            encoding="latin-1",
        )

    result = run_tool(
        ToolCall(
            tool_namespace="tas.scan_grouping",
            tool_name="group_bt7_scans",
            arguments={"root_dirs": [str(tmp_path)], "recursive": False},
        )
    )

    assert result.status == ToolResultStatus.success
    assert result.output["record_count"] == 2
    assert result.output["group_count"] >= 1
