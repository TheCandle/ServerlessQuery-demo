# 文件路径: optimization/threading_utils.py

import itertools
import math
import os
import re
import sys
import numpy as np
import pandas as pd
# import networkx as nx # 原始文件似乎未使用
# import matplotlib.pyplot as plt # 原始文件似乎未使用
import time
import torch # 保留，原始文件导入了

# --- 导入重构后的模块 (仅修改路径) ---
# 使用绝对导入路径
from core.plan_node import PlanNode
from core.partition_rules import is_stage_boundary_operator, is_pipeline_breaker_operator
from core.thread_block import ThreadBlock
from config.structure_config import thread_cost, default_dop # 假设原始文件用了 default_dop
# --- 结束导入 ---



# ==============================================================================
# 从原始 dop_utils.py 直接搬运的函数
# ==============================================================================

def get_root_nodes(base_nodes):
    """
    从所有节点中，筛选出没有出现在其他节点 child_plans 中的节点，作为根节点。
    (直接搬运)
    """
    child_ids = set()
    for node in base_nodes:
        for child in node.child_plans:
            child_ids.add(child.plan_id)
    roots = [node for node in base_nodes if node.plan_id not in child_ids]
    return roots

def base_execution_time(node):
    """返回当前节点的基本执行时间 (直接搬运)"""
    if node.operator_type == 'CTE Scan':
        return 0
    return node.pred_execution_time # 原始逻辑

def process_same_thread_child(child, thread_blocks):
    """处理子节点在同一线程内的情况 (直接搬运)"""
    return calculate_thread_execution_time(child, thread_blocks)

def process_new_thread_child(child, parent_node, parent_thread_time, thread_blocks):
    """处理子节点属于新线程的情况 (直接搬运，添加父节点参数)"""
    # 调用递归计算新线程的时间
    _, child_complete, _, child_up, _, _ = calculate_thread_execution_time(child, thread_blocks)

    # --- 修改这里：使用传入的 parent_node ---
    # 记录父子关系 (确保 parent_node 和 child 都有 thread_id)
    parent_tid = getattr(parent_node, 'thread_id', None)
    child_tid = getattr(child, 'thread_id', None)

    if parent_tid is not None and child_tid is not None and parent_tid in thread_blocks:
         # 原始逻辑可能没有检查 thread_blocks[parent_tid] 的类型，我们保持简单
         try: # 增加 try-except 避免属性错误
             thread_blocks[parent_tid].child_thread_ids.add(child_tid)
         except AttributeError:
              print(f"警告: thread_blocks[{parent_tid}] 没有 child_thread_ids 属性或不是集合。")
    # 调整时间
    adjustment = parent_thread_time / 2
    adjusted_child_complete = child_complete + adjustment
    return adjustment, adjusted_child_complete, child_up

def aggregate_child_results(same_results, new_results):
    """合并子节点结果 (直接搬运)"""
    child_exec_list = []
    child_complete_list = []
    local_transfer_list = []
    up_transfer_list = []

    for res in same_results:
        child_exec_list.append(res[0])
        child_complete_list.append(res[1])
        local_transfer_list.append(res[2])
        up_transfer_list.append(res[3])
    for res in new_results:
        child_exec_list.append(0)
        child_complete_list.append(res[1])
        local_transfer_list.append(res[2]) # 假设原始逻辑是这样
        up_transfer_list.append(res[2]) # 假设原始逻辑是这样
    return child_exec_list, child_complete_list, local_transfer_list, up_transfer_list

def final_adjustment(thread_exec, local_transfer, child_complete_list, more_agg_times, tmp_flag):
    """最终调整完成时间 (直接搬运)"""
    child_complete = max(child_complete_list, default=0)
    thread_complete = max(thread_exec + local_transfer, child_complete)
    if tmp_flag and (thread_exec + local_transfer < child_complete):
        thread_complete = max(thread_complete, child_complete + thread_exec - more_agg_times)
        more_agg_times = thread_exec
        tmp_flag = False
    return thread_complete, more_agg_times, tmp_flag


