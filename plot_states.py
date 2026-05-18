#!/usr/bin/env python3
"""Plot state coverage nodes and edges from states.csv."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def _require_plot_deps():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as err:
        raise SystemExit(
            "plot_states.py requires matplotlib. "
            "Install it first, for example: uv add matplotlib"
        ) from err

    return plt


def _read_rows(csv_file):
    with Path(csv_file).open(mode="r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])

        data_type_col = "data_type"
        if data_type_col not in fieldnames and "state_type" in fieldnames:
            data_type_col = "state_type"

        required = {"subject", "fuzzer", data_type_col, "time", "data"}
        missing = required.difference(fieldnames)
        if missing:
            missing_cols = ", ".join(sorted(missing))
            raise ValueError(f"states csv is missing columns: {missing_cols}")

        rows = []
        for row in reader:
            try:
                rows.append(
                    {
                        "subject": row["subject"],
                        "fuzzer": row["fuzzer"],
                        "data_type": row[data_type_col],
                        "run": int(row.get("run") or 1),
                        "time": float(row["time"]),
                        "data": float(row["data"]),
                    }
                )
            except (TypeError, ValueError):
                continue

    return rows


def _time_is_absolute_seconds(rows) -> bool:
    if not rows:
        return False

    max_time = max(row["time"] for row in rows)
    return max_time > 10000


def _last_value_at_cutoff(rows, cutoff_min, use_absolute_seconds):
    if not rows:
        return None

    if use_absolute_seconds:
        start = rows[0]["time"]
        candidates = [row for row in rows if row["time"] <= start + cutoff_min * 60]
    else:
        candidates = [row for row in rows if row["time"] <= cutoff_min]

    if not candidates:
        return None

    return candidates[-1]["data"]


def _infer_plot_args(rows):
    subjects = sorted({row["subject"] for row in rows})
    if not subjects:
        raise ValueError("states csv has no usable rows")

    put = subjects[0]
    subject_rows = [row for row in rows if row["subject"] == put]
    fuzzers = sorted({row["fuzzer"] for row in subject_rows})
    runs = max(row["run"] for row in subject_rows)

    uses_absolute_seconds = _time_is_absolute_seconds(subject_rows)
    if uses_absolute_seconds:
        cut_off = int(
            max(
                max(row["time"] for row in subject_rows if row["run"] == run)
                - min(row["time"] for row in subject_rows if row["run"] == run)
                for run in {row["run"] for row in subject_rows}
            )
            // 60
        )
    else:
        cut_off = int(max(row["time"] for row in subject_rows))

    return put, runs, max(cut_off, 1), fuzzers


def build_mean_dataframe(csv_file, put=None, runs=None, cut_off=None, step=1, fuzzers=None):
    rows = _read_rows(csv_file)
    inferred_put, inferred_runs, inferred_cut_off, inferred_fuzzers = _infer_plot_args(rows)
    put = put or inferred_put
    runs = runs or inferred_runs
    cut_off = cut_off or inferred_cut_off
    fuzzers = fuzzers or inferred_fuzzers

    mean_list = []
    for subject in [put]:
        for fuzzer in fuzzers:
            for data_type in ["nodes", "edges"]:
                rows1 = sorted(
                    [
                        row
                        for row in rows
                        if row["subject"] == subject
                        and row["fuzzer"] == fuzzer
                        and row["data_type"] == data_type
                    ],
                    key=lambda row: (row["run"], row["time"]),
                )

                use_absolute_seconds = _time_is_absolute_seconds(rows1)
                mean_list.append(
                    {
                        "subject": subject,
                        "fuzzer": fuzzer,
                        "data_type": data_type,
                        "time": 0,
                        "data": 0.0,
                    }
                )

                for minute in range(step, cut_off + 1, step):
                    total = 0.0
                    run_count = 0

                    for run in range(1, runs + 1):
                        rows2 = [row for row in rows1 if row["run"] == run]
                        value = _last_value_at_cutoff(
                            rows2,
                            minute,
                            use_absolute_seconds,
                        )
                        if value is None:
                            print(f"Issue with run {run}. Skipping")
                            continue

                        total += value
                        run_count += 1

                    mean_list.append(
                        {
                            "subject": subject,
                            "fuzzer": fuzzer,
                            "data_type": data_type,
                            "time": minute,
                            "data": total / max(run_count, 1),
                        }
                    )

    return mean_list


def _plot_data_type(plt, mean_df, plot_fuzzers, data_type, ylabel, out_file):
    fig, ax = plt.subplots(figsize=(10, 4.8))
    fig.suptitle("State coverage analysis")

    for fuzzer in plot_fuzzers:
        grp = [
            row
            for row in mean_df
            if row["fuzzer"] == fuzzer and row["data_type"] == data_type
        ]
        ax.plot(
            [row["time"] for row in grp],
            [row["data"] for row in grp],
            label=fuzzer,
        )

    ax.set_xlabel("Time (in min)")
    ax.set_ylabel(ylabel)
    ax.grid(True)
    ax.legend(loc="upper left")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    plt.savefig(out_file)
    plt.close(fig)


def main(csv_file, output_dir, put=None, runs=None, cut_off=None, step=1, fuzzers=None):
    plt = _require_plot_deps()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    mean_df = build_mean_dataframe(
        csv_file=csv_file,
        put=put,
        runs=runs,
        cut_off=cut_off,
        step=step,
        fuzzers=fuzzers,
    )
    plot_fuzzers = fuzzers or sorted({row["fuzzer"] for row in mean_df})

    print("Saving mean logs into file...")
    mean_file = output_dir / "mean_plot_data.csv"
    with mean_file.open(mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["subject", "fuzzer", "data_type", "time", "data"],
        )
        writer.writeheader()
        writer.writerows(mean_df)

    nodes_file = output_dir / "nodes.png"
    edges_file = output_dir / "edges.png"
    _plot_data_type(plt, mean_df, plot_fuzzers, "nodes", "#nodes", nodes_file)
    _plot_data_type(plt, mean_df, plot_fuzzers, "edges", "#edges", edges_file)
    print(f"Saved {nodes_file}")
    print(f"Saved {edges_file}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Plot state coverage nodes and edges from states.csv."
    )
    parser.add_argument("csv_file", help="Input states CSV file")
    parser.add_argument("output_dir", help="Output directory for nodes.png and edges.png")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(
        csv_file=args.csv_file,
        output_dir=args.output_dir,
    )
