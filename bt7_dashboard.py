#!/usr/bin/env python
"""
BT-7 Scan Dashboard using Plotly Dash
Displays scan data in a sortable grid with interactive plots.

Features:
- Sortable table showing scan metadata
- Bar visualizations for numeric ranges
- Interactive plot popup with axis selection
- Handles missing sample environment columns (T, H field)
- Priority display: scanned variables, H/K/L/E, motors (A3, A4), sample environment
"""

import dash
from dash import dcc, html, dash_table, Input, Output, State, callback_context
import dash.exceptions
import plotly.graph_objs as go
import plotly.express as px
import pandas as pd
import numpy as np
from pathlib import Path
import re
import argparse
import threading
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Initialize Dash app
app = dash.Dash(__name__)

# Global variables
scan_data = []
grid_df = pd.DataFrame()
display_df = pd.DataFrame()
tooltip_data = {}
data_refresh_flag = threading.Event()
data_last_updated = time.time()
data_dir = "."
experiment_id = None

# Priority columns for display (in order)
PRIORITY_COLUMNS = [
    'Filename', 'scan_title', 'scan_var',  # Identification
    'H', 'K', 'L', 'E',                     # Physical coordinates
    'A3', 'A4', 'A5', 'A6',                 # Key motors
    'Ei', 'Ef',                              # Energy
    'Temp', 'MagField',                      # Sample environment
    'Time', 'Monitor', 'Detector',           # Counting
    'start_time', 'npoints'                  # Scan info
]

# Column width configuration
COLUMN_WIDTHS = {
    'Filename': '140px',
    'scan_title': '250px',
    'scan_var': '80px',
    'H': '100px',
    'K': '100px',
    'L': '100px',
    'E': '100px',
    'A3': '100px',
    'A4': '100px',
    'A5': '100px',
    'A6': '100px',
    'Ei': '80px',
    'Ef': '80px',
    'Temp': '100px',
    'MagField': '100px',
    'Time': '80px',
    'Monitor': '90px',
    'Detector': '100px',
    'start_time': '140px',
    'npoints': '70px',
}


class FileWatchHandler(FileSystemEventHandler):
    """Handler for file system events that triggers data refresh."""

    def __init__(self, file_pattern="*.bt7"):
        self.file_pattern = file_pattern
        super().__init__()

    def on_created(self, event):
        self._handle_file_event(event, "created")

    def on_modified(self, event):
        self._handle_file_event(event, "modified")

    def _handle_file_event(self, event, event_type):
        if event.is_directory:
            return
        file_path = Path(event.src_path)
        if file_path.suffix == '.bt7':
            print(f"File {event_type}: {file_path.name}")
            data_refresh_flag.set()


def setup_file_watchers(watch_dir):
    """Set up file system watchers for .bt7 files."""
    observer = Observer()
    handler = FileWatchHandler("*.bt7")
    observer.schedule(handler, str(watch_dir), recursive=True)
    observer.start()
    print(f"Watching {watch_dir} for .bt7 files")
    return observer


def refresh_data_background():
    """Background thread to handle data refresh."""
    global scan_data, grid_df, display_df, tooltip_data, data_last_updated

    while True:
        data_refresh_flag.wait()
        data_refresh_flag.clear()

        print("Refreshing scan data...")
        try:
            new_scan_data = read_bt7_files(data_dir, experiment_id)
            new_grid_df = prepare_grid_data(new_scan_data)
            new_display_df, new_tooltip_data = format_grid_data(new_grid_df)

            scan_data = new_scan_data
            grid_df = new_grid_df
            display_df = new_display_df
            tooltip_data = new_tooltip_data
            data_last_updated = time.time()

            print(f"Data refresh completed. Now showing {len(scan_data)} scans.")
        except Exception as e:
            print(f"Error during data refresh: {e}")

        time.sleep(2)


