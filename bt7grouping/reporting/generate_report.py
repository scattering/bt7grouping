import os
import sys
import shutil
import datetime
import glob
import subprocess

# Ensure local modules are in path
sys.path.append(os.path.join(os.getcwd(), 'TripleAxisGrouping'))
sys.path.append(os.path.join(os.getcwd(), 'TripleAxisGrouping', 'src'))

import classify_scans

def generate_report(input_dirs, output_dir):
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)
    
    print("Scanning and grouping files...")
    records = classify_scans.scan_files(input_dirs)
    groups = classify_scans.group_records(records)
    
    html_content = [
        "<html><head><title>Experiment Report</title>",
        "<style>",
        "body { font-family: sans-serif; margin: 20px; }",
        ".group { border: 1px solid #ccc; margin-bottom: 20px; padding: 10px; border-radius: 5px; }",
        ".group-header { background-color: #f0f0f0; padding: 5px; font-weight: bold; }",
        ".log-event { color: #555; font-style: italic; margin: 5px 0; border-left: 3px solid #ffa500; padding-left: 10px; }",
        ".file-list { font-family: monospace; font-size: 0.9em; max-height: 300px; overflow-y: auto; background: #fafafa; padding: 5px; }",
        "img { max-width: 600px; height: auto; border: 1px solid #ddd; margin: 5px; }",
        ".plot-container { display: flex; flex-wrap: wrap; }",
        "a { text-decoration: none; color: #007bff; }",
        "a:hover { text-decoration: underline; }",
        "</style></head><body>",
        f"<h1>Experiment Report</h1>",
        f"<p>Generated: {datetime.datetime.now()}</p>",
        f"<p>Input Directories: {', '.join(input_dirs)}</p>"
    ]
    
    group_counter = 0
    
    for grp in groups:
        if not grp: continue
        
        # Check if log group
        if all(r.get('type') == 'log' for r in grp):
            moves = [r['description'] for r in grp if 'move' in r['description'].lower()]
            if moves:
                ts = datetime.datetime.fromtimestamp(grp[0]['timestamp'])
                html_content.append(f"<div class='log-event'><strong>{ts}</strong>: Instrument Log<br>")
                last_move = None
                for m in moves:
                    if m != last_move:
                        html_content.append(f"&gt; {m}<br>")
                        last_move = m
                html_content.append("</div>")
            continue
            
        # Data Group
        data_files = [r for r in grp if r.get('type') == 'data']
        if not data_files: continue
        
        group_counter += 1
        group_name = f"Group_{group_counter:03d}"
        
        # Heuristic for group name
        first = data_files[0]
        scan_type = "Scan"
        if "mesh" in first['filename'].lower():
            scan_type = "Mesh"
        elif "align" in first['scan_cmd'].lower() or "peak" in first['scan_cmd'].lower():
            scan_type = "Alignment"
            
        group_dir_name = f"{group_name}_{scan_type}"
        group_path = os.path.join(output_dir, group_dir_name)
        os.makedirs(group_path)
        
        # Symlink files and generate 1D plots
        html_file_list = []
        plot_gallery = []
        
        # Helper to run plotting in separate process to avoid library conflicts or memory leaks
        # And easier to manage paths
        
        # For Mesh, we combine files
        if scan_type == "Mesh" and len(data_files) > 1:
            mesh_plot_filename = "mesh_plot.png"
            mesh_plot_abs = os.path.join(group_path, mesh_plot_filename)
            # Pass all files to plot_mesh.py
            # Construct command
            file_paths = [r['path'] for r in data_files]
            
            cmd = [sys.executable, "TripleAxisGrouping/plot_mesh.py", mesh_plot_abs] + file_paths
            try:
                subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if os.path.exists(mesh_plot_abs):
                    plot_gallery.append(f"<div class='plot-item'><h4>Mesh Plot</h4><img src='{group_dir_name}/{mesh_plot_filename}'></div>")
            except Exception as e:
                print(f"Mesh plotting failed: {e}")

        # For individual files (1D Scans)
        # We will generate a plot for EACH file.
        for rec in data_files:
            src = rec['path']
            filename = rec['filename']
            dst = os.path.join(group_path, filename)
            try:
                if not os.path.exists(dst):
                    os.symlink(src, dst)
            except OSError:
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
            
            # Generate 1D plot
            plot_filename = f"{filename}.png"
            plot_abs = os.path.join(group_path, plot_filename)
            
            cmd = [sys.executable, "TripleAxisGrouping/plot_scan.py", src, plot_abs]
            subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            has_plot = os.path.exists(plot_abs)
            
            link = f"<a href='{group_dir_name}/{filename}'>{filename}</a>"
            if has_plot:
                # Add to gallery? Or link?
                # If too many files, gallery is huge.
                # Let's add a small link " [Plot]"
                link += f" <a href='{group_dir_name}/{plot_filename}' target='_blank'>[Plot]</a>"
                
                # Add to gallery only if alignment or small group, or if requested "add plots"
                # User said "For the individual files, add plots".
                # I'll put them in a scrollable container or just link them.
                # Let's show the first 3 in the main view and hide others?
                # Or just put them all in the file list as links.
                
            html_file_list.append(link)

        # HTML Entry
        start_time = datetime.datetime.fromtimestamp(first['timestamp'])
        
        # Temperature range
        temps = [r['temp'] for r in data_files if r['temp'] is not None]
        temp_str = "N/A"
        if temps:
            tmin, tmax = min(temps), max(temps)
            temp_str = f"{tmin:.1f} K" if (tmax - tmin) < 1.0 else f"{tmin:.1f} K - {tmax:.1f} K"

        html_content.append(f"<div class='group'>")
        html_content.append(f"<div class='group-header'>{group_dir_name} | {first['instrument']} | {start_time}</div>")
        html_content.append(f"<ul>")
        html_content.append(f"<li><strong>Command:</strong> {first['scan_cmd']}</li>")
        html_content.append(f"<li><strong>Files:</strong> {len(data_files)}</li>")
        html_content.append(f"<li><strong>Temperature:</strong> {temp_str}</li>")
        html_content.append(f"<li><strong>Q-Center:</strong> H={first['h']}, K={first['k']}, L={first['l']}, E={first['e']}</li>")
        html_content.append(f"</ul>")
        
        if plot_gallery:
            html_content.append("<div class='plot-container'>")
            html_content.append("".join(plot_gallery))
            html_content.append("</div>")
        
        html_content.append(f"<div class='file-list'>")
        html_content.append("<br>".join(html_file_list))
        html_content.append(f"</div>")
            
        html_content.append("</div>")

    html_content.append("</body></html>")
    
    with open(os.path.join(output_dir, "index.html"), "w") as f:
        f.write("\n".join(html_content))
        
    print(f"Report generated at: {os.path.join(output_dir, 'index.html')}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate a local TAS scan report")
    parser.add_argument("directories", nargs="+", help="Explicit local data directories")
    parser.add_argument("--output", required=True, help="Output directory")
    args = parser.parse_args()
    dirs = args.directories
    
    output = args.output
    generate_report(dirs, output)
