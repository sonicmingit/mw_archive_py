let models = [];
let activeTag = "";
let activeAuthor = "";
let activeSource = "";
let activeFolder = "";
let onlyFavorites = false;
let onlyPrinted = false;
let useV2 = localStorage.getItem("useV2") === "true";
let compactMode = localStorage.getItem("mw_gallery_compact_mode") === "true";
let selectionMode = false;
let displayedCount = 20;
let loadIncrement = 20;
let isTagsExpanded = false;
let isAuthorsExpanded = false;
let currentLightboxList = [];
let currentLightboxIndex = 0;
const filterChipLimit = 12;
const authorChipLimit = 10;
const kwInput = document.getElementById("kw");
const filterChips = document.getElementById("filterChips");
const authorChips = document.getElementById("authorChips");
const sourceMenu = document.getElementById("sourceMenu");
const folderMenu = document.getElementById("folderMenu");
const clearBtn = document.getElementById("clearBtn");
const resetSearchBtn = document.getElementById("resetSearchBtn");
const totalCountEl = document.getElementById("totalCount");
const sortOrderSelect = document.getElementById("sortOrder");
const favOnlyBtn = document.getElementById("favOnlyBtn");
const printedOnlyBtn = document.getElementById("printedOnlyBtn");
const filterModal = document.getElementById("filterModal");
const filterModalTitle = document.getElementById("filterModalTitle");
const filterModalChips = document.getElementById("filterModalChips");
const lightbox = document.getElementById("lightbox");
const lightboxImg = document.getElementById("lightbox-img");
const lightboxCaption = document.getElementById("lightbox-caption");
const selectionToggleBtn = document.getElementById("selectionToggleBtn");
const compactToggleBtn = document.getElementById("compactToggleBtn");
const selectionBar = document.getElementById("selectionBar");
const selectedCountEl = document.getElementById("selectedCount");
const clearSelectionBtn = document.getElementById("clearSelectionBtn");
const addToFolderBtn = document.getElementById("addToFolderBtn");
const batchDeleteBtn = document.getElementById("batchDeleteBtn");
const folderModal = document.getElementById("folderModal");
const folderOptionList = document.getElementById("folderOptionList");
const newFolderNameInput = document.getElementById("newFolderName");
const newFolderDescriptionInput = document.getElementById("newFolderDescription");
const folderModalMsg = document.getElementById("folderModalMsg");
const folderModalSaveBtn = document.getElementById("folderModalSaveBtn");
const folderModalCloseBtn = document.getElementById("folderModalCloseBtn");
const folderModalCancelBtn = document.getElementById("folderModalCancelBtn");
const v2ToggleBtn = document.getElementById("v2ToggleBtn");
let favoriteSet = new Set();
let printedSet = new Set();
let selectedModelKeys = new Set();
let folders = [];
let infiniteScrollBound = false;

function getModelKey(m) {
  return String((m && m.dir) || "");
}

function getFolderById(folderId) {
  return folders.find((folder) => folder.id === folderId) || null;
}

function cloneFolders() {
  return folders.map((folder) => ({
    id: folder.id,
    name: folder.name,
    description: folder.description || "",
    modelDirs: Array.isArray(folder.modelDirs) ? folder.modelDirs.slice() : [],
    createdAt: folder.createdAt || "",
    updatedAt: folder.updatedAt || ""
  }));
}

function normalizeFolders(rawFolders) {
  const list = Array.isArray(rawFolders) ? rawFolders : [];
  const seenIds = new Set();
  const seenNames = new Set();
  return list.reduce((acc, item) => {
    if (!item || typeof item !== "object") return acc;
    const name = String(item.name || "").trim();
    if (!name) return acc;
    const folderId = String(item.id || "").trim() || `${Date.now()}_${acc.length}`;
    if (seenIds.has(folderId)) return acc;
    const loweredName = name.toLowerCase();
    if (seenNames.has(loweredName)) return acc;
    seenIds.add(folderId);
    seenNames.add(loweredName);
    const modelDirs = [];
    (Array.isArray(item.modelDirs) ? item.modelDirs : []).forEach((value) => {
      const key = String(value || "").trim();
      if (key && !modelDirs.includes(key)) modelDirs.push(key);
    });
    acc.push({
      id: folderId,
      name,
      description: String(item.description || "").trim(),
      modelDirs,
      createdAt: String(item.createdAt || "").trim(),
      updatedAt: String(item.updatedAt || "").trim()
    });
    return acc;
  }, []);
}

function buildFlagsPayload() {
  return {
    favorites: Array.from(favoriteSet),
    printed: Array.from(printedSet),
    folders: cloneFolders()
  };
}