def parse_ice_file(filepath):
    """Parse ICE format BT-7 file."""
    try:
        with open(filepath, 'r', encoding='latin-1') as f:
            content = f.read()
    except:
        return None, None

    if not content.startswith('#ICE'):
        return None, None

    lines = content.split('\n')

    header = {}
    columns = []
    data_rows = []
    in_data = False

    for line in lines:
        if line.startswith('#Filename'):
            header['filename'] = line.split(maxsplit=1)[1].strip() if len(line.split(maxsplit=1)) > 1 else ''
        elif line.startswith('#Date'):
            header['date'] = line.replace('#Date', '').strip()
        elif line.startswith('#ExptID'):
            header['expt_id'] = line.split()[1] if len(line.split()) > 1 else ''
        elif line.startswith('#ExptName'):
            header['expt_name'] = line.replace('#ExptName', '').strip()
        elif line.startswith('#Npoints'):
            header['npoints'] = int(line.split()[1]) if len(line.split()) > 1 else 0
        elif line.startswith('#Scan '):
            parts = line.split()
            if len(parts) >= 3:
                header['scan_var'] = parts[2]
        elif line.startswith('#ScanDescr'):
            header['scan_descr'] = line.replace('#ScanDescr', '').strip()
            # Extract title from ScanDescr
            title_match = re.search(r'Title=([^:]+)', line)
            if title_match:
                header['scan_title'] = title_match.group(1).strip()
        elif line.startswith('#FixedE'):
            parts = line.split()
            if len(parts) >= 2:
                header['fixed_e'] = parts[1]  # Ei or Ef
        elif line.startswith('#Columns'):
            columns = line.replace('#Columns', '').split()
            in_data = True
            continue

        if in_data and not line.startswith('#') and line.strip():
            values = line.split()
            if len(values) == len(columns):
                row = {}
                for i, col in enumerate(columns):
                    val = values[i]
                    if val == 'N/A' or val.startswith('['):
                        row[col] = np.nan
                    else:
                        try:
                            row[col] = float(val)
                        except:
                            row[col] = val
                data_rows.append(row)

    if not data_rows:
        return header, None

    df = pd.DataFrame(data_rows)
    return header, df


def read_bt7_files(directory, expt_id=None):
    """Read BT-7 scan files from a directory."""
    scan_data = []
    dir_path = Path(directory)

    # Find all .bt7 files
    bt7_files = sorted(dir_path.glob("**/*.bt7"))

    print(f"Found {len(bt7_files)} BT-7 files")

    for filepath in bt7_files:
        try:
            header, df = parse_ice_file(filepath)

            if header is None or df is None or len(df) == 0:
                continue

            # Filter by experiment ID if specified
            if expt_id and header.get('expt_id') != str(expt_id):
                continue

            scan_info = {
                'Filename': filepath.name,
                'filepath': str(filepath),
                'scan_number': extract_scan_number(filepath.name),
            }

            # Add header info
            scan_info['scan_title'] = header.get('scan_title', '')
            scan_info['scan_var'] = header.get('scan_var', '')
            scan_info['npoints'] = header.get('npoints', len(df))
            scan_info['start_time'] = header.get('date', '')
            scan_info['fixed_e'] = header.get('fixed_e', '')

            # Extract ranges/statistics for key columns
            key_columns = ['QX', 'QY', 'QZ', 'H', 'K', 'L', 'E',
                          'A1', 'A2', 'A3', 'A4', 'A5', 'A6',
                          'Ei', 'Ef', 'Time', 'Monitor', 'Detector',
                          'Temp', 'MagField', 'TemperatureControlReading']

            # Map column aliases
            column_aliases = {
                'TemperatureControlReading': 'Temp',
            }

            for col in df.columns:
                # Use alias if available
                display_col = column_aliases.get(col, col)

                if col in key_columns or display_col in key_columns:
                    col_data = pd.to_numeric(df[col], errors='coerce')
                    if not col_data.isna().all():
                        scan_info[f'{display_col}_min'] = col_data.min()
                        scan_info[f'{display_col}_max'] = col_data.max()
                        scan_info[f'{display_col}_mean'] = col_data.mean()
                        scan_info[f'{display_col}_range'] = col_data.max() - col_data.min()

                        if len(col_data) > 1:
                            diffs = col_data.diff().dropna()
                            if len(diffs) > 0:
                                scan_info[f'{display_col}_step'] = diffs.abs().median()

            # Store the dataframe for plotting
            scan_info['_dataframe'] = df
            scan_data.append(scan_info)

        except Exception as e:
            print(f"Error reading {filepath}: {e}")
            continue

    return scan_data


