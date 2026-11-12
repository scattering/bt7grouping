import numpy as np
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import sys
import os
import traceback

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'TripleAxisGrouping', 'src'))

try:
    import readncnr3
except ImportError:
    print("Warning: readncnr3 not found or failed to import.")
    sys.exit(1)

def plot_mesh(file_list, output_file='mesh_plot.png'):
    reader = readncnr3.datareader()
    
    x_list = []
    y_list = []
    z_list = []
    
    xlabel = "X"
    ylabel = "Y"
    
    print(f"Reading {len(file_list)} files for mesh...")
    
    # Heuristic to determine axes from the first file
    first_data = None
    try:
        first_data = reader.readbuffer(file_list[0])
        varying = first_data.metadata['count_info'].get('varying', [])
        
        # If varying contains 2 variables, those are likely X and Y.
        # But in a mesh scan (nested loop), the inner loop varies in the file, 
        # the outer loop is constant per file but varies across files.
        # The 'varying' field in the file metadata usually only lists the inner loop variable 
        # (e.g., 'qx', 'qy' if they are coupled, or just 'qx').
        # Actually, for a mesh scan, often both are listed if defined in the scan command?
        # In the previous step, `d.metadata['count_info']['varying']` printed `['qx', 'qy']`.
        
        # We need to find which two columns actually vary across the *entire dataset*.
        pass
    except:
        pass

    # Read all data
    for fpath in file_list:
        try:
            data = reader.readbuffer(fpath)
            keys = list(data.data.keys())
            keys_lower = {k.lower(): k for k in keys}
            
            vx = None
            vy = None
            vz = None
            
            # Determine Axes strategy:
            # Look for Qx, Qy, Qz, A3, A4
            # We want to find the columns that correspond to the mesh dimensions.
            
            # Strategy: Grab candidates
            candidates = {}
            for k in ['qx', 'qy', 'qz', 'a3', 'a4', 'h', 'k', 'l']:
                if k in keys_lower:
                    candidates[k] = np.array(data.data[keys_lower[k]])
            
            # Counts
            if 'counts' in keys_lower:
                vz = np.array(data.data[keys_lower['counts']])
            elif 'detector' in keys_lower:
                vz = np.array(data.data[keys_lower['detector']])
            elif 'detector_corrected' in keys_lower:
                vz = np.array(data.data[keys_lower['detector_corrected']])
            
            if vz is None:
                continue
                
            # Store candidates to analyze variance later
            # For now, let's just dump the candidates into a list structure
            # But we need to align them.
            
            # If we haven't picked axes yet, wait until we have all data?
            # No, that consumes memory. 
            # But we need to know what to append to x_list.
            
            # Let's append a dict of arrays
            rec = {'z': vz}
            for k, v in candidates.items():
                rec[k] = v
            
            # Check length
            l = len(vz)
            valid = True
            for k, v in rec.items():
                if len(v) != l:
                    valid = False
            
            if valid:
                x_list.append(rec)
                
        except Exception as e:
            # print(f"Failed to read {fpath}: {e}")
            pass
            
    if not x_list:
        print("No valid data found.")
        return

    # Combine
    combined = {}
    keys = x_list[0].keys()
    for k in keys:
        try:
            combined[k] = np.concatenate([item[k] for item in x_list])
        except KeyError:
            pass # Ignore if some files miss columns (bad)
            
    Z = combined['z']
    
    # Identify X and Y axes
    # Criteria: significant variance
    variances = []
    for k in keys:
        if k == 'z': continue
        v = combined[k]
        rng = v.max() - v.min()
        if rng > 1e-4: # Some threshold
            variances.append((k, rng))
            
    # Sort by name priority? 
    # Qx, Qy, Qz > A3, A4 > H, K, L?
    # Actually Qx, Qy, Qz usually map to H, K, L in some contexts, but let's stick to what's found.
    # We expect exactly 2 axes for a 2D mesh.
    
    variances.sort(key=lambda x: x[1], reverse=True)
    
    if len(variances) < 2:
        print("Less than 2 varying axes found. Cannot plot mesh.")
        return
        
    # Pick top 2? 
    # Warning: Qx, Qy, Qz might all vary if scanning along a diagonal?
    # But usually a mesh is defined by 2 independent scan directions.
    # If scanning (1,1,0) vs (0,0,1), then H and K vary together. 
    # If we find H, K, L varying, we might check correlation.
    
    # Simple approach: Pick the two with largest range? Or standard pairs.
    # Standard pairs: (Qx, Qy), (Qx, Qz), (Qy, Qz), (A3, A4), (H, L), (H, K), (K, L)
    
    axes_found = [v[0] for v in variances]
    print(f"Varying axes candidates: {axes_found}")
    
    xaxis = axes_found[0]
    yaxis = axes_found[1]
    
    # Check for preferred pairs
    preferred_pairs = [
        {'qx', 'qy'}, {'qx', 'qz'}, {'qy', 'qz'},
        {'h', 'k'}, {'h', 'l'}, {'k', 'l'},
        {'a3', 'a4'}
    ]
    
    # Try to find a set in axes_found that matches a preferred pair
    found_pair = False
    for pair in preferred_pairs:
        current_vars = set(axes_found)
        if pair.issubset(current_vars):
            # Use this pair
            lst = list(pair)
            # Sort them? H before K before L?
            # Qx before Qy before Qz?
            # A3 before A4?
            ordering = {'h':1, 'k':2, 'l':3, 'qx':1, 'qy':2, 'qz':3, 'a3':1, 'a4':2}
            lst.sort(key=lambda x: ordering.get(x, 99))
            xaxis = lst[0]
            yaxis = lst[1]
            found_pair = True
            break
            
    xlabel = xaxis
    ylabel = yaxis
    X = combined[xaxis]
    Y = combined[yaxis]
    
    print(f"Plotting {xlabel} vs {ylabel}")
    
    plt.figure(figsize=(10, 8))
    
    # Use Triangulation for rendering
    # Filter duplicates points if any (triangulation fails with duplicates)
    # A simple way to filter is rounding?
    
    # Stack
    XY = np.vstack((X, Y)).T
    # Unique
    XY_unique, indices = np.unique(XY.round(decimals=5), axis=0, return_index=True)
    X_u = XY_unique[:,0]
    Y_u = XY_unique[:,1]
    Z_u = Z[indices]
    
    try:
        triang = mtri.Triangulation(X_u, Y_u)
        
        # Calculate aspect ratio
        x_range = X_u.max() - X_u.min()
        y_range = Y_u.max() - Y_u.min()
        
        # tripcolor
        plt.tripcolor(triang, Z_u, shading='gouraud', cmap='jet')
        # Alternatively tricontourf
        # plt.tricontourf(triang, Z_u, 15, cmap='jet')
        
    except Exception as e:
        print(f"Triangulation failed: {e}. Falling back to scatter.")
        plt.scatter(X, Y, c=Z, s=20, cmap='jet', marker='s')

    plt.colorbar(label='Counts')
    plt.xlabel(xlabel.upper())
    plt.ylabel(ylabel.upper())
    plt.title(f'Mesh Plot')
    
    plt.savefig(output_file)
    plt.close()
    print(f"Plot saved to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: plot_mesh.py <output_file> <input_files...>")
        sys.exit(1)
        
    output = sys.argv[1]
    files = sys.argv[2:]
    
    plot_mesh(files, output)
