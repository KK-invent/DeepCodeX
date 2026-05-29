#!/bin/bash
# ============================================================
# DeepCodex Backup Script
# 备份 DEEPCODEX-DEVLOG.md、配置文件、bin/ 脚本到安全位置
# ============================================================

set -euo pipefail

DEEPCODEX_HOME="${DEEPCODEX_HOME:-${HOME}/.codex-deepseek}"
BACKUP_ROOT="${DEEPCODEX_HOME}/backups"
TIMESTAMP=$(date "+%Y-%m-%d_%H%M%S")
BACKUP_DIR="${BACKUP_ROOT}/${TIMESTAMP}"
RETENTION_DAYS="${DEEPCODEX_BACKUP_RETENTION_DAYS:-5}"
# app-backups/ 里是 app.asar 整包备份（每份 ~140MB），原本无人清理会无限堆积撑爆磁盘。
# 这里按"份数"保留：只留最新 APP_ASAR_KEEP 份 app.asar.*，旧的回滚点意义递减、删掉。
APP_BACKUP_DIR="${DEEPCODEX_HOME}/app-backups"
APP_ASAR_KEEP="${DEEPCODEX_APP_ASAR_KEEP:-2}"

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  DeepCodex 备份 - ${TIMESTAMP}${NC}"
echo -e "${GREEN}========================================${NC}"

# 创建备份目录
mkdir -p "${BACKUP_DIR}"

# ---- 1. 核心：开发日志（最重要） ----
cp "${DEEPCODEX_HOME}/DEEPCODEX-DEVLOG.md" "${BACKUP_DIR}/DEEPCODEX-DEVLOG.md"
echo -e "${GREEN}  ✓${NC} DEEPCODEX-DEVLOG.md"

# ---- 2. 维护手册 ----
cp "${DEEPCODEX_HOME}/DEEPCODEX-MAINTENANCE.md" "${BACKUP_DIR}/" 2>/dev/null && \
  echo -e "${GREEN}  ✓${NC} DEEPCODEX-MAINTENANCE.md" || \
  echo -e "${YELLOW}  ⚠${NC} DEEPCODEX-MAINTENANCE.md 不存在"

# ---- 3. AGENTS.md（全局指令） ----
cp "${DEEPCODEX_HOME}/AGENTS.md" "${BACKUP_DIR}/" 2>/dev/null && \
  echo -e "${GREEN}  ✓${NC} AGENTS.md" || \
  echo -e "${YELLOW}  ⚠${NC} AGENTS.md 不存在"

# ---- 4. 主配置 ----
cp "${DEEPCODEX_HOME}/config.toml" "${BACKUP_DIR}/config.toml"
echo -e "${GREEN}  ✓${NC} config.toml"

# ---- 5. bin/ 目录（所有脚本） ----
mkdir -p "${BACKUP_DIR}/bin"
cp "${DEEPCODEX_HOME}/bin/"*.py "${BACKUP_DIR}/bin/" 2>/dev/null && \
  echo -e "${GREEN}  ✓${NC} bin/（${BACKUP_DIR}/bin 下有 $(ls "${BACKUP_DIR}/bin/"*.py 2>/dev/null | wc -l | tr -d ' ') 个脚本）"

# ---- 6. CodeGraph 配置（如果有） ----
if [ -f "${DEEPCODEX_HOME}/.codegraph/config.json" ]; then
  mkdir -p "${BACKUP_DIR}/.codegraph"
  cp "${DEEPCODEX_HOME}/.codegraph/config.json" "${BACKUP_DIR}/.codegraph/"
  echo -e "${GREEN}  ✓${NC} .codegraph/config.json"
fi

# Do not copy ~/.codex, ~/.claude, auth.json, secrets.env, sessions, logs, or
# SQLite state. Backups are for maintainable source/config only.

# ---- 生成备份清单 ----
cat > "${BACKUP_DIR}/MANIFEST.txt" << EOF
DeepCodex Backup - ${TIMESTAMP}
================================
Source: ${DEEPCODEX_HOME}
Backup: ${BACKUP_DIR}

文件清单：
$(find "${BACKUP_DIR}" -type f -not -name "MANIFEST.txt" | sed 's|^'"${BACKUP_DIR}"'/|  - |')

备份时间：$(date "+%Y-%m-%d %H:%M:%S %Z")
EOF

echo ""
echo -e "${GREEN}  ✓${NC} MANIFEST.txt"

# ---- 清理旧备份（保留 RETENTION_DAYS 天） ----
echo ""
echo -e "${YELLOW}--- 清理 ${RETENTION_DAYS} 天前的备份 ---${NC}"
deleted=0
while IFS= read -r -d '' dir; do
  rm -rf "${dir}"
  deleted=$((deleted + 1))
done < <(find "${BACKUP_ROOT}" -maxdepth 1 -type d -name "????-??-??_*" -mtime +${RETENTION_DAYS} -print0)
echo -e "${GREEN}  ✓${NC} 已清理 ${deleted} 个旧备份"

# ---- 清理 app-backups/（只保留最新 APP_ASAR_KEEP 份 app.asar.*） ----
echo ""
echo -e "${YELLOW}--- 清理 app-backups（保留最新 ${APP_ASAR_KEEP} 份 app.asar） ---${NC}"
app_deleted=0
if [ -d "${APP_BACKUP_DIR}" ]; then
  # 按修改时间从新到旧排列，跳过前 APP_ASAR_KEEP 个，其余删除
  while IFS= read -r old_asar; do
    [ -z "${old_asar}" ] && continue
    rm -f "${old_asar}"
    app_deleted=$((app_deleted + 1))
  done < <(ls -1t "${APP_BACKUP_DIR}"/app.asar.* 2>/dev/null | tail -n +$((APP_ASAR_KEEP + 1)))
fi
echo -e "${GREEN}  ✓${NC} 已清理 ${app_deleted} 份旧 app.asar 备份"

# ---- 裁剪 logs_2.sqlite（Codex 日志库，默认保留 3 天，安全带 app 运行） ----
echo ""
echo -e "${YELLOW}--- 裁剪 logs_2.sqlite ---${NC}"
python3 "${DEEPCODEX_HOME}/bin/deepcodex-log-prune.py" 2>&1 | sed 's/^/  /' || \
  echo -e "${YELLOW}  ⚠${NC} 日志裁剪跳过（非致命）"

# ---- 统计 ----
BACKUP_SIZE=$(du -sh "${BACKUP_DIR}" 2>/dev/null | cut -f1)
TOTAL_SIZE=$(du -sh "${BACKUP_ROOT}" 2>/dev/null | cut -f1)
BACKUP_COUNT=$(find "${BACKUP_ROOT}" -maxdepth 1 -type d -name "????-??-??_*" | wc -l | tr -d ' ')

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  备份完成${NC}"
echo -e "${GREEN}  位置：${BACKUP_DIR}${NC}"
echo -e "${GREEN}  大小：${BACKUP_SIZE}${NC}"
echo -e "${GREEN}  累计：${BACKUP_COUNT} 个备份，共 ${TOTAL_SIZE}${NC}"
echo -e "${GREEN}========================================${NC}"
