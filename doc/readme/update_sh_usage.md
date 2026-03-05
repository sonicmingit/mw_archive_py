# update.sh 使用说明（本地快速更新/重部署）

> 适用脚本：根目录 [update.sh](../../update.sh)
>
> 目标用户：需要“一条命令完成拉代码 + 构建 + 重启”的部署/本地测试用户

## 1. 这个脚本做什么

`update.sh` 会按顺序执行：

1. 进入指定 Git 仓库目录，执行 `git pull`
2. 判断是否有新提交
3. 有更新时自动继续：构建 + 运行脚本
4. 无更新时会询问：是否仍然继续重部署
5. 最后打印本次更新日志（默认最多 3 条）

## 2. 默认配置（脚本内）

脚本顶部配置区当前是：

```bash
BASE_DIR="/home/docker/mw_archive"
REPO_DIR="${BASE_DIR}/mw_archive_py"
BUILD_SCRIPT="${REPO_DIR}/docker_build.sh"
RUN_SCRIPT="${BASE_DIR}/docker_run.sh"
LOG_COUNT=3
```

说明：
- `BASE_DIR`：你的部署基目录
- `REPO_DIR`：Git 仓库目录（执行 `git pull` 的地方）
- `BUILD_SCRIPT`：构建脚本路径（如 `docker_build.sh`）
- `RUN_SCRIPT`：重启/运行脚本路径（如 `docker_run.sh`）
- `LOG_COUNT`：最后打印多少条 Git 更新日志

## 3. 首次使用

```bash
chmod +x update.sh
bash update.sh
```

如果提示脚本不可执行，也给被调用脚本加权限：

```bash
chmod +x docker_build.sh
chmod +x /你的路径/docker_run.sh
```

## 4. 如何改成“本地快速构建更新”

你主要改 `update.sh` 顶部这 4 个路径变量即可。

### 方案 A：本地 Docker 快速更新（推荐）

适合你本机也是 Docker 部署的场景。

示例（按你的实际路径改）：

```bash
BASE_DIR="/home/sonic/work"
REPO_DIR="${BASE_DIR}/0.mw_archive"
BUILD_SCRIPT="${REPO_DIR}/docker_build.sh"
RUN_SCRIPT="${REPO_DIR}/scripts/docker_run_local.sh"
LOG_COUNT=5
```

然后准备 `scripts/docker_run_local.sh`（示例）：

```bash
#!/usr/bin/env bash
set -e

docker rm -f mw-archiver >/dev/null 2>&1 || true
docker run -d \
  --name mw-archiver \
  -p 8000:8000 \
  -v "$(pwd)/app/data:/app/data" \
  -v "$(pwd)/app/logs:/app/logs" \
  -v "$(pwd)/app/cookie.txt:/app/cookie.txt" \
  mw-archiver:latest
```

### 方案 B：本地 Python 进程快速重启

如果你不是 Docker，而是本机直接 `python server.py`：

```bash
BASE_DIR="/home/sonic/work"
REPO_DIR="${BASE_DIR}/0.mw_archive"
BUILD_SCRIPT="${REPO_DIR}/scripts/noop_build.sh"
RUN_SCRIPT="${REPO_DIR}/scripts/restart_local_server.sh"
```

其中 `noop_build.sh` 可以只是：

```bash
#!/usr/bin/env bash
echo "skip build"
```

`restart_local_server.sh` 负责你自己的重启方式（如 `pkill + nohup`、`systemctl restart`、`pm2 restart`）。

## 5. 交互行为说明

- 当 `git pull` 没有更新时，脚本会问：
  - `未检测到代码更新，是否继续执行重新部署？[y/N]`
- 输入 `y/yes` 才会继续
- 其他输入或回车：直接退出（这属于正常退出）

## 6. 常见问题

### Q1：为什么“无更新”时脚本直接结束，没有提问？
你可能在无交互终端执行（如 CI、后台任务）。  
脚本会自动判定无 TTY，并默认**不继续重部署**。

### Q2：提示 `构建脚本不存在或不可执行`
检查：
- 路径是否正确
- 文件是否存在
- 是否 `chmod +x`

### Q3：我只想重部署，不想拉代码
可直接执行你设置的 `RUN_SCRIPT`。  
如果你仍想走 `update.sh`，在提示时输入 `y` 可强制重部署。

## 7. 建议

- 把 `RUN_SCRIPT` 做成你团队统一模板（停止旧容器/进程 -> 启动新实例）
- 保持 `update.sh` 只负责“编排流程”，具体部署细节放在 `RUN_SCRIPT`
- 线上与本地可以维护两套 `RUN_SCRIPT`，减少误操作
