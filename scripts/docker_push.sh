#!/usr/bin/env bash

# 脚本说明：
# - 将本地镜像打标签并推送到 Docker Hub。
# - 同时推送两个标签：
#   1) latest
#   2) app/version.yml 中 project_version 对应的版本标签（如 5.2.0）
# - 默认本地源镜像为 mw-archiver:latest，可通过第一个参数覆盖。
#
# 用法：
#   bash docker_push.sh
#   bash docker_push.sh my-local-image:latest

set -euo pipefail

SOURCE_IMAGE="${1:-mw-archiver:latest}"
TARGET_REPO="sonicming/mw-archiver"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VERSION_FILE="$REPO_ROOT/app/version.yml"

if [[ ! -f "$VERSION_FILE" ]]; then
  echo "错误：未找到 $VERSION_FILE"
  exit 1
fi

# 从 app/version.yml 提取 project_version（格式要求 X.Y.Z）
PROJECT_VERSION="$(grep -E '^[[:space:]]*project_version[[:space:]]*:' "$VERSION_FILE" | head -n1 | sed -E 's/^[^:]+:[[:space:]]*//; s/[[:space:]]+$//')"

if [[ -z "$PROJECT_VERSION" ]]; then
  echo "错误：$VERSION_FILE 中未找到 project_version"
  exit 1
fi

if [[ ! "$PROJECT_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "错误：project_version 格式不正确（期望 X.Y.Z，当前: $PROJECT_VERSION）"
  exit 1
fi

TARGET_IMAGE_LATEST="${TARGET_REPO}:latest"
TARGET_IMAGE_VERSION="${TARGET_REPO}:${PROJECT_VERSION}"

echo "即将推送以下镜像："
echo "- 源镜像: $SOURCE_IMAGE"
echo "- 目标镜像1: $TARGET_IMAGE_LATEST"
echo "- 目标镜像2: $TARGET_IMAGE_VERSION"
echo ""

# 检查 Docker 是否可用
if ! docker info >/dev/null 2>&1; then
  echo "错误：Docker 守护进程未运行，请启动 Docker 服务"
  exit 1
fi

# 检查源镜像是否存在
if ! docker image inspect "$SOURCE_IMAGE" >/dev/null 2>&1; then
  echo "错误：源镜像 $SOURCE_IMAGE 不存在"
  echo "当前本地镜像列表："
  docker images
  exit 1
fi

# 打标签
echo "正在打标签："
echo "- $SOURCE_IMAGE -> $TARGET_IMAGE_LATEST"
docker tag "$SOURCE_IMAGE" "$TARGET_IMAGE_LATEST"
echo "- $SOURCE_IMAGE -> $TARGET_IMAGE_VERSION"
docker tag "$SOURCE_IMAGE" "$TARGET_IMAGE_VERSION"

# 校验标签结果
if ! docker image inspect "$TARGET_IMAGE_LATEST" >/dev/null 2>&1; then
  echo "错误：latest 标签打标失败"
  exit 1
fi
if ! docker image inspect "$TARGET_IMAGE_VERSION" >/dev/null 2>&1; then
  echo "错误：版本标签打标失败"
  exit 1
fi

echo "打标签成功。开始推送到 Docker Hub..."

# 推送 latest
echo "推送：$TARGET_IMAGE_LATEST"
docker push "$TARGET_IMAGE_LATEST"

# 推送 version
echo "推送：$TARGET_IMAGE_VERSION"
docker push "$TARGET_IMAGE_VERSION"

echo ""
echo "推送完成："
echo "- $TARGET_IMAGE_LATEST"
echo "- $TARGET_IMAGE_VERSION"
echo "如果推送失败，请检查："
echo "1) 是否已 docker login"
echo "2) 是否有 sonicming 仓库推送权限"