async function loadFlags() {
  try {
    const res = await fetch("/api/gallery/flags");
    if (!res.ok) throw new Error("flags request failed");
    const data = await res.json();
    favoriteSet = new Set(Array.isArray(data.favorites) ? data.favorites : []);
    printedSet = new Set(Array.isArray(data.printed) ? data.printed : []);
    folders = normalizeFolders(data.folders);
  } catch (e) {
    console.warn("载入标记失败", e);
    favoriteSet = new Set();
    printedSet = new Set();
    folders = [];
  }
}

async function saveFlags() {
  try {
    const res = await fetch("/api/gallery/flags", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildFlagsPayload())
    });
    if (!res.ok) throw new Error("save flags failed");
  } catch (e) {
    console.warn("保存标记失败", e);
    throw e;
  }
}

function formatDate(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("zh-CN");
}

function sortModelsDesc(list) {
  const sortMode = sortOrderSelect?.value || "collected";
  return list.slice().sort((a, b) => {
    const aPrimary = sortMode === "published" ? a?.publishedAt : a?.collectedAt;
    const bPrimary = sortMode === "published" ? b?.publishedAt : b?.collectedAt;
    const aFallback = sortMode === "published" ? a?.collectedAt : a?.publishedAt;
    const bFallback = sortMode === "published" ? b?.collectedAt : b?.publishedAt;
    const aTime = Date.parse(aPrimary || aFallback || "");
    const bTime = Date.parse(bPrimary || bFallback || "");
    const aValid = Number.isFinite(aTime);
    const bValid = Number.isFinite(bTime);
    if (aValid || bValid) {
      if (!aValid) return 1;
      if (!bValid) return -1;
      if (aTime !== bTime) return bTime - aTime;
    }
    const aName = (a?.title || a?.baseName || "").toLowerCase();
    const bName = (b?.title || b?.baseName || "").toLowerCase();
    return bName.localeCompare(aName);
  });
}

function getSourceValue(m) {
  const src = String((m && m.source) || "").trim().toLowerCase();
  if (src === "mw_cn" || src === "mw_global" || src === "localmodel" || src === "others") return src;
  const dir = m?.dir || "";
  if (dir.startsWith("LocalModel_")) return "localmodel";
  if (dir.startsWith("Others_")) return "others";
  return "mw_cn";
}

function formatSourceLabel(value) {
  if (value === "mw_cn") return "MakerWorld 国内";
  if (value === "mw_global") return "MakerWorld 国际";
  if (value === "others") return "其他来源";
  if (value === "localmodel") return "手动导入";
  return "MakerWorld 国内";
}

function getFolderCount(folderId) {
  const folder = getFolderById(folderId);
  return folder ? folder.modelDirs.length : 0;
}

function selectTag(tag) {
  activeTag = tag;
  displayedCount = loadIncrement;
  renderAll();
}

function selectAuthor(name) {
  activeAuthor = name;
  displayedCount = loadIncrement;
  renderAll();
}

function selectSource(source) {
  activeSource = source;
  displayedCount = loadIncrement;
  renderAll();
}

function selectFolder(folderId) {
  activeFolder = folderId;
  displayedCount = loadIncrement;
  renderAll();
}

function syncFlagFilterButtons() {
  if (favOnlyBtn) {
    favOnlyBtn.classList.toggle("active", onlyFavorites);
    favOnlyBtn.setAttribute("aria-pressed", onlyFavorites ? "true" : "false");
  }
  if (printedOnlyBtn) {
    printedOnlyBtn.classList.toggle("active", onlyPrinted);
    printedOnlyBtn.setAttribute("aria-pressed", onlyPrinted ? "true" : "false");
  }
}

function syncModeButtons() {
  if (selectionToggleBtn) {
    selectionToggleBtn.classList.toggle("active", selectionMode);
    selectionToggleBtn.setAttribute("aria-pressed", selectionMode ? "true" : "false");
  }
  if (compactToggleBtn) {
    compactToggleBtn.classList.toggle("active", compactMode);
    compactToggleBtn.setAttribute("aria-pressed", compactMode ? "true" : "false");
  }
  document.body.classList.toggle("selection-mode", selectionMode);
  document.body.classList.toggle("compact-mode", compactMode);
}

function syncSelectionBar() {
  const count = selectedModelKeys.size;
  if (selectedCountEl) selectedCountEl.textContent = String(count);
  if (selectionBar) selectionBar.style.display = selectionMode ? "flex" : "none";
  if (addToFolderBtn) addToFolderBtn.disabled = count === 0;
  if (batchDeleteBtn) batchDeleteBtn.disabled = count === 0;
  if (clearSelectionBtn) clearSelectionBtn.disabled = count === 0;
}

function createFilterChip({ label, value, count, isActive, onSelect, extraClass, subLabel }) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "side-item" + (isActive ? " active" : "") + (extraClass ? ` ${extraClass}` : "");
  const rightText = typeof count === "number" ? count : (subLabel || "");
  btn.innerHTML = `<span>${label}</span> <span style="font-size:12px; opacity:0.6;">${rightText}</span>`;
  btn.addEventListener("click", () => onSelect(value));
  return btn;
}

