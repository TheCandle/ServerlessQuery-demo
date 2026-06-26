#!/bin/bash
# 公用函数，供其他脚本调用

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*" >&2
}

check_success() {
    if [ $? -ne 0 ]; then
        log_error "$1"
        exit 1
    fi
}

check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "命令 '$1' 未找到，请安装后再试。"
        exit 1
    fi
}

wait_for_db() {
    local port="$1"
    local max_attempts=30
    local attempt=1
    log_info "等待数据库启动 (端口 $port) ..."
    while ! gsql -p "$port" -U "$DB_USER" -d postgres -c "SELECT 1" &>/dev/null; do
        if [ $attempt -ge $max_attempts ]; then
            log_error "数据库启动超时"
            exit 1
        fi
        sleep 2
        ((attempt++))
    done
    log_info "数据库已就绪"
}