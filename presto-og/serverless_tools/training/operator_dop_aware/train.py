import os
import sys
import time
import pandas as pd
import torch

# import dop_model
from . import model as dop_model
from utils import propagate_estimates_in_dataframe

# 将项目根目录添加到 sys.path
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# import utils
from utils import feature_engineering as utils_feat
from utils import get_model_paths
# from ...utils import helpers as utils_help # 如果用到 split_queries 等
# from structure import dop_operators_exec, dop_operators_mem, dop_operator_features, dop_train_epochs, operator_lists
from config.structure_config import dop_operators_exec, dop_operators_mem, dop_operator_features, dop_train_epochs, operator_lists
all_operator_results_exec = []
all_operator_results_mem = []
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

# --- 1. 修改 process_and_train_curve 函数定义，增加 use_estimates 参数 ---
def process_and_train_curve(
    train_data,
    test_data,
    operator,
    test_size=0.2,
    epochs=100,
    lr=0.001,
    use_estimates=False,
    onnx_model_dir: str = None,
):
    """
    数据加载、处理和训练执行时间和内存预测的曲线拟合模型。

    Parameters:
    - csv_path_pattern: str, glob 模式，用于找到 plan_info.csv 文件
    - operator: str, 操作符类型，用于筛选数据
    - output_prefix: str, 用于保存模型的前缀
    - train_queries: list of int, 用于训练的查询 ID
    - test_queries: list of int, 用于测试的查询 ID
    - test_size: float, 测试集比例（仅用于内部划分）
    - epochs: int, 训练轮数
    - lr: float, 学习率

    Returns:
    - results: dict, 包含执行时间和内存模型及评估结果
    """
    # 使用算子配置中的特征（exec+mem并集）进行数据准备，避免只截取旧的两列特征
    features_exec = dop_operator_features[operator]['exec']
    features_mem = dop_operator_features[operator]['mem']
    feature_columns = sorted(set(features_exec + features_mem))

    X_train, X_test, y_train, y_test, group_train, group_test = utils_feat.prepare_data(
        train_data=train_data,
        test_data = test_data,
        operator=operator,
        feature_columns=feature_columns,
        target_columns=['execution_time', 'peak_mem', 'dop'],
        use_estimates=use_estimates, # <-- 传递开关
        return_group_cols=True,
    )
    # ==================== 新增的健壮性检查 ====================
    if X_train.empty or y_train.empty:
        print(f"警告: 算子 '{operator}' 没有有效的训练数据，将跳过此算子的训练。")
        return # 直接从函数返回，不执行后续操作
    # ==========================================================
    # 提取目标列
    y_train_exec = y_train['execution_time']  # 提取 execution_time 列
    y_test_exec = y_test['execution_time']    # 提取 execution_time 列
    y_train_mem = y_train['peak_mem']         # 提取 peak_mem 列
    y_test_mem = y_test['peak_mem']           # 提取 peak_mem 列
    dop_train = y_train['dop']                # 提取 dop 列
    dop_test = y_test['dop']                  # 提取 dop 列
    # features_exec / features_mem 已在前面基于配置获取

    # 转换为 PyTorch 张量
    X_train_exec_tensor = torch.tensor(X_train[features_exec].values, dtype=torch.float32)
    X_test_exec_tensor = torch.tensor(X_test[features_exec].values, dtype=torch.float32)
    X_train_mem_tensor = torch.tensor(X_train[features_mem].values, dtype=torch.float32)
    X_test_mem_tensor = torch.tensor(X_test[features_mem].values, dtype=torch.float32)
    y_train_exec_tensor = torch.tensor(y_train_exec.values, dtype=torch.float32)
    y_test_exec_tensor = torch.tensor(y_test_exec.values, dtype=torch.float32)
    y_train_mem_tensor = torch.tensor(y_train_mem.values, dtype=torch.float32)
    y_test_mem_tensor = torch.tensor(y_test_mem.values, dtype=torch.float32)
    dop_train_tensor = torch.tensor(dop_train.values, dtype=torch.float32)
    dop_test_tensor = torch.tensor(dop_test.values, dtype=torch.float32)
    group_train_query_tensor = torch.tensor(group_train['query_num'].values, dtype=torch.int64)
    group_train_plan_tensor = torch.tensor(group_train['plan_id'].values, dtype=torch.int64)
    group_train_round_tensor = torch.tensor(group_train['round_num'].values, dtype=torch.int64)

    # Record the start time for training
    start_train_time = time.time()

    # Check if the operator exists in the mapping
    start_train_time_exec = time.time()
    results_exec = None
    results_mem = None
    if operator in dop_operators_exec:
        # Call the corresponding training function dynamically
        results_exec = train_one_operator_exec(
            X_train_exec=X_train_exec_tensor, 
            X_test_exec=X_test_exec_tensor,
            y_train_exec=y_train_exec_tensor,  # 使用提取的 execution_time
            y_test_exec=y_test_exec_tensor,    # 使用提取的 execution_time
            dop_train=dop_train_tensor,       # 使用提取的 dop
            dop_test=dop_test_tensor,         # 使用提取的 dop
            group_query_train=group_train_query_tensor,
            group_plan_train=group_train_plan_tensor,
            group_round_train=group_train_round_tensor,
            operator=operator,
            onnx_model_dir=onnx_model_dir,
        )
    start_train_time_mem = time.time()    
    # 当前先只关注 execution time，暂时跳过 memory 模型训练
    if False and operator in dop_operators_mem:
        # Call the corresponding training function dynamically
        results_mem = train_one_operator_mem(
            X_train_mem=X_train_mem_tensor,
            X_test_mem=X_test_mem_tensor,
            y_train_mem=y_train_mem_tensor,   # 使用提取的 peak_mem
            y_test_mem=y_test_mem_tensor,     # 使用提取的 peak_mem
            dop_train=dop_train_tensor,       # 使用提取的 dop
            dop_test=dop_test_tensor,         # 使用提取的 dop
            operator=operator,
            onnx_model_dir=onnx_model_dir,
        )
    
       # Calculate the training time
    training_time_exec = time.time() - start_train_time_exec
    training_time_mem = time.time() - start_train_time_mem
    if results_exec is not None:
        # Extract the performance metrics for execution time and memory
        performance_exec = results_exec["performance_exec"]  # Directly the MAE_error
        native_time_exec = results_exec["native_time_exec"]
        onnx_time_exec = results_exec["onnx_time_exec"]
        compare_exec = results_exec["comparisons_exec"]
        compare_exec['Comparison Type'] = 'Execution Time'

        eval_dir = os.path.join(PROJECT_ROOT, "output", "evaluations", "dop_aware", "operator_comparisons")
        os.makedirs(eval_dir, exist_ok=True) # 确保目录存在
        compare_exec.to_csv(os.path.join(eval_dir, f"{operator}_combined_comparison_exec.csv"), index=False)
        # compare_exec.to_csv(f"tmp_result/{operator}_combined_comparison_exec.csv", index=False)
        data_to_save_exec = {
            'Operator': [operator],
            'Training Time (s)': [training_time_exec],
            'Execution Time MAE': [performance_exec['MAE_error']],
            'Execution Time Q-error': [performance_exec['Q_error']],
            'Average Execution Time': [performance_exec['average_actual_value']],
            'Native Execution Time (s)': [native_time_exec],
            'ONNX Execution Time (s)': [onnx_time_exec],
        }
        all_operator_results_exec.append(pd.DataFrame(data_to_save_exec))
    if results_mem is not None:
        performance_mem = results_mem["performance_mem"]    # Directly the MAE_error
        native_time_mem = results_mem["native_time_mem"]
        onnx_time_mem = results_mem["onnx_time_mem"]
        compare_mem = results_mem["comparisons_mem"]
        compare_mem['Comparison Type'] = 'Memory'
        eval_dir = os.path.join(PROJECT_ROOT, "output", "evaluations", "dop_aware", "operator_comparisons")
        os.makedirs(eval_dir, exist_ok=True) # 确保目录存在
        compare_mem.to_csv(os.path.join(eval_dir, f"{operator}_combined_comparison_mem.csv"), index=False)
        # compare_mem.to_csv(f"tmp_result/{operator}_combined_comparison_mem.csv", index=False)
        data_to_save_mem = {
            'Operator': [operator],
            'Training Time (s)': [training_time_mem],
            # TO ASK: 这里的 'Execution Time MAE' 和 'Execution Time Q-error' 是不是应该改成 'Memory MAE' 和 'Memory Q-error'？因为这是内存模型的结果。
            'Execution Time MAE': [performance_mem['MAE_error']],
            'Execution Time Q-error': [performance_mem['Q_error']],
            'Average Execution Time': [performance_mem['average_actual_value']],
            'Memory MAE': [performance_mem['MAE_error']],
            'Memory Q-error': [performance_mem['Q_error']],
            'Average Memory': [performance_mem['average_actual_value']],
            'Native Memory Time (s)': [native_time_mem],
            'ONNX Memory Time (s)': [onnx_time_mem]
        }
        # Convert to DataFrame and append to the global list
        all_operator_results_mem.append(pd.DataFrame(data_to_save_mem))
    


