# UI 重构设计方案

## 目标

将本地模型库的 `gallery.html` 和 `config.html` 重构为仿照 MakerWorld 官网的现代化设计风格,提升用户体验和视觉美感。

---

## MakerWorld 设计特征分析

### 配色方案
- **主色调**: 
  - 品牌蓝: `#00B8D4` (青蓝色,用于主要按钮和链接)
  - 深色背景: `#1A1A1A` - `#2D2D2D` (导航栏、卡片背景)
  - 浅色背景: `#F5F5F5` - `#FAFAFA` (页面背景)
- **辅助色**:
  - 成功绿: `#4CAF50`
  - 警告橙: `#FF9800`
  - 错误红: `#F44336`
- **文字颜色**:
  - 主文字: `#212121`
  - 次要文字: `#757575`
  - 禁用文字: `#BDBDBD`

### 布局特点
1. **顶部导航栏**
   - 固定在顶部,高度约 64px
   - 左侧 Logo + 导航菜单
   - 右侧搜索框 + 用户头像/登录按钮
   - 半透明背景 + 毛玻璃效果(backdrop-filter)

2. **模型卡片网格**
   - 响应式网格布局 (Grid)
   - 桌面: 4-5 列
   - 平板: 2-3 列
   - 手机: 1-2 列
   - 卡片悬浮效果 (hover 时阴影加深、轻微上移)

3. **卡片设计**
   - 圆角: 12px
   - 封面图片: 16:9 或 1:1 比例
   - 底部信息区: 标题 + 作者 + 统计数据
   - 标签: 小型圆角胶囊样式

4. **筛选侧边栏**
   - 固定宽度 240-280px
   - 分组折叠面板
   - 复选框 + 滑块样式

### 交互模式
- **卡片悬浮**: 阴影从 2px 增加到 8px,Y 轴上移 -4px
- **按钮点击**: 轻微缩放 (scale: 0.98)
- **加载动画**: 骨架屏 (Skeleton) 或旋转加载器
- **平滑过渡**: 所有交互使用 `transition: all 0.3s ease`

### 字体排版
- **主字体**: "Inter", "PingFang SC", "Microsoft YaHei", sans-serif
- **标题**: 
  - H1: 32px, font-weight: 700
  - H2: 24px, font-weight: 600
  - H3: 18px, font-weight: 600
- **正文**: 14px, font-weight: 400
- **小字**: 12px, font-weight: 400

---

## 设计改进方案

### Gallery 页面重构

#### 1. 顶部导航栏
```
┌─────────────────────────────────────────────────────────────┐
│ 🏠 本地模型库    [搜索框...]          [手动导入] [配置]  │
└─────────────────────────────────────────────────────────────┘
```

**改进点**:
- 固定顶部,滚动时不消失
- 搜索框集成到导航栏,实时搜索
- 添加面包屑导航
- 毛玻璃背景效果

#### 2. 筛选区域
```
┌──────────┐  ┌─────────────────────────────────────────────┐
│ 来源     │  │ [全部] [收藏] [已打印]                      │
│ □ MW     │  │                                             │
│ □ Others │  │ 排序: [最新采集 ▼]  显示: [20/页 ▼]       │
│          │  └─────────────────────────────────────────────┘
│ 分类     │
│ □ 工具   │
│ □ 装饰   │
│ ...      │
│          │
│ 作者     │
│ □ 作者A  │
│ □ 作者B  │
└──────────┘
```

**改进点**:
- 左侧固定侧边栏,可折叠
- 分组使用手风琴折叠面板
- 复选框使用现代化样式
- 顶部快速筛选标签

#### 3. 模型卡片
```
┌─────────────────────┐
│                     │
│   [封面图片]        │
│                     │
├─────────────────────┤
│ 模型标题            │
│ 👤 作者名           │
│ ❤️ 100  💾 50  👁️ 1K │
│ [标签1] [标签2]     │
└─────────────────────┘
```

**改进点**:
- 封面图片使用 object-fit: cover
- 悬浮时显示更多信息(摘要、实例数)
- 收藏/打印状态用角标显示
- 统计数据使用图标 + 数字
- 标签限制显示 3 个,更多用 +N 表示

