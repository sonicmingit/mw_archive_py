# Figma React 剩余页面接入设计

## 1. 目标

继续保留 `figma/Makerworldarchiveuniapp` 现有页面结构与视觉风格，将剩余 3 页接入真实后端能力：

- `Settings`
- `ScanImport`
- `OrganizeDir`

本轮目标是做到“真实读取、真实触发、有限保存”，不为了追求一步到位而扩散到大量额外协议设计。

## 2. 范围

### 本轮包含

- `Settings` 读取真实设置和工具配置
- `ScanImport` 使用真实批量导入能力
- `OrganizeDir` 使用真实整理目录能力
- 补齐这些页面的 `loading / error / success` 状态
- 延续已有前端 API 层，避免页面直接散落请求逻辑

### 本轮不包含

- 完整重做设置表单协议
- Cookie 精细化增删改校验
- 所有通知通道的完整保存/测试能力一次性打通
- 大规模调整现有页面交互结构

## 3. 方案选择

采用方案 A：

保留现有 UI 和交互层次，只把它们接到已补好的 `/api/mobile/settings`、`/api/mobile/tools`，并对接最稳定的现有写接口完成“能读、能触发、有限保存”。

优点：

- 与前面 4 页的接法一致
- 风险最低
- 能最快把整套原型变成真实前端

## 4. 页面设计

### 4.1 Settings

读取接口：

- `GET /api/mobile/settings`
- `GET /api/mobile/tools`

已存在的可复用后端写接口：

- `POST /api/notify-config`
- `POST /api/notify-test`
- `POST /api/cookies`
- `POST /api/local-batch-import/config`
- `POST /api/local-3mf-organizer/config`

设计原则：

- 先把页面改成真实读数据
- 对保存按钮采用“按区块保存”的保守方式
- 只接最明确稳定的保存路径，避免一次性把所有字段写错

具体行为：

- “测试连接”使用真实后端地址做健康请求
- 通知配置页展示真实 Telegram / Feishu / Wecom 状态
- 任务设置页展示真实监控目录和整理目录配置
- Cookie 页展示真实国内/国际 Cookie 数量和状态概览

### 4.2 ScanImport

读取接口：

- `GET /api/mobile/tools`

写接口：

- `POST /api/local-batch-import/scan`
- 如现有返回结构更适合，则兼容 `POST /api/local-batch-import/run`

具体行为：

- 默认填入真实 `watchDirs[0]`
- 作者输入框先作为前端保留字段；如果后端当前不消费，就不强行透传
- 点击后触发真实扫描并显示真实统计结果

### 4.3 OrganizeDir

读取接口：

- `GET /api/mobile/tools`

写接口：

- `POST /api/local-3mf-organizer/run`

具体行为：

- 默认填入真实 `rootDir`
- 开始整理触发真实后端任务
- 展示真实处理结果摘要

## 5. 前端结构设计

沿用已有 API 层，新增最小能力：

- `src/app/lib/mobile-api.ts`
  - 增加 `getSettings`
  - 增加 `getTools`
  - 增加 `runScanImport`
  - 增加 `runOrganizer`
  - 如保存能力稳定，再增加 `saveNotifyConfig` / `saveCookies`

- `src/app/types/mobile.ts`
  - 增加设置页、工具页、扫描结果、整理结果类型

## 6. 状态设计

每页都要补齐：

- 初始加载中
- 请求失败
- 提交中
- 成功反馈

交互降级原则：

- 如果某个写接口当前协议不稳定，按钮保留，但只做提示，不做危险写入

## 7. 风险控制

### 风险 1：现有设置页字段和真实后端配置结构并不 1:1

处理方式：

- 优先真实展示
- 保存只接后端明确定义的字段
- 不为了“表单全能保存”而冒险覆盖未知配置

### 风险 2：扫描和整理返回结构可能与原型统计字段不一致

处理方式：

- 在 API 层做一次映射
- 页面只消费映射后的统一类型

### 风险 3：设置页的测试行为没有统一健康接口

处理方式：

- 连接测试使用真实 GET 请求到后端聚合接口
- 不额外发明新的健康检查协议

## 8. 验证

本轮至少验证：

- `Settings / ScanImport / OrganizeDir` 页面构建通过
- 默认值来自真实后端
- 扫描和整理按钮可真实触发
- 请求失败不会让页面崩溃

## 9. 结论

本轮继续采用前面已经验证有效的“统一 API 层 + 页面最小改造”模式，把剩余 3 页补齐为真实可用页面，并把高风险保存动作控制在稳定边界内。