def extract_scan_number(filename):
    """Extract scan number from BT-7 filename."""
    # Try various patterns
    patterns = [
        r'(\d+)\.bt7$',  # Just numbers before .bt7
        r'scan(\d+)',     # scan followed by numbers
        r'_(\d+)\.bt7$',  # underscore then numbers
    ]
    for pattern in patterns:
        match = re.search(pattern, filename, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return 0


def prepare_grid_data(scan_data):
    """Prepare data for the Dash grid display."""
    if not scan_data:
        return pd.DataFrame()

    grid_rows = []
    all_columns = set()

    for scan in scan_data:
        for key in scan.keys():
            if not key.startswith('_'):
                all_columns.add(key)

    # Build column order based on priority
    column_order = []
    for col in PRIORITY_COLUMNS:
        if col in all_columns or any(f'{col}_min' in scan for scan in scan_data):
            column_order.append(col)

    # Add remaining columns alphabetically
    remaining = sorted([c for c in all_columns if c not in column_order
                       and not c.endswith(('_min', '_max', '_mean', '_range', '_step'))
                       and c not in ['filepath', 'scan_number']])
    column_order.extend(remaining)

    for scan in scan_data:
        row = {}
        for col in column_order:
            if col in scan:
                row[col] = scan[col]
            else:
                row[col] = None
        row['scan_number'] = scan.get('scan_number', 0)

        # Copy statistics
        for key, value in scan.items():
            if key.endswith(('_min', '_max', '_mean', '_range', '_step')):
                row[key] = value

        grid_rows.append(row)

    df = pd.DataFrame(grid_rows)

    # Calculate global min/max for bar visualizations
    numeric_fields = ['H', 'K', 'L', 'E', 'A3', 'A4', 'A5', 'A6',
                     'Temp', 'MagField', 'Ei', 'Ef', 'Time', 'Monitor', 'Detector']

    for field in numeric_fields:
        min_col = f'{field}_min'
        max_col = f'{field}_max'
        if min_col in df.columns and max_col in df.columns:
            valid_mins = df[min_col].dropna()
            valid_maxs = df[max_col].dropna()
            if len(valid_mins) > 0 and len(valid_maxs) > 0:
                df[f'{field}_global_min'] = valid_mins.min()
                df[f'{field}_global_max'] = valid_maxs.max()

    return df


def create_position_bar_chart(scan_min, scan_max, global_min, global_max, width=40):
    """Create a bar chart showing scan range position within global range."""
    if pd.isna(scan_min) or pd.isna(scan_max) or pd.isna(global_min) or pd.isna(global_max):
        return ""

    global_range = global_max - global_min
    if global_range == 0:
        return "█" * width

    start_pos = (scan_min - global_min) / global_range
    end_pos = (scan_max - global_min) / global_range

    start_char = int(start_pos * width)
    end_char = int(end_pos * width)

    if end_char == start_char:
        end_char = min(start_char + 1, width)

    bar = "░" * start_char + "█" * (end_char - start_char) + "░" * (width - end_char)
    return bar


def format_grid_data(df):
    """Format data for display in the grid with bar visualizations."""
    if df.empty:
        return df, {}

    display_df = df.copy()
    tooltip_data = {}

    # Add bar visualizations for numeric fields
    numeric_fields = ['H', 'K', 'L', 'E', 'A3', 'A4', 'A5', 'A6',
                     'Temp', 'MagField', 'Ei', 'Ef', 'Time', 'Monitor', 'Detector']

    for field in numeric_fields:
        min_col = f'{field}_min'
        max_col = f'{field}_max'
        global_min_col = f'{field}_global_min'
        global_max_col = f'{field}_global_max'

        if all(col in display_df.columns for col in [min_col, max_col, global_min_col, global_max_col]):
            display_df[field] = display_df.apply(
                lambda row: create_position_bar_chart(
                    row[min_col], row[max_col],
                    row[global_min_col], row[global_max_col]
                ) if all(pd.notna(row.get(col)) for col in [min_col, max_col, global_min_col, global_max_col]) else "",
                axis=1
            )

            # Create tooltips
            step_col = f'{field}_step'
            tooltip_data[field] = []
            for idx, row in display_df.iterrows():
                if all(pd.notna(row.get(col)) for col in [min_col, max_col]):
                    min_val = row[min_col]
                    max_val = row[max_col]
                    step = row.get(step_col, 0) if pd.notna(row.get(step_col)) else 0
                    tooltip = f"Min: {min_val:.3f}\nMax: {max_val:.3f}\nStep: {step:.4f}"
                    tooltip_data[field].append(tooltip)
                else:
                    tooltip_data[field].append("")

    # Remove internal columns from display
    cols_to_remove = [col for col in display_df.columns
                     if col.endswith(('_min', '_max', '_mean', '_range', '_step',
                                     '_global_min', '_global_max', '_fraction'))
                     or col in ['filepath']]
    display_df = display_df.drop(columns=[c for c in cols_to_remove if c in display_df.columns])

    # Reorder columns
    ordered_cols = [col for col in PRIORITY_COLUMNS if col in display_df.columns]
    remaining_cols = sorted([col for col in display_df.columns
                            if col not in ordered_cols and col != 'scan_number'])
    final_order = ordered_cols + remaining_cols
    if 'scan_number' in display_df.columns:
        final_order.append('scan_number')

    display_df = display_df[[c for c in final_order if c in display_df.columns]]

    return display_df, tooltip_data


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='BT-7 Scan Dashboard')
    parser.add_argument('directory', nargs='?', default='.',
                       help='Directory containing BT-7 files (default: current directory)')
    parser.add_argument('--expt', type=str, default=None,
                       help='Filter by experiment ID')
    parser.add_argument('--port', type=int, default=8050,
                       help='Port for dashboard (default: 8050)')
    parser.add_argument('--no-watch', action='store_true',
                       help='Disable file watching')
    return parser.parse_args()