def evaluate_one_operator_exec(
    models_exec,
    X_test_exec,
    y_test_exec,
    dop_test,
    operator,
    epsilon=1e-2,
    onnx_model_dir: str = None,
):
    """单独执行 exec 评估（不触发训练）。"""
    return dop_model.predict_and_evaluate_exec_curve(
        model=models_exec,
        X_test=X_test_exec,
        y_test=y_test_exec,
        dop_test=dop_test,
        epsilon=epsilon,
        operator=operator,
        suffix="exec",
        onnx_model_dir=onnx_model_dir,
        enable_debug=True,
        debug_sample_count=30,
    )


def train_one_operator_exec(
    X_train_exec,
    X_test_exec,
    y_train_exec,
    y_test_exec,
    dop_train,
    dop_test,
    group_query_train,
    group_plan_train,
    group_round_train,
    operator,
    epsilon=1e-2,
    onnx_model_dir: str = None,
):
     # Separate target variables for execution time and memory

    # ==================== 新增的防御性检查 ====================
    # 检查传入的Tensor第一维度（行数）是否为0
    if X_train_exec.shape[0] == 0:
        print(f"警告: 算子 '{operator}' (exec model) 没有有效的训练样本传入，将跳过训练。")
        return None # 返回None，上层调用需要处理这种情况
    # ==========================================================
    # Train exec model with operator-specific hyperparameters
    hard_exec_ops = {
        # 'TableScan',
        # 'LookupJoinOperator',
        # 'OrderBy',
        # 'LocalExchangeSourceOperator',
        'AssignUniqueId',
        'EnforceSingleRow',
        'LocalMerge',
        'Merge',
        'MergeOperator',
        'ExplainAnalyzeOperator',
        'TaskOutputOperator',
        'OrderBy',
        'CallbackSink',
        'Aggregation',
        'PartialAggregation',
        'NestedLoopJoinBuild',
        'NestedLoopJoinProbe',
        'HashBuilderOperator',
        'LookupJoinOperator',
        'LocalExchangeSinkOperator',
    }
    very_hard_exec_ops = {
        # 'Aggregation',
        # 'PartialAggregation',
        # 'HashBuilderOperator',
    }

    if operator in very_hard_exec_ops:
        exec_lr = 3e-5
        exec_batch_size = 32
        # exec_lr = 1e-4
        # exec_batch_size = 16
    elif operator in hard_exec_ops:
        exec_lr = 1e-3
        exec_batch_size = 32
    else:
        # exec_lr = 3e-5
        exec_lr = 1e-3
        exec_batch_size = 32
        # exec_lr = 5e-4
        # exec_batch_size = 32

    print(f"[Exec Hyperparams] operator={operator}, lr={exec_lr}, batch_size={exec_batch_size}, epochs={dop_train_epochs[operator]['exec']}")
    models_exec, training_times_exec = dop_model.train_exec_curve_model(
        X_train_exec,
        y_train_exec,
        dop_train,
        group_query_train,
        group_plan_train,
        group_round_train,
        batch_size=exec_batch_size,
        epochs=dop_train_epochs[operator]['exec'],
        lr=exec_lr,
    )
    # Predict and evaluate execution time models
    results_exec = evaluate_one_operator_exec(
        models_exec=models_exec,
        X_test_exec=X_test_exec,
        y_test_exec=y_test_exec,
        dop_test=dop_test,
        operator=operator,
        epsilon=epsilon,
        onnx_model_dir=onnx_model_dir,
    )


    # Combine results
    return {
        "models_exec": models_exec,
        "performance_exec": results_exec["metrics"],
        "training_times_exec": training_times_exec,
        "comparisons_exec": results_exec["comparisons"],
        "native_time_exec": results_exec["native_time"],
        "onnx_time_exec": results_exec["onnx_time"],
}


