import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import argparse
import json
from typing import Dict, List, Tuple

import pandas as pd

from core.pdg_builder import convert_stage_dag_to_pdg
from core.thread_block import ThreadBlock
from core.onnx_manager import ONNXModelManager
from inference.predict_queries import build_thread_blocks_from_nodes
from utils.data_utils import normalize_plan_dataframe, build_query_plan


def _collect_segments(top_segment):
    """Collect all segments reachable from top segment."""
    segments = []
    visited = set()

    def dfs(seg):
        key = id(seg)
        if key in visited:
            return
        visited.add(key)
        segments.append(seg)
        for up in getattr(seg, 'upstream_segments', []) or []:
            dfs(up)

    dfs(top_segment)
    return segments


def _check_thread_blocks(all_nodes, thread_blocks: Dict[int, ThreadBlock]) -> List[str]:
    issues = []

    # 1) 覆盖性与唯一性
    all_node_ids = {id(n) for n in all_nodes}
    tb_node_ids = []
    for tid, tb in thread_blocks.items():
        for n in tb.nodes:
            tb_node_ids.append((id(n), tid, getattr(n, 'plan_id', None), getattr(n, 'operator_type', None)))

    covered_ids = {x[0] for x in tb_node_ids}
    if covered_ids != all_node_ids:
        issues.append(f"TB覆盖不完整: all_nodes={len(all_node_ids)}, tb_nodes={len(covered_ids)}")

    seen = {}
    dup = []
    for nid, tid, pid, op in tb_node_ids:
        if nid in seen and seen[nid] != tid:
            dup.append((pid, op, seen[nid], tid))
        seen[nid] = tid
    if dup:
        issues.append(f"发现节点被分到多个TB: {dup[:5]}")

    # 2) parent-child stage一致性
    for n in all_nodes:
        for c in n.child_plans:
            pt = getattr(n, 'thread_id', None)
            ct = getattr(c, 'thread_id', None)
            if pt is None or ct is None:
                issues.append(f"存在未分配thread_id节点: parent={getattr(n,'plan_id',None)}, child={getattr(c,'plan_id',None)}")
                continue
            if pt != ct:
                if pt not in thread_blocks:
                    issues.append(f"跨stage边缺失父TB: parent_tid={pt}")
                else:
                    if ct not in thread_blocks[pt].child_thread_ids:
                        issues.append(
                            f"跨stage边未登记在child_thread_ids: parent_plan={getattr(n,'plan_id',None)}({pt}) -> child_plan={getattr(c,'plan_id',None)}({ct})"
                        )

    return issues


def _check_pdg(top_segment) -> Tuple[List[str], Dict[str, float]]:
    issues = []
    segments = _collect_segments(top_segment)

    # 无环检查
    state = {}  # 0/1/2

    def dfs(seg):
        key = id(seg)
        st = state.get(key, 0)
        if st == 1:
            return True
        if st == 2:
            return False
        state[key] = 1
        for up in getattr(seg, 'upstream_segments', []) or []:
            if dfs(up):
                return True
        state[key] = 2
        return False

    if dfs(top_segment):
        issues.append("PDG存在环（upstream依赖循环）")

    # 时延自洽性
    stats = {
        'segment_count': float(len(segments)),
        'max_pipeline_latency': 0.0,
        'sum_pipeline_latency': 0.0,
    }

    for seg in segments:
        pls = list(getattr(seg, 'pipeline_latencies', []) or [])
        if not pls:
            issues.append("存在segment无pipeline_latencies")
            continue
        if any((p is None or p < 0) for p in pls):
            issues.append(f"存在非法pipeline_latency: {pls}")
        stats['max_pipeline_latency'] = max(stats['max_pipeline_latency'], max(pls))
        stats['sum_pipeline_latency'] += sum(pls)

    return issues, stats


def _node_view(node):
    return {
        'plan_id': getattr(node, 'plan_id', None),
        'operator_type': getattr(node, 'operator_type', None),
        'thread_id': getattr(node, 'thread_id', None),
        'dop': getattr(node, 'dop', None),
        'execution_time': getattr(node, 'execution_time', None),
        'pred_execution_time': getattr(node, 'pred_execution_time', None),
        'pred_dop_exec_time': dict(getattr(node, 'pred_dop_exec_map', {}) or {}),
        'true_dop_exec_time': dict(getattr(node, 'true_dop_exec_map', {}) or {}),
    }


