# MakerWorld Archive - UI/UX 规范说明

## 1. 设计理念
参考 MakerWorld (https://makerworld.com.cn/zh) 风格
- **风格:** 极简、干净、现代。
- **主题:** 支持明亮 (Light) 和暗黑 (Dark) 模式。
- **核心元素:** 3D模型卡片式展示、配置/详情使用居中浮层或独立页面、150-300ms 平滑过渡动画。

## 2. 配色方案
使用 Tailwind CSS 自定义配置。
- **主色调:** `#52C963` (Bambu 绿)
- **背景 (明亮):** `#FFFFFF` (白) 或 `#F8FAFC` (slate-50)
- **背景 (暗黑):** `#0F172A` (slate-900) 或 `#1E293B` (slate-800)
- **文字 (明亮):** `#0F172A` (slate-900) 用于标题, `#475569` (slate-600) 用于正文。
- **文字 (暗黑):** `#F8FAFC` (slate-50) 用于标题, `#94A3B8` (slate-400) 用于正文。
- **边框:** `border-gray-200` (明亮) / `border-slate-700` (暗黑)

## 3. 字体排印
- **字体栈:** 现代无衬线字体 (Inter, Roboto 或 Tailwind 默认无衬线字体)。
- **标题:** 粗体，高对比度。
- **正文:** 移动端最小 16px，易读的行距 (1.5 - 1.75)。

## 4. 布局与响应式
- **容器布局:** `max-w-7xl` mx-auto 居中布局。
- **模型网格:** 响应式的模型卡片网格 (`grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4`)。
- **页面与弹窗:** 居中浮窗或带背景模糊 (`backdrop-blur-sm`) 的沉浸式详情页。

## 5. UI/UX Pro Max 最佳实践
- **图标:** Lucide Icons (不使用 Emoji)。标准图标尺寸 `w-6 h-6`。
- **交互设计:**
  - 所有可点击元素统一使用 `cursor-pointer`。
  - Hover 悬浮状态仅改变颜色或透明度 (`transition-colors duration-200`)，不使用会导致布局抖动的 transform 动画。
  - 清晰的键盘聚焦框 `focus-visible:ring-2 focus-visible:ring-[#52C963]`。
- **无障碍访问:**
  - 保证高对比度 (最低 4.5:1)。
  - 设置页和表单标签必须使用正确的 `<label>`。
- **数据加载:** 获取数据时展示骨架屏或优雅的加载图标。

## 6. 技术栈
- **前端框架:** Vue 3 (Composition API) - CDN 引入
- **样式框架:** Tailwind CSS - CDN 引入
- **图标库:** Lucide Icons - CDN 引入 (`https://unpkg.com/lucide@latest`)