#### 4. 响应式布局
- **桌面 (>1200px)**: 4 列网格
- **平板 (768-1200px)**: 3 列网格
- **手机 (<768px)**: 2 列网格,侧边栏折叠为抽屉

### Config 页面重构

#### 1. 整体布局
```
┌─────────────────────────────────────────────────────────────┐
│ ← 返回模型库                    归档控制台 v2.2  │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│ │ 📁 配置信息  │  │ 📦 模型归档  │  │ 📋 缺失记录  │         │
│ └─────────────┘  └─────────────┘  └─────────────┘         │
│                                                             │
│ [选项卡内容区域]                                            │
│                                                             │
│ [实时日志窗口 - 固定底部]                                   │
└─────────────────────────────────────────────────────────────┘
```

**改进点**:
- 使用选项卡(Tabs)组织内容
- 实时日志固定在底部,可折叠
- 卡片式布局,增加视觉层次
- 添加操作确认对话框

#### 2. 配置表单
- 使用现代化输入框样式
- 添加输入验证提示
- Cookie 输入框添加显示/隐藏切换
- 保存成功后显示 Toast 提示

#### 3. 缺失记录表格
- 使用条纹表格样式
- 添加分页功能
- 支持批量操作
- 状态用彩色标签显示

---

## 技术实现方案

### CSS 架构
```
static/css/
├── variables.css      # CSS 变量定义
├── reset.css          # 样式重置
├── layout.css         # 布局样式
├── components.css     # 通用组件
├── gallery.css        # 模型库专用
└── config.css         # 配置页专用
```

### 关键 CSS 变量
```css
:root {
  /* 颜色 */
  --color-primary: #00B8D4;
  --color-primary-dark: #0097A7;
  --color-success: #4CAF50;
  --color-warning: #FF9800;
  --color-error: #F44336;
  
  /* 背景 */
  --bg-page: #FAFAFA;
  --bg-card: #FFFFFF;
  --bg-dark: #1A1A1A;
  
  /* 文字 */
  --text-primary: #212121;
  --text-secondary: #757575;
  --text-disabled: #BDBDBD;
  
  /* 间距 */
  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-md: 16px;
  --spacing-lg: 24px;
  --spacing-xl: 32px;
  
  /* 圆角 */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  
  /* 阴影 */
  --shadow-sm: 0 2px 4px rgba(0,0,0,0.1);
  --shadow-md: 0 4px 8px rgba(0,0,0,0.12);
  --shadow-lg: 0 8px 16px rgba(0,0,0,0.15);
  
  /* 过渡 */
  --transition-fast: 0.15s ease;
  --transition-base: 0.3s ease;
  --transition-slow: 0.5s ease;
}
```

### 响应式断点
```css
/* 手机 */
@media (max-width: 767px) { ... }

/* 平板 */
@media (min-width: 768px) and (max-width: 1199px) { ... }

/* 桌面 */
@media (min-width: 1200px) { ... }
```

---

## 组件设计

### 1. 模型卡片组件
```html
<div class="model-card">
  <div class="model-card__image">
    <img src="..." alt="...">
    <div class="model-card__badges">
      <span class="badge badge--favorite">❤️</span>
      <span class="badge badge--printed">✓</span>
    </div>
  </div>
  <div class="model-card__content">
    <h3 class="model-card__title">模型标题</h3>
    <div class="model-card__author">
      <img class="avatar avatar--sm" src="..." alt="作者">
      <span>作者名</span>
    </div>
    <div class="model-card__stats">
      <span><i class="icon-heart"></i> 100</span>
      <span><i class="icon-download"></i> 50</span>
      <span><i class="icon-eye"></i> 1K</span>
    </div>
    <div class="model-card__tags">
      <span class="tag">标签1</span>
      <span class="tag">标签2</span>
      <span class="tag tag--more">+3</span>
    </div>
  </div>
</div>
```

### 2. 搜索框组件
```html
<div class="search-box">
  <i class="search-box__icon icon-search"></i>
  <input 
    type="text" 
    class="search-box__input" 
    placeholder="搜索模型..."
  >
  <button class="search-box__clear" aria-label="清除">
    <i class="icon-close"></i>
  </button>
</div>
```