def _build_pretty_view(all_nodes, thread_blocks: Dict[int, ThreadBlock], top_segment):
    tb_view = []
    for tid in sorted(thread_blocks.keys()):
        tb = thread_blocks[tid]
        nodes_sorted = sorted(tb.nodes, key=lambda n: getattr(n, 'plan_id', 0))

        node_id_set = {id(n) for n in tb.nodes}
        tb_roots = [n for n in tb.nodes if getattr(n, 'parent_node', None) is None or id(getattr(n, 'parent_node', None)) not in node_id_set]
        tb_root = sorted(tb_roots, key=lambda n: getattr(n, 'plan_id', 0))[0] if tb_roots else (nodes_sorted[0] if nodes_sorted else None)

        tb_pred_dop_exec_time = dict(getattr(tb_root, 'pred_dop_exec_map', {}) or {}) if tb_root is not None else {}

        tb_view.append({
            'thread_id': tid,
            'node_count': len(nodes_sorted),
            'child_thread_ids': sorted(list(getattr(tb, 'child_thread_ids', set()) or [])),
            'tb_root_plan_id': getattr(tb_root, 'plan_id', None) if tb_root is not None else None,
            'tb_root_operator': getattr(tb_root, 'operator_type', None) if tb_root is not None else None,
            'pred_exec_time': getattr(tb, 'pred_time', None),
            'pred_dop_exec_time': getattr(tb, 'pred_dop_exec_time', {}),
            'tb_pred_dop_exec_time': tb_pred_dop_exec_time,
            'nodes': [_node_view(n) for n in nodes_sorted],
        })

    tb_edges = []
    for n in all_nodes:
        for c in n.child_plans:
            pt = getattr(n, 'thread_id', None)
            ct = getattr(c, 'thread_id', None)
            if pt != ct:
                tb_edges.append({
                    'from_thread': pt,
                    'to_thread': ct,
                    'parent_plan_id': getattr(n, 'plan_id', None),
                    'parent_operator': getattr(n, 'operator_type', None),
                    'child_plan_id': getattr(c, 'plan_id', None),
                    'child_operator': getattr(c, 'operator_type', None),
                })

    segments = _collect_segments(top_segment)
    seg_idx = {id(s): i for i, s in enumerate(segments)}
    pdg_view = []
    for i, seg in enumerate(segments):
        nodes = getattr(seg, 'nodes', []) or []
        pdg_view.append({
            'segment_index': i,
            'is_inner_stage': getattr(seg, 'is_inner_stage', None),
            'pipeline_latencies': list(getattr(seg, 'pipeline_latencies', []) or []),
            'upstream_segment_indices': [seg_idx[id(u)] for u in (getattr(seg, 'upstream_segments', []) or []) if id(u) in seg_idx],
            'node_count': len(nodes),
            'nodes': [_node_view(n) for n in nodes],
        })

    return {
        'thread_blocks': tb_view,
        'tb_cross_stage_edges': tb_edges,
        'pdg_segments': pdg_view,
    }


def _fmt_map_brief(m: Dict) -> str:
    if not m:
        return '{}'
    keys = sorted(m.keys())
    sample = keys[:6]
    parts = [f"{k}:{round(float(m[k]), 3)}" for k in sample]
    suffix = '' if len(keys) <= 6 else f" ... (+{len(keys)-6})"
    return '{' + ', '.join(parts) + '}' + suffix


def _render_pretty_text(pretty, verbose: bool = False):
    lines = []
    lines.append('================ TB 摘要 ================')
    for tb in pretty['thread_blocks']:
        tb_map = tb.get('tb_pred_dop_exec_time') or {}
        lines.append(
            f"TB[{tb['thread_id']}] root=({tb.get('tb_root_plan_id')},{tb.get('tb_root_operator')}) "
            f"nodes={tb['node_count']} children={tb['child_thread_ids']}"
        )
        lines.append(f"  tb_pred_dop_exec_time: {_fmt_map_brief(tb_map)}")

        if verbose:
            for n in tb['nodes']:
                lines.append(
                    f"  - plan={n['plan_id']:<4} op={str(n['operator_type'])[:40]:<40} dop={n['dop']} "
                    f"exec={n['execution_time']} pred_exec={n.get('pred_execution_time')}"
                )
                lines.append(f"    pred_dop_exec_time(node)={n.get('pred_dop_exec_time') or {}}")

    lines.append('')
    lines.append('========== TB 跨 Stage 边(parent->child) ==========')
    if not pretty['tb_cross_stage_edges']:
        lines.append('  (none)')
    else:
        for e in pretty['tb_cross_stage_edges']:
            lines.append(
                f"  TB[{e['from_thread']}] plan={e['parent_plan_id']}({e['parent_operator']}) -> "
                f"TB[{e['to_thread']}] plan={e['child_plan_id']}({e['child_operator']})"
            )

    lines.append('')
    lines.append('================ PDG 摘要 ================')
    for s in pretty['pdg_segments']:
        lines.append(
            f"SEG[{s['segment_index']}] inner={s['is_inner_stage']} "
            f"lat={s['pipeline_latencies']} upstream={s['upstream_segment_indices']} nodes={s['node_count']}"
        )

    return '\n'.join(lines)


