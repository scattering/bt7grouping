"""Command-line interface for bt7grouping."""

import argparse
import sys

from .grouper import scan_files, group_records, print_groups, GroupingConfig


def main():
    """Main entry point for the bt7group command."""
    parser = argparse.ArgumentParser(
        description="Group BT-7 triple-axis spectrometer scan files"
    )
    parser.add_argument(
        "directories",
        nargs="+",
        help="Directories to scan for BT-7 files"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show verbose output including file lists"
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Don't scan subdirectories"
    )
    parser.add_argument(
        "--q-tolerance",
        type=float,
        default=0.1,
        help="Q-space tolerance for grouping (default: 0.1 rlu)"
    )
    parser.add_argument(
        "--no-experiment-grouping",
        action="store_true",
        help="Don't group by experiment ID"
    )
    parser.add_argument(
        "--include-alignment",
        action="store_true",
        help="Don't separate alignment scans from measurements"
    )

    args = parser.parse_args()

    # Configure grouping
    config = GroupingConfig(
        q_tolerance=args.q_tolerance,
        group_by_experiment=not args.no_experiment_grouping,
        separate_alignment=not args.include_alignment,
    )

    # Scan files
    print(f"Scanning {len(args.directories)} directories...")
    records = scan_files(
        args.directories,
        recursive=not args.no_recursive
    )
    print(f"Found {len(records)} data files")

    if not records:
        print("No BT-7 files found.")
        sys.exit(0)

    # Group records
    print("Grouping scans...")
    groups = group_records(records, config=config)

    # Print results
    print_groups(groups, verbose=args.verbose)


if __name__ == "__main__":
    main()
