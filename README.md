# 3D打印本地模型管理工具

![mw_archive](https://aliyun-wb-h9vflo19he.oss-cn-shanghai.aliyuncs.com/use/makerworld_archive.png)

一个面向本地模型管理的工具，支持 3MF 文件上传解析、模型库浏览与维护；

## 当前版本
- `v5.2.3`
- 更新说明见 [doc/logs/v5.2.3_update_log.md](doc/logs/v5.2.3_update_log.md)
- 本次重点：修复暗黑模式下手动导入弹窗显示问题；新增归档更新独立日志，记录跳过/失败/未定位明细。

## 核心能力
- 本地上传 3MF 后自动解析并入库，快速建立个人模型库
- 模型库支持浏览、搜索、筛选与状态标记（如收藏、已打印）
- 支持手动导入本地模型与附件管理，便于整理历史文件
- 解析结果可直接用于本地详情页查看，减少反复打开源站
- 提供缺失文件记录与重试机制，降低导入失败后的手工处理成本
- 支持批量修复/重建历史页面，版本升级后可一键同步旧数据展示效果
- 支持通过浏览器插件/油猴脚本从 MakerWorld 快速导入模型（辅助能力）

## 项目结构
```text
mw_archive/
├─ app/
│  ├─ archiver.py
│  ├─ server.py
│  ├─ config.json
│  ├─ cookie.txt
│  ├─ data/
│  ├─ logs/
│  ├─ static/
│  └─ templates/
├─ plugin/
│  ├─ chrome_extension/
│  │  ├─ mw_quick_archive_ext/
│  │  └─ 使用说明.md
│  └─ tampermonkey/
│     ├─ mw_quick_archive.user.js
│     └─ 使用说明.md
├─ scripts/
├─ doc/
├─ Dockerfile
├─ docker_build.sh
└─ update.sh
```

## 页面
![主页](doc/screenshot/主页.png)
![模型详情](doc/screenshot/模型详情.png)

## 运行环境
- Python `3.10+`（建议 `3.11`）
- 依赖见 [app/requirements.txt](app/requirements.txt)
- 可选：Docker

## 本地启动
```bash
cd app
python -m venv .venv
# Windows
. .venv/Scripts/activate
# macOS/Linux
# source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

默认地址：
- 模型库：`http://127.0.0.1:8000/`
- 配置页：`http://127.0.0.1:8000/config`

## Docker 启动
在当前目录下，**先创建 `app/data`、`app/logs` 目录和 `app/cookie.txt` 空文件**

> 注: logs和cookie.txt不是必须的，可以不挂载

```bash
# 直接拉取
docker run -d \
  --name mw-archiver \
  -p 8000:8000 \
  -v $PWD/app/data:/app/data \
  -v $PWD/app/logs:/app/logs \
  -v $PWD/app/cookie.txt:/app/cookie.txt \
  sonicming/mw-archiver:latest
```

如果网络问题可以更换镜像源 `docker.1ms.run/sonicming/mw-archiver:latest`

```bash
# 本地构建
bash docker_build.sh

docker run -d \
  --name mw-archiver \
  -p 8000:8000 \
  -v $PWD/app/data:/app/data \
  -v $PWD/app/logs:/app/logs \
  -v $PWD/app/cookie.txt:/app/cookie.txt \
  mw-archiver
```

### Docker 参数详细说明

* **`-d`**：后台运行容器（detach 模式），容器启动后不会阻塞当前终端。
* **`--name mw-archiver`**：为容器指定一个自定义名称标识（即 `mw-archiver`），方便后续使用 `docker logs mw-archiver` 或 `docker stop mw-archiver` 进行管理。
* **`-p 8000:8000`**：端口映射，格式为 `宿主机端口:容器内端口`。将容器内部的 `8000` 端口映射给宿主机的 `8000` 端口，启动后即可通过 `http://localhost:8000` 访问网页服务。
* **`-v $PWD/app/data:/app/data`**：数据目录映射（Volume）。将宿主机当前目录下的 `app/data` 挂载到容器内的 `/app/data`，使得所有归档下载的模型（3MF 文件、图片等数据）持久化保存在宿主机中，**防止容器重启或重建时数据丢失**。
* **`-v $PWD/app/logs:/app/logs`**(非必须)：日志目录映射。将运行日志和错误信息（如缺失 3MF 的记录日志）保存到宿主机，方便排查使用。
* **`-v $PWD/app/cookie.txt:/app/cookie.txt`**(非必须)：Cookie 凭证文件映射。此文件用于 MakerWorld 下载模型所需的认证信息。挂载出来便于配置持久化（即使在网页后端自动更新或重写了它的内容，宿主机上的文件也会同步更新）。*[注意：在首次执行 docker run 之前，如果 `app/cookie.txt` 在宿主机不存在，可能会被 Docker 错误识别并创建为目录，可以先在本地执行 `touch app/cookie.txt` 创建空文件]*。
* **`sonicming/mw-archiver:latest`**：启动使用的 Docker 镜像名称以及对应的版本标签（latest）。

## Docker Compose 启动

创建 `docker-compose.yml` 文件：

> 注: logs和cookie.txt不是必须的，可以不挂载

```yaml
version: '3.8'

services:
  mw-archiver:
    image: sonicming/mw-archiver:latest
    container_name: mw-archiver
    ports:
      - "8000:8000"
    volumes:
      - ./app/data:/app/data
      - ./app/logs:/app/logs
      - ./app/cookie.txt:/app/cookie.txt
    restart: unless-stopped
```

在同级目录下，**确保已经创建了 `app/data`、`app/logs` 目录和 `app/cookie.txt` 空文件**，然后执行以下命令将服务放置在后台启动：

```bash
docker-compose up -d
```


## 配置说明
### 配置文件
一般不用修改

配置文件为 [app/config.json](app/config.json)：

```json
{
  "download_dir": "./data",
  "cookie_file": "./cookie.txt",
  "logs_dir": "./logs"
}
```

### 完整cookie获取
随便打开一个模型，按f12，选择network，然后刷新页面，找到请求，复制cookie

![cookie](doc/screenshot/完整cookie获取.png)


**cookie失效问题：**
有时候cookie并不是失效了，而是触发了验证，需要手动下载一个模型解决验证

![cookie手动验证](doc/screenshot/cookie手动验证.png)

之后尽快在控制台重新下载模型
![重新下载](doc/screenshot/重新下载.png)

## 常用流程
http://127.0.0.1:8000
1. 在 `/config` 设置 Cookie（或调用 `POST /api/cookie`）。
2. 在 `/config` 输入模型链接执行归档（或调用 `POST /api/archive`）。
3. 若同模型再次归档，系统自动执行更新。
4. 归档历史样式升级时，点击“归档修复”中的“一键更新历史归档”或调用 `POST /api/archive/rebuild-pages`。
5. 在 `/` 模型库查看、筛选、标记和打开本地模型页面。

注: 为减少触发验证,目前只能一次归档一个模型.

## API 清单
> 详细的接口、传参示例和返回说明，请参见完整的 [API 接口文档 (doc/api.md)](doc/readme/api.md)

## 插件说明
Chrome 插件：
- 一键归档
- 目录：`plugin/chrome_extension/mw_quick_archive_ext`
- 说明：[plugin/chrome_extension/使用说明.md](plugin/chrome_extension/使用说明.md)

油猴脚本：
- 一键归档
- 文件：`plugin/tampermonkey/mw_quick_archive.user.js`
- 说明：[plugin/tampermonkey/使用说明.md](plugin/tampermonkey/使用说明.md)
- 直接安装插件地址 [地址](https://github.com/sonicmingit/mw_archive_py/raw/refs/heads/main/plugin/tampermonkey/mw_quick_archive.user.js)

## 脚本说明
- `update.sh`：更新与部署编排脚本，支持 `git pull` 无更新时确认是否继续重部署。详细用法与“快速本地构建更新”配置见 [doc/readme/update_sh_usage.md](doc/readme/update_sh_usage.md)。
- `app/version.yml`：统一版本源（项目、油猴、Chrome 扩展版本）。
- `scripts/sync_version.py`：将 `app/version.yml` 的版本同步到项目文件。
- `scripts/release_tag.ps1`：一键执行“版本同步 -> commit -> 打 tag -> push”；推送 `v*` tag 后会由 GitHub Actions 自动创建 Release。
- `scripts/rebuild_index_from_meta.py`：根据 `meta.json` 重建归档页面（兼容场景）。

## 文档目录
- [api.md (API 接口文档)](doc/readme/api.md)
- [meta.json 字段说明](doc/readme/meta_json_fields.md)
- [Bug 跟踪说明与模板](doc/bugs/README.md)
- [需求开发记录说明与模板](doc/plan/README.md)
- [版本日志说明与模板索引](doc/logs/README.md)
- [update.sh 使用说明](doc/readme/update_sh_usage.md)
- [项目架构与功能文档.md](doc/archives项目架构与功能文档.md)

## License
本项目采用 [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) 开源协议。
