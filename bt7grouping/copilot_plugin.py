"""TAS co-pilot plugin entry points for bt7grouping."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from .grouper import GroupingConfig, group_records, scan_files
from .reader import read_bt7_file


def get_tool_specs():
    from tas_copilot_contracts import (
        Availability,
        ImplementationType,
        PermissionLevel,
        SideEffectLevel,
        ToolSpec,
    )

    common = {
        "version": "0.1.0",
        "availability": Availability.available,
        "implementation_type": ImplementationType.python_entrypoint,
        "side_effect_level": SideEffectLevel.none,
        "required_dependencies": ["bt7grouping"],
        "provenance_policy": "Record file paths, directory roots, adapter version, and extracted metadata.",
        "permissions_required": [PermissionLevel.read_only],
        "enabled_by_default": True,
        "owner_repo": "git@github.com:scattering/bt7grouping.git",
        "documentation_url": "https://github.com/scattering/bt7grouping",
        "maintainer": "William Ratcliff",
    }
    return [
        ToolSpec(
            name="read_bt7_file",
            namespace="tas.data_reader",
            description="Read one BT-7 data file and return extracted metadata plus column names.",
            input_schema={
                "type": "object",
                "required": ["path"],
                "properties": {"path": {"type": "string"}},
            },
            output_schema={"type": "object"},
            preconditions=["Path points to a readable BT-7/NICE/ICE data file."],
            postconditions=["No file contents are modified."],
            **common,
        ),
        ToolSpec(
            name="group_bt7_scans",
            namespace="tas.scan_grouping",
            description="Scan one or more directories for BT-7 files and group related scan records.",
            input_schema={
                "type": "object",
                "required": ["root_dirs"],
                "properties": {
                    "root_dirs": {"type": "array", "items": {"type": "string"}},
                    "recursive": {"type": "boolean"},
                    "file_extensions": {"type": "array", "items": {"type": "string"}},
                    "q_tolerance": {"type": "number"},
                    "e_tolerance": {"type": "number"},
                    "temp_tolerance": {"type": "number"},
                    "group_by_experiment": {"type": "boolean"},
                    "separate_alignment": {"type": "boolean"},
                },
            },
            output_schema={"type": "object"},
            preconditions=["Root directories are readable local paths."],
            postconditions=["No file contents are modified."],
            **common,
        ),
    ]


def run_tool(call):
    from tas_copilot_contracts import ProvenanceRecord, ToolError, ToolResult, ToolResultStatus

    if call.tool_namespace == "tas.data_reader" and call.tool_name == "read_bt7_file":
        return _read_file(call, ToolResult, ToolResultStatus, ToolError, ProvenanceRecord)
    if call.tool_namespace == "tas.scan_grouping" and call.tool_name == "group_bt7_scans":
        return _group_scans(call, ToolResult, ToolResultStatus, ToolError, ProvenanceRecord)
    return ToolResult(
        status=ToolResultStatus.validation_failed,
        output=None,
        errors=[ToolError(code="unknown_tool", message=f"Unknown bt7grouping tool {call.tool_namespace}.{call.tool_name}")],
        tool_name=call.tool_name,
        tool_namespace=call.tool_namespace,
        tool_version="0.1.0",
    )


def _read_file(call, ToolResult, ToolResultStatus, ToolError, ProvenanceRecord):
    path = call.arguments.get("path")
    if not path:
        return ToolResult(
            status=ToolResultStatus.validation_failed,
            output=None,
            errors=[ToolError(code="missing_path", message="path is required")],
            tool_name=call.tool_name,
            tool_namespace=call.tool_namespace,
            tool_version="0.1.0",
        )
    try:
        data = read_bt7_file(path)
    except Exception as exc:
        return ToolResult(
            status=ToolResultStatus.error,
            output=None,
            errors=[ToolError(code=exc.__class__.__name__, message=str(exc))],
            tool_name=call.tool_name,
            tool_namespace=call.tool_namespace,
            tool_version="0.1.0",
        )
    return ToolResult(
        status=ToolResultStatus.success,
        output={
            "metadata": _json_ready(asdict(data.metadata)),
            "columns": list(data.columns),
            "data_column_count": len(data.data),
            "row_count": _row_count(data.data),
            "psd_map": _psd_map_payload(data),
            "line_scan": _line_scan_payload(data),
        },
        tool_name=call.tool_name,
        tool_namespace=call.tool_namespace,
        tool_version="0.1.0",
        provenance=[ProvenanceRecord(source_type="data_file", source_id=path, method="bt7grouping.read_bt7_file")],
    )


def _group_scans(call, ToolResult, ToolResultStatus, ToolError, ProvenanceRecord):
    root_dirs = call.arguments.get("root_dirs")
    if not root_dirs:
        return ToolResult(
            status=ToolResultStatus.validation_failed,
            output=None,
            errors=[ToolError(code="missing_root_dirs", message="root_dirs is required")],
            tool_name=call.tool_name,
            tool_namespace=call.tool_namespace,
            tool_version="0.1.0",
        )
    config = GroupingConfig(
        q_tolerance=float(call.arguments.get("q_tolerance", 0.1)),
        e_tolerance=float(call.arguments.get("e_tolerance", 0.5)),
        temp_tolerance=float(call.arguments.get("temp_tolerance", 1.0)),
        group_by_experiment=bool(call.arguments.get("group_by_experiment", True)),
        separate_alignment=bool(call.arguments.get("separate_alignment", True)),
    )
    records = scan_files(
        root_dirs,
        recursive=bool(call.arguments.get("recursive", True)),
        file_extensions=call.arguments.get("file_extensions"),
    )
    groups = group_records(records, config=config)
    return ToolResult(
        status=ToolResultStatus.success,
        output={
            "record_count": len(records),
            "group_count": len(groups),
            "records": [_json_ready(asdict(record)) for record in records],
            "groups": [_group_payload(group) for group in groups],
        },
        tool_name=call.tool_name,
        tool_namespace=call.tool_namespace,
        tool_version="0.1.0",
        provenance=[ProvenanceRecord(source_type="data_directory", source_id=";".join(root_dirs), method="bt7grouping.group_records")],
    )


def _row_count(data: dict) -> int:
    for values in data.values():
        return len(values)
    return 0


def _psd_map_payload(data) -> dict | None:
    psd_columns = sorted(
        [column for column in data.columns if column.startswith("PSDC")],
        key=lambda name: int(name[4:]) if name[4:].isdigit() else 999,
    )
    if not psd_columns:
        return None
    row_count = _row_count(data.data)
    if row_count == 0:
        return None

    temperature_axis = _first_numeric_column(
        data.data,
        ["TemperatureControlReading", "TemperatureSetpoint", "Temp", "Temperature"],
    )
    intensity = []
    for row_index in range(row_count):
        row = []
        for column in psd_columns:
            values = data.data.get(column)
            row.append(_json_number(values[row_index]) if values is not None and row_index < len(values) else None)
        intensity.append(row)

    warnings = [
        "PSD detector-channel intensities are exposed in detector-channel/two-theta space.",
        "q_axis is intentionally omitted until a reviewed BT-7 PSD two-theta-to-Q calibration is available.",
    ]
    return {
        "status": "partial",
        "psd_channel_axis": list(range(len(psd_columns))),
        "psd_columns": psd_columns,
        "two_theta_axis": _constant_or_values(data.data.get("A4")),
        "two_theta_axis_source": "A4" if "A4" in data.data else None,
        "temperature_axis": [_json_number(value) for value in temperature_axis] if temperature_axis is not None else None,
        "temperature_axis_source": _temperature_axis_source(data.data),
        "intensity": intensity,
        "intensity_source": "PSDC columns",
        "q_axis": None,
        "q_axis_source": None,
        "warnings": warnings,
    }


def _line_scan_payload(data) -> dict | None:
    q_axis = _first_numeric_column(data.data, ["QX", "H", "Qx"])
    detector = data.data.get("Detector")
    if q_axis is None or detector is None or len(q_axis) == 0:
        return None
    monitor = data.data.get("Monitor")
    intensity = []
    raw_detector = []
    q_values = []
    for index, q_value in enumerate(q_axis):
        if index >= len(detector):
            continue
        q_json = _json_number(q_value)
        detector_json = _json_number(detector[index])
        if q_json is None or detector_json is None:
            continue
        monitor_value = _json_number(monitor[index]) if monitor is not None and index < len(monitor) else None
        q_values.append(q_json)
        raw_detector.append(detector_json)
        intensity.append(detector_json / monitor_value if monitor_value else detector_json)
    if not q_values:
        return None
    temperature = _mean_numeric(_first_numeric_column(data.data, ["TemperatureControlReading", "TemperatureSetpoint", "Temp", "Temperature"]))
    energy = _mean_numeric(data.data.get("E"))
    return {
        "status": "success",
        "q_axis": q_values,
        "q_axis_source": "QX",
        "energy_transfer_meV": energy,
        "energy_axis_source": "E" if "E" in data.data else None,
        "temperature_K": temperature,
        "temperature_axis_source": _temperature_axis_source(data.data),
        "intensity": intensity,
        "intensity_source": "Detector/Monitor" if monitor is not None else "Detector",
        "raw_detector": raw_detector,
        "monitor_normalized": monitor is not None,
        "detector_mode": data.metadata.analyzer_detector_mode,
    }


def _mean_numeric(values):
    if values is None:
        return None
    cleaned = [_json_number(value) for value in values]
    numeric = [value for value in cleaned if value is not None]
    if not numeric:
        return None
    return sum(numeric) / len(numeric)


def _first_numeric_column(data: dict, columns: list[str]):
    for column in columns:
        values = data.get(column)
        if values is not None and len(values) > 0:
            return values
    return None


def _temperature_axis_source(data: dict) -> str | None:
    for column in ["TemperatureControlReading", "TemperatureSetpoint", "Temp", "Temperature"]:
        if column in data:
            return column
    return None


def _constant_or_values(values):
    if values is None or len(values) == 0:
        return None
    cleaned = [_json_number(value) for value in values]
    numeric = [value for value in cleaned if value is not None]
    if not numeric:
        return None
    first = numeric[0]
    if all(abs(value - first) < 1e-6 for value in numeric):
        return {"type": "constant", "value": first}
    return {"type": "per_point", "values": cleaned}


def _json_number(value):
    try:
        if value != value:
            return None
        return float(value)
    except Exception:
        return None


def _group_payload(group) -> dict:
    return {
        "group_type": group.group_type,
        "expt_id": group.expt_id,
        "expt_name": group.expt_name,
        "scan_type": group.scan_type,
        "q_center": group.q_center,
        "temp_range": group.temp_range,
        "time_range": group.time_range,
        "record_paths": [record.path for record in group.records],
    }


def _json_ready(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_json_ready(item) for item in value)
    return value