# Parse arguments
args = parse_arguments()
data_dir = args.directory
experiment_id = args.expt

# Read initial data
print(f"Loading BT-7 data from {data_dir}...")
scan_data = read_bt7_files(data_dir, experiment_id)
grid_df = prepare_grid_data(scan_data)
display_df, tooltip_data = format_grid_data(grid_df)
print(f"Loaded {len(scan_data)} scans")

# Build column styles
visible_columns = [col for col in display_df.columns if col != 'scan_number']
style_cell_conditional = [
    {'if': {'column_id': col}, 'width': width}
    for col, width in COLUMN_WIDTHS.items()
    if col in visible_columns
] + [
    {'if': {'column_id': col}, 'width': '100px'}
    for col in visible_columns
    if col not in COLUMN_WIDTHS
]

# Create the layout
app.layout = html.Div([
    html.H1("BT-7 Scan Dashboard", style={'textAlign': 'center'}),

    html.Div([
        html.P(f"Showing {len(scan_data)} scans from {data_dir}" +
               (f" (Experiment {experiment_id})" if experiment_id else "")),
        html.P("Click on a row to view detailed plots. Bars show relative coverage. "
               "Hover over bars for min/max/step values."),
    ], style={'margin': '20px'}),

    # Data table
    dash_table.DataTable(
        id='scan-table',
        columns=[
            {"name": col, "id": col}
            for col in display_df.columns if col != 'scan_number'
        ],
        data=display_df.to_dict('records') if not display_df.empty else [],
        tooltip_data=[
            {col: tooltip_data.get(col, [""])[i] if col in tooltip_data and i < len(tooltip_data.get(col, [])) else ""
             for col in display_df.columns if col != 'scan_number'}
            for i in range(len(display_df))
        ] if not display_df.empty else [],
        tooltip_duration=None,
        sort_action="native",
        sort_mode="multi",
        row_selectable="multi",
        page_size=50,
        fill_width=False,
        style_cell={
            'textAlign': 'left',
            'fontFamily': 'monospace',
            'fontSize': '12px',
            'whiteSpace': 'pre',
            'overflow': 'hidden',
            'textOverflow': 'ellipsis',
            'minWidth': '60px',
            'maxWidth': '400px'
        },
        style_cell_conditional=style_cell_conditional,
        style_header={
            'backgroundColor': 'rgb(230, 230, 230)',
            'fontWeight': 'bold'
        },
        style_table={
            'overflowX': 'auto',
            'width': '100%'
        }
    ),

    # Modal for plot popup
    dcc.Store(id='selected-scan-data'),
    html.Div(id='plot-modal', style={'display': 'none'}),

    # Hidden components for callbacks
    html.Button(id='close-popup', style={'display': 'none'}),
    dcc.Dropdown(id='x-column-dropdown', style={'display': 'none'}),
    dcc.Dropdown(id='y-column-dropdown', style={'display': 'none'}),
    dcc.RadioItems(id='y-scale-toggle', style={'display': 'none'}),
    dcc.Graph(id='scan-plot', style={'display': 'none'}),

    # Interval for auto-refresh
    dcc.Interval(id='refresh-interval', interval=5000, n_intervals=0),
    dcc.Store(id='last-update-time', data=time.time()),
])