function openFilterModal({ type, items, total }) {
  if (!filterModal || !filterModalChips || !filterModalTitle) return;
  const isTag = type === "tag";
  const activeValue = isTag ? activeTag : activeAuthor;
  const allLabel = isTag ? "全部模型" : "全部作者";
  const selectFn = isTag ? selectTag : selectAuthor;
  filterModalTitle.textContent = isTag ? "全部分类" : "全部作者";
  filterModalChips.innerHTML = "";

  filterModalChips.appendChild(createFilterChip({
    label: allLabel,
    value: "",
    count: total,
    isActive: activeValue === "",
    onSelect: (value) => {
      selectFn(value);
      closeFilterModal();
    }
  }));

  items.forEach(([value, count]) => {
    filterModalChips.appendChild(createFilterChip({
      label: value,
      value,
      count,
      isActive: activeValue === value,
      onSelect: (val) => {
        selectFn(val);
        closeFilterModal();
      }
    }));
  });

  filterModal.style.display = "flex";
  filterModal.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
}

function closeFilterModal() {
  if (!filterModal) return;
  filterModal.style.display = "none";
  filterModal.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
}

async function toggleFavorite(m) {
  const key = getModelKey(m);
  if (!key) return;
  const nextValue = !favoriteSet.has(key);
  if (nextValue) favoriteSet.add(key);
  else favoriteSet.delete(key);
  try {
    await saveFlags();
    renderAll();
  } catch (_) {
    if (nextValue) favoriteSet.delete(key);
    else favoriteSet.add(key);
  }
}

async function togglePrinted(m) {
  const key = getModelKey(m);
  if (!key) return;
  const nextValue = !printedSet.has(key);
  if (nextValue) printedSet.add(key);
  else printedSet.delete(key);
  try {
    await saveFlags();
    renderAll();
  } catch (_) {
    if (nextValue) printedSet.delete(key);
    else printedSet.add(key);
  }
}

function cleanupSelection() {
  const validKeys = new Set(models.map((m) => getModelKey(m)));
  selectedModelKeys = new Set(Array.from(selectedModelKeys).filter((key) => validKeys.has(key)));
}

async function deleteModel(m) {
  const key = getModelKey(m);
  if (!key) return;
  const name = m.title || m.baseName || m.dir || "该模型";
  if (!window.confirm(`确定物理删除「${name}」？删除后无法恢复。`)) return;
  try {
    const res = await fetch(`/api/models/${encodeURIComponent(key)}/delete`, { method: "POST" });
    if (!res.ok) throw new Error("delete failed");
    models = models.filter((item) => getModelKey(item) !== key);
    favoriteSet.delete(key);
    printedSet.delete(key);
    folders = folders.map((folder) => ({
      ...folder,
      modelDirs: folder.modelDirs.filter((dir) => dir !== key)
    }));
    selectedModelKeys.delete(key);
    cleanupSelection();
    displayedCount = loadIncrement;
    renderAll();
  } catch (e) {
    console.error("删除失败", e);
    alert("删除失败，请检查服务器日志");
  }
}

async function batchDeleteSelected() {
  const keys = Array.from(selectedModelKeys);
  if (!keys.length) return;
  if (!window.confirm(`确定批量删除已选中的 ${keys.length} 个模型？该操作会物理删除目录且无法恢复。`)) return;
  try {
    const res = await fetch("/api/models/batch-delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_dirs: keys })
    });
    if (!res.ok) throw new Error("batch delete failed");
    const data = await res.json();
    const deleted = Array.isArray(data.deleted) ? data.deleted : [];
    const failed = Array.isArray(data.failed) ? data.failed : [];
    if (deleted.length) {
      models = models.filter((item) => !deleted.includes(getModelKey(item)));
      deleted.forEach((key) => {
        favoriteSet.delete(key);
        printedSet.delete(key);
        selectedModelKeys.delete(key);
      });
      folders = folders.map((folder) => ({
        ...folder,
        modelDirs: folder.modelDirs.filter((dir) => !deleted.includes(dir))
      }));
    }
    cleanupSelection();
    displayedCount = loadIncrement;
    renderAll();
    if (failed.length) {
      const detail = failed.map((item) => `${item.model_dir}: ${item.message}`).join("\n");
      alert(`已删除 ${deleted.length} 个模型，以下删除失败：\n${detail}`);
    }
  } catch (e) {
    console.error("批量删除失败", e);
    alert("批量删除失败，请检查服务器日志");
  }
}

