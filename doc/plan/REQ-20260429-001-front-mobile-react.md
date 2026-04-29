# Figma React 前端接入移动端聚合接口设计

## 1. 目标

在不破坏 `figma/Makerworldarchiveuniapp` 现有视觉结构和交互骨架的前提下，将核心 4 页从 `mockData` 切换为真实后端数据：

- `Overview`
- `Library`
- `Archive`
- `ModelDetail`

本轮聚焦“可真实浏览、可提交归档、可查看详情”，不扩展额外管理能力，不重写 UI，不迁移到 `uniapp`。

## 2. 范围

### 本轮包含

- 新增统一 API 请求层
- 新增页面级数据加载与错误处理
- 将 4 个核心页面改为请求 `/api/mobile/*`
- 补齐基础 `loading / error / empty` 状态
- 保持现有页面结构、配色、导航方式基本不变

### 本轮不包含

- 迁移到 `uniapp`
- 引入全局状态管理
- 大规模重构组件树
- 扩展收藏管理、删除模型、深度设置保存等高级写操作

## 3. 方案选择

### 方案 A：统一 API 层 + 页面最小改造

每个页面继续保留当前结构，但不再直接使用 `mockData`，而是通过统一的 API 模块请求后端聚合接口，并在页面内部维护自己的加载状态。

优点：

- 改动集中，利于后续继续接 `Settings / ScanImport / OrganizeDir`
- 页面不会重复写请求细节和 URL 拼接
- 风险最低，最贴合当前项目状态

缺点：

- 仍然是页面级状态，不是完整的数据层架构

### 方案 B：每页直连接口

优点是更快，但会造成重复请求逻辑、重复类型定义和重复错误处理，不适合这个项目接下来继续扩展。

### 方案 C：先上全局状态层

长期更完整，但本轮范围太小，投入不划算。

### 结论

采用方案 A。

## 4. 页面接入设计

### 4.1 Overview

接口：

- `GET /api/mobile/overview`

页面行为：

- 加载模型总数
- 渲染快捷操作
- 渲染最近更新列表
- 点击最近更新进入 `/model/:id`

状态：

- 首屏加载文案或轻量骨架
- 请求失败时展示重试提示

### 4.2 Library

接口：

- `GET /api/mobile/library`

页面行为：

- 渲染模型列表
- 本地搜索仍在前端完成
- 当前页已有的视图切换、筛选抽屉、菜单弹层先保留
- 对暂无真实后端支持的筛选项，先用前端已有数据字段做轻筛选

状态：

- 初始加载
- 请求失败
- 空列表

### 4.3 Archive

接口：

- `GET /api/mobile/archive-center`
- `POST /api/archive`
- `POST /api/logs/missing-3mf/redownload`

页面行为：

- 归档输入框提交真实归档任务
- 任务队列使用真实队列数据
- 缺失文件列表使用真实缺失文件数据
- “重新下载所有” 对接现有批量重试接口
- 单条“重新下载”若后端当前没有稳定单项接口，则先保留按钮但走轻提示或同批量策略

状态：

- 提交中
- 刷新中
- 请求失败
- 空队列 / 空缺失列表

### 4.4 ModelDetail

接口：

- `GET /api/mobile/models/{model_dir}`

页面行为：

- 读取模型基础详情
- 轮播图展示图片
- 配置实例展示真实实例数据
- 附件列表展示真实附件
- “打开源网页”打开真实源链接

状态：

- 详情加载中
- 模型不存在
- 请求失败

## 5. 前端结构设计

建议最小新增以下结构：

- `src/app/lib/api.ts`
  - 统一封装 `fetch`
  - 统一处理 JSON、异常、基础 base URL
- `src/app/lib/mobile-api.ts`
  - 导出 `getOverview`、`getLibrary`、`getArchiveCenter`、`createArchiveTask`、`getModelDetail`
- `src/app/types/mobile.ts`
  - 定义与 `/api/mobile/*` 对应的前端类型

现有页面文件继续保留：

- `src/app/pages/Overview.tsx`
- `src/app/pages/Library.tsx`
- `src/app/pages/Archive.tsx`
- `src/app/pages/ModelDetail.tsx`

`mockData.ts` 本轮不强制删除，但核心 4 页不再依赖它。

## 6. 数据流设计

### 总体原则

- 每个页面自己请求自己所需的数据
- 不引入全局 store
- 请求逻辑从 UI 中抽离到 API 模块

### 页面数据流

- `Overview`
  - mount -> `getOverview()` -> render
- `Library`
  - mount -> `getLibrary()` -> 前端搜索/筛选 -> render
- `Archive`
  - mount -> `getArchiveCenter()`
  - submit -> `createArchiveTask()`
  - success 后刷新 `getArchiveCenter()`
- `ModelDetail`
  - route param `id` -> `getModelDetail(id)` -> render

## 7. 错误处理

统一约定：

- 网络失败：展示“加载失败，请重试”
- 404 详情页：展示“未找到模型”
- 提交归档失败：展示后端返回错误
- 空数据：展示友好空态，不让页面留白

## 8. 测试与验证

本轮至少验证：

- 前端可以构建通过
- 4 个页面不再引用 `mockData` 作为主数据源
- 归档提交成功后队列能刷新
- 模型详情可打开真实模型
- 当接口失败时页面不会崩溃

## 9. 风险与边界

### 风险 1：Figma 原型字段和真实接口字段不完全一致

处理方式：

- 在 `mobile-api.ts` 中做轻映射
- 不把映射散落到页面中

### 风险 2：原型中某些交互暂时没有完全匹配的后端能力

处理方式：

- 保留交互外观
- 对未完成行为降级为禁用、提示或仅本地展示

### 风险 3：后端返回路径可能是相对路径

处理方式：

- API 层统一做 URL 归一化

## 10. 结论

本轮采用“统一 API 层 + 页面最小改造”的方式，把 Figma React 原型升级为可真实连接项目后端的移动端 H5 前端。这样既保住当前设计成果，也为后续继续接入剩余页面留下最小阻力路径。
