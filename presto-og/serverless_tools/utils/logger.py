# -*- coding: utf-8 -*-
"""
日志工具模块
包含日志记录、实验跟踪等功能
"""

import os
import sys
from datetime import datetime


class TeeStream:
    """将终端输出同时写入到日志文件"""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for stream in self.streams:
            stream.write(data)
            stream.flush()

    def flush(self):
        for stream in self.streams:
            stream.flush()


def setup_file_logging(log_dir: str = "logs", log_prefix: str = "train"):
    """设置文件日志：将 stdout/stderr 同时输出到终端和文件"""
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"{log_prefix}_{ts}.log")

    # 保留原始输出流，避免重复包装
    if not hasattr(sys, "_original_stdout"):
        sys._original_stdout = sys.stdout
    if not hasattr(sys, "_original_stderr"):
        sys._original_stderr = sys.stderr

    log_file = open(log_path, "a", encoding="utf-8")
    sys.stdout = TeeStream(sys._original_stdout, log_file)
    sys.stderr = TeeStream(sys._original_stderr, log_file)

    print(f"[日志] 已启用文件日志: {log_path}")
    return log_path


def log_experiment_start(dataset: str, method: str, train_mode: str, eval_mode: str = None):
    """记录实验开始"""
    print("=" * 60)
    print(f"开始实验: {method.upper()} 方法")
    print(f"数据集: {dataset}")
    print(f"训练模式: {train_mode}")
    if eval_mode:
        print(f"评估模式: {eval_mode}")
    print("=" * 60)


def log_experiment_end(dataset: str, method: str, output_path: str = None):
    """记录实验结束"""
    print("=" * 60)
    print(f"实验完成: {method.upper()} 方法")
    print(f"数据集: {dataset}")
    if output_path:
        print(f"输出路径: {output_path}")
    print("=" * 60)
