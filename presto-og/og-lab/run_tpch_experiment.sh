#!/bin/bash
set -euo pipefail

# 加载配置和工具函数
source "$(dirname "$0")/config.sh"
source "$(dirname "$0")/utils.sh"

# 默认参数
WARMUP=2
RUNS=3
QUERY_DIR="/home/candle/og-tpch-workspace/tpch-queries"
DB_NAME="tpch_cs"
DOP_LIST="64"
OUTPUT_FILE="${WORKSPACE_DIR}/tpch-results/tpch_experiment_summary.csv"
DETAIL_FILE="${WORKSPACE_DIR}/tpch-results/tpch_experiment_detail.csv"
TIMEOUT=600

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --warmup)
            WARMUP="$2"
            shift 2
            ;;
        --runs)
            RUNS="$2"
            shift 2
            ;;
        --dop-list)
            DOP_LIST="$2"
            shift 2
            ;;
        --query-dir)
            QUERY_DIR="$2"
            shift 2
            ;;
        --db-name)
            DB_NAME="$2"
            shift 2
            ;;
        --output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        --detail)
            DETAIL_FILE="$2"
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --help)
            echo "用法: $0 [选项]"
            echo "选项:"
            echo "  --warmup N            预热执行次数 (默认: 2)"
            echo "  --runs N               正式执行次数 (默认: 3)"
            echo "  --dop-list LIST        逗号分隔的 query_dop 值列表 (默认: 1,2,4,8)"
            echo "  --query-dir DIR        查询文件目录 (默认: \$TPCH_QUERY_DIR)"
            echo "  --db-name NAME         数据库名称 (默认: tpch_cs)"
            echo "  --output FILE          摘要输出文件 (默认: \$WORKSPACE_DIR/tpch-results/tpch_experiment_summary.csv)"
            echo "  --detail FILE          详细输出文件 (每次运行的时间) (默认: \$WORKSPACE_DIR/tpch-results/tpch_experiment_detail.csv)"
            echo "  --timeout SECONDS      单个查询超时时间 (默认: 600秒)"
            echo "  --help                 显示此帮助"
            exit 0
            ;;
        *)
            log_error "未知参数: $1"
            exit 1
            ;;
    esac
done

# 检查 bc
if ! command -v bc &> /dev/null; then
    log_error "bc 命令未找到，请安装 bc"
    exit 1
fi

# 检查查询目录
if [ ! -d "$QUERY_DIR" ]; then
    log_error "查询目录不存在: $QUERY_DIR"
    exit 1
fi

# 确保数据库已启动
if ! gs_ctl status -D "$GAUSS_DATA_DIR" &>/dev/null; then
    log_warn "数据库未运行，尝试启动..."
    gs_ctl start -D "$GAUSS_DATA_DIR" -Z single_node -l "$GAUSS_LOG_FILE"
    check_success "启动数据库失败"
fi
wait_for_db "$GAUSS_PORT"

# 设置数据库连接
export PGPASSWORD="$GAUSS_PASSWORD"
GSQL_CMD="gsql -p $GAUSS_PORT -U $DB_USER -d $DB_NAME -q -X -A -t"

# 测试数据库连接
log_info "测试数据库连接..."
if ! $GSQL_CMD -c "SELECT 1" > /dev/null 2>&1; then
    log_error "无法连接到数据库 $DB_NAME，请检查配置或数据库状态。"
    exit 1
fi

# 准备输出目录
mkdir -p "$(dirname "$OUTPUT_FILE")"
# 初始化摘要文件
echo "query,query_dop,runs,avg_time_ms,min_time_ms,max_time_ms,run_times_ms" > "$OUTPUT_FILE"
# 初始化详细文件（每次运行一行）
echo "query,query_dop,run_number,runtime_ms" > "$DETAIL_FILE"

# 将 DOP_LIST 转换为数组
IFS=',' read -ra DOP_ARRAY <<< "$DOP_LIST"
log_info "将测试 query_dop 值: ${DOP_ARRAY[*]}，预热 $WARMUP 次，正式运行 $RUNS 次"