@app.callback(
    [Output('selected-scan-data', 'data'),
     Output('plot-modal', 'children'),
     Output('plot-modal', 'style')],
    [Input('scan-table', 'active_cell'),
     Input('scan-table', 'selected_rows')],
    [State('scan-table', 'data')]
)
def show_plot_popup(active_cell, selected_rows, table_data):
    """Show plot popup when a cell is clicked."""
    ctx = callback_context
    if not ctx.triggered:
        return None, [], {'display': 'none'}

    # Use selected rows if available
    if selected_rows and len(selected_rows) > 0:
        row_indices = selected_rows
    elif active_cell:
        row_indices = [active_cell['row']]
    else:
        return None, [], {'display': 'none'}

    # Get selected scans
    valid_indices = [idx for idx in row_indices if idx < len(scan_data)]
    if not valid_indices:
        return None, [], {'display': 'none'}

    selected_scans = [scan_data[idx] for idx in valid_indices]
    first_scan = selected_scans[0]
    first_df = first_scan['_dataframe']

    # Get numeric columns
    numeric_cols = [col for col in first_df.select_dtypes(include=[np.number]).columns]

    # Prioritize certain columns for defaults
    priority_x = ['E', 'QX', 'H', 'K', 'L', 'A3', 'A4']
    priority_y = ['Detector', 'DDC1', 'DDC0', 'Monitor']

    x_col = next((c for c in priority_x if c in numeric_cols), numeric_cols[0] if numeric_cols else None)
    y_col = next((c for c in priority_y if c in numeric_cols), numeric_cols[1] if len(numeric_cols) > 1 else None)

    # Check what the scan variable is and use that for x
    scan_var = first_scan.get('scan_var', '')
    if scan_var in numeric_cols:
        x_col = scan_var

    if x_col is None or y_col is None:
        return None, [], {'display': 'none'}

    # Create initial plot
    fig = go.Figure()
    colors = px.colors.qualitative.Set1

    for i, scan in enumerate(selected_scans):
        df = scan['_dataframe']
        scan_name = scan.get('Filename', f'Scan {i+1}')
        color = colors[i % len(colors)]

        if x_col in df.columns and y_col in df.columns:
            fig.add_trace(go.Scatter(
                x=df[x_col],
                y=df[y_col],
                mode='lines+markers',
                name=scan_name,
                line=dict(color=color),
                marker=dict(color=color)
            ))

    title = f"Scan Data: {', '.join([s.get('Filename', '') for s in selected_scans[:3]])}"
    if len(selected_scans) > 3:
        title += f" (+{len(selected_scans)-3} more)"

    fig.update_layout(
        title=title,
        xaxis_title=x_col,
        yaxis_title=y_col,
        height=500,
        showlegend=len(selected_scans) > 1
    )

    # Create popup content
    popup_content = [
        html.Div([
            html.H3(title, style={'margin': '10px'}),
            html.Button('Close', id='close-popup', n_clicks=0,
                       style={'float': 'right', 'margin': '10px'}),

            html.Div([
                html.Label("X-axis:"),
                dcc.Dropdown(
                    id='x-column-dropdown',
                    options=[{'label': col, 'value': col} for col in numeric_cols],
                    value=x_col,
                    style={'width': '200px', 'display': 'inline-block', 'margin': '10px'}
                ),

                html.Label("Y-axis:"),
                dcc.Dropdown(
                    id='y-column-dropdown',
                    options=[{'label': col, 'value': col} for col in numeric_cols],
                    value=y_col,
                    style={'width': '200px', 'display': 'inline-block', 'margin': '10px'}
                ),

                html.Label("Scale:"),
                dcc.RadioItems(
                    id='y-scale-toggle',
                    options=[
                        {'label': 'Linear', 'value': 'linear'},
                        {'label': 'Log', 'value': 'log'}
                    ],
                    value='linear',
                    inline=True,
                    style={'display': 'inline-block', 'margin': '10px'}
                ),
            ], style={'margin': '20px'}),

            dcc.Graph(id='scan-plot', figure=fig)

        ], style={
            'position': 'fixed',
            'top': '5%',
            'left': '5%',
            'width': '90%',
            'height': '90%',
            'backgroundColor': 'white',
            'border': '2px solid black',
            'zIndex': 1000,
            'padding': '20px',
            'overflow': 'auto'
        })
    ]

    scan_data_for_store = {
        'scan_indices': valid_indices
    }

    return scan_data_for_store, popup_content, {'display': 'block'}


