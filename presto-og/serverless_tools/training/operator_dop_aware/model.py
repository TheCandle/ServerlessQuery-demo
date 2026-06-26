import os
import sys
import time
import random
import numpy as np
import pandas as pd
import onnxruntime as ort
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
# 将项目根目录添加到 sys.path
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import utils

# 定义网络模型
class Exec_CurveFitModel(nn.Module):
    def __init__(self, input_dim, min_a=0.05, max_a=2.0, min_b=1e-3, max_b=5e4, min_d=0.2, max_d=1.0, c_scale=5e4, e_scale=5e4):
        super(Exec_CurveFitModel, self).__init__()
        self.bn_input = nn.BatchNorm1d(input_dim)
        self.fc = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.LeakyReLU(negative_slope=0.2),
            nn.Linear(128, 64),
            nn.LeakyReLU(negative_slope=0.2),
            nn.Linear(64, 32),
            nn.LeakyReLU(negative_slope=0.2),
            nn.Linear(32, 5),  # 输出 a, b, c, d, e
        )
        self.min_a = min_a
        self.max_a = max_a
        self.min_b = min_b
        self.max_b = max_b
        self.min_d = min_d
        self.max_d = max_d
        self.c_scale = c_scale
        self.e_scale = e_scale

    def forward(self, x):
        x = self.bn_input(x)
        pred_params = self.fc(x)
        
        # 获取 a, b, c
        # a, b, c, d, e = pred_params[:, 0], pred_params[:, 1], pred_params[:, 2], pred_params[:, 3], pred_params[:, 4]
        # a = torch.sigmoid(pred_params[:, 0]) * (self.max_a - self.min_a) + self.min_a
        # b = self.max_b * torch.sigmoid(pred_params[:, 1]) + self.min_b
        # c = self.c_scale * torch.tanh(pred_params[:, 2])
        # d = torch.sigmoid(pred_params[:, 3]) * (self.max_d - self.min_d) + self.min_d
        # e = self.e_scale * torch.tanh(pred_params[:, 4])
        a = torch.sigmoid(pred_params[:, 0]) * (self.max_a - self.min_a) + self.min_a
        b = self.max_b * torch.sigmoid(pred_params[:, 1]) + self.min_b
        c = pred_params[:, 2]
        d = torch.sigmoid(pred_params[:, 3])
        e = pred_params[:, 4]

        # 返回映射后的参数
        return torch.stack([a, b, c, d, e], dim=1)
    
# 定义网络模型
class Mem_CurveFitModel(nn.Module):
    def __init__(self, input_dim, min_a=0, max_a=1):
        super(Mem_CurveFitModel, self).__init__()
        self.bn_input = nn.BatchNorm1d(input_dim)
        self.fc = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.LeakyReLU(negative_slope=0.2),
            nn.Linear(128, 64),
            nn.LeakyReLU(negative_slope=0.2),
            nn.Linear(64, 32),
            nn.LeakyReLU(negative_slope=0.2),
            nn.Linear(32, 4),  # 输出 a, b, c, d
        )
        self.min_a = min_a
        self.max_a = max_a

    def forward(self, x): 
        x = self.bn_input(x)
        pred_params = self.fc(x)
        
        # 获取 a, b, c
        a, b, c, d = pred_params[:, 0], pred_params[:, 1], pred_params[:, 2], pred_params[:, 3]
        
        # 对 a 应用 Sigmoid 激活函数并映射到 [min_a, max_a]
        a = torch.sigmoid(pred_params[:, 0]) * (self.max_a - self.min_a) + self.min_a
        b = pred_params[:, 1]
        c = pred_params[:, 2]
        d = pred_params[:, 3]

        # 返回映射后的参数
        return torch.stack([a, b, c, d], dim=1)
    
def reset_model(model):
    """重新初始化模型参数"""
    for m in model.modules():
        if isinstance(m, nn.Linear):
            nn.init.kaiming_normal_(m.weight)
            if m.bias is not None:
                nn.init.zeros_(m.bias)
    return model


