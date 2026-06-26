#!/bin/bash
# ==================================================
# 全局配置 – 请根据实际情况修改以下变量
# ==================================================

# 项目根目录（脚本所在位置，自动获取，不要修改）
export PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# -------------------- 工作空间目录（所有下载内容存放于此）--------------------
export WORKSPACE_DIR="${HOME}/og-tpch-workspace"   # 可修改为你希望的路径
mkdir -p "$WORKSPACE_DIR"

# -------------------- openGauss 相关 --------------------
export OPENGAUSS_VERSION="6.0.0"
export OPENGAUSS_REPO="https://github.com/opengauss-mirror/openGauss-server.git"
# export BINARYLIBS_URL="https://opengauss.obs.cn-south-1.myhuaweicloud.com/6.0.0/binarylibs/gcc10.3/openGauss-third_party_binarylibs_openEuler_2203_x86_64.tar.gz"
# export BINARYLIBS_DIR_NAME="openGauss-third_party_binarylibs_openEuler_2203_x86_64"
export BINARYLIBS_URL="https://opengauss.obs.cn-south-1.myhuaweicloud.com/6.0.0/binarylibs/gcc10.3/openGauss-third_party_binarylibs_Centos7.6_x86_64.tar.gz"
export BINARYLIBS_DIR_NAME="openGauss-third_party_binarylibs_Centos7.6_x86_64"

# openGauss 源码目录
export OPENGAUSS_SRC_DIR="${WORKSPACE_DIR}/openGauss-server"
# binarylibs 目录
export BINARYLIBS_DIR="${WORKSPACE_DIR}/${BINARYLIBS_DIR_NAME}"
# 安装目录（即 GAUSSHOME）
export GAUSS_HOME="${WORKSPACE_DIR}/openGauss-server/mppdb_temp_install"
# 数据目录
export GAUSS_DATA_DIR="${WORKSPACE_DIR}/GaussData"
# 日志文件
export GAUSS_LOG_FILE="${WORKSPACE_DIR}/openGauss.log"
export GAUSS_PORT="40040"
export GAUSS_NODENAME="opengauss"

# 数据库用户
export DB_USER="candle"
# 数据库密码 – 建议通过环境变量 GAUSS_PASSWORD 传入，或交互式输入
export GAUSS_PASSWORD="${GAUSS_PASSWORD:-}"

# -------------------- TPCH 相关 --------------------
export TPCH_SCALE_FACTOR="100"
export TPCH_DBGEN_REPO="https://github.com/electrum/tpch-dbgen.git"
export TPCH_DBGEN_DIR="${WORKSPACE_DIR}/tpch-dbgen"
export TPCH_DATA_DIR="${WORKSPACE_DIR}/tpch-data"
export TPCH_QUERY_DIR="${WORKSPACE_DIR}/tpch-queries"

# -------------------- DDL 及导入文件 --------------------
# 这两个文件应位于项目根目录（保持不变）
export DDL_FILE="${PROJECT_ROOT}/dss_cs.ddl"
export IMPORT_SQL_FILE="${PROJECT_ROOT}/import_data.sql"