async function load() {
  try {
    await loadFlags();
    const res = await fetch("/api/gallery");
    models = await res.json();
  } catch (e) {
    console.error("载入模型失败", e);
    models = [];
  }
  cleanupSelection();
  syncFlagFilterButtons();
  syncModeButtons();
  syncSelectionBar();
  displayedCount = loadIncrement;
  renderAll();
  setupInfiniteScroll();
}

function renderFilters() {
  if (!filterChips) return;
  const counts = {};
  models.forEach((m) => (m.tags || []).forEach((tag) => {
    counts[tag] = (counts[tag] || 0) + 1;
  }));
  filterChips.innerHTML = "";
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const displayLimit = isTagsExpanded ? entries.length : filterChipLimit;

  entries.slice(0, displayLimit).forEach(([tag, count]) => {
    filterChips.appendChild(createFilterChip({
      label: tag,
      value: tag,
      count,
      isActive: activeTag === tag,
      onSelect: selectTag
    }));
  });

  if (entries.length > filterChipLimit) {
    const moreBtn = document.createElement("button");
    moreBtn.type = "button";
    moreBtn.className = "side-item";
    moreBtn.style.textAlign = "center";
    moreBtn.style.color = "var(--color-primary)";
    moreBtn.textContent = isTagsExpanded ? "收起标签" : `更多标签 (${entries.length - filterChipLimit})+`;
    moreBtn.addEventListener("click", () => {
      isTagsExpanded = !isTagsExpanded;
      renderFilters();
    });
    filterChips.appendChild(moreBtn);
  }
}

function renderAuthorFilters() {
  if (!authorChips) return;
  const counts = {};
  models.forEach((m) => {
    const name = m.author?.name || "未知作者";
    counts[name] = (counts[name] || 0) + 1;
  });
  authorChips.innerHTML = "";
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const displayLimit = isAuthorsExpanded ? entries.length : authorChipLimit;

  entries.slice(0, displayLimit).forEach(([name, count]) => {
    authorChips.appendChild(createFilterChip({
      label: name,
      value: name,
      count,
      isActive: activeAuthor === name,
      onSelect: selectAuthor
    }));
  });

  if (entries.length > authorChipLimit) {
    const moreBtn = document.createElement("button");
    moreBtn.type = "button";
    moreBtn.className = "side-item";
    moreBtn.style.textAlign = "center";
    moreBtn.style.color = "var(--color-primary)";
    moreBtn.textContent = isAuthorsExpanded ? "收起作者" : `更多作者 (${entries.length - authorChipLimit})+`;
    moreBtn.addEventListener("click", () => {
      isAuthorsExpanded = !isAuthorsExpanded;
      renderAuthorFilters();
    });
    authorChips.appendChild(moreBtn);
  }
}

function renderSourceMenu() {
  if (!sourceMenu) return;
  const counts = {};
  models.forEach((m) => {
    const key = getSourceValue(m);
    counts[key] = (counts[key] || 0) + 1;
  });
  const total = models.length || 0;
  const labels = {
    mw_cn: "MakerWorld 国内",
    mw_global: "MakerWorld 国际",
    localmodel: "手动导入",
    others: "其他来源"
  };
  const order = ["mw_cn", "mw_global", "localmodel", "others"];
  sourceMenu.innerHTML = "";

  sourceMenu.appendChild(createFilterChip({
    label: "全部",
    value: "",
    count: total,
    isActive: activeSource === "",
    onSelect: selectSource
  }));

  order.forEach((key) => {
    if (!(key in counts)) return;
    sourceMenu.appendChild(createFilterChip({
      label: labels[key],
      value: key,
      count: counts[key] || 0,
      isActive: activeSource === key,
      onSelect: selectSource
    }));
  });
}

function renderFolderMenu() {
  if (!folderMenu) return;
  folderMenu.innerHTML = "";
  folderMenu.appendChild(createFilterChip({
    label: "全部",
    value: "",
    count: models.length,
    isActive: activeFolder === "",
    onSelect: selectFolder
  }));
  folders.forEach((folder) => {
    folderMenu.appendChild(createFilterChip({
      label: folder.name,
      value: folder.id,
      count: getFolderCount(folder.id),
      isActive: activeFolder === folder.id,
      onSelect: selectFolder,
      extraClass: "side-item--folder"
    }));
  });
}

function updateLoadMoreIndicator(hasMore) {
  const grid = document.getElementById("grid");
  if (!grid || !grid.parentElement) return;
  let indicator = document.getElementById("loadMoreIndicator");
  if (hasMore) {
    if (!indicator) {
      indicator = document.createElement("div");
      indicator.id = "loadMoreIndicator";
      indicator.className = "load-more-indicator";
      indicator.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 加载更多...';
      grid.parentElement.appendChild(indicator);
    }
    indicator.style.display = "block";
  } else if (indicator) {
    indicator.style.display = "none";
  }
}

