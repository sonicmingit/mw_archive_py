#!/usr/bin/env bash

# 脚本说明：
# - 用于“一键发布”当前版本（Shell 版）：
#   1) 检查 tag 是否已存在
#   2) 打 tag 并推送 main + tag
# - 版本来源：app/version.yml 的 project_version
# - 脚本不会执行 git add / git commit，代码提交需人工提前完成
# - GitHub 推送完成后，可交互选择是否继续推送 Docker 镜像
# - Docker 推送脚本：scripts/docker_push.sh
#
# 用法：
#   bash scripts/release_tag.sh

set -euo pipefail

# 计算仓库根目录（当前脚本位于 scripts/ 下）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VERSION_FILE="$REPO_ROOT/app/version.yml"
DOCKER_PUSH_SCRIPT="$REPO_ROOT/scripts/docker_push.sh"

# 检查必要文件是否存在
if [[ ! -f "$VERSION_FILE" ]]; then
  echo "错误：app/version.yml 不存在: $VERSION_FILE"
  exit 1
fi

# 从 app/version.yml 提取 project_version（要求 X.Y.Z）
PROJECT_VERSION="$(grep -E '^[[:space:]]*project_version[[:space:]]*:' "$VERSION_FILE" | head -n1 | sed -E 's/^[^:]+:[[:space:]]*//; s/[[:space:]]+$//')"
if [[ -z "$PROJECT_VERSION" ]]; then
  echo "错误：app/version.yml 中未找到 project_version"
  exit 1
fi
if [[ ! "$PROJECT_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "错误：project_version 格式不正确（期望 X.Y.Z，当前: $PROJECT_VERSION）"
  exit 1
fi

# 规范化 tag 格式
TAG="v$PROJECT_VERSION"

# 切换到仓库根目录，确保 git 与脚本执行上下文正确
cd "$REPO_ROOT"

# 要求当前分支为 main，避免误在其它分支打发布 tag
CURRENT_BRANCH="$(git branch --show-current)"
if [[ "$CURRENT_BRANCH" != "main" ]]; then
  echo "错误：当前分支不是 main（当前: $CURRENT_BRANCH），请切换到 main 后再执行"
  exit 1
fi

# 先检查 tag 是否已存在；若存在则直接终止
if [[ -n "$(git tag --list "$TAG")" ]]; then
  echo "错误：tag 已存在: $TAG，已停止执行"
  exit 1
fi

# 打 tag 前再次人工确认
echo ""
echo "================ 发布前确认 ================"
echo "版本号: $TAG"
echo "当前分支: $CURRENT_BRANCH"
echo "将执行：git tag + git push(origin main) + git push(origin tag)"
echo "============================================"
echo ""
read -r -p "确认以上内容无误并继续执行 tag/push ? 输入 y 继续，其它任意键取消: " CONFIRM_RELEASE
if [[ "$CONFIRM_RELEASE" != "y" && "$CONFIRM_RELEASE" != "Y" ]]; then
  echo "已取消发布操作（未执行 tag/push）"
  exit 1
fi

# 打 tag 并推送 main 与 tag
git tag "$TAG"
git push origin HEAD
git push origin "$TAG"

echo "已发布 tag: $TAG"
echo "GitHub Actions 将自动创建 Release。"

# GitHub 推送完成后，询问是否继续推送 Docker 镜像
echo ""
read -r -p "是否同步推送 Docker 镜像（latest + $PROJECT_VERSION）? 输入 y 继续，其它任意键跳过: " CONFIRM_DOCKER
if [[ "$CONFIRM_DOCKER" == "y" || "$CONFIRM_DOCKER" == "Y" ]]; then
  if [[ ! -f "$DOCKER_PUSH_SCRIPT" ]]; then
    echo "错误：未找到 Docker 推送脚本: $DOCKER_PUSH_SCRIPT"
    exit 1
  fi
  echo "开始执行 Docker 镜像推送..."
  bash "$DOCKER_PUSH_SCRIPT"
else
  echo "已跳过 Docker 镜像推送。"
fi
