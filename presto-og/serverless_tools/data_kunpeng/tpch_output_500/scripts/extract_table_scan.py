#!/usr/bin/env python3
import csv
import sys

def extract_table_scan(input_file, output_file=sys.stdout):
    """
    从输入文件中筛选 operator_type 为 TableScanOperator 的行，
    输出 query_id, dop, execution_time, l_input_rows, r_input_rows 列，
    并按 l_input_rows 分组（相等值为同一组）后输出。

    排序键：l_input_rows -> query_id -> dop
    """
    with open(input_file, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        # 检查必需的列是否存在
        required_cols = ['query_id', 'operator_type', 'dop', 'execution_time', 'l_input_rows', 'r_input_rows']
        for col in required_cols:
            if col not in reader.fieldnames:
                print(f"错误：文件中缺少列 '{col}'", file=sys.stderr)
                sys.exit(1)

        # 先收集再排序
        rows = [row for row in reader if row['operator_type'] == 'TableScanOperator']

        def to_int_or_max(v):
            try:
                return int(v)
            except (TypeError, ValueError):
                return sys.maxsize

        def group_sort_key(row):
            l_rows = to_int_or_max(row['l_input_rows'])
            qid = to_int_or_max(row['query_id'])
            dop = to_int_or_max(row['dop'])

            # l_input_rows 相等视为同一 group
            return (l_rows, qid, dop)

        rows.sort(key=group_sort_key)

        # 写入输出
        out_writer = csv.DictWriter(
            output_file,
            fieldnames=['query_id', 'dop', 'execution_time', 'l_input_rows', 'r_input_rows'],
            delimiter=';'
        )
        out_writer.writeheader()

        for row in rows:
            out_row = {
                'query_id': row['query_id'],
                'dop': row['dop'],
                'execution_time': row['execution_time'],
                'l_input_rows': row['l_input_rows'],
                'r_input_rows': row['r_input_rows']
            }
            out_writer.writerow(out_row)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("用法: python extract_table_scan.py <输入文件>", file=sys.stderr)
        sys.exit(1)
    extract_table_scan(sys.argv[1])