# 版本更新日志说明与模板

本目录用于记录每次版本发布的更新日志，并维护 README「当前版本」区块的同步记录，便于后续追溯。

## 目录规则

- 版本日志文件命名：`vX.Y.Z_update_log.md`
- 每个版本一个独立日志文件
- 推荐在发布前完成日志内容编写，并与根目录 `README.md` 的「## 当前版本」保持一致

## 记录建议

- `更新概述`：面向用户，说明本次重点变化
- `详细变更`：按新增 / 优化 / 修复分组
- `涉及文件`：列出核心改动文件与作用
- `README 当前版本同步记录`：每次改动根 `README.md` 的当前版本区块后，补一条同步记录

## 版本更新日志模板

```markdown
# vX.Y.Z 更新日志

> 更新日期: YYYY-MM-DD

## 更新概述
简要说明本次版本的核心变化与目标价值。

## 详细变更

### 新增功能
- ...

### 优化改进
- ...

### Bug 修复
- ...

## 兼容性与注意事项
- 是否存在兼容性变化：
- 升级建议：

## 涉及文件
- `path/to/file` - 变更说明

## 验证记录
- 自测范围：
- 自测结果：
- 待验证项：
```

## README 当前版本同步记录

用于记录根目录 `README.md` 中「## 当前版本」区块的每次同步内容，便于和版本日志、Release 文案对齐追溯。

### 记录模板

```markdown
## YYYY-MM-DD HH:mm
- 版本号：
- 更新说明链接：
- 本次重点：
- 同步人：
- 备注：
```

### 历史记录

#### 2026-03-06 11:35
- 版本号：`v5.3`
- 更新说明链接：[`doc/logs/v5.3_update_log.md`](./v5.3_update_log.md)
- 本次重点：新增 Telegram 推送与机器人交互；新增国内 / 国际平台 Cookie 支持；Docker 部署改为推荐持久化 `app/config/` 目录。
- 同步人：AI（Codex）
- 备注：同步根 `README.md` 当前版本区块，并补充 Docker 升级说明。

#### 2026-03-05 17:40
- 版本号：`v5.2.3`
- 更新说明链接：[`doc/logs/v5.2.3_update_log.md`](./v5.2.3_update_log.md)
- 本次重点：修复暗黑模式下手动导入弹窗显示问题；新增归档更新独立日志，记录跳过/失败/未定位明细。
- 同步人：AI（Codex）
- 备注：发布前同步根 `README.md` 当前版本区块。

#### 2026-03-05 20:10
- 版本号：`v5.2.2`
- 更新说明链接：[`doc/logs/v5.2.2_update_log.md`](./v5.2.2_update_log.md)
- 本次重点：修复归档同名实例文件覆盖问题；新增实例 `fileName` 记录并统一重下载路径的防覆盖策略。
- 同步人：AI（Codex）
- 备注：发布前同步根 `README.md` 当前版本区块。

#### 2026-03-05 19:40
- 版本号：`v5.2.0`
- 更新说明链接：[`doc/logs/v5.2_update_log.md`](./v5.2_update_log.md)
- 本次重点：新增亮色/暗黑主题切换，主页与配置页支持一键切换；在线详情页（`/v2/files/...`）自动跟随主页主题。
- 同步人：AI（Codex）
- 备注：由根 `README.md` 当前版本区块同步补录。

## 版本日志索引

- [`v5.3_update_log.md`](./v5.3_update_log.md)
- [`v5.2.3_update_log.md`](./v5.2.3_update_log.md)
- [`v5.2.2_update_log.md`](./v5.2.2_update_log.md)
- [`v5.2_update_log.md`](./v5.2_update_log.md)
- [`v5.1.2_update_log.md`](./v5.1.2_update_log.md)
- [`v5.1.1_update_log.md`](./v5.1.1_update_log.md)
- [`v5.1_update_log.md`](./v5.1_update_log.md)
- [`v5.0_update_log.md`](./v5.0_update_log.md)
- [`v4.5_update_log.md`](./v4.5_update_log.md)
- [`v4.0_update_log.md`](./v4.0_update_log.md)