def validate_one_query(
    plan_df: pd.DataFrame,
    query_id: int,
    query_dop: int,
    no_dop_model_dir: str = None,
    dop_model_dir: str = None,
):
    group = plan_df[(plan_df['query_id'] == query_id) & (plan_df['query_dop'] == query_dop)]
    if group.empty:
        raise ValueError(f"query ({query_id}, {query_dop}) 不存在")

    onnx_manager = None
    if no_dop_model_dir and dop_model_dir:
        onnx_manager = ONNXModelManager(
            no_dop_model_dir=no_dop_model_dir,
            dop_model_dir=dop_model_dir,
        )

    
    nodes_dict, _ = build_query_plan(group, use_estimates=False, onnx_manager=onnx_manager)

    all_nodes = list(nodes_dict.values())

    # 如果没有提供模型目录，做回退，避免debug输出全0。
    # 提供了模型目录时，这里应直接使用真实模型预测值。
    if onnx_manager is None:
        for n in all_nodes:
            pred_t = getattr(n, 'pred_execution_time', None)
            if pred_t is None or pred_t <= 0:
                setattr(n, 'pred_execution_time', getattr(n, 'execution_time', 0))

    thread_blocks = build_thread_blocks_from_nodes(all_nodes)

    # Ensure per-node/per-threadblock DOP prediction maps are prepared for debugging output.
    for n in all_nodes:
        n.compute_parallel_dop_predictions()
    for tb in thread_blocks.values():
        tb.aggregate_metrics()

    top_segment = convert_stage_dag_to_pdg(thread_blocks, all_nodes)

    tb_issues = _check_thread_blocks(all_nodes, thread_blocks)
    pdg_issues, stats = _check_pdg(top_segment)
    pretty = _build_pretty_view(all_nodes, thread_blocks, top_segment)

    result = {
        'query_id': query_id,
        'query_dop': query_dop,
        'node_count': len(all_nodes),
        'thread_block_count': len(thread_blocks),
        'tb_issues': tb_issues,
        'pdg_issues': pdg_issues,
        'stats': stats,
        'pretty': pretty,
        'ok': len(tb_issues) == 0 and len(pdg_issues) == 0,
    }
    return result


def main():
    parser = argparse.ArgumentParser(description='Validate TB/PDG partition and latency model consistency')
    parser.add_argument('--plan_csv', required=True, help='path to plan_info csv')
    parser.add_argument('--query_id', type=int, required=True)
    parser.add_argument('--query_dop', type=int, required=True)
    parser.add_argument('--output_json', default='tb_pdg_validation.json')
    parser.add_argument('--output_txt', default='tb_pdg_validation.txt')
    parser.add_argument('--no_dop_model_dir', default=None, help='path to no_dop ONNX model directory')
    parser.add_argument('--dop_model_dir', default=None, help='path to dop ONNX model directory')
    parser.add_argument('--verbose', action='store_true', help='print detailed per-node info')
    args = parser.parse_args()

    plan_df = pd.read_csv(args.plan_csv, delimiter=';', encoding='utf-8')
    plan_df = normalize_plan_dataframe(plan_df)

    result = validate_one_query(
        plan_df,
        args.query_id,
        args.query_dop,
        no_dop_model_dir=args.no_dop_model_dir,
        dop_model_dir=args.dop_model_dir,
    )

    with open(args.output_json, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    pretty_text = _render_pretty_text(result['pretty'], verbose=args.verbose)
    with open(args.output_txt, 'w', encoding='utf-8') as f:
        f.write(pretty_text)

    print(pretty_text)
    print('\n================ 验证摘要 ================')
    print(json.dumps({
        'query_id': result['query_id'],
        'query_dop': result['query_dop'],
        'ok': result['ok'],
        'tb_issues': result['tb_issues'],
        'pdg_issues': result['pdg_issues'],
        'stats': result['stats'],
        'output_json': args.output_json,
        'output_txt': args.output_txt,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