def evaluate_one_operator_exec(
    models_exec,
    X_test_exec,
    y_test_exec,
    dop_test,
    operator,
    epsilon=1e-2,
    onnx_model_dir: str = None,
):
    """离线执行 exec 模型评估（不触发训练）。"""
    return dop_model.predict_and_evaluate_exec_curve(
        model=models_exec,
        X_test=X_test_exec,
        y_test=y_test_exec,
        dop_test=dop_test,
        epsilon=epsilon,
        operator=operator,
        suffix="exec",
        onnx_model_dir=onnx_model_dir,
        enable_debug=True,
        debug_sample_count=30,
    )


def evaluate_one_operator_exec_onnx(
    onnx_path,
    X_test_exec,
    y_test_exec,
    dop_test,
    epsilon=1e-2,
):
    """离线评估 ONNX exec 模型（完全不依赖训练阶段对象）。"""
    import numpy as np
    import onnxruntime as ort

    if X_test_exec.shape[0] == 0 or y_test_exec.numel() == 0 or dop_test.numel() == 0:
        print("[WARN][eval_exec_onnx] empty test set, skip evaluation.")
        return {
            "metrics": {
                "MAE_error": None,
                "Q_error": None,
                "average_actual_value": None,
            },
            "comparisons": pd.DataFrame(columns=["Actual", "Predicted_ONNX", "Difference_ONNX"]),
            "onnx_time": None,
            "skipped": True,
            "skip_reason": "empty_test_set",
        }

    session = ort.InferenceSession(onnx_path)
    input_name = session.get_inputs()[0].name

    start_time = time.time()
    pred_params = session.run(None, {input_name: X_test_exec.numpy().astype(np.float32)})[0]
    onnx_time = time.time() - start_time

    pred_params_t = torch.from_numpy(pred_params)
    a = pred_params_t[:, 0]
    b = pred_params_t[:, 1]
    c = pred_params_t[:, 2]
    d = pred_params_t[:, 3]
    e = pred_params_t[:, 4]

    dop_safe = torch.clamp(dop_test, min=epsilon)
    predictions_onnx = torch.relu(b / (dop_safe ** a) + c * (dop_safe ** d) + e)
    predictions_onnx = torch.clamp(predictions_onnx, 1e-2)

    mae_onnx = torch.mean(torch.abs(y_test_exec - predictions_onnx))
    q_error = torch.mean(torch.maximum(y_test_exec / predictions_onnx, predictions_onnx / y_test_exec) - 1)
    avg_actual_value = torch.mean(y_test_exec)

    comparisons = pd.DataFrame({
        "Actual": y_test_exec,
        "Predicted_ONNX": predictions_onnx,
        "Difference_ONNX": y_test_exec - predictions_onnx,
    })

    print(f"ONNX model prediction time: {onnx_time:.6f} seconds")

    return {
        "metrics": {
            "MAE_error": mae_onnx,
            "Q_error": q_error,
            "average_actual_value": avg_actual_value,
        },
        "comparisons": comparisons,
        "onnx_time": onnx_time,
        "skipped": False,
    }