def calculate_thread_execution_time(node, thread_blocks):
    """递归计算线程时间和相关指标 (直接搬运 dop_utils 版本)"""
    if node.visit:
        return 0, 0, 0, 0, 0, False
    node.visit = True

    thread_exec = base_execution_time(node)
    more_agg = False
    tmp_flag = False
    more_agg_times = 0 # 原始初始化

    same_results = []
    new_results = []

    # 遍历子节点 (原始逻辑)
    for child in node.child_plans:
        if getattr(child, 'thread_id', node.thread_id) == node.thread_id:
            res = calculate_thread_execution_time(child, thread_blocks) # 递归调用
            same_results.append(res)
        else:
            # 原始的 process_new_thread_child 调用方式可能依赖全局变量或不同的参数
            # 这里我们按照 dop_utils 的模式调用，传入 thread_exec
            res = process_new_thread_child(child, node, thread_exec, thread_blocks)
            new_results.append(res)

    child_exec_list, child_complete_list, local_transfer_list, up_transfer_list = aggregate_child_results(same_results, new_results)

    local_transfer = max(local_transfer_list, default=0)
    up_transfer = max(up_transfer_list, default=0)

    thread_exec += sum(child_exec_list) # 累加

    # 处理物化算子 (原始逻辑)
    if node.materialized:
        if 'hash join' in node.operator_type.lower():
            if child_exec_list:
                up_transfer = max(up_transfer, local_transfer + thread_exec - child_exec_list[0])
            else:
                up_transfer = max(up_transfer, local_transfer + thread_exec)
        else:
            up_transfer = max(up_transfer, local_transfer + thread_exec - node.build_time)
        more_agg_times = thread_exec # 原始逻辑似乎是这样
        more_agg = True
    else:
        more_agg_times = 0

    child_complete = max(child_complete_list, default=0)
    thread_complete = max(thread_exec + local_transfer, child_complete)
    thread_complete, more_agg_times, tmp_flag = final_adjustment(thread_exec, local_transfer, child_complete_list, more_agg_times, tmp_flag)

    # 将计算结果写入节点属性 (原始逻辑)
    node.thread_execution_time = thread_exec
    node.thread_complete_time = thread_complete
    node.local_data_transfer_start_time = local_transfer
    node.up_data_transfer_start_time = up_transfer

    return thread_exec, thread_complete, local_transfer, up_transfer, more_agg_times if more_agg else 0, more_agg


# def calculate_query_execution_time(all_nodes, thread_blocks):
#     """计算整个查询的执行时间 (直接搬运 dop_utils 版本)"""
#     # 重置访问状态
#     for node in all_nodes:
#         node.visit = False

#     root_nodes = get_root_nodes(all_nodes)

#     total_time = 0 # 原始初始化可能是这样
#     plan_count = 0 # 原始初始化

#     for node in root_nodes: # 原始逻辑可能是遍历根节点
#         plan_count += 1 # 原始逻辑可能包含计数
#         _, node_time, _, _, _, _ = calculate_thread_execution_time(node, thread_blocks)
#         # 原始逻辑可能是累加根节点的完成时间？或者取最大值？
#         total_time += node_time # 假设是累加

#     # 原始逻辑是否包含线程成本？
#     # final_time = total_time + plan_count * thread_cost # 参照 dop_choosen 写法?
#     final_time = total_time # 假设 dop_utils 只返回时间本身

#     return final_time if final_time > 0 else 1e-6 # 保持返回正数

def calculate_query_execution_time(thread_blocks):
    """
    计算整个查询的执行时间。
    假设 thread_blocks 是 {thread_id: ThreadBlock} 结构，每个 ThreadBlock 有 nodes 属性（list of PlanNode）。
    """

    # 1. 重置所有节点的访问状态
    for tb in thread_blocks.values():
        for node in tb.nodes:
            node.visit = False

    # 2. 收集所有节点，找出所有根节点（没有父节点的节点）
    all_nodes = []
    for tb in thread_blocks.values():
        all_nodes.extend(tb.nodes)

    root_nodes = get_root_nodes(all_nodes)  # 假设这个函数基于节点间的parent/child关系找到根节点

    total_time = 0
    plan_count = 0

    # 3. 遍历每个根节点计算执行时间
    for node in root_nodes:
        plan_count += 1
        _, node_time, _, _, _, _ = calculate_thread_execution_time(node, thread_blocks)
        total_time += node_time  # 你可以改成取最大值：total_time = max(total_time, node_time)

    # 4. 返回时间，防止为0
    final_time = total_time if total_time > 0 else 1e-6
    return final_time


