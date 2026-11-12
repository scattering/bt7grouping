import sys
import os
import glob
import numpy as np
from datetime import datetime
import re

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'TripleAxisGrouping', 'src'))

try:
    import readncnr3
except ImportError:
    print("Warning: readncnr3 not found or failed to import.")
    readncnr3 = None

class GenericData:
    def __init__(self):
        self.metadata = {
            'file_info': {},
            'count_info': {},
            'q_center': {},
            'temperature_info': {},
            'timestamp': {}
        }
        self.data = {}

class NiceReader:
    def readbuffer(self, filepath):
        data_obj = GenericData()
        data_obj.metadata['file_info']['filename'] = os.path.basename(filepath)
        
        with open(filepath, 'r', encoding='latin-1') as f:
            lines = f.readlines()
        
        header_lines = []
        column_names = []
        data_rows = []
        in_data = False
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith('##'):
                # Column header
                # e.g. ## pt A3(deg) ...
                parts = line[2:].strip().split()
                # Sometimes there are multiple spaces or tabs
                # Re-split carefully?
                # The example showed: ## pt    A3(deg)    A4(deg) ...
                # split() should handle it.
                column_names = line[2:].strip().split()
                in_data = True
                continue
            
            if line.startswith('#'):
                header_lines.append(line)
                # Parse key-value pairs
                # Format: # key value(s)
                parts = line[1:].strip().split(maxsplit=1)
                if len(parts) == 2:
                    key, value = parts
                    self._parse_header_key(data_obj, key, value)
            else:
                if in_data:
                    # Data row
                    try:
                        vals = line.split()
                        row = [float(v) if v.lower() != 'nan' else np.nan for v in vals]
                        data_rows.append(row)
                    except ValueError:
                        pass # Skip bad lines

        # Convert data to dictionary
        if column_names and data_rows:
            data_array = np.array(data_rows)
            # Check dimensions
            if data_array.shape[1] == len(column_names):
                for i, col in enumerate(column_names):
                    # Clean column name (remove units like (deg))
                    clean_col = col.split('(')[0]
                    data_obj.data[clean_col] = data_array[:, i]
                    data_obj.data[col] = data_array[:, i] # Keep original too
            
            # Post-process for metadata from data (like Q-center)
            self._extract_from_data(data_obj)
            
        return data_obj

    def _parse_header_key(self, data_obj, key, value):
        # Map NICE keys to our metadata structure
        if key == 'epoch':
            try:
                data_obj.metadata['timestamp']['epoch'] = float(value)
                data_obj.metadata['timestamp']['datetime'] = datetime.fromtimestamp(float(value))
            except:
                pass
        elif key == 'date':
             data_obj.metadata['timestamp']['date_str'] = value
        elif key == 'trajectoryData.description' or key == 'trajectory.description':
            data_obj.metadata['file_info']['scan_description'] = value.strip('"')
        elif key == 'trajectory.command':
             # Prefer command if available and description is generic
             if data_obj.metadata['file_info'].get('scan_description', '').startswith('start.sample') or \
                not data_obj.metadata['file_info'].get('scan_description'):
                 data_obj.metadata['file_info']['scan_description'] = value.strip('"')
        elif key == 'trajectory.scanned':
             data_obj.metadata['count_info']['varying'] = value.strip('[]')
        elif key == 'experiment.instrument':
            data_obj.metadata['file_info']['instrument'] = value

    def _extract_from_data(self, data_obj):
        # Extract Q center from first point
        # Look for Q.setH, etc.
        q_h = None
        q_k = None
        q_l = None
        q_e = None
        
        # Try various column names
        for col in data_obj.data:
            c = col.lower()
            if c in ['q.seth', 'q(x)', 'qx', 'h']:
                q_h = data_obj.data[col][0]
            elif c in ['q.setk', 'q(y)', 'qy', 'k']:
                q_k = data_obj.data[col][0]
            elif c in ['q.setl', 'q(z)', 'qz', 'l']:
                q_l = data_obj.data[col][0]
            elif c in ['et', 'e', 'energy']:
                q_e = data_obj.data[col][0]

        if q_h is not None: data_obj.metadata['q_center']['h_center'] = q_h
        if q_k is not None: data_obj.metadata['q_center']['k_center'] = q_k
        if q_l is not None: data_obj.metadata['q_center']['l_center'] = q_l
        if q_e is not None: data_obj.metadata['q_center']['e_center'] = q_e
        
        # Temperature
        if 'temp' in data_obj.data:
             data_obj.metadata['temperature_info']['Tstart'] = data_obj.data['temp'][0]
             data_obj.metadata['temperature_info']['Tmean'] = np.mean(data_obj.data['temp'])
        elif 'temp.set1' in data_obj.data:
             data_obj.metadata['temperature_info']['Tstart'] = data_obj.data['temp.set1'][0]