function setupInfiniteScroll() {
  if (infiniteScrollBound) return;
  const content = document.querySelector(".content");
  if (!content) return;
  let isLoading = false;
  content.addEventListener("scroll", () => {
    if (isLoading) return;
    const scrollTop = content.scrollTop;
    const scrollHeight = content.scrollHeight;
    const clientHeight = content.clientHeight;
    if (scrollTop + clientHeight >= scrollHeight * 0.8) {
      const total = getFilteredList().length;
      if (displayedCount >= total) return;
      isLoading = true;
      displayedCount += loadIncrement;
      renderGrid(true);
      setTimeout(() => { isLoading = false; }, 300);
    }
  });
  infiniteScrollBound = true;
}

function openLightbox(list, index) {
  if (!list || !list.length || !lightbox || !lightboxImg) return;
  currentLightboxList = list;
  currentLightboxIndex = index;
  const m = list[index];
  lightboxImg.src = `/files/${m.dir}/images/${m.cover || "design_01.png"}`;
  lightboxImg.alt = m.title || m.baseName || "";
  if (lightboxCaption) lightboxCaption.textContent = m.title || m.baseName || "";
  lightbox.style.display = "flex";
  lightbox.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
}

function closeLightbox() {
  if (!lightbox) return;
  lightbox.style.display = "none";
  lightbox.setAttribute("aria-hidden", "true");
  if (lightboxImg) lightboxImg.src = "";
  document.body.style.overflow = "";
}

function lightboxPrev() {
  if (currentLightboxIndex > 0) {
    currentLightboxIndex -= 1;
    openLightbox(currentLightboxList, currentLightboxIndex);
  }
}

function lightboxNext() {
  if (currentLightboxIndex < currentLightboxList.length - 1) {
    currentLightboxIndex += 1;
    openLightbox(currentLightboxList, currentLightboxIndex);
  }
}

function getFilteredList() {
  const keyword = (kwInput?.value || "").trim().toLowerCase();
  let list = models;
  if (keyword) {
    list = list.filter((m) => {
      const title = (m.title || m.baseName || "").toLowerCase();
      const tags = (m.tags || []).map((t) => t.toLowerCase());
      return title.includes(keyword) || tags.some((t) => t.includes(keyword));
    });
  }
  if (activeTag) list = list.filter((m) => (m.tags || []).includes(activeTag));
  if (activeAuthor) list = list.filter((m) => (m.author?.name || "未知作者") === activeAuthor);
  if (activeSource) list = list.filter((m) => getSourceValue(m) === activeSource);
  if (activeFolder) {
    const folder = getFolderById(activeFolder);
    const folderKeys = new Set(folder ? folder.modelDirs : []);
    list = list.filter((m) => folderKeys.has(getModelKey(m)));
  }
  if (onlyFavorites) list = list.filter((m) => favoriteSet.has(getModelKey(m)));
  if (onlyPrinted) list = list.filter((m) => printedSet.has(getModelKey(m)));
  return sortModelsDesc(list);
}

function getModelDetailUrl(m) {
  const safeDir = encodeURIComponent(m.dir);
  return useV2 ? `/v2/files/${safeDir}` : `/files/${safeDir}/index.html`;
}

function updateVersionToggle() {
  if (!v2ToggleBtn) return;
  const label = v2ToggleBtn.querySelector(".toggle-label");
  if (label) label.textContent = useV2 ? "V2" : "本地";
  v2ToggleBtn.classList.toggle("active", useV2);
}

function toggleSelectionForModel(modelKey) {
  if (!modelKey) return;
  if (selectedModelKeys.has(modelKey)) selectedModelKeys.delete(modelKey);
  else selectedModelKeys.add(modelKey);
  syncSelectionBar();
  renderGrid();
}

function clearSelection() {
  selectedModelKeys = new Set();
  syncSelectionBar();
  renderGrid();
}

function setSelectionMode(nextValue) {
  selectionMode = !!nextValue;
  if (!selectionMode) clearSelection();
  syncModeButtons();
  syncSelectionBar();
  renderGrid();
}