def evaluate_one_operator_exec_offline(
    test_data,
    operator,
    dataset,
    train_mode,
    use_estimates=False,
    epsilon=1e-2,
):
    """完全离线评估：自动准备特征并加载 ONNX 模型进行 exec 评估。"""
    if operator not in dop_operator_features:
        raise ValueError(f"未知算子: {operator}")

    test_data_local = test_data.copy()
    if use_estimates:
        print("!!! 离线评估模拟模式：正在对测试数据进行基数传播预处理... !!!")
        test_data_local = propagate_estimates_in_dataframe(test_data_local)

    features_exec = dop_operator_features[operator]["exec"]
    features_mem = dop_operator_features[operator]["mem"]
    feature_columns = sorted(set(features_exec + features_mem))

    # 仅用 test_data 进行 prepare，train_data 传空同结构 DataFrame
    X_dummy, X_test, y_dummy, y_test, group_dummy, group_test = utils_feat.prepare_data(
        train_data=test_data_local.iloc[0:0].copy(),
        test_data=test_data_local,
        operator=operator,
        feature_columns=feature_columns,
        target_columns=["execution_time", "peak_mem", "dop"],
        use_estimates=use_estimates,
        return_group_cols=True,
    )

    _ = X_dummy, y_dummy, group_dummy  # 占位，避免未使用警告

    if X_test.empty or y_test.empty:
        print(f"警告: 算子 '{operator}' 在测试数据中没有有效样本。")
        return {
            "metrics": {
                "MAE_error": None,
                "Q_error": None,
                "average_actual_value": None,
            },
            "comparisons": pd.DataFrame(columns=["Actual", "Predicted_ONNX", "Difference_ONNX"]),
            "onnx_time": None,
            "skipped": True,
            "skip_reason": "empty_test_set",
        }

    X_test_exec_tensor = torch.tensor(X_test[features_exec].values, dtype=torch.float32)
    y_test_exec_tensor = torch.tensor(y_test["execution_time"].values, dtype=torch.float32)
    dop_test_tensor = torch.tensor(y_test["dop"].values, dtype=torch.float32)

    model_dir = get_model_paths(dataset, train_mode, "dop_aware")["model_dir"]
    operator_name = operator.replace(" ", "_")
    onnx_path = os.path.join(model_dir, operator, f"exec_{operator_name}.onnx")

    if not os.path.exists(onnx_path):
        raise FileNotFoundError(f"未找到 ONNX 模型: {onnx_path}")

    return evaluate_one_operator_exec_onnx(
        onnx_path=onnx_path,
        X_test_exec=X_test_exec_tensor,
        y_test_exec=y_test_exec_tensor,
        dop_test=dop_test_tensor,
        epsilon=epsilon,
    )