def get_reader(filepath):
    # Peek at file to decide reader
    try:
        with open(filepath, 'r', encoding='latin-1') as f:
            first_line = f.readline()
        if first_line.startswith('# NICE'):
            return NiceReader()
        else:
            return readncnr3.datareader()
    except:
        return None

class LogParser:
    def __init__(self):
        self.events = []

    def parse_file(self, filepath):
        year = datetime.now().year # Default, will try to infer
        # Try to infer year from filename if possible (e.g. 2022_11_03.console.log)
        filename = os.path.basename(filepath)
        match = re.match(r'(\d{4})_(\d{2})_(\d{2})\.console\.log', filename)
        if match:
            current_date = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        else:
            current_date = None

        with open(filepath, 'r', encoding='latin-1') as f:
            for line in f:
                line = line.strip()
                # Example: 03-Nov 11:18:27> move ei 13.7
                # Regex for timestamp
                # Note: The log format seems to be DD-Mon HH:MM:SS>
                m = re.match(r'^(\d{2}-[A-Za-z]{3} \d{2}:\d{2}:\d{2})> (.*)', line)
                if m:
                    ts_str, cmd = m.groups()
                    try:
                        # Parse time
                        dt = datetime.strptime(ts_str, "%d-%b %H:%M:%S")
                        
                        # Handle year: The log doesn't have year in the line.
                        # We must rely on the filename date or heuristic.
                        if current_date:
                            dt = dt.replace(year=current_date.year)
                            # Handle month rollover? If file is 2022_12_31 and log says 01-Jan...
                            # But usually one log per day/session?
                            # Let's assume the filename date is the start.
                        else:
                            dt = dt.replace(year=year) # Fallback
                            
                        epoch = dt.timestamp()
                        
                        # Filter for interesting commands
                        if self._is_interesting(cmd):
                            self.events.append({
                                'timestamp': epoch,
                                'type': 'log',
                                'description': cmd,
                                'path': filepath
                            })
                    except ValueError:
                        pass

    def _is_interesting(self, cmd):
        # Inelastic keywords: ei, ef, energy
        # General: move, scan, align
        keywords = ['move ei', 'move ef', 'move e', 'scan', 'findpeak', 'align', 'ice started']
        cmd_lower = cmd.lower()
        return any(k in cmd_lower for k in keywords)

def scan_files(root_dirs):
    records = []
    log_parser = LogParser()
    
    for root_dir in root_dirs:
        for root, dirs, files in os.walk(root_dir):
            for file in files:
                filepath = os.path.join(root, file)
                
                # Parse Logs
                if file.endswith('.console.log'):
                    log_parser.parse_file(filepath)
                    continue

                if file.endswith('.nxs') or file.endswith('.h5') or file.endswith('.hdf') or '.nxs' in file:
                    continue
                if not (file.endswith('.bt7') or file.endswith('.bt9') or file.endswith('.ng5') or file.endswith('.bt4')):
                    continue
                
                reader = get_reader(filepath)
                if not reader:
                    continue
                
                try:
                    data = reader.readbuffer(filepath)
                    
                    # Ensure timestamp
                    ts = data.metadata.get('timestamp', {})
                    epoch = ts.get('epoch', 0)
                    if not epoch and 'year' in ts:
                        try:
                            # Construct datetime
                            # time string is likely HH:MM
                            t_str = ts.get('time', '00:00')
                            dt = datetime(ts['year'], ts['month'], ts['day'])
                            # Parse time if possible
                            if ':' in t_str:
                                h, m = map(int, t_str.split(':')[:2])
                                dt = dt.replace(hour=h, minute=m)
                            epoch = dt.timestamp()
                        except:
                            pass
                    
                    # Create a record
                    rec = {
                        'path': filepath,
                        'filename': data.metadata['file_info'].get('filename', file),
                        'timestamp': epoch,
                        'scan_cmd': data.metadata['file_info'].get('scan_description', ''),
                        'varying': data.metadata['count_info'].get('varying', ''),
                        'h': data.metadata['q_center'].get('h_center'),
                        'k': data.metadata['q_center'].get('k_center'),
                        'l': data.metadata['q_center'].get('l_center'),
                        'e': data.metadata['q_center'].get('e_center'),
                        'temp': data.metadata['temperature_info'].get('Tstart'),
                        'instrument': data.metadata['file_info'].get('instrument', 'unknown'),
                        'type': 'data'
                    }
                    records.append(rec)
                except Exception as e:
                    # print(f"Failed to read {file}: {e}")
                    pass
    
    # Merge log events
    records.extend(log_parser.events)
    return records