function renderGrid(append = false) {
  const grid = document.getElementById("grid");
  const empty = document.getElementById("empty");
  if (!grid || !empty) return;
  const list = getFilteredList();
  const total = list.length;
  if (totalCountEl) totalCountEl.textContent = String(total);
  const displayList = list.slice(0, displayedCount);

  if (!append) grid.innerHTML = "";
  if (!displayList.length) {
    const tips = [];
    if (activeTag) tips.push(`标签「${activeTag}」`);
    if (kwInput?.value.trim()) tips.push(`关键词「${kwInput.value.trim()}」`);
    if (activeAuthor) tips.push(`作者「${activeAuthor}」`);
    if (activeSource) tips.push(`来源「${formatSourceLabel(activeSource)}」`);
    if (activeFolder) {
      const folder = getFolderById(activeFolder);
      if (folder) tips.push(`收藏夹「${folder.name}」`);
    }
    if (onlyFavorites) tips.push("收藏");
    if (onlyPrinted) tips.push("已打印");
    empty.textContent = tips.length ? `未找到匹配 ${tips.join("、")}` : "暂无模型";
    empty.style.display = "block";
    updateLoadMoreIndicator(false);
    return;
  }
  empty.style.display = "none";

  const startIdx = append ? grid.children.length : 0;
  displayList.slice(startIdx).forEach((m) => {
    const modelKey = getModelKey(m);
    const isFavorite = modelKey && favoriteSet.has(modelKey);
    const isPrinted = modelKey && printedSet.has(modelKey);
    const isSelected = modelKey && selectedModelKeys.has(modelKey);

    const card = document.createElement("article");
    card.className = "card";
    if (isSelected) card.classList.add("card--selected");
    card.setAttribute("role", "listitem");
    card.tabIndex = 0;
    if (selectionMode) {
      card.classList.add("card--selectable");
      card.addEventListener("click", () => toggleSelectionForModel(modelKey));
    }

    const selectionBadge = document.createElement("button");
    selectionBadge.type = "button";
    selectionBadge.className = "card-select-toggle";
    selectionBadge.setAttribute("aria-pressed", isSelected ? "true" : "false");
    selectionBadge.innerHTML = isSelected ? '<i class="fas fa-check"></i>' : '<i class="fas fa-plus"></i>';
    selectionBadge.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleSelectionForModel(modelKey);
    });
    card.appendChild(selectionBadge);

    const coverWrap = document.createElement("div");
    coverWrap.className = "card-cover";
    coverWrap.addEventListener("click", (e) => {
      if (selectionMode) {
        e.preventDefault();
        e.stopPropagation();
        toggleSelectionForModel(modelKey);
        return;
      }
      window.open(getModelDetailUrl(m), "_blank");
    });

    const cover = document.createElement("img");
    cover.src = `/files/${m.dir}/images/${m.cover || "design_01.png"}`;
    cover.loading = "lazy";
    cover.alt = m.title || m.baseName || "模型封面";
    cover.onerror = () => { cover.src = "/static/imgs/fav.png"; };
    coverWrap.appendChild(cover);
    card.appendChild(coverWrap);

    const body = document.createElement("div");
    body.className = "card-body";

    const title = document.createElement("h3");
    title.className = "title";
    title.title = m.title || m.baseName || "未知模型";
    title.textContent = m.title || m.baseName || "未知模型";
    title.addEventListener("click", (e) => {
      if (selectionMode) {
        e.preventDefault();
        e.stopPropagation();
        toggleSelectionForModel(modelKey);
        return;
      }
      window.open(getModelDetailUrl(m), "_blank");
    });
    body.appendChild(title);

    const meta = document.createElement("div");
    meta.className = "card-meta";
    const authorWrap = document.createElement("div");
    authorWrap.className = "author";
    if (m.author?.avatarRelPath) {
      const avatar = document.createElement("img");
      avatar.src = `/files/${m.dir}/${m.author.avatarRelPath}`;
      avatar.alt = m.author?.name || "User";
      authorWrap.appendChild(avatar);
    } else {
      const avatarPlaceholder = document.createElement("div");
      avatarPlaceholder.className = "avatar-placeholder";
      avatarPlaceholder.innerHTML = '<i class="fas fa-user"></i>';
      authorWrap.appendChild(avatarPlaceholder);
    }
    const authorName = document.createElement("span");
    authorName.className = "author-name";
    authorName.textContent = m.author?.name || "Unknown";
    authorWrap.appendChild(authorName);
    meta.appendChild(authorWrap);
    body.appendChild(meta);

    const statsWrap = document.createElement("div");
    statsWrap.className = "stats";
    if (m.stats?.likes > 0) statsWrap.appendChild(createStatIcon("fas fa-thumbs-up", m.stats.likes, "点赞"));
    if (m.stats?.favorites > 0) statsWrap.appendChild(createStatIcon("fas fa-star", m.stats.favorites, "收藏"));
    if (m.stats?.prints > 0) statsWrap.appendChild(createStatIcon("fas fa-print", m.stats.prints, "打印"));
    if (m.stats?.downloads > 0 || m.downloadCount > 0) {
      statsWrap.appendChild(createStatIcon("fas fa-download", m.stats?.downloads || m.downloadCount, "下载"));
    }
    body.appendChild(statsWrap);

    const dateInfo = document.createElement("div");
    dateInfo.className = "card-dates";
    if (m.publishedAt) {
      const publishDate = document.createElement("span");
      publishDate.className = "date-item";
      publishDate.innerHTML = `<i class="far fa-calendar-alt"></i> ${formatDate(m.publishedAt)}`;
      dateInfo.appendChild(publishDate);
    }
    if (m.collectedAt) {
      const collectDate = document.createElement("span");
      collectDate.className = "date-item";
      collectDate.innerHTML = `<i class="fas fa-archive"></i> ${formatDate(m.collectedAt)}`;
      dateInfo.appendChild(collectDate);
    }
    if (dateInfo.children.length > 0) body.appendChild(dateInfo);

    const actions = document.createElement("div");
    actions.className = "card-actions";

    const openBtn = document.createElement("button");
    openBtn.className = "action-btn";
    openBtn.title = "查看详情";
    openBtn.innerHTML = '<i class="fas fa-arrow-up-right-from-square"></i>';
    openBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      window.open(getModelDetailUrl(m), "_blank");
    });
    actions.appendChild(openBtn);

    const favBtn = document.createElement("button");
    favBtn.className = "action-btn" + (isFavorite ? " active" : "");
    favBtn.title = isFavorite ? "取消收藏" : "收藏";
    favBtn.innerHTML = isFavorite ? '<i class="fas fa-heart"></i>' : '<i class="far fa-heart"></i>';
    favBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      await toggleFavorite(m);
    });
    actions.appendChild(favBtn);

    const printedBtn = document.createElement("button");
    printedBtn.className = "action-btn" + (isPrinted ? " active" : "");
    printedBtn.title = isPrinted ? "取消标记" : "标记已打印";
    printedBtn.innerHTML = isPrinted ? '<i class="fas fa-check-circle"></i>' : '<i class="far fa-check-circle"></i>';
    printedBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      await togglePrinted(m);
    });
    actions.appendChild(printedBtn);

    const spacer = document.createElement("div");
    spacer.style.flex = "1";
    actions.appendChild(spacer);

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "action-btn danger";
    deleteBtn.title = "删除模型";
    deleteBtn.innerHTML = '<i class="fas fa-trash-alt"></i>';
    deleteBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      await deleteModel(m);
    });
    actions.appendChild(deleteBtn);

    body.appendChild(actions);
    card.appendChild(body);
    grid.appendChild(card);
  });

  updateLoadMoreIndicator(displayedCount < total);
}

