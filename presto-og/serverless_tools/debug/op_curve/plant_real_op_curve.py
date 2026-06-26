import argparse
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import pandas as pd


def plot_plan_dop_time(csv_path: str, plan_id: int, save_path: Optional[str] = None) -> pd.DataFrame:
    # 兼容你当前数据的分隔符（看起来是 ';'）
    df = pd.read_csv(csv_path, sep=';')

    required_cols = {"plan_id", "dop", "execution_time"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"CSV 缺少必要列: {missing}，当前列为: {list(df.columns)}")

    # 数值清洗
    df["plan_id"] = pd.to_numeric(df["plan_id"], errors="coerce")
    df["dop"] = pd.to_numeric(df["dop"], errors="coerce")
    df["execution_time"] = pd.to_numeric(df["execution_time"], errors="coerce")

    sub = df[df["plan_id"] == plan_id].copy()
    if sub.empty:
        raise ValueError(f"没有找到 plan_id={plan_id} 的数据")



    # ----------------- 打印平均之前的数据（原始组内所有时间）-----------------
    print(f"\n===== Plan {plan_id} : 平均之前的原始数据（按 DOP 分组）=====")
    for dop_val, group in sub.groupby("dop", sort=True):
        times = group["execution_time"].tolist()
        print(f"DOP = {dop_val} : 所有测量值 -> {times}")

    agg = (
        sub.groupby("dop", as_index=False)["execution_time"]
        .mean()
        .sort_values("dop")
    )

    print("\n===== 平均之后的聚合结果 =====")
    print(agg.to_string(index=False))

    plt.figure(figsize=(8, 5))
    plt.plot(agg["dop"], agg["execution_time"], marker="o", linewidth=2)
    plt.title(f"Plan {plan_id}: Avg Execution Time vs DOP")
    plt.xlabel("DOP")
    plt.ylabel("Average Execution Time")
    plt.grid(True, linestyle="--", alpha=0.4)
    plt.tight_layout()

    if save_path:
        out = Path(save_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(out, dpi=150)
        print(f"图已保存到: {out}")
    else:
        plt.show()

    return agg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="绘制指定 plan_id 在不同 dop 下的平均 execution_time 曲线"
    )
    parser.add_argument(
        "--csv-path",
        default="./Q14/q14plan_info.csv",
        help="plan_info CSV 文件路径",
    )
    parser.add_argument("--plan-id", type=int, required=True, help="要绘图的 plan_id")
    parser.add_argument(
        "--save-path",
        default=None,
        help="图片保存路径；不传则直接弹窗显示",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    agg = plot_plan_dop_time(args.csv_path, args.plan_id, args.save_path)
    print("\n各 DOP 平均 execution_time:")
    print(agg.to_string(index=False))


if __name__ == "__main__":
    main()