# ==============================================================================
# 线程块划分和更新相关函数 (直接搬运)
# ==============================================================================

def assign_thread_ids_by_plan_id(node, thread_id=0, max_thread_id=0, visited=None):
    """递归为计划树分配线程 ID。处理 Presto LocalExchange sink/source 成对边界。"""
    if visited is None:
        visited = set()

    def _dfs(cur_node, cur_thread_id, cur_max_thread_id, parent_operator_type=''):
        node_key = id(cur_node)
        if node_key in visited:
            return cur_max_thread_id
        visited.add(node_key)

        cur_node.thread_id = cur_thread_id
        cur_max_thread_id = max(cur_max_thread_id, cur_thread_id)

        node_op = getattr(cur_node, 'operator_type', '')
        node_op_l = node_op.lower()
        parent_op_l = (parent_operator_type or '').lower()

        for child in cur_node.child_plans:
            child_thread_id = cur_thread_id

            # 默认：遇到 stage-boundary 则切分。
            should_split = is_stage_boundary_operator(node_op)

            # 关键修正：LocalExchangeSink / LocalExchangeSource 是同一个逻辑边界的两端，
            # 无论树上方向是 Sink->Source 还是 Source->Sink，都只允许切一次。
            if (
                (node_op_l == 'localexchangesourceoperator' and parent_op_l == 'localexchangesinkoperator') or
                (node_op_l == 'localexchangesinkoperator' and parent_op_l == 'localexchangesourceoperator')
            ):
                should_split = False

            if should_split:
                child_thread_id = cur_max_thread_id + 1

            cur_max_thread_id = _dfs(child, child_thread_id, cur_max_thread_id, node_op)

        return cur_max_thread_id

    return _dfs(node, thread_id, max_thread_id)


def collect_all_nodes_by_plan_id(base_nodes):
    """通过 DFS 收集所有节点 (直接搬运)"""
    all_nodes = []
    visited_ids = set()
    stack = list(base_nodes)
    while stack:
        node = stack.pop()
        if node.plan_id in visited_ids:
            continue
        visited_ids.add(node.plan_id)
        all_nodes.append(node)
        stack.extend(node.child_plans)
    return all_nodes

def _get_pipeline_key(node):
    """返回用于划分 thread_block 的 pipeline 标识。"""
    stage_id = getattr(node, 'stage_id', None)
    pipeline_id = getattr(node, 'pipeline_id', None)
    if stage_id is None or pipeline_id is None:
        return None
    try:
        return (int(stage_id), int(pipeline_id))
    except (TypeError, ValueError):
        return None