### 3. 筛选侧边栏组件
```html
<aside class="sidebar">
  <div class="sidebar__section">
    <h4 class="sidebar__title">来源</h4>
    <div class="checkbox-group">
      <label class="checkbox">
        <input type="checkbox" value="makerworld">
        <span class="checkbox__label">MakerWorld</span>
        <span class="checkbox__count">(120)</span>
      </label>
    </div>
  </div>
</aside>
```

---

## 验证计划

### 自动化测试
由于项目当前没有前端测试框架,暂不添加自动化测试。

### 手动验证

#### 1. 视觉验证
- [ ] 在 Chrome/Firefox/Edge 浏览器中打开 `http://localhost:8000`
- [ ] 检查配色是否符合设计规范
- [ ] 检查字体、间距、圆角是否一致
- [ ] 检查卡片悬浮效果是否流畅

#### 2. 响应式验证
- [ ] 调整浏览器窗口宽度到 1920px (桌面)
  - 验证: 模型卡片应显示 4 列
  - 验证: 侧边栏应固定显示
- [ ] 调整浏览器窗口宽度到 768px (平板)
  - 验证: 模型卡片应显示 2-3 列
  - 验证: 侧边栏应可折叠
- [ ] 调整浏览器窗口宽度到 375px (手机)
  - 验证: 模型卡片应显示 1-2 列
  - 验证: 侧边栏应折叠为抽屉菜单

#### 3. 功能验证
- [ ] 搜索功能: 输入关键词,验证实时筛选
- [ ] 筛选功能: 勾选分类/作者,验证卡片过滤
- [ ] 排序功能: 切换排序方式,验证卡片顺序
- [ ] 分页功能: 点击页码,验证页面跳转
- [ ] 收藏/打印标记: 点击标记,验证状态保存

#### 4. 配置页验证
- [ ] Cookie 保存: 输入 Cookie 并保存,验证成功提示
- [ ] 模型归档: 输入 URL 并归档,验证实时日志输出
- [ ] 缺失记录: 点击重试,验证下载进度

---

## 实施步骤

### 阶段 1: 设计资源准备 (当前)
- [x] 创建设计文稿
- [ ] 生成 UI 设计图
- [ ] 准备图标资源

### 阶段 2: CSS 重构
- [ ] 创建 CSS 变量文件
- [ ] 重构 gallery.css
- [ ] 重构 config.css
- [ ] 添加响应式样式

### 阶段 3: HTML 重构
- [ ] 重构 gallery.html 结构
- [ ] 重构 config.html 结构
- [ ] 更新 JavaScript 逻辑

### 阶段 4: 测试与优化
- [ ] 手动功能测试
- [ ] 响应式测试
- [ ] 性能优化
- [ ] 浏览器兼容性测试

---

## 风险与注意事项

### 潜在风险
1. **JavaScript 兼容性**: 现有 JS 代码可能需要调整以适配新的 DOM 结构
2. **性能影响**: 复杂的 CSS 效果可能影响低端设备性能
3. **浏览器兼容性**: 毛玻璃效果(backdrop-filter)在旧浏览器中不支持

### 解决方案
1. 保持 DOM 结构的类名和 ID 不变,仅调整样式
2. 使用 CSS `will-change` 优化动画性能
3. 为不支持的特性提供降级方案

---

## 用户审核要点

> [!IMPORTANT]
> **需要用户确认的设计决策**

1. **配色方案**: 是否使用 MakerWorld 的青蓝色 (#00B8D4) 作为主色调?
2. **布局方式**: 是否采用左侧固定侧边栏 + 右侧卡片网格的布局?
3. **卡片样式**: 是否使用圆角卡片 + 悬浮阴影效果?
4. **响应式策略**: 手机端是否将侧边栏折叠为抽屉菜单?
5. **图标库**: 是否需要引入图标库(如 Font Awesome 或 Material Icons)?

---

**文档版本**: v1.0  
**创建时间**: 2026-01-30  
**状态**: 等待用户审核