def group_records(records):
    # Sort by timestamp
    records.sort(key=lambda x: x['timestamp'])
    
    groups = []
    current_group = []
    
    for rec in records:
        if rec.get('type') == 'log':
            # Logs break groups if they are "significant" (like moves) 
            # OR we can just add them to the stream and let the printer handle them.
            # Strategy: Treat logs as separate "groups" or "events" to intersperse.
            if current_group and current_group[0].get('type') == 'data':
                groups.append(current_group)
                current_group = []
            
            # Add log to its own group (or accumulate logs)
            if current_group and current_group[0].get('type') == 'log':
                current_group.append(rec)
            else:
                current_group = [rec]
            continue
            
        # It is data
        if current_group and current_group[0].get('type') == 'log':
            groups.append(current_group)
            current_group = []

        if not current_group:
            current_group.append(rec)
            continue
        
        last = current_group[-1]
        
        # Similarity criteria (Only for data)
        # 1. Same scan command type (first word of command)
        # 2. Similar Q (if not varying Q)
        
        # Check command similarity
        cmd1 = last['scan_cmd']
        cmd2 = rec['scan_cmd']
        
        # Simple heuristic: if commands are identical strings, definitely same group
        same_cmd = (cmd1 == cmd2)
        
        # Check Q similarity (tolerance 0.05)
        # Handle Nones
        q1 = np.array([last['h'], last['k'], last['l'], last['e']])
        q2 = np.array([rec['h'], rec['k'], rec['l'], rec['e']])
        
        # Replace None with 0 for comparison, or fail?
        q_match = True
        try:
            q1 = q1.astype(float)
            q2 = q2.astype(float)
            if np.any(np.isnan(q1)) or np.any(np.isnan(q2)):
                 # If Q is missing, rely on command
                 pass 
            else:
                 dist = np.linalg.norm(q1 - q2)
                 if dist > 0.1: # Tolerance
                     q_match = False
        except:
            pass # Q extraction failed or incomplete
        
        is_related = False
        
        if same_cmd and q_match:
            is_related = True
        elif same_cmd and not q_match:
            is_related = False 
            
        # Mesh check
        if 'mesh' in last['filename'].lower() and 'mesh' in rec['filename'].lower():
            if (rec['timestamp'] - last['timestamp']) < 3600*4: # 4 hours
                is_related = True
        
        if is_related:
            current_group.append(rec)
        else:
            groups.append(current_group)
            current_group = [rec]
            
    if current_group:
        groups.append(current_group)
        
    return groups
def print_groups(groups):
    print(f"Found {len(groups)} groups (including log segments).")
    
    for i, grp in enumerate(groups):
        if not grp: continue
        
        # Check if this group is purely log events
        is_log_only = all(r.get('type') == 'log' for r in grp)
        
        if is_log_only:
            # Print significant log events if they are "moves"
            moves = [r['description'] for r in grp if 'move' in r['description'].lower()]
            if moves:
                print(f"\n--- Log Events ({datetime.fromtimestamp(grp[0]['timestamp'])}) ---")
                # Deduplicate consecutive identical moves
                last_move = None
                for m in moves:
                    if m != last_move:
                        print(f"  > {m}")
                        last_move = m
        else:
            # Data group
            data_files = [r for r in grp if r.get('type') == 'data']
            if not data_files: continue
            
            first = data_files[0]
            last = data_files[-1]
            
            print(f"\nGroup {i+1}: {len(data_files)} files")
            print(f"  Instrument: {first['instrument']}")
            print(f"  First: {first['filename']} ({datetime.fromtimestamp(first['timestamp'])})")
            print(f"  Last:  {last['filename']} ({datetime.fromtimestamp(last['timestamp'])})")
            print(f"  Command: {first['scan_cmd']}")
            print(f"  Varying: {first['varying']}")
            print(f"  Q Center: H={first['h']}, K={first['k']}, L={first['l']}, E={first['e']}")
            
            # Check if T changed
            temps = [r['temp'] for r in data_files if r['temp'] is not None]
            if temps:
                tmin, tmax = min(temps), max(temps)
                if tmax - tmin > 1.0:
                    print(f"  Temperature Scan: {tmin:.1f} K -> {tmax:.1f} K")
                else:
                    print(f"  Temperature: {tmin:.1f} K (constant)")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Classify TAS scans")
    parser.add_argument("directories", nargs="+", help="Explicit local data directories")
    dirs = parser.parse_args().directories
    
    print("Scanning files...")
    records = scan_files(dirs)
    print(f"Scanned {len(records)} files.")
    
    print("Grouping...")
    groups = group_records(records)
    
    print_groups(groups)