def update_thread_blocks(base_nodes):
    """按 stage_id + pipeline_id 划分线程块。"""
    if not base_nodes:
        return {}

    root_nodes = get_root_nodes(base_nodes)
    all_nodes = collect_all_nodes_by_plan_id(root_nodes)

    # 直接按 plan_info.csv 里的 stage_id + pipeline_id 分组：同一 pipeline 视为同一个 thread_block。
    pipeline_to_thread_id = {}
    next_thread_id = 0
    for node in sorted(
        all_nodes,
        key=lambda n: (
            getattr(n, 'query_id', 0),
            getattr(n, 'stage_id', 0),
            getattr(n, 'pipeline_id', 0),
            getattr(n, 'plan_id', 0),
        ),
    ):
        key = _get_pipeline_key(node)
        if key is None:
            # 兜底：如果个别节点缺少 pipeline 信息，仍保持可运行，但尽量不影响其他 pipeline 的划分。
            key = ('plan', getattr(node, 'plan_id', id(node)))
        if key not in pipeline_to_thread_id:
            pipeline_to_thread_id[key] = next_thread_id
            next_thread_id += 1
        node.thread_id = pipeline_to_thread_id[key]

    all_nodes = collect_all_nodes_by_plan_id(root_nodes)

    thread_blocks = {}
    for node in all_nodes:
        tid = getattr(node, 'thread_id', 0)
        if tid not in thread_blocks:
            thread_blocks[tid] = ThreadBlock(tid, [])
        thread_blocks[tid].nodes.append(node)

    for node in all_nodes:
        parent = getattr(node, 'parent_node', None)
        if parent is None:
            continue
        parent_tid = getattr(parent, 'thread_id', None)
        child_tid = getattr(node, 'thread_id', None)
        if parent_tid is None or child_tid is None or parent_tid == child_tid:
            continue
        if parent_tid in thread_blocks:
            thread_blocks[parent_tid].child_thread_ids.add(child_tid)

    for root in root_nodes:
        root.compute_parallel_dop_predictions()

    calculate_query_execution_time(thread_blocks)

    for tb in thread_blocks.values():
        tb.aggregate_metrics()
        
    for tb in thread_blocks.values():
        if not tb.child_thread_ids:
            continue

        redistribution_node = None
        max_data_volume = 0
        for node in tb.nodes:
            if 'streaming' in node.operator_type.lower() or 'redistribute' in node.operator_type.lower():
                node_data_volume = node.actual_rows * node.width
                if node_data_volume > max_data_volume:
                    max_data_volume = node_data_volume
                    redistribution_node = node
        
        if redistribution_node is None:
            continue

        data_volume = redistribution_node.actual_rows * redistribution_node.width
        op_type = redistribution_node.operator_type.lower()
        if 'gather' in op_type:
            k_base = 8.0e-04
        elif 'broadcast' in op_type:
            k_base = 7.0e-05
        else:
            k_base = 1.0e-05
        
        if redistribution_node.send_time > 0 or redistribution_node.execution_time > 0:
            actual_time = max(redistribution_node.send_time, redistribution_node.execution_time)
            baseline_child_dop = redistribution_node.downdop if redistribution_node.downdop > 0 else redistribution_node.dop
            if baseline_child_dop > 0 and data_volume > 0:
                k_base = actual_time * baseline_child_dop / data_volume
        
        for child_id in tb.child_thread_ids:
            child_tb = thread_blocks[child_id]
            parent_candidate_dops = list(redistribution_node.pred_dop_exec_map.keys())
            if hasattr(tb, 'candidate_dops') and tb.candidate_dops:
                parent_candidate_dops = list(set(parent_candidate_dops) | set(tb.candidate_dops))
            child_candidate_dops = list(child_tb.pred_dop_exec_time.keys())
            if hasattr(child_tb, 'candidate_dops') and child_tb.candidate_dops:
                child_candidate_dops = list(set(child_candidate_dops) | set(child_tb.candidate_dops))
            
            for parent_dop in parent_candidate_dops:
                for child_dop in child_candidate_dops:
                    base_transfer_time = k_base * data_volume / max(child_dop, 1)
                    receiver_factor = 1.0 + 0.1 * math.log(max(parent_dop, 1))
                    dop_diff_ratio = abs(parent_dop - child_dop) / max(parent_dop, child_dop, 1)
                    if data_volume > 1e7:
                        mismatch_penalty = base_transfer_time * dop_diff_ratio * 0.4
                    else:
                        mismatch_penalty = base_transfer_time * dop_diff_ratio * 0.15
                    total_transfer_cost = base_transfer_time * receiver_factor + mismatch_penalty
                    if not hasattr(child_tb, 'dop_mismatch_penalties'):
                        child_tb.dop_mismatch_penalties = {}
                    if parent_dop not in child_tb.dop_mismatch_penalties:
                        child_tb.dop_mismatch_penalties[parent_dop] = {}
                    child_tb.dop_mismatch_penalties[parent_dop][child_dop] = total_transfer_cost

    for tb in thread_blocks.values():
        tb.child_max_execution_time = max(
            (thread_blocks[child_tid].thread_execution_time
             for child_tid in tb.child_thread_ids if child_tid in thread_blocks),
            default=0
        )

    return thread_blocks

import itertools

import itertools

