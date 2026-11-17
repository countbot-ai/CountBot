#!/usr/bin/env bash
#
# 部署到生产服务器。
#
# 刻意不使用 --delete：仓库与服务器共享同一套目录结构，但服务器在仓库之外
# 还存放了运行时数据（users/<id>/workspace 下的用户技能与记忆、data 下的数据库、
# 全局 memory 等）。带 --delete 的同步会把这些「本地不存在」的文件判定为多余
# 并删除，等于用仓库内容覆盖生产数据。
#
# 需要清理旧构建产物时，只针对 frontend/dist 单独处理。

set -euo pipefail

REMOTE="${REMOTE:-countbot}"
REMOTE_DIR="${REMOTE_DIR:-/opt/countbot}"
LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 运行时数据与本地环境产物：与代码无关，绝不能同步，更不能删除
EXCLUDES=(
  --exclude='/.venv/'
  --exclude='/node_modules/'
  --exclude='/frontend/node_modules/'
  --exclude='/.git/'
  --exclude='__pycache__/'
  --exclude='*.pyc'
  # ---- 生产数据 ----
  --exclude='/users/'          # 多用户工作区：技能、记忆、上传、wiki
  --exclude='/workspace/'      # 管理员工作区
  --exclude='/memory/'         # 全局记忆
  --exclude='/data/'           # 数据库与日志
  --exclude='/config/'         # 运行时配置（含密钥）
  --exclude='/.backup-split/'  # 备份
  --exclude='/uploads/'
  # ---- 本地开发产物 ----
  --exclude='/.pytest_cache/'
  --exclude='*.log'
  --exclude='.DS_Store'
  --exclude='/.workbuddy/'
  --exclude='/.zcode-runtime/'
  # 构建产物由下方独立步骤对齐，避免主同步把旧分块留在服务器上
  --exclude='/frontend/dist/'
)

DRY_RUN="${DRY_RUN:-0}"
DRY_FLAG=""
if [[ "$DRY_RUN" == "1" ]]; then
  DRY_FLAG="--dry-run"
  echo "== 演练模式：不实际写入 =="
fi

# 前端产物过期时中止：同步的是仓库里的 dist，源码比 dist 新说明还没构建，
# 直接发布会让线上跑到旧界面（这类问题排查成本远高于一次构建）。
if [[ "${ALLOW_STALE_DIST:-0}" != "1" && -f "${LOCAL_DIR}/frontend/dist/index.html" ]]; then
  STALE=$(find "${LOCAL_DIR}/frontend/src" \
    -newer "${LOCAL_DIR}/frontend/dist/index.html" \
    \( -name '*.vue' -o -name '*.ts' -o -name '*.css' \) 2>/dev/null | wc -l | tr -d ' ')
  if [[ "$STALE" != "0" ]]; then
    echo "!! 有 ${STALE} 个前端源文件比 dist 新，请先构建："
    echo "   cd frontend && npx vite build --outDir /tmp/dist-new && rsync -a --delete /tmp/dist-new/ dist/"
    echo "   （确认无需构建时用 ALLOW_STALE_DIST=1 跳过此检查）"
    exit 1
  fi
fi

echo "== 同步代码到 ${REMOTE}:${REMOTE_DIR} =="
rsync -az ${DRY_FLAG} --no-perms --no-owner --no-group \
  "${EXCLUDES[@]}" \
  -e "ssh -o ConnectTimeout=15" \
  "${LOCAL_DIR}/" "${REMOTE}:${REMOTE_DIR}/"

# 产物文件名带内容 hash，每次构建都会换一批；这里只对 dist 做 --delete，
# 线上不会残留旧分块。整个 REMOTE_DIR 下还有生产数据，绝不能带 --delete。
echo "== 对齐前端产物（仅 frontend/dist） =="
rsync -az ${DRY_FLAG} --delete --no-perms --no-owner --no-group \
  -e "ssh -o ConnectTimeout=15" \
  "${LOCAL_DIR}/frontend/dist/" "${REMOTE}:${REMOTE_DIR}/frontend/dist/"

if [[ "$DRY_RUN" == "1" ]]; then
  echo "== 演练结束 =="
  exit 0
fi

echo "== 重启服务 =="
ssh -o ConnectTimeout=15 "$REMOTE" \
  "find ${REMOTE_DIR}/backend -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null; systemctl restart countbot; sleep 20; systemctl is-active countbot"

echo "== 健康检查 =="
ssh -o ConnectTimeout=10 "$REMOTE" "curl -s -m 8 http://127.0.0.1:80/api/system/health"
echo
