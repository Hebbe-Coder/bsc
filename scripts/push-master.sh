#!/usr/bin/env bash
# scripts/push-master.sh
# 推送 master 到指定 origin 的助手脚本。
# 用法：bash scripts/push-master.sh <URL> [ssh|https] [--dry-run]
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "用法: $0 <remote-url> [ssh|https] [--dry-run]"
  echo "例:   $0 git@github.com:foo/bar.git ssh"
  echo "      $0 https://github.com/foo/bar.git https --dry-run"
  exit 1
fi

URL="$1"
PROTO="${2:-ssh}"
DRY_RUN=""
for arg in "$@"; do
  if [[ "$arg" == "--dry-run" ]]; then
    DRY_RUN="--dry-run"
  fi
done

# 协议自检
if [[ "$PROTO" == "ssh" ]]; then
  if ! command -v ssh >/dev/null 2>&1; then
    echo "[!] 选 ssh 但本机找不到 ssh 命令" >&2; exit 2
  fi
elif [[ "$PROTO" == "https" ]]; then
  if ! command -v git >/dev/null 2>&1; then
    echo "[!] 选 https 但本机找不到 git" >&2; exit 2
  fi
fi

# 身份自检
USER_NAME=$(git config user.name || true)
USER_EMAIL=$(git config user.email || true)
if [[ -z "$USER_NAME" || "$USER_NAME" == "WorkBuddy" || -z "$USER_EMAIL" || "$USER_EMAIL" == "workbuddy@local" ]]; then
  echo "[!] 检测到占位身份：name='$USER_NAME' email='$USER_EMAIL'"
  echo "    push 前请先设置真实身份："
  echo "      git config --global user.name  \"你的名字\""
  echo "      git config --global user.email \"你的邮箱\""
  exit 3
fi

# 当前分支必须是 master
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$BRANCH" != "master" ]]; then
  echo "[!] 当前分支是 '$BRANCH'，脚本只允许在 master 上跑（避免误推其它分支）"
  exit 4
fi

# 脏树自检
if [[ -n "$(git status --short)" ]]; then
  echo "[!] 工作树有未提交改动（$(git status --short | wc -l) 个），请先 commit 或 stash"
  exit 5
fi

echo "[i] set-url origin -> $URL"
git remote set-url origin "$URL"

echo "[i] 推送 master 到 origin $DRY_RUN"
git push -u origin master $DRY_RUN

if [[ -z "$DRY_RUN" ]]; then
  echo "[i] 核验远端状态"
  git ls-remote origin
  echo "[✓] push 完成。HEAD on origin: $(git rev-parse --short HEAD)"
fi
