#!/bin/bash
set -euo pipefail

source "$(dirname "$0")/config.sh"
source "$(dirname "$0")/utils.sh"

# 加载 openGauss 环境变量
if [ -f "${OPENGAUSS_SRC_DIR}/cmake_env.sh" ]; then
    source "${OPENGAUSS_SRC_DIR}/cmake_env.sh"
else
    # 如果文件不存在，尝试手动设置 PATH
    export PATH="${GAUSS_HOME}/bin:${PATH}"
    export LD_LIBRARY_PATH="${GAUSS_HOME}/lib:${LD_LIBRARY_PATH}"
fi

# 确保数据库已启动
if ! gs_ctl status -D "$GAUSS_DATA_DIR" &>/dev/null; then
    log_warn "数据库未运行，尝试启动..."
    gs_ctl start -D "$GAUSS_DATA_DIR" -Z single_node -l "$GAUSS_LOG_FILE"
    check_success "启动数据库失败"
fi
wait_for_db "$GAUSS_PORT"
cat: .: Is a directory
