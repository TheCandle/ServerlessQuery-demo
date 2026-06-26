#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path


def load_plan_info(plan_info_path: Path):
    """
    Build lookup:
      (query_id, plan_id) -> (query_num, stage_id, pipeline_id)
    plan_info.csv is semicolon-separated.
    """
    lookup = {}
    with plan_info_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            query_num = row.get("query_num")
            query_id = row.get("query_id")
            plan_id = row.get("plan_id")
            stage_id = row.get("stage_id")
            pipeline_id = row.get("pipeline_id")
            if query_id is None or plan_id is None:
                continue
            lookup[(str(query_id), str(plan_id))] = (query_num, stage_id, pipeline_id)
    return lookup


def extract_rows(data: dict, plan_lookup: dict):
    rows = []
    for query in data.get("queries", []):
        query_id = query.get("query_id")
        if query_id is None:
            continue
        query_id_str = str(query_id)

        for tb in query.get("thread_blocks", []):
            thread_block_id = tb.get("thread_block_id")

            # thread_block does not equal plan_id.
            # We pick one operator inside this thread_block and use its plan_id to locate
            # stage_id / pipeline_id in plan_info.csv.
            operators = tb.get("operators", []) or []
            picked_plan_id = None
            has_local_merge = False
            has_nested_loop_join_build = False
            has_enforce_single_row = False
            for op in operators:
                plan_id = op.get("plan_id")
                if plan_id is not None and picked_plan_id is None:
                    picked_plan_id = str(plan_id)

                # If any operator in this pipeline/thread_block is one of the
                # special operators below, force the pipeline DOP to 1.
                op_name = str(
                    op.get("operator_name")
                    or op.get("name")
                    or op.get("operator_type")
                    or ""
                )
                if "LocalMerge" in op_name:
                    has_local_merge = True
                if "NestedLoopJoinBuild" in op_name:
                    has_nested_loop_join_build = True
                if "EnforceSingleRow" in op_name:
                    has_enforce_single_row = True

            output_query_id = query_id
            stage_id, pipeline_id = (None, None)
            if picked_plan_id is not None:
                output_query_id, stage_id, pipeline_id = plan_lookup.get(
                    (query_id_str, picked_plan_id),
                    (query_id, None, None),
                )

            force_single_dop = (
                has_local_merge
                or has_nested_loop_join_build
                or has_enforce_single_row
            )
            effective_dop = 1 if force_single_dop else tb.get("optimal_dop")

            rows.append(
                {
                    "query_id": output_query_id,
                    "thread_block_id": thread_block_id,
                    "stage_id": stage_id,
                    "pipeline_id": pipeline_id,
                    "optimal_dop": effective_dop,
                }
            )
    return rows


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Extract query_id, thread_block_id, optimal_dop from "
            "pipeline_optimization.json, and enrich with query_num, stage_id/pipeline_id "
            "from plan_info.csv by (query_id, operator.plan_id in each thread_block)."
        )
    )
    parser.add_argument(
        "-i",
        "--input",
        default="output/tpch/optimization_results/pipeline_optimization.json",
        help="Path to input JSON file",
    )
    parser.add_argument(
        "-p",
        "--plan-info",
        default="data_kunpeng/tpch_output_22/plan_info.csv",
        help="Path to plan_info.csv (semicolon-separated)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="output/tpch/optimization_results/stage_threadblock_optimal_dop.csv",
        help="Path to output CSV file",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    plan_info_path = Path(args.plan_info)
    output_path = Path(args.output)

    with input_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    plan_lookup = load_plan_info(plan_info_path)
    rows = extract_rows(data, plan_lookup)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "query_id",
                "thread_block_id",
                "stage_id",
                "pipeline_id",
                "optimal_dop",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    missing = sum(1 for r in rows if r["stage_id"] is None or r["pipeline_id"] is None)
    print(f"Extracted {len(rows)} rows -> {output_path}")
    if missing:
        print(f"Warning: {missing} rows could not be matched in {plan_info_path}")


if __name__ == "__main__":
    main()