@app.callback(
    Output('plot-modal', 'style', allow_duplicate=True),
    [Input('close-popup', 'n_clicks')],
    prevent_initial_call=True
)
def close_popup(n_clicks):
    """Close the plot popup."""
    if n_clicks:
        return {'display': 'none'}
    return {'display': 'block'}


@app.callback(
    Output('scan-plot', 'figure'),
    [Input('x-column-dropdown', 'value'),
     Input('y-column-dropdown', 'value'),
     Input('y-scale-toggle', 'value')],
    [State('selected-scan-data', 'data')]
)
def update_plot(x_column, y_column, y_scale, scan_data_state):
    """Update plot based on dropdown selections."""
    if not scan_data_state or not x_column or not y_column:
        return go.Figure()

    indices = scan_data_state.get('scan_indices', [])
    selected_scans = [scan_data[i] for i in indices if i < len(scan_data)]

    if not selected_scans:
        return go.Figure()

    fig = go.Figure()
    colors = px.colors.qualitative.Set1

    for i, scan in enumerate(selected_scans):
        df = scan['_dataframe']
        scan_name = scan.get('Filename', f'Scan {i+1}')
        color = colors[i % len(colors)]

        if x_column in df.columns and y_column in df.columns:
            fig.add_trace(go.Scatter(
                x=df[x_column],
                y=df[y_column],
                mode='lines+markers',
                name=scan_name,
                line=dict(color=color),
                marker=dict(color=color)
            ))

    title = f"{y_column} vs {x_column}"

    fig.update_layout(
        title=title,
        xaxis_title=x_column,
        yaxis_title=y_column,
        yaxis_type=y_scale,
        height=500,
        showlegend=len(selected_scans) > 1
    )

    return fig


if __name__ == '__main__':
    print("Starting BT-7 Scan Dashboard...")
    print(f"Open your browser to http://127.0.0.1:{args.port}")

    # Start file watcher if enabled
    observer = None
    if not args.no_watch:
        observer = setup_file_watchers(data_dir)
        refresh_thread = threading.Thread(target=refresh_data_background, daemon=True)
        refresh_thread.start()

    try:
        app.run(debug=False, port=args.port, host='0.0.0.0')
    except KeyboardInterrupt:
        print("\nShutting down...")
        if observer:
            observer.stop()
            observer.join()
