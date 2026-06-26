#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extract stage-level DOP from plan_info and pipeline_optimization.

Output columns:
    query_id,stage_id,dop
"""

import argparse
from pathlib import Path

import pandas as pd


def pick_stage_dop(dops: pd.Series) -> int:
    """
    Pick one DOP for a stage:
    1) highest frequency
    2) if tie, smallest DOP
    """
    counts = dops.value_counts()
    max_count = counts.max()
    candidates = counts[counts == max_count].index.tolist()
    return int(min(candidates))


def extract_stage_dop(plan_info_path: Path, pipeline_path: Path, output_path: Path) -> None:
    plan_df = pd.read_csv(plan_info_path, sep=";")
    pipeline_df = pd.read_csv(pipeline_path)

    required_plan_cols = {"query_id", "plan_id", "stage_id"}
    required_pipeline_cols = {"query_id", "plan_id", "dop"}
    missing_plan = required_plan_cols - set(plan_df.columns)
    missing_pipeline = required_pipeline_cols - set(pipeline_df.columns)
    if missing_plan:
        raise ValueError(f"Missing columns in plan_info: {sorted(missing_plan)}")
    if missing_pipeline:
        raise ValueError(f"Missing columns in pipeline_optimization: {sorted(missing_pipeline)}")

    merged = plan_df.merge(
        pipeline_df[["query_id", "plan_id", "dop"]].rename(columns={"dop": "pipeline_dop"}),
        on=["query_id", "plan_id"],
        how="left",
    )

    # Keep rows with matched DOP only.
    merged = merged[merged["pipeline_dop"].notna()].copy()
    merged["pipeline_dop"] = merged["pipeline_dop"].astype(int)

    stage_dop = (
        merged.groupby(["query_id", "stage_id"], as_index=False)["pipeline_dop"]
        .agg(pick_stage_dop)
        .rename(columns={"pipeline_dop": "dop"})
        .sort_values(["query_id", "stage_id"])
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    stage_dop.to_csv(output_path, index=False)

    print(f"Output: {output_path}")
    print(f"Rows: {len(stage_dop)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract query-stage DOP mapping from plan_info and pipeline optimization CSVs."
    )
    parser.add_argument(
        "--plan-info",
        default="./data_kunpeng/tpch_output_22/plan_info.csv",
        help="Path to plan_info.csv (semicolon-separated).",
    )
    parser.add_argument(
        "--pipeline-optimization",
        default="./output/tpch/optimization_results/pipeline_optimization.csv",
        help="Path to pipeline_optimization.csv (comma-separated).",
    )
    parser.add_argument(
        "--output",
        default="./output/tpch/optimization_results/query_stage_dop.csv",
        help="Output CSV path.",
    )
    args = parser.parse_args()

    extract_stage_dop(
        plan_info_path=Path(args.plan_info),
        pipeline_path=Path(args.pipeline_optimization),
        output_path=Path(args.output),
    )


if __name__ == "__main__":
    main()