function createStatIcon(iconClass, count, title) {
  const span = document.createElement("span");
  span.className = "stat-chip";
  span.title = title || "";
  span.innerHTML = `<i class="${iconClass}"></i> ${count}`;
  return span;
}

function renderFolderModalOptions() {
  if (!folderOptionList) return;
  folderOptionList.innerHTML = "";
  if (!folders.length) {
    folderOptionList.innerHTML = '<div class="folder-option-list__empty">暂无收藏夹，可直接在下方新建。</div>';
    return;
  }
  folders.forEach((folder) => {
    const label = document.createElement("label");
    label.className = "folder-option";
    label.innerHTML = `
      <input type="checkbox" value="${folder.id}">
      <span class="folder-option__content">
        <span class="folder-option__name">${folder.name}</span>
        <span class="folder-option__desc">${folder.description || "无简介"}</span>
      </span>
    `;
    folderOptionList.appendChild(label);
  });
}

function openFolderModal() {
  if (!folderModal) return;
  renderFolderModalOptions();
  if (folderModalMsg) folderModalMsg.textContent = "";
  if (newFolderNameInput) newFolderNameInput.value = "";
  if (newFolderDescriptionInput) newFolderDescriptionInput.value = "";
  folderModal.style.display = "flex";
  folderModal.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
}

function closeFolderModal() {
  if (!folderModal) return;
  folderModal.style.display = "none";
  folderModal.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
}

async function saveFolderSelection() {
  const selectedKeys = Array.from(selectedModelKeys);
  if (!selectedKeys.length) {
    if (folderModalMsg) folderModalMsg.textContent = "请先选择模型。";
    return;
  }
  const checkedFolderIds = Array.from(folderOptionList?.querySelectorAll('input[type="checkbox"]:checked') || []).map((node) => node.value);
  const folderName = String(newFolderNameInput?.value || "").trim();
  const folderDescription = String(newFolderDescriptionInput?.value || "").trim();
  if (!checkedFolderIds.length && !folderName) {
    if (folderModalMsg) folderModalMsg.textContent = "请选择已有收藏夹，或填写新的收藏夹名称。";
    return;
  }

  const nextFolders = cloneFolders();
  let createdFolderId = "";
  if (folderName) {
    const duplicate = nextFolders.find((folder) => folder.name.toLowerCase() === folderName.toLowerCase());
    if (duplicate) {
      if (folderModalMsg) folderModalMsg.textContent = "收藏夹名称已存在，请更换名称。";
      return;
    }
    createdFolderId = `folder_${Date.now()}`;
    nextFolders.push({
      id: createdFolderId,
      name: folderName,
      description: folderDescription,
      modelDirs: [],
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    });
  }

  checkedFolderIds.concat(createdFolderId ? [createdFolderId] : []).forEach((folderId) => {
    const folder = nextFolders.find((item) => item.id === folderId);
    if (!folder) return;
    selectedKeys.forEach((key) => {
      if (!folder.modelDirs.includes(key)) folder.modelDirs.push(key);
    });
    folder.updatedAt = new Date().toISOString();
  });

  folders = normalizeFolders(nextFolders);
  try {
    await saveFlags();
    renderAll();
    closeFolderModal();
  } catch (_) {
    if (folderModalMsg) folderModalMsg.textContent = "保存收藏夹失败，请稍后重试。";
  }
}