def set_training_seed(seed: int = 42):
    """Set deterministic seed for reproducible training."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

def curve_exec_loss(
    pred_params,
    dop,
    true_time,
    segment_ids=None,
    epsilon=1e-2,
    alpha=0.5,
    grad_weight=1,
    log_file="loss_debug.log",
    a_floor=0.15,
    b_floor=0.2,
    floor_weight=0.1,
    ce_reg_weight=1e-6,
    rel_denom_floor=1.0,
):
    """
    执行时间曲线损失：点误差 + 梯度匹配误差。

    - 点误差：约束每个样本的预测执行时间
    - 梯度误差：约束相邻 dop 上的曲线斜率趋势与真实曲线一致
    - segment_ids 不为空时，会把一个 batch 里的多条曲线拆开分别计算 loss
    """
    if segment_ids is not None:
        unique_segments = torch.unique(segment_ids, sorted=True)
        total_loss = torch.tensor(0.0, device=pred_params.device, dtype=pred_params.dtype)
        valid_segments = 0
        for seg in unique_segments:
            seg_mask = segment_ids == seg
            seg_loss = curve_exec_loss(
                pred_params[seg_mask],
                dop[seg_mask],
                true_time[seg_mask],
                segment_ids=None,
                epsilon=epsilon,
                alpha=alpha,
                grad_weight=grad_weight,
                log_file=log_file,
                a_floor=a_floor,
                b_floor=b_floor,
                floor_weight=floor_weight,
                ce_reg_weight=ce_reg_weight,
                rel_denom_floor=rel_denom_floor,
            )
            total_loss = total_loss + seg_loss
            valid_segments += 1
        if valid_segments == 0:
            return torch.tensor(0.0, device=pred_params.device, dtype=pred_params.dtype)
        return total_loss / valid_segments

    a, b, c, d, e = (
        pred_params[:, 0],
        pred_params[:, 1],
        pred_params[:, 2],
        pred_params[:, 3],
        pred_params[:, 4],
    )

    dop_safe = torch.clamp(dop, min=epsilon)

    # 预测执行时间
    pred_time = b / (dop_safe ** a) + c * (dop_safe ** d) + e

    # 点误差：相对误差（分母加下限，避免极小 true_time 造成梯度爆炸）
    denom = torch.clamp(torch.abs(true_time), min=rel_denom_floor)
    point_loss = torch.mean(torch.abs(pred_time - true_time) / denom)

    # --- 梯度匹配损失（差分对差分）---
    sort_idx = torch.argsort(dop_safe)
    dop_sorted = dop_safe[sort_idx]
    true_sorted = true_time[sort_idx]
    pred_sorted = pred_time[sort_idx]

    if dop_sorted.numel() > 1:
        delta_dop = dop_sorted[1:] - dop_sorted[:-1]
        valid_mask = torch.abs(delta_dop) > epsilon

        if torch.any(valid_mask):
            valid_delta = delta_dop[valid_mask]
            true_grad_pair = (true_sorted[1:] - true_sorted[:-1])[valid_mask] / valid_delta
            pred_grad_pair = (pred_sorted[1:] - pred_sorted[:-1])[valid_mask] / valid_delta

            grad_loss = torch.mean(
                torch.abs(pred_grad_pair - true_grad_pair) / (torch.abs(true_grad_pair) + epsilon)
            )
        else:
            grad_loss = torch.tensor(0.0, device=pred_params.device, dtype=pred_params.dtype)
    else:
        grad_loss = torch.tensor(0.0, device=pred_params.device, dtype=pred_params.dtype)

    # 动态权重：自动平衡 point_loss 与 grad_loss
    dynamic_grad_weight = grad_weight * (point_loss.detach() / (grad_loss.detach() + 1e-8))

    # floor penalty（无量纲相对惩罚）: 避免 a->0 或 b->0，导致曲线几乎学不到下降趋势
    a_floor_penalty = torch.mean(torch.relu(1.0 - a / (a_floor + 1e-8)) ** 2)
    b_floor_penalty = torch.mean(torch.relu(1.0 - b / (b_floor + 1e-8)) ** 2)
    floor_penalty = a_floor_penalty + b_floor_penalty

    # 动态平衡 floor penalty 与 point_loss，避免量纲/量级不一致导致失效
    dynamic_floor_weight = floor_weight * (point_loss.detach() / (floor_penalty.detach() + 1e-8))

    ce_reg = torch.mean(c ** 2 + e ** 2)

    # loss = point_loss + dynamic_grad_weight * grad_loss + dynamic_floor_weight * floor_penalty + ce_reg_weight * ce_reg
    
    pred_time = torch.clamp(pred_time, min=1e-6)
    true_time = torch.clamp(true_time, min=1e-6)
    point_loss = torch.mean(torch.abs(torch.log1p(pred_time) - torch.log1p(true_time)))
    loss = point_loss + 0.1 * grad_loss + 0.01 * floor_penalty + 1e-6 * ce_reg
    # loss = 2 * point_loss + dynamic_grad_weight * grad_loss
    return loss

def curve_mem_loss(pred_params, dop, true_mem, epsilon=1e-2, alpha=0.5, log_file="./loss_debug.log"):
    # 打开日志文件（以追加模式），并写入错误信息
    # def log_to_file(message):
    #     with open(log_file, "a") as f:
    #         f.write(message + "\n")
    # 修改 log_to_file 函数内部打开文件的路径
    if not log_file:  # 如果 log_file 是空字符串
        raise ValueError("log_file cannot be an empty string. Please provide a valid file path.")
    # print("log_file path:", log_file)  # 打印 log_file 的路径，帮助调试
    def log_to_file(message):
        # 确保目录存在
        print(log_file)
        print(os.path.dirname(log_file))
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, "a") as f:
            f.write(message + "\n")

    a, b, c, d = pred_params[:, 0], pred_params[:, 1], pred_params[:, 2], pred_params[:, 3]
    
    # 计算预测时间
    pred_mem = torch.max(b * (dop ** a) + c, d)

    # TO ASK  这里有好多 NaN 的 pred_time是啥原因
    # 如果 pred_time 为 NaN 或者小于等于零，打印 a, b, c 和 pred_time
    if torch.any(torch.isnan(pred_mem)):
        log_to_file(f"NaN or invalid pred_time detected!")
        log_to_file(f"a: {a}")
        log_to_file(f"b: {b}")
        log_to_file(f"c: {c}")
        log_to_file(f"pred_time: {pred_mem}")


    # 如果 pred_time 小于 true_time，将 abs_error 乘以 2
    abs_error = torch.abs(pred_mem - true_mem) / ((a + 0.1))
    pred_mem = torch.clamp(pred_mem, min=0.1)
    # 计算相对误差
    # relative_error = torch.log(torch.max(pred_mem/true_mem, true_mem/pred_mem))
    
    # 返回最终损失
    loss = torch.mean(abs_error)  # 加上负值惩罚项
    
    return loss

def train_exec_curve_model(X_train, y_train, dop_train, group_query_train, group_plan_train, group_round_train, batch_size=8, epochs=300, lr=5e-4, seed=42, enable_data_debug=True):
    """
    训练用于预测曲线参数的模型。

    batch_size 表示一次更新包含多少条曲线（curve groups），而不是多少个样本点。
    每条曲线内部可能有不同数量的 dop 点，训练时会先打包，再按 segment_ids 拆开计算 loss。
    """
    set_training_seed(seed)
    input_dim = X_train.shape[1]
    model = Exec_CurveFitModel(input_dim)
    optimizer = optim.Adam(model.parameters(), lr=lr, eps=1e-4)

    if enable_data_debug:
        print("[DEBUG][train_exec] ===== data ranges =====")
        print(
            f"X_train shape={tuple(X_train.shape)} y_train shape={tuple(y_train.shape)} dop_train shape={tuple(dop_train.shape)}"
        )
        print(
            f"y_train min={float(torch.min(y_train)):.6f} max={float(torch.max(y_train)):.6f} mean={float(torch.mean(y_train)):.6f}"
        )
        print(
            f"dop_train min={float(torch.min(dop_train)):.6f} max={float(torch.max(dop_train)):.6f} mean={float(torch.mean(dop_train)):.6f}"
        )

    # 按 (query_num, plan_id, round_num) 分组：一个 key 对应一条曲线
    group_keys = torch.stack([group_query_train, group_plan_train, group_round_train], dim=1)
    group_to_indices = {}
    for idx in range(group_keys.shape[0]):
        key = (
            int(group_keys[idx, 0].item()),
            int(group_keys[idx, 1].item()),
            int(group_keys[idx, 2].item()),
        )
        if key not in group_to_indices:
            group_to_indices[key] = []
        group_to_indices[key].append(idx)

    curve_groups = []
    for key, idx_list in group_to_indices.items():
        if len(idx_list) < 2:
            continue
        idx_tensor = torch.tensor(idx_list, dtype=torch.long)
        curve_groups.append({
            "key": key,
            "X": X_train[idx_tensor],
            "y": y_train[idx_tensor],
            "dop": dop_train[idx_tensor],
        })

    if len(curve_groups) == 0:
        train_dataset = TensorDataset(X_train, y_train, dop_train)
        dataset_size = len(train_dataset)
        drop_last = (dataset_size > 1) and (dataset_size % batch_size == 1)
        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, drop_last=drop_last)
        use_curve_batching = False
    else:
        use_curve_batching = True

    # Smoother LR decay to avoid early convergence plateau on difficult operators.
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=20, gamma=0.9)

    start_time = time.time()  # 记录训练开始时间
    best_loss = float('inf')
    bad_epochs = 0
    patience = 40

    for epoch in range(epochs):
        model.train()
        epoch_loss = 0.0  # 初始化该 epoch 的总损失
        valid_batches = 0
        
        if use_curve_batching:
            random.shuffle(curve_groups)
            for batch_start in range(0, len(curve_groups), batch_size):
                batch_groups = curve_groups[batch_start:batch_start + batch_size]
                batch_X = []
                batch_y = []
                batch_dop = []
                batch_segment_ids = []

                for seg_id, group in enumerate(batch_groups):
                    n = group["X"].shape[0]
                    batch_X.append(group["X"])
                    batch_y.append(group["y"])
                    batch_dop.append(group["dop"])
                    batch_segment_ids.append(torch.full((n,), seg_id, dtype=torch.long, device=group["X"].device))

                X_batch = torch.cat(batch_X, dim=0)
                y_batch = torch.cat(batch_y, dim=0)
                dop_batch = torch.cat(batch_dop, dim=0)
                segment_ids = torch.cat(batch_segment_ids, dim=0)

                optimizer.zero_grad()
                pred_params = model(X_batch)
                loss = curve_exec_loss(pred_params, dop_batch, y_batch, segment_ids=segment_ids)
                if not torch.isfinite(loss):
                    print(f"Non-finite loss at epoch {epoch}, curve-batch start {batch_start}. Skipping this batch.")
                    continue

                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                optimizer.step()

                epoch_loss += loss.item()
                valid_batches += 1
        else:
            for batch_idx, (X_batch, y_batch, dop_batch) in enumerate(train_loader):
                optimizer.zero_grad()
                pred_params = model(X_batch)
                loss = curve_exec_loss(pred_params, dop_batch, y_batch)
                if not torch.isfinite(loss):
                    print(f"Non-finite loss at epoch {epoch}, batch {batch_idx}. Skipping this batch.")
                    continue

                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                optimizer.step()

                epoch_loss += loss.item()
                valid_batches += 1

        # 计算该 epoch 的平均损失
        n_batches = max(valid_batches, 1)
        avg_epoch_loss = epoch_loss / n_batches

        # Step the scheduler to adjust the learning rate
        scheduler.step()

        if avg_epoch_loss + 1e-6 < best_loss:
            best_loss = avg_epoch_loss
            bad_epochs = 0
        else:
            bad_epochs += 1

        if (epoch + 1) % 10 == 0:
            print(f"Epoch [{epoch + 1}/{epochs}], Average Loss: {avg_epoch_loss:.4f}, Best Loss: {best_loss:.4f}, Learning Rate: {scheduler.get_last_lr()[0]:.6f}")

        # if bad_epochs >= patience:
        #     print(f"Early stopping at epoch {epoch + 1}. Best Average Loss: {best_loss:.4f}")
        #     break

    training_time = time.time() - start_time  # 计算训练时间
    return model, training_time  # 返回模型和训练时间


def train_mem_curve_model(X_train, y_train, dop_train, batch_size=32, epochs=300, lr=3e-4):
    """
    训练用于预测曲线参数的模型，使用批量训练，并加入学习率调度器。

    Parameters:
    - X_train: Tensor, 特征
    - y_train: Tensor, 实际执行时间
    - dop_train: Tensor, 并行度
    - batch_size: int, 批次大小
    - epochs: int, 训练轮数
    - lr: float, 初始学习率

    Returns:
    - model: CurveFitModel, 训练后的模型
    - training_time: float, 训练时间
    """
    input_dim = X_train.shape[1]
    model = Mem_CurveFitModel(input_dim)
    optimizer = optim.Adam(model.parameters(), lr=lr, eps=1e-4)

    
    # 创建 DataLoader 进行批量训练
    train_dataset = TensorDataset(X_train, y_train, dop_train)
    # Avoid drop_last=True: if samples < batch_size, it would create 0 batches and crash training.
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, drop_last=False)
    # 设置学习率调度器，StepLR 每 10 轮降低一次学习率，gamma=0.8
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=10, gamma=0.8)

    start_time = time.time()  # 记录训练开始时间
    best_loss = float('inf')
    bad_epochs = 0
    patience = 25

    for epoch in range(epochs):
        model.train()
        epoch_loss = 0.0  # 初始化该 epoch 的总损失
        valid_batches = 0
        
        for batch_idx, (X_batch, y_batch, dop_batch) in enumerate(train_loader):
            optimizer.zero_grad()

            # Forward pass
            pred_params = model(X_batch)
            loss = curve_mem_loss(pred_params, dop_batch, y_batch)
            if not torch.isfinite(loss):
                print(f"Non-finite loss at epoch {epoch}, batch {batch_idx}. Skipping this batch.")
                continue

            # Backward pass and optimization
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

            # 累加损失
            epoch_loss += loss.item()
            valid_batches += 1

        # 计算该 epoch 的平均损失
        n_batches = max(valid_batches, 1)
        avg_epoch_loss = epoch_loss / n_batches

        # Step the scheduler to adjust the learning rate
        scheduler.step()

        if avg_epoch_loss + 1e-6 < best_loss:
            best_loss = avg_epoch_loss
            bad_epochs = 0
        else:
            bad_epochs += 1

        if (epoch + 1) % 10 == 0:
            print(f"Epoch [{epoch + 1}/{epochs}], Average Loss: {avg_epoch_loss:.4f}, Best Loss: {best_loss:.4f}, Learning Rate: {scheduler.get_last_lr()[0]:.6f}")

        # if bad_epochs >= patience:
        #     print(f"Early stopping at epoch {epoch + 1}. Best Average Loss: {best_loss:.4f}")
        #     break

    training_time = time.time() - start_time  # 计算训练时间
    return model, training_time  # 返回模型和训练时间

def debug_exec_predictions(model, X_debug, y_debug, dop_debug, sample_count=8, epsilon=1e-2):
    """打印执行曲线预测的关键中间量，定位参数/量级异常。"""
    if X_debug.shape[0] == 0 or y_debug.numel() == 0 or dop_debug.numel() == 0:
        print("[DEBUG][exec] empty debug inputs, skip detailed prediction dump.")
        return

    model.eval()
    with torch.no_grad():
        pred_params = model(X_debug)
        a = pred_params[:, 0]
        b = pred_params[:, 1]
        c = pred_params[:, 2]
        d = pred_params[:, 3]
        e = pred_params[:, 4]

        dop_safe = torch.clamp(dop_debug, min=epsilon)
        pred_exec = b / (dop_safe ** a) + c * (dop_safe ** d) + e

        n = min(sample_count, pred_params.shape[0])
        print("[DEBUG][exec] ===== sample params/predictions =====")
        for i in range(n):
            print(
                f"idx={i} dop={float(dop_safe[i]):.4f} true={float(y_debug[i]):.4f} pred={float(pred_exec[i]):.4f} "
                f"a={float(a[i]):.6f} b={float(b[i]):.6f} c={float(c[i]):.6f} d={float(d[i]):.6f} e={float(e[i]):.6f}"
            )

        print(
            "[DEBUG][exec] ranges: "
            f"a[{float(torch.min(a)):.6f}, {float(torch.max(a)):.6f}] "
            f"b[{float(torch.min(b)):.6f}, {float(torch.max(b)):.6f}] "
            f"c[{float(torch.min(c)):.6f}, {float(torch.max(c)):.6f}] "
            f"d[{float(torch.min(d)):.6f}, {float(torch.max(d)):.6f}] "
            f"e[{float(torch.min(e)):.6f}, {float(torch.max(e)):.6f}] "
            f"true[{float(torch.min(y_debug)):.6f}, {float(torch.max(y_debug)):.6f}] "
            f"pred[{float(torch.min(pred_exec)):.6f}, {float(torch.max(pred_exec)):.6f}]"
        )


def predict_and_evaluate_exec_curve(
    model,
    X_test,
    y_test,
    dop_test,
    epsilon=1e-2,
    operator=None,
    suffix="",
    onnx_model_dir: str = None,
    enable_debug=False,
    debug_sample_count=8,
    enable_data_debug=True,
):
    """
    使用模型进行预测并评估性能，同时保存 ONNX 模型并比较预测时间。

    Parameters:
    - model: CurveFitModel, 训练好的 PyTorch 模型
    - X_test: Tensor, 测试特征
    - y_test: Tensor, 实际执行时间
    - dop_test: Tensor, 测试并行度
    - operator: str, 操作符类型，用于命名保存的 ONNX 文件
    - output_prefix: str, 保存 ONNX 模型的前缀路径
    - suffix: str, ONNX 模型文件名后缀

    Returns:
    - results: dict, 包含预测性能和时间对比
    """
    model.eval()

    has_empty_test = X_test.shape[0] == 0 or y_test.numel() == 0 or dop_test.numel() == 0

    if enable_data_debug:
        print("[DEBUG][eval_exec] ===== data ranges =====")
        print(
            f"X_test shape={tuple(X_test.shape)} y_test shape={tuple(y_test.shape)} dop_test shape={tuple(dop_test.shape)}"
        )
        if has_empty_test:
            print("[DEBUG][eval_exec] empty test set detected; skip min/max/mean stats.")
        else:
            print(
                f"y_test min={float(torch.min(y_test)):.6f} max={float(torch.max(y_test)):.6f} mean={float(torch.mean(y_test)):.6f}"
            )
            print(
                f"dop_test min={float(torch.min(dop_test)):.6f} max={float(torch.max(dop_test)):.6f} mean={float(torch.mean(dop_test)):.6f}"
            )

    if has_empty_test:
        print("[WARN][eval_exec] empty test set, skip evaluation for this operator.")
        performance = {
            "metrics": {
                "MAE_error": None,
                "Q_error": None,
                "average_actual_value": None,
            },
            "comparisons": pd.DataFrame(columns=["Actual", "Predicted_Native", "Difference_Native"]),
            "native_time": None,
            "onnx_time": None,
            "onnx_accuracy": None,
            "skipped": True,
            "skip_reason": "empty_test_set",
        }
        return performance

    # 原生 PyTorch 模型预测
    start_time = time.time()
    with torch.no_grad():
        pred_params = model(X_test)
        a, b, c, d, e = pred_params[:, 0], pred_params[:, 1], pred_params[:, 2], pred_params[:, 3], pred_params[:, 4]
        dop_safe = torch.clamp(dop_test, min=epsilon)
        predictions_native = torch.relu(b / (dop_safe ** a) + c * (dop_safe ** d) + e)
        predictions_native = torch.clamp(predictions_native, 1e-2)
        # predictions_native = torch.maximum(b * (dop_safe ** a), c)
    native_time = time.time() - start_time

    if enable_debug:
        debug_exec_predictions(
            model=model,
            X_debug=X_test,
            y_debug=y_test,
            dop_debug=dop_test,
            sample_count=debug_sample_count,
            epsilon=epsilon,
        )

    # 保存为 ONNX 模型
    onnx_path = None
    if operator:
        if onnx_model_dir is None:
            # Backward compatibility (previous hard-coded output).
            onnx_model_dir = "../output/models/operator_dop_aware"
        operator_name = operator.replace(' ', '_')
        onnx_path = os.path.join(onnx_model_dir, operator, f"{suffix}_{operator_name}.onnx")
        onnx_dir = os.path.dirname(onnx_path)
        os.makedirs(onnx_dir, exist_ok=True)

        # 导出 ONNX 模型
        dummy_input = torch.randn(X_test.size(0), X_test.size(1))
        torch.onnx.export(
            model,
            dummy_input,
            onnx_path,
            input_names=["input"],
            output_names=["output"],
            dynamic_axes={"input": {0: "batch_size"}, "output": {0: "batch_size"}},
            opset_version=11,
        )
        print(f"ONNX model saved to: {onnx_path}")

    # 使用 ONNX Runtime 进行预测
    predictions_onnx = None
    onnx_time = None
    if onnx_path:
        session = ort.InferenceSession(onnx_path)
        input_name = session.get_inputs()[0].name
        start_time = time.time()
        predictions_onnx = session.run(None, {input_name: X_test.numpy().astype(np.float32)})[0]
        onnx_time = time.time() - start_time

     # Calculate standard mean absolute error (MAE) for native predictions
    mae_native = torch.mean(torch.abs(y_test - predictions_native))

    # Calculate Prediction Accuracy for native model
    Q_error = torch.mean(
         torch.maximum(y_test / predictions_native, predictions_native / y_test) - 1
    )

    # Create comparison DataFrame
    comparisons = pd.DataFrame({
        'Actual': y_test,
        'Predicted_Native': predictions_native,
        'Difference_Native': y_test - predictions_native,
    })

    # Calculate Prediction Accuracy for ONNX model
    time_accuracy_onnx = None
    if onnx_time is not None:
        time_accuracy_onnx = torch.mean(
            (1 - torch.abs(y_test - predictions_native) / (y_test + epsilon)) * 100
        )

    # Calculate the average of the actual target values
    avg_actual_value = torch.mean(y_test)

    # Print model prediction times
    print(f"Native model prediction time: {native_time:.6f} seconds")
    if onnx_time is not None:
        print(f"ONNX model prediction time: {onnx_time:.6f} seconds")

    # Organize the performance metrics into one dictionary
    performance = {
        "metrics": {
            "MAE_error": mae_native,
            "Q_error": Q_error,
            "average_actual_value": avg_actual_value
        },
        "comparisons": comparisons,
        "native_time": native_time,
        "onnx_time": onnx_time,
        "onnx_accuracy": time_accuracy_onnx
    }

    return performance


def predict_and_evaluate_mem_curve(
    model,
    X_test,
    y_test,
    dop_test,
    epsilon=1e-2,
    operator=None,
    suffix="",
    onnx_model_dir: str = None,
):
    """
    使用模型进行预测并评估性能，同时保存 ONNX 模型并比较预测时间。

    Parameters:
    - model: CurveFitModel, 训练好的 PyTorch 模型
    - X_test: Tensor, 测试特征
    - y_test: Tensor, 实际执行时间
    - dop_test: Tensor, 测试并行度
    - operator: str, 操作符类型，用于命名保存的 ONNX 文件
    - output_prefix: str, 保存 ONNX 模型的前缀路径
    - suffix: str, ONNX 模型文件名后缀

    Returns:
    - results: dict, 包含预测性能和时间对比
    """
    model.eval()

    # 原生 PyTorch 模型预测
    start_time = time.time()
    with torch.no_grad():
        pred_params = model(X_test)
        a, b, c, d = pred_params[:, 0], pred_params[:, 1], pred_params[:, 2], pred_params[:, 3]
        predictions_native = torch.relu(torch.max(b * (dop_test ** a) + c, d))
        predictions_native = torch.clamp(predictions_native, 1e-2)
        # predictions_native = torch.maximum(b * (dop_test ** a), c)
    native_time = time.time() - start_time

    # 保存为 ONNX 模型
    onnx_path = None
    if operator:
        if onnx_model_dir is None:
            # Backward compatibility (previous hard-coded output).
            onnx_model_dir = "../output/models/operator_dop_aware"
        operator_name = operator.replace(' ', '_')
        onnx_path = os.path.join(onnx_model_dir, operator, f"{suffix}_{operator_name}.onnx")
        onnx_dir = os.path.dirname(onnx_path)
        os.makedirs(onnx_dir, exist_ok=True)

        # 导出 ONNX 模型
        dummy_input = torch.randn(X_test.size(0), X_test.size(1))
        torch.onnx.export(
            model,
            dummy_input,
            onnx_path,
            input_names=["input"],
            output_names=["output"],
            dynamic_axes={"input": {0: "batch_size"}, "output": {0: "batch_size"}},
            opset_version=11,
        )
        print(f"ONNX model saved to: {onnx_path}")

    # 使用 ONNX Runtime 进行预测
    predictions_onnx = None
    onnx_time = None
    if onnx_path:
        session = ort.InferenceSession(onnx_path)
        input_name = session.get_inputs()[0].name
        start_time = time.time()
        predictions_onnx = session.run(None, {input_name: X_test.numpy().astype(np.float32)})[0]
        onnx_time = time.time() - start_time

     # Calculate standard mean absolute error (MAE) for native predictions
    mae_native = torch.mean(torch.abs(y_test - predictions_native))

    # Calculate Prediction Accuracy for native model
    Q_error = torch.mean(
         torch.maximum((y_test / predictions_native) , (predictions_native / y_test)) - 1
    )

    # Create comparison DataFrame
    comparisons = pd.DataFrame({
        'Actual': y_test,
        'Predicted_Native': predictions_native,
        'Difference_Native': y_test - predictions_native,
    })

    # Calculate Prediction Accuracy for ONNX model
    time_accuracy_onnx = None
    if onnx_time is not None:
        time_accuracy_onnx = torch.mean(
            (1 - torch.abs(y_test - predictions_native) / (y_test + epsilon)) * 100
        )

    # Calculate the average of the actual target values
    avg_actual_value = torch.mean(y_test)

    # Print model prediction times
    print(f"Native model prediction time: {native_time:.6f} seconds")
    if onnx_time is not None:
        print(f"ONNX model prediction time: {onnx_time:.6f} seconds")

    # Organize the performance metrics into one dictionary
    performance = {
        "metrics": {
            "MAE_error": mae_native,
            "Q_error": Q_error,
            "average_actual_value": avg_actual_value
        },
        "comparisons": comparisons,
        "native_time": native_time,
        "onnx_time": onnx_time,
        "onnx_accuracy": time_accuracy_onnx
    }

    return performance