def generate_aligned_dop_configurations(thread_blocks, max_configs=10):
    # 1. 构建 child -> parent 映射
    parent_map = {}
    for block in thread_blocks.values():
        for child_id in block.child_thread_ids:
            parent_map[child_id] = block.thread_id

    # 2. 构建 parent -> children 映射
    children_map = {}
    for block in thread_blocks.values():
        if block.thread_id not in children_map:
            children_map[block.thread_id] = []
        for child_id in block.child_thread_ids:
            children_map[block.thread_id].append(child_id)

    # 3. 找到所有顶层 blocks（即没有父节点）
    root_blocks = [tb for tb in thread_blocks.values() if tb.thread_id not in parent_map]

    # 4. 递归生成配置（带去重和剪枝）
    memo = {}

    def enumerate_configs(thread_id, limit=1000, in_stack=None):
        if in_stack is None:
            in_stack = set()
        # Reuse computed sub-results.
        memo_key = (thread_id, limit)
        if memo_key in memo:
            return memo[memo_key]
        # Cycle detected in thread-block DAG: stop descending this branch.
        if thread_id in in_stack:
            tb_cycle = thread_blocks[thread_id]
            fallback = [{thread_id: dop} for dop in tb_cycle.candidate_optimal_dops]
            memo[memo_key] = fallback
            return fallback

        in_stack.add(thread_id)
        tb = thread_blocks[thread_id]
        cand_dops = tb.candidate_optimal_dops
        left_bounds = cand_dops[:-1]
        d_right = cand_dops[-1]

        if thread_id not in children_map:
            result = [{thread_id: dop} for dop in cand_dops]
            in_stack.remove(thread_id)
            memo[memo_key] = result
            return result

        child_ids = [cid for cid in children_map[thread_id] if cid != thread_id]
        child_config_lists = [enumerate_configs(cid, limit, in_stack) for cid in child_ids]

        aligned_configs_set = set()
        aligned_configs = []

        # 生成对齐配置
        for merged_child_configs in itertools.product(*child_config_lists):
            merged_child_config = {}
            for child_cfg in merged_child_configs:
                merged_child_config.update(child_cfg)

            for dop in left_bounds:
                new_config = dict(merged_child_config)
                new_config[thread_id] = dop
                frozen = frozenset(new_config.items())
                if frozen not in aligned_configs_set:
                    aligned_configs_set.add(frozen)
                    aligned_configs.append(new_config)
                    if len(aligned_configs) >= limit:
                        in_stack.remove(thread_id)
                        memo[memo_key] = aligned_configs
                        return aligned_configs

        # 添加不对齐（使用 d_right）的配置
        for merged_child_configs in itertools.product(*child_config_lists):
            merged_child_config = {}
            for child_cfg in merged_child_configs:
                merged_child_config.update(child_cfg)
            new_config = dict(merged_child_config)
            new_config[thread_id] = d_right
            frozen = frozenset(new_config.items())
            if frozen not in aligned_configs_set:
                aligned_configs_set.add(frozen)
                aligned_configs.append(new_config)
                if len(aligned_configs) >= limit:
                    in_stack.remove(thread_id)
                    memo[memo_key] = aligned_configs
                    return aligned_configs

        in_stack.remove(thread_id)
        memo[memo_key] = aligned_configs
        return aligned_configs

    # 5. 获取每个 root 的所有配置列表
    all_config_lists = [enumerate_configs(root.thread_id, limit=max_configs * 2) for root in root_blocks]

    # 6. 对这些配置进行笛卡尔积，并合并每个组合为一个整体配置
    all_configs_set = set()
    all_configs = []

    for config_combo in itertools.product(*all_config_lists):
        merged_config = {}
        for config in config_combo:
            merged_config.update(config)
        if not merged_config:
            continue
        frozen = frozenset(merged_config.items())
        if frozen not in all_configs_set:
            all_configs_set.add(frozen)
            all_configs.append(merged_config)
            if len(all_configs) >= max_configs:
                break

    # 7. 添加特殊“强制并行度 8”配置
    force_parallel_config = {}
    for thread_id, tb in thread_blocks.items():
        if len(tb.candidate_optimal_dops) == 1:
            force_parallel_config[thread_id] = tb.candidate_optimal_dops[0]
        else:
            force_parallel_config[thread_id] = 8
    frozen_force = frozenset(force_parallel_config.items())

    if force_parallel_config and frozen_force not in all_configs_set:
        all_configs.append(force_parallel_config)

    return all_configs[:max_configs]


