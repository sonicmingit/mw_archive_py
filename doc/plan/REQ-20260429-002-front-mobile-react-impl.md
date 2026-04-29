# Figma React Mobile Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `figma/Makerworldarchiveuniapp` 的核心 4 页改为请求项目后端真实接口，并保留当前 Figma 原型的页面结构与视觉风格。

**Architecture:** 新增一个轻量前端 API 层和类型层，统一消费 `/api/mobile/*` 与少量现有写接口；页面内部用 `useEffect + useState` 管理加载、错误、空态和提交态，不引入全局 store。

**Tech Stack:** React 18, React Router 7, TypeScript, Vite, existing FastAPI mobile endpoints

---

### Task 1: Add the frontend API layer and shared mobile types

**Files:**
- Create: `figma/Makerworldarchiveuniapp/src/app/lib/api.ts`
- Create: `figma/Makerworldarchiveuniapp/src/app/lib/mobile-api.ts`
- Create: `figma/Makerworldarchiveuniapp/src/app/types/mobile.ts`
- Test: `figma/Makerworldarchiveuniapp/src/app/lib/mobile-api.ts`

- [ ] **Step 1: Write the failing test**

Create a tiny executable contract check for URL normalization and error propagation by importing the new API helpers from a temporary Node script and asserting they reject on non-OK responses.

- [ ] **Step 2: Run test to verify it fails**

Run: `node -e "import('./src/app/lib/mobile-api.ts').then(() => process.exit(1)).catch(() => process.exit(0))"`
Expected: FAIL because the files do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add:
- `api.ts` for `fetchJson`, `resolveApiUrl`, and `resolveAssetUrl`
- `mobile-api.ts` for `getOverview`, `getLibrary`, `getArchiveCenter`, `createArchiveTask`, `redownloadMissingFiles`, `getModelDetail`
- `mobile.ts` for page-facing interfaces only

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run build`
Expected: the new modules compile successfully.

- [ ] **Step 5: Commit**

```bash
git add figma/Makerworldarchiveuniapp/src/app/lib figma/Makerworldarchiveuniapp/src/app/types
git commit -m "feat: add mobile frontend api layer"
```

### Task 2: Connect Overview and Library to real data

**Files:**
- Modify: `figma/Makerworldarchiveuniapp/src/app/pages/Overview.tsx`
- Modify: `figma/Makerworldarchiveuniapp/src/app/pages/Library.tsx`
- Test: `figma/Makerworldarchiveuniapp/src/app/pages/Overview.tsx`
- Test: `figma/Makerworldarchiveuniapp/src/app/pages/Library.tsx`

- [ ] **Step 1: Write the failing test**

Remove `mockData` usage from both pages and wire imports to the new API/types so the pages fail to build until loading/error handling is added correctly.

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run build`
Expected: FAIL with missing state/typing/build errors after `mockData` is removed.

- [ ] **Step 3: Write minimal implementation**

Implement:
- `Overview` requests `/api/mobile/overview`
- `Library` requests `/api/mobile/library`
- both pages render loading, error, and empty states
- search remains local to the page

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add figma/Makerworldarchiveuniapp/src/app/pages/Overview.tsx figma/Makerworldarchiveuniapp/src/app/pages/Library.tsx
git commit -m "feat: connect overview and library pages"
```

### Task 3: Connect Archive to queue and submit endpoints

**Files:**
- Modify: `figma/Makerworldarchiveuniapp/src/app/pages/Archive.tsx`
- Test: `figma/Makerworldarchiveuniapp/src/app/pages/Archive.tsx`

- [ ] **Step 1: Write the failing test**

Replace `mockTasks` and inline missing-file arrays with typed API state so the page no longer compiles until real response handling is added.

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run build`
Expected: FAIL with unresolved state or type usage after the mock removal.

- [ ] **Step 3: Write minimal implementation**

Implement:
- initial load from `getArchiveCenter`
- submit flow using `createArchiveTask`
- refresh queue
- bulk redownload using `redownloadMissingFiles`
- graceful empty/error/submitting states

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add figma/Makerworldarchiveuniapp/src/app/pages/Archive.tsx
git commit -m "feat: connect archive center page"
```

### Task 4: Connect ModelDetail to real metadata

**Files:**
- Modify: `figma/Makerworldarchiveuniapp/src/app/pages/ModelDetail.tsx`
- Test: `figma/Makerworldarchiveuniapp/src/app/pages/ModelDetail.tsx`

- [ ] **Step 1: Write the failing test**

Remove `mockModels` dependency and switch the page to the mobile detail type so it fails to compile until async loading and null-state handling exist.

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run build`
Expected: FAIL with build/type errors after the mock dependency is removed.

- [ ] **Step 3: Write minimal implementation**

Implement:
- fetch by route `id`
- loading state before data arrives
- not-found and request-error fallback states
- real source URL action
- real attachments and instance modal data

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add figma/Makerworldarchiveuniapp/src/app/pages/ModelDetail.tsx
git commit -m "feat: connect model detail page"
```

### Task 5: Final verification and mock dependency cleanup

**Files:**
- Modify: `figma/Makerworldarchiveuniapp/src/app/data/mockData.ts`
- Test: `figma/Makerworldarchiveuniapp/package.json`

- [ ] **Step 1: Check remaining references to mock data**

Run: `Select-String -Path 'src\\app\\**\\*.ts*' -Pattern 'mockModels|mockTasks'`
Expected: no matches in the 4 connected pages.

- [ ] **Step 2: Run full frontend build**

Run: `npm run build`
Expected: PASS

- [ ] **Step 3: Summarize any intentionally deferred interactions**

Document if single-item missing-file retry or attachment preview remains UI-only.

- [ ] **Step 4: Commit**

```bash
git add figma/Makerworldarchiveuniapp/src/app/pages figma/Makerworldarchiveuniapp/src/app/data/mockData.ts doc/plan/REQ-20260429-002-front-mobile-react-impl.md
git commit -m "test: verify mobile frontend integration"
```