function renderAll() {
  cleanupSelection();
  renderFilters();
  renderAuthorFilters();
  renderSourceMenu();
  renderFolderMenu();
  syncFlagFilterButtons();
  syncModeButtons();
  syncSelectionBar();
  updateVersionToggle();
  renderGrid();
}

if (kwInput) {
  kwInput.addEventListener("input", () => {
    displayedCount = loadIncrement;
    renderGrid();
  });
}

if (clearBtn && kwInput) {
  clearBtn.addEventListener("click", () => {
    kwInput.value = "";
    displayedCount = loadIncrement;
    renderGrid();
  });
}

if (resetSearchBtn) {
  resetSearchBtn.addEventListener("click", () => {
    if (kwInput) kwInput.value = "";
    activeTag = "";
    activeAuthor = "";
    activeSource = "";
    activeFolder = "";
    onlyFavorites = false;
    onlyPrinted = false;
    isTagsExpanded = false;
    isAuthorsExpanded = false;
    displayedCount = loadIncrement;
    renderAll();
  });
}

if (sortOrderSelect) {
  sortOrderSelect.addEventListener("change", () => {
    displayedCount = loadIncrement;
    renderGrid();
  });
}

if (favOnlyBtn) {
  favOnlyBtn.addEventListener("click", () => {
    onlyFavorites = !onlyFavorites;
    displayedCount = loadIncrement;
    syncFlagFilterButtons();
    renderGrid();
  });
}

if (printedOnlyBtn) {
  printedOnlyBtn.addEventListener("click", () => {
    onlyPrinted = !onlyPrinted;
    displayedCount = loadIncrement;
    syncFlagFilterButtons();
    renderGrid();
  });
}

if (selectionToggleBtn) {
  selectionToggleBtn.addEventListener("click", () => setSelectionMode(!selectionMode));
}

if (compactToggleBtn) {
  compactToggleBtn.addEventListener("click", () => {
    compactMode = !compactMode;
    localStorage.setItem("mw_gallery_compact_mode", compactMode ? "true" : "false");
    syncModeButtons();
    renderGrid();
  });
}

if (clearSelectionBtn) clearSelectionBtn.addEventListener("click", clearSelection);
if (addToFolderBtn) addToFolderBtn.addEventListener("click", openFolderModal);
if (batchDeleteBtn) batchDeleteBtn.addEventListener("click", batchDeleteSelected);
if (folderModalSaveBtn) folderModalSaveBtn.addEventListener("click", saveFolderSelection);
if (folderModalCloseBtn) folderModalCloseBtn.addEventListener("click", closeFolderModal);
if (folderModalCancelBtn) folderModalCancelBtn.addEventListener("click", closeFolderModal);

if (folderModal) {
  folderModal.addEventListener("click", (e) => {
    if (e.target === folderModal) closeFolderModal();
  });
}

if (filterModal) {
  const filterCloseBtn = filterModal.querySelector(".filter-modal__close");
  if (filterCloseBtn) filterCloseBtn.addEventListener("click", closeFilterModal);
  filterModal.addEventListener("click", (e) => {
    if (e.target === filterModal) closeFilterModal();
  });
}

if (lightbox) {
  const closeBtn = lightbox.querySelector(".lightbox-close");
  const prevBtn = lightbox.querySelector(".lightbox-prev");
  const nextBtn = lightbox.querySelector(".lightbox-next");
  if (closeBtn) closeBtn.addEventListener("click", closeLightbox);
  if (prevBtn) prevBtn.addEventListener("click", lightboxPrev);
  if (nextBtn) nextBtn.addEventListener("click", lightboxNext);
  lightbox.addEventListener("click", (e) => {
    if (e.target === lightbox) closeLightbox();
  });
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeFilterModal();
    closeFolderModal();
    closeLightbox();
  }
});

if (v2ToggleBtn) {
  v2ToggleBtn.addEventListener("click", () => {
    useV2 = !useV2;
    localStorage.setItem("useV2", useV2 ? "true" : "false");
    updateVersionToggle();
  });
}

load();
