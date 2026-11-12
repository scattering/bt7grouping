import numpy as np
import matplotlib.pyplot as plt
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

def plot_scan(filepath, output_file):
    reader = readncnr3.datareader()
    try:
        data = reader.readbuffer(filepath)
        
        # Identify X axis
        # 1. Check 'varying' in metadata
        varying = data.metadata['count_info'].get('varying')
        
        # 2. Check columns
        keys = list(data.data.keys())
        keys_lower = {k.lower(): k for k in keys}
        
        x_col = None
        x_label = "Index"
        
        if varying:
            # varying might be a list or string
            if isinstance(varying, list):
                v = varying[0]
            else:
                v = varying
            
            # Try to match v with columns
            # v might be "sampleTheta" or "A3"
            # columns might be "A3" or "A3(deg)"
            
            # Simple match
            if v in keys:
                x_col = v
                x_label = v
            elif v.lower() in keys_lower:
                x_col = keys_lower[v.lower()]
                x_label = x_col
            else:
                # Fuzzy match
                for k in keys:
                    if v.lower() in k.lower():
                        x_col = k
                        x_label = k
                        break
        
        # Fallback: Find the column with max variance (normalized?)
        # Or standard columns like 'A3', 'A4', 'Qx'
        if x_col is None:
            # Prioritize standard scan variables
            standards = ['a3', 'a4', 'a2', 'a1', 'qx', 'qy', 'qz', 'temp']
            for s in standards:
                if s in keys_lower:
                    # Check if it actually varies
                    arr = np.array(data.data[keys_lower[s]])
                    if arr.max() - arr.min() > 1e-5:
                        x_col = keys_lower[s]
                        x_label = x_col
                        break
        
        if x_col is None:
            print(f"Could not identify X axis for {filepath}")
            return False

        X = np.array(data.data[x_col])
        
        # Identify Y axis (Counts)
        y_col = None
        if 'counts' in keys_lower:
            y_col = keys_lower['counts']
        elif 'detector' in keys_lower:
            y_col = keys_lower['detector']
        elif 'detector_corrected' in keys_lower:
            y_col = keys_lower['detector_corrected']
            
        if y_col is None:
            print("No counts found.")
            return False
            
        Y = np.array(data.data[y_col])
        Y_err = np.sqrt(Y) # Poisson error approximation
        
        plt.figure(figsize=(8, 6))
        plt.errorbar(X, Y, yerr=Y_err, fmt='o-', capsize=3, label=os.path.basename(filepath))
        plt.xlabel(x_label)
        plt.ylabel(y_col)
        plt.title(f"{os.path.basename(filepath)}")
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.legend()
        
        plt.savefig(output_file)
        plt.close()
        print(f"Plot saved to {output_file}")
        return True
        
    except Exception as e:
        print(f"Failed to plot {filepath}: {e}")
        # traceback.print_exc()
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: plot_scan.py <input_file> <output_file>")
        sys.exit(1)
        
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    plot_scan(input_file, output_file)
