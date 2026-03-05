# 版本发布流程（防遗忘手册）

本文用于记录本项目的标准发布步骤。按本文执行即可完成从版本同步到 GitHub Release 的发布流程。

## 一、当前发布机制

- 版本号唯一来源：`app/version.yml`
- 版本同步脚本：`scripts/sync_version.py`
- 一键打 tag 并推送（PowerShell）：`scripts/release_tag.ps1`
- 一键打 tag 并推送（Shell）：`scripts/release_tag.sh`
- Docker 镜像推送脚本：`scripts/docker_push.sh`
- GitHub Release 自动创建：`.github/workflows/release.yml`
- Release 正文来源：`README.md` 的 `## 当前版本` 区块（由 `scripts/build_release_notes.py` 自动提取）

## 二、每次发布前要做的事

1. 功能开发完成并已本地验证。
2. 准备本次版本号（`X.Y.Z`）。
3. 在 `doc/logs/` 新建或更新本次版本日志：
   - 文件名：`vX.Y.Z_update_log.md`
4. 更新 `README.md` 的 `## 当前版本` 内容（面向用户的简要说明）。

## 三、实际发布步骤

1. 修改 `app/version.yml`：
   - `project_version`
   - `tampermonkey_version`（如本次有油猴脚本改动）
   - `chrome_extension_version`（如本次有扩展改动）

2. 运行版本同步（可单独执行）：
   ```bash
   python3 scripts/sync_version.py
   ```

3. 执行一键发布脚本（手动，二选一）：
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\release_tag.ps1
   ```
   ```bash
   bash scripts/release_tag.sh
   ```

4. 脚本会自动执行：
   - 校验当前分支为 `main`
   - 检查目标 tag 是否已存在（存在则停止）
   - 输出发布信息并等待确认
   - `git tag vX.Y.Z`
   - `git push origin HEAD`
   - `git push origin vX.Y.Z`
   - Shell 版在 GitHub 推送完成后，会额外询问是否执行 `scripts/docker_push.sh` 推送 Docker 镜像（`latest` + 当前版本标签）

5. 推送 tag 后，GitHub Actions 自动创建 Release。

## 四、tag 已存在时的行为

- 当前两个发布脚本都会在“创建 tag 前”检查 tag 是否已存在。
- 如果 tag 已存在，脚本会提示并立即终止，不会继续执行任何 tag/push 动作。
- 脚本不会自动 commit，代码提交需人工提前完成。

## 五、发布后检查清单

- GitHub 仓库 `Releases` 页面已出现对应 `vX.Y.Z`
- Release 正文内容正确（与 README 当前版本区块一致）
- Release 附带 `Source code (zip/tar.gz)`
- README 与 `doc/logs/vX.Y.Z_update_log.md` 内容一致

## 六、与 AI 协作约定

每次功能开发完成后，按下面节奏协作：

1. 你告诉 AI 本次版本号（`X.Y.Z`）。
2. AI 负责总结更新内容并执行版本同步脚本。
3. 你手动执行 `scripts/release_tag.ps1` 发布版本。