# 遍历所有查询
# for i in {11..22}; do
for i in {10..10}; do
    query_file="$QUERY_DIR/$i.sql"
    if [ ! -f "$query_file" ]; then
        log_warn "查询文件 $query_file 不存在，跳过查询 $i"
        continue
    fi
    extra_setting=""
    if [ "$i" -eq 9 ]; then
        extra_setting="SET enable_nestloop=off;SET enable_mergejoin = off;"
    fi
    # 读取查询内容
    query_content=$(cat "$query_file")

    for dop in "${DOP_ARRAY[@]}"; do
        log_info "===== 处理查询 $i, query_dop=$dop ====="

        # 预热阶段
        if [ "$WARMUP" -gt 0 ]; then
            log_info "预热 $WARMUP 次..."
            for w in $(seq 1 "$WARMUP"); do
                log_info "预热第 $w 次..."
                # 构建 SQL：只执行查询（不计时），输出丢弃
                sql="SET query_dop = $dop; $extra_setting $query_content; \q"
                timeout "$TIMEOUT" bash -c "echo \"$sql\" | $GSQL_CMD > /dev/null 2>&1" || true
            done
            log_info "预热完成"
        fi

        # 正式运行阶段
        run_times=()
        success_run=0
        for r in $(seq 1 "$RUNS"); do
            log_info "执行第 $r 次..."

            # 构建 SQL：包含 SET 和 EXPLAIN ANALYZE
            sql="SET query_dop = $dop; $extra_setting EXPLAIN ANALYZE $query_content; \q"

            # 临时文件
            out_file="${WORKSPACE_DIR}/tpch-results/tmp_q${i}_dop${dop}_run${r}.out"
            err_file="${WORKSPACE_DIR}/tpch-results/tmp_q${i}_dop${dop}_run${r}.err"

            set +e
            timeout "$TIMEOUT" bash -c "echo \"$sql\" | $GSQL_CMD" > "$out_file" 2> "$err_file"
            exit_code=$?
            set -e

            runtime=""
            if [ $exit_code -eq 124 ]; then
                log_error "第 $r 次执行查询 $i, dop=$dop 超时 (超过 ${TIMEOUT}秒)"
                continue
            elif [ $exit_code -ne 0 ]; then
                log_error "第 $r 次执行查询 $i, dop=$dop 失败，退出码: $exit_code"
                continue
            else
                # 提取 Total runtime
                runtime_line=$(grep -i "Total runtime:" "$out_file" | tail -1) || true
                if [ -n "$runtime_line" ]; then
                    runtime=$(echo "$runtime_line" | sed -n 's/.*Total runtime: \([0-9.]*\) ms.*/\1/p') || true
                    if [ -n "$runtime" ]; then
                        run_times+=("$runtime")
                        ((++success_run))
                        log_info "第 $r 次耗时: $runtime ms"
                    else
                        log_warn "第 $r 次未能解析时间，行内容: $runtime_line"
                    fi
                else
                    log_warn "第 $r 次输出中未找到 Total runtime"
                fi
            fi

            # 无论成功或失败，记录详细信息（如果有 runtime）
            if [ -n "$runtime" ]; then
                echo "$i,$dop,$r,$runtime" >> "$DETAIL_FILE"
            else
                echo "$i,$dop,$r,FAILED" >> "$DETAIL_FILE"
            fi

            # 清理临时文件
            rm -f "$out_file" "$err_file" 2>/dev/null || true
        done

        # 计算统计数据
        if [ ${#run_times[@]} -eq 0 ]; then
            log_warn "查询 $i, dop=$dop 所有运行均失败"
            echo "$i,$dop,$RUNS,0,0,0," >> "$OUTPUT_FILE"
            continue
        fi

        # 使用 bc 处理浮点数
        sum=0
        min=${run_times[0]}
        max=${run_times[0]}
        for t in "${run_times[@]}"; do
            sum=$(echo "$sum + $t" | bc)
            if (( $(echo "$t < $min" | bc -l) )); then min=$t; fi
            if (( $(echo "$t > $max" | bc -l) )); then max=$t; fi
        done
        avg=$(echo "scale=3; $sum / ${#run_times[@]}" | bc)

        run_times_str=$(IFS=','; echo "${run_times[*]}")
        echo "$i,$dop,${#run_times[@]},$avg,$min,$max,$run_times_str" >> "$OUTPUT_FILE"

        log_info "查询 $i, dop=$dop 平均耗时: $avg ms (min=$min, max=$max)"
    done
done

log_info "实验完成！"
log_info "摘要文件: $OUTPUT_FILE"
log_info "详细文件: $DETAIL_FILE"