def evaluate_all_operators_exec_offline(
    test_data,
    dataset,
    train_mode,
    use_estimates=False,
    epsilon=1e-2,
    save_per_operator_comparisons=True,
):
    """批量离线评估所有 exec 算子，并输出汇总 CSV。"""
    results_rows = []

    eval_base_dir = os.path.join(PROJECT_ROOT, "output", "evaluations", "dop_aware")
    compare_dir = os.path.join(eval_base_dir, "operator_comparisons")
    os.makedirs(eval_base_dir, exist_ok=True)
    if save_per_operator_comparisons:
        os.makedirs(compare_dir, exist_ok=True)

    operators_in_test = set(test_data["operator_type"].unique()) if "operator_type" in test_data.columns else set()

    for operator in operator_lists:
        if operator not in dop_operators_exec:
            continue
        if operator not in operators_in_test:
            print(f"信息: 算子 '{operator}' 在测试数据中不存在，跳过离线评估。")
            continue

        print(f"\n[Offline Eval] operator: {operator}")
        try:
            op_result = evaluate_one_operator_exec_offline(
                test_data=test_data,
                operator=operator,
                dataset=dataset,
                train_mode=train_mode,
                use_estimates=use_estimates,
                epsilon=epsilon,
            )
        except FileNotFoundError as e:
            print(f"警告: {e}，跳过。")
            continue
        except Exception as e:
            print(f"警告: 算子 '{operator}' 离线评估失败: {e}")
            continue

        metrics = op_result.get("metrics", {})
        comparisons = op_result.get("comparisons", pd.DataFrame())

        if save_per_operator_comparisons and isinstance(comparisons, pd.DataFrame) and not comparisons.empty:
            comparisons.to_csv(os.path.join(compare_dir, f"{operator}_combined_comparison_exec.csv"), index=False)

        results_rows.append({
            "Operator": operator,
            "Execution Time MAE": metrics.get("MAE_error"),
            "Execution Time Q-error": metrics.get("Q_error"),
            "Average Execution Time": metrics.get("average_actual_value"),
            "ONNX Execution Time (s)": op_result.get("onnx_time"),
        })

    final_results_df_exec = pd.DataFrame(results_rows)
    final_csv_file_path_exec = os.path.join(eval_base_dir, "all_operators_performance_exec.csv")
    final_results_df_exec.to_csv(final_csv_file_path_exec, index=False)
    print(f"离线评估汇总已保存: {final_csv_file_path_exec}")

    return final_results_df_exec


def train_one_operator_mem(
    X_train_mem,
    X_test_mem,
    y_train_mem,
    y_test_mem,
    dop_train,
    dop_test,
    operator,
    epsilon=1e-2,
    onnx_model_dir: str = None,
):
     # Separate target variables for execution time and memory

    # Train models for execution time and memory separately
    models_mem, training_times_mem = dop_model.train_mem_curve_model(X_train_mem, y_train_mem, dop_train, epochs=dop_train_epochs[operator]['mem'])


    # Predict and evaluate memory models
    results_mem = dop_model.predict_and_evaluate_mem_curve(
        model=models_mem,
        X_test=X_test_mem,
        y_test=y_test_mem,
        dop_test = dop_test,
        epsilon=epsilon,
        operator=operator,
        suffix="mem",
        onnx_model_dir=onnx_model_dir,
    )

    # Combine results
    return {
        "models_mem": models_mem,
        "performance_mem": results_mem["metrics"],
        "training_times_mem": training_times_mem,
        "comparisons_mem": results_mem["comparisons"],
        "native_time_mem": results_mem["native_time"],
        "onnx_time_mem": results_mem["onnx_time"]
    }
    
    
# --- 3. 修改 train_all_operators 函数定义，增加 use_estimates 参数 ---
def train_all_operators(
    train_data,
    test_data,
    total_queries,
    train_ratio=0.8,
    use_estimates=False,
    dataset: str = None,
    train_mode: str = None,
):
    # 分割查询
    # train_queries, test_queries = utils.split_queries(total_queries, train_ratio)
    
    # --- 新增的基数传播步骤 ---
    if use_estimates:
        print("!!! 训练模拟模式：正在对训练和测试数据进行基数传播预处理... !!!")
        train_data = propagate_estimates_in_dataframe(train_data)
        test_data = propagate_estimates_in_dataframe(test_data)
    # --- 结束新增步骤 ---
    # Resolve ONNX output directory for per-operator models.
    # ONNXModelManager expects: output/{dataset}/models/{train_mode}/operator_dop_aware/{operator}/exec_*.onnx
    onnx_model_dir = None
    if dataset and train_mode:
        onnx_model_dir = get_model_paths(dataset, train_mode, 'dop_aware')['model_dir']

    # Train each operator and collect the results
    for operator in operator_lists:
        # --- 新增：在循环开始时进行存在性检查 ---
        if operator not in train_data['operator_type'].unique():
            print(f"信息: 算子 '{operator}' 在提供的训练数据中不存在，将完全跳过此算子。")
            continue
        # --- 检查结束 ---
        if operator in dop_operators_exec or operator in dop_operators_mem:
            print(f"\nTraining operator: {operator}")
            process_and_train_curve(
                train_data=train_data,
                test_data=test_data,
                operator=operator,
                use_estimates=use_estimates, # <-- pass use_estimates
                onnx_model_dir=onnx_model_dir,
            )
    
    # After processing all operators, combine all results into one DataFrame
    # final_results_df_exec = pd.concat(all_operator_results_exec, ignore_index=True)
    if all_operator_results_exec:
        final_results_df_exec = pd.concat(all_operator_results_exec, ignore_index=True)
    else:
        print("没有数据可以拼接！")
        # 处理列表为空的情况
        final_results_df_exec = pd.DataFrame()  # 或者返回 None，根据业务需求决定

    # Save the final combined DataFrame to a single CSV file
    # final_csv_file_path_exec = "tmp_result/all_operators_performance_results_exec.csv"
    eval_base_dir = os.path.join(PROJECT_ROOT, "output", "evaluations", "dop_aware")
    os.makedirs(eval_base_dir, exist_ok=True)
    final_csv_file_path_exec = os.path.join(eval_base_dir, "all_operators_performance_exec.csv")
    final_results_df_exec.to_csv(final_csv_file_path_exec, index=False)
    # final_results_df_mem = pd.concat(all_operator_results_mem, ignore_index=True)
    final_csv_file_path_mem = os.path.join(eval_base_dir, "all_operators_performance_mem.csv")
    # 当前仅训练 exec；mem 结果文件输出为空表保持兼容
    pd.DataFrame().to_csv(final_csv_file_path_mem, index=False)

    print(f"All operator exec results have been saved to {final_csv_file_path_exec}")