let models = [];
let activeTag = "";
let activeAuthor = "";
let activeSource = "";
let onlyFavorites = false;
let onlyPrinted = false;
let useV2 = localStorage.getItem('useV2') === 'true';
let displayedCount = 20; // Initial display count
let loadIncrement = 20; // Load 20 more each time
let isTagsExpanded = false;
let isAuthorsExpanded = false;
let currentLightboxList = [];
let currentLightboxIndex = 0;
const filterChipLimit = 12;
const authorChipLimit = 10;
const statBlueprint = [
  { key: "likes", icon: "👍", label: "点赞" },
  { key: "favorites", icon: "⭐", label: "收藏" },
  { key: "downloads", icon: "⬇️", label: "下载" },
  { key: "prints", icon: "🖨️", label: "打印" },
  { key: "views", icon: "👁️", label: "浏览" }
];
const kwInput = document.getElementById("kw");
const filterChips = document.getElementById("filterChips");
const authorChips = document.getElementById("authorChips");
const sourceMenu = document.getElementById("sourceMenu");
const clearBtn = document.getElementById("clearBtn");
const resetSearchBtn = document.getElementById("resetSearchBtn");
const paginationWrap = document.getElementById("pagination");
const pageSizeInput = document.getElementById("pageSizeInput");
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
let favoriteSet = new Set();
let printedSet = new Set();

function getModelKey(m) {
  return String(m.dir || "");
}

async function loadFlags() {
  try {
    const res = await fetch("/api/gallery/flags");
    if (!res.ok) throw new Error("flags request failed");
    const data = await res.json();
    favoriteSet = new Set(Array.isArray(data.favorites) ? data.favorites : []);
    printedSet = new Set(Array.isArray(data.printed) ? data.printed : []);
  } catch (e) {
    console.warn("载入标记失败", e);
    favoriteSet = new Set();
    printedSet = new Set();
  }
}

async function saveFlags() {
  try {
    await fetch("/api/gallery/flags", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        favorites: Array.from(favoriteSet),
        printed: Array.from(printedSet)
      })
    });
  } catch (e) {
    console.warn("保存标记失败", e);
  }
}

function clampPageSize(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return pageSize;
  return Math.min(100, Math.max(1, Math.floor(parsed)));
}

function formatDate(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("zh-CN");
}

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function selectTag(tag) {
  activeTag = tag;
  displayedCount = loadIncrement;
  renderFilters();
  renderAuthorFilters();
  render();
}

function selectAuthor(name) {
  activeAuthor = name;
  displayedCount = loadIncrement;
  renderFilters();
  renderAuthorFilters();
  render();
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

function selectSource(source) {
  activeSource = source;
  displayedCount = loadIncrement;
  renderSourceMenu();
  render();
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

// Updated to create Sidebar Items
function createFilterChip({ label, value, count, isActive, onSelect, extraClass }) {
  const btn = document.createElement("button");
  btn.type = "button";
  // Use .side-item for sidebar styling
  btn.className = "side-item" + (isActive ? " active" : "") + (extraClass ? ` ${extraClass}` : "");

  // Format: "Label (Count)"
  btn.innerHTML = `<span>${label}</span> <span style="font-size:12px; opacity:0.6;">${typeof count === "number" ? count : ""}</span>`;

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
    onSelect: (value) => { selectFn(value); closeFilterModal(); }
  }));

  items.forEach(([value, count]) => {
    filterModalChips.appendChild(createFilterChip({
      label: value,
      value,
      count,
      isActive: activeValue === value,
      onSelect: (val) => { selectFn(val); closeFilterModal(); }
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

function toggleFavorite(m) {
  const key = getModelKey(m);
  if (!key) return;
  if (favoriteSet.has(key)) { favoriteSet.delete(key); } else { favoriteSet.add(key); }
  saveFlags();
  render();
}

function togglePrinted(m) {
  const key = getModelKey(m);
  if (!key) return;
  if (printedSet.has(key)) { printedSet.delete(key); } else { printedSet.add(key); }
  saveFlags();
  render();
}

function deleteModel(m) {
  const key = getModelKey(m);
  if (!key) return;
  const name = m.title || m.baseName || m.dir || "该模型";
  if (!window.confirm(`确定物理删除「${name}」? 删除后无法恢复。`)) return;
  fetch(`/api/models/${encodeURIComponent(key)}/delete`, { method: "POST" })
    .then((res) => {
      if (!res.ok) throw new Error("delete failed");
      models = models.filter(item => getModelKey(item) !== key);
      favoriteSet.delete(key);
      printedSet.delete(key);
      saveFlags();
      displayedCount = loadIncrement;
      renderFilters();
      renderAuthorFilters();
      renderSourceMenu();
      render();
    })
    .catch((e) => {
      console.error("删除失败", e);
      alert("删除失败，请检查服务器日志");
    });
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
  renderFilters();
  renderAuthorFilters();
  renderSourceMenu();
  syncFlagFilterButtons();
  displayedCount = loadIncrement;
  render();
  setupInfiniteScroll();
}

function renderFilters() {
  if (!filterChips) return;
  const counts = {};
  models.forEach(m => (m.tags || []).forEach(tag => {
    counts[tag] = (counts[tag] || 0) + 1;
  }));
  filterChips.innerHTML = "";
  const entries = Object.entries(counts)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));

  const displayLimit = isTagsExpanded ? entries.length : filterChipLimit;

  entries.slice(0, displayLimit)
    .forEach(([tag, count]) => filterChips.appendChild(createFilterChip({
      label: tag,
      value: tag,
      count,
      isActive: activeTag === tag,
      onSelect: selectTag
    })));

  if (entries.length > filterChipLimit) {
    const moreBtn = document.createElement("button");
    moreBtn.type = "button";
    moreBtn.className = "side-item";
    moreBtn.style.textAlign = "center";
    moreBtn.style.color = "var(--color-primary)";
    moreBtn.textContent = isTagsExpanded ? `收起标签` : `更多标签 (${entries.length - filterChipLimit})+`;
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
  models.forEach(m => {
    const name = (m.author && m.author.name) ? m.author.name : "未知作者";
    counts[name] = (counts[name] || 0) + 1;
  });
  authorChips.innerHTML = "";
  const entries = Object.entries(counts)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));

  const displayLimit = isAuthorsExpanded ? entries.length : authorChipLimit;

  entries.slice(0, displayLimit)
    .forEach(([name, count]) => authorChips.appendChild(createFilterChip({
      label: name,
      value: name,
      count,
      isActive: activeAuthor === name,
      onSelect: selectAuthor
    })));

  if (entries.length > authorChipLimit) {
    const moreBtn = document.createElement("button");
    moreBtn.type = "button";
    moreBtn.className = "side-item";
    moreBtn.style.textAlign = "center";
    moreBtn.style.color = "var(--color-primary)";
    moreBtn.textContent = isAuthorsExpanded ? `收起作者` : `更多作者 (${entries.length - authorChipLimit})+`;
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
  models.forEach(m => {
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

  const allBtn = document.createElement("button");
  allBtn.type = "button";
  // Sidebar style
  allBtn.className = "side-item" + (activeSource === "" ? " active" : "");
  allBtn.innerHTML = `<span>全部</span> <span style="font-size:12px;opacity:0.6;">${total}</span>`;
  allBtn.addEventListener("click", () => selectSource(""));
  sourceMenu.appendChild(allBtn);

  order.forEach((key) => {
    if (!(key in counts)) return;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "side-item" + (activeSource === key ? " active" : "");
    btn.innerHTML = `<span>${labels[key]}</span> <span style="font-size:12px;opacity:0.6;">${counts[key] || 0}</span>`;
    btn.addEventListener("click", () => selectSource(key));
    sourceMenu.appendChild(btn);
  });
}

function updateLoadMoreIndicator(hasMore) {
  const grid = document.getElementById("grid");
  if (!grid) return;

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
  } else {
    if (indicator) indicator.style.display = "none";
  }
}

function setupInfiniteScroll() {
  const content = document.querySelector('.content');
  if (!content) return;

  let isLoading = false;

  content.addEventListener('scroll', () => {
    if (isLoading) return;

    const scrollTop = content.scrollTop;
    const scrollHeight = content.scrollHeight;
    const clientHeight = content.clientHeight;

    // Load more when scrolled to 80% of content
    if (scrollTop + clientHeight >= scrollHeight * 0.8) {
      isLoading = true;
      displayedCount += loadIncrement;
      render(true);
      setTimeout(() => { isLoading = false; }, 300);
    }
  });
}

function openLightbox(list, index) {
  if (!list || !list.length) return;
  currentLightboxList = list;
  currentLightboxIndex = index;
  const m = list[index];
  const imgPath = `/files/${m.dir}/images/${m.cover || 'design_01.png'}`;
  lightboxImg.src = imgPath;
  lightboxImg.alt = m.title || m.baseName || '';
  lightboxImg.classList.remove('zoomed');
  lightboxCaption.textContent = m.title || m.baseName || '';
  lightbox.style.display = 'flex';
  lightbox.setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';
  const closeBtn = lightbox.querySelector('.lightbox-close');
  if (closeBtn) closeBtn.focus();
}
function closeLightbox() {
  lightbox.style.display = 'none';
  lightbox.setAttribute('aria-hidden', 'true');
  lightboxImg.src = '';
  document.body.style.overflow = '';
}
function lightboxPrev() {
  if (currentLightboxIndex > 0) { currentLightboxIndex--; openLightbox(currentLightboxList, currentLightboxIndex); }
}
function lightboxNext() {
  if (currentLightboxIndex < currentLightboxList.length - 1) { currentLightboxIndex++; openLightbox(currentLightboxList, currentLightboxIndex); }
}

function getFilteredList() {
  const keyword = (kwInput?.value || "").trim().toLowerCase();
  let list = models;
  if (keyword) {
    list = list.filter(m => {
      const title = (m.title || m.baseName || "").toLowerCase();
      const tags = (m.tags || []).map(t => t.toLowerCase());
      return title.includes(keyword) || tags.some(t => t.includes(keyword));
    });
  }
  if (activeTag) {
    list = list.filter(m => (m.tags || []).includes(activeTag));
  }
  if (activeAuthor) {
    list = list.filter(m => (m.author?.name || "未知作者") === activeAuthor);
  }
  if (activeSource) {
    list = list.filter(m => getSourceValue(m) === activeSource);
  }
  if (onlyFavorites) {
    list = list.filter(m => favoriteSet.has(getModelKey(m)));
  }
  if (onlyPrinted) {
    list = list.filter(m => printedSet.has(getModelKey(m)));
  }

  return sortModelsDesc(list);
}

function render(append = false) {
  const grid = document.getElementById("grid");
  const empty = document.getElementById("empty");
  if (!grid) return;

  const list = getFilteredList();
  const total = list.length;
  if (totalCountEl) totalCountEl.textContent = String(total);

  // Infinite scroll: slice based on displayedCount
  const displayList = list.slice(0, displayedCount);

  if (!append) grid.innerHTML = "";

  if (!displayList.length) {
    const tips = [];
    if (activeTag) tips.push(`标签「${activeTag}」`);
    if (keyword) tips.push(`关键词「${kwInput.value.trim()}」`);
    if (activeAuthor) tips.push(`作者「${activeAuthor}」`);
    if (activeSource) tips.push(`来源「${formatSourceLabel(activeSource)}」`);
    if (onlyFavorites) tips.push("收藏");
    if (onlyPrinted) tips.push("已打印");
    empty.textContent = tips.length ? `未找到匹配 ${tips.join("、")}` : "暂无模型";
    empty.style.display = "block";
    return;
  }
  empty.style.display = "none";

  const startIdx = append ? grid.children.length : 0;

  displayList.slice(startIdx).forEach((m, idx) => {
    const modelKey = getModelKey(m);
    const isFavorite = modelKey && favoriteSet.has(modelKey);
    const isPrinted = modelKey && printedSet.has(modelKey);

    const card = document.createElement("article");
    card.className = "card";
    card.setAttribute('role', 'listitem');
    card.tabIndex = 0;

    // Cover Area (Clean, No Overlay)
    const coverWrap = document.createElement("div");
    coverWrap.className = "card-cover";
    coverWrap.onclick = () => window.open(getModelDetailUrl(m), `_blank`);

    const cover = document.createElement("img");
    const coverName = m.cover || "design_01.png";
    cover.src = `/files/${m.dir}/images/${coverName}`;
    cover.loading = 'lazy';
    cover.alt = m.title || m.baseName || "模型封面";
    cover.onerror = () => { cover.src = '/static/imgs/no-image.png'; };
    coverWrap.appendChild(cover);

    // Card Body
    const body = document.createElement("div");
    body.className = "card-body";

    // Title
    const title = document.createElement("h3");
    title.className = "title";
    title.title = m.title || m.baseName || "未知模型";
    title.textContent = m.title || m.baseName || "未知模型";
    title.onclick = () => window.open(getModelDetailUrl(m), `_blank`);
    body.appendChild(title);

    // Author Info
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

    // Stats Row (Icons Only)
    const statsWrap = document.createElement("div");
    statsWrap.className = "stats";

    if (m.stats?.likes > 0) {
      statsWrap.appendChild(createStatIcon("fas fa-thumbs-up", m.stats.likes, "点赞"));
    }
    if (m.stats?.favorites > 0) {
      statsWrap.appendChild(createStatIcon("fas fa-star", m.stats.favorites, "收藏"));
    }
    if (m.stats?.prints > 0) {
      statsWrap.appendChild(createStatIcon("fas fa-print", m.stats.prints, "打印"));
    }
    if (m.stats?.downloads > 0 || m.downloadCount > 0) {
      statsWrap.appendChild(createStatIcon("fas fa-download", m.stats?.downloads || m.downloadCount, "下载"));
    }
    body.appendChild(statsWrap);

    // Date Info
    const dateInfo = document.createElement("div");
    dateInfo.className = "card-dates";

    if (m.publishedAt) {
      const publishDate = document.createElement("span");
      publishDate.className = "date-item";
      publishDate.innerHTML = `<i class="far fa-calendar-alt"></i> ${formatDate(m.publishedAt)}`;
      publishDate.title = `发布时间: ${new Date(m.publishedAt).toLocaleString('zh-CN')}`;
      dateInfo.appendChild(publishDate);
    }

    if (m.collectedAt) {
      const collectDate = document.createElement("span");
      collectDate.className = "date-item";
      collectDate.innerHTML = `<i class="fas fa-archive"></i> ${formatDate(m.collectedAt)}`;
      collectDate.title = `采集时间: ${new Date(m.collectedAt).toLocaleString('zh-CN')}`;
      dateInfo.appendChild(collectDate);
    }

    if (dateInfo.children.length > 0) {
      body.appendChild(dateInfo);
    }

    // Bottom Actions Row (PERSISTENT & ALWAYS VISIBLE)
    const actions = document.createElement("div");
    actions.className = "card-actions";

    // Favorite Button
    const favBtn = document.createElement("button");
    favBtn.className = "action-btn" + (isFavorite ? " active" : "");
    favBtn.title = isFavorite ? "取消收藏" : "收藏";
    favBtn.innerHTML = isFavorite ? '<i class="fas fa-heart"></i>' : '<i class="far fa-heart"></i>';
    favBtn.onclick = (e) => { e.stopPropagation(); toggleFavorite(m); };
    actions.appendChild(favBtn);

    // Printed Button
    const printedBtn = document.createElement("button");
    printedBtn.className = "action-btn" + (isPrinted ? " active" : "");
    printedBtn.title = isPrinted ? "取消标记" : "标记已打印";
    printedBtn.innerHTML = isPrinted ? '<i class="fas fa-check-circle"></i>' : '<i class="far fa-check-circle"></i>';
    printedBtn.onclick = (e) => { e.stopPropagation(); togglePrinted(m); };
    actions.appendChild(printedBtn);

    // Spacer
    const spacer = document.createElement("div");
    spacer.style.flex = "1";
    actions.appendChild(spacer);

    // Delete Button
    const deleteBtn = document.createElement("button");
    deleteBtn.className = "action-btn danger";
    deleteBtn.title = "删除模型";
    deleteBtn.innerHTML = '<i class="fas fa-trash-alt"></i>';
    deleteBtn.onclick = (e) => { e.stopPropagation(); deleteModel(m); };
    actions.appendChild(deleteBtn);

    body.appendChild(actions);

    // Append cover first, then body
    card.appendChild(coverWrap);
    card.appendChild(body);
    grid.appendChild(card);
  });

  // Show load more indicator if there are more items
  updateLoadMoreIndicator(displayedCount < total);
}

// Helper to create simple stat icon
function createStatIcon(iconClass, count, title) {
  const span = document.createElement("span");
  span.className = "stat-chip";
  span.title = title || "";
  span.innerHTML = `<i class="${iconClass}"></i> ${count}`;
  return span;
}

function getModelDetailUrl(m) {
  var safeDir = encodeURIComponent(m.dir);
  return useV2 ? `/v2/files/${safeDir}` : `/files/${safeDir}/index.html`;
}

function escapeHtml(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

function formatDate(isoString) {
  if (!isoString) return '';
  const date = new Date(isoString);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

if (kwInput) {
  kwInput.addEventListener("input", () => { displayedCount = loadIncrement; render(); });
}
if (clearBtn && kwInput) {
  clearBtn.addEventListener("click", () => {
    kwInput.value = "";
    displayedCount = loadIncrement;
    render();
  });
}

// Reset all filters button
if (resetSearchBtn) {
  resetSearchBtn.addEventListener("click", () => {
    // Clear search input
    if (kwInput) kwInput.value = "";

    // Clear filters
    activeTag = "";
    activeAuthor = "";
    activeSource = "";
    onlyFavorites = false;
    onlyPrinted = false;

    // Collapse expanded lists
    isTagsExpanded = false;
    isAuthorsExpanded = false;

    // Reset display count
    displayedCount = loadIncrement;

    // Update UI
    syncFlagFilterButtons();
    renderFilters();
    renderAuthorFilters();
    renderSourceMenu();
    render();
  });
}

// Removed legacy reset button listener that used non-existent currentPage


// Removed pageSize input - using infinite scroll now

if (sortOrderSelect) {
  sortOrderSelect.addEventListener("change", () => {
    displayedCount = loadIncrement;
    render();
  });
}

if (favOnlyBtn) {
  favOnlyBtn.addEventListener("click", () => {
    onlyFavorites = !onlyFavorites;
    displayedCount = loadIncrement;
    syncFlagFilterButtons();
    render();
  });
}
if (printedOnlyBtn) {
  printedOnlyBtn.addEventListener("click", () => {
    onlyPrinted = !onlyPrinted;
    displayedCount = loadIncrement;
    syncFlagFilterButtons();
    render();
  });
}

// Setup infinite scroll
function setupInfiniteScroll() {
  const content = document.querySelector('.content');
  if (!content) return;

  let isLoading = false;

  content.addEventListener('scroll', () => {
    if (isLoading) return;

    const scrollTop = content.scrollTop;
    const scrollHeight = content.scrollHeight;
    const clientHeight = content.clientHeight;

    // Load more when scrolled to 80% of content
    if (scrollTop + clientHeight >= scrollHeight * 0.8) {
      const list = getFilteredList();
      const total = list.length;

      if (displayedCount < total) {
        isLoading = true;
        displayedCount += loadIncrement;
        render(true);
        setTimeout(() => { isLoading = false; }, 300);
      }
    }
  });
}

function updateLoadMoreIndicator(hasMore) {
  const grid = document.getElementById("grid");
  if (!grid) return;

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
  } else {
    if (indicator) indicator.style.display = "none";
  }
}

if (filterModal) {
  const closeBtn = filterModal.querySelector(".filter-modal__close");
  if (closeBtn) closeBtn.addEventListener("click", closeFilterModal);
  filterModal.addEventListener("click", (e) => { if (e.target === filterModal) closeFilterModal(); });
}

// lightbox controls
if (lightbox) {
  const closeBtn = lightbox.querySelector('.lightbox-close');
  const prevBtn = lightbox.querySelector('.lightbox-prev');
  const nextBtn = lightbox.querySelector('.lightbox-next');

  if (closeBtn) closeBtn.addEventListener('click', closeLightbox);
  if (prevBtn) prevBtn.addEventListener('click', lightboxPrev);
  if (nextBtn) nextBtn.addEventListener('click', lightboxNext);

  lightbox.addEventListener('click', (e) => { if (e.target === lightbox) closeLightbox(); });

  let touchStartX = 0; let touchStartY = 0; let touchStartTime = 0; let lastTap = 0;
  lightboxImg.addEventListener('touchstart', (e) => {
    if (e.touches && e.touches.length === 1) {
      touchStartX = e.touches[0].clientX; touchStartY = e.touches[0].clientY; touchStartTime = Date.now();
    }
  }, { passive: true });
  lightboxImg.addEventListener('touchend', (e) => {
    const dt = Date.now() - touchStartTime;
    const now = Date.now();
    if (now - lastTap < 300) { lightboxImg.classList.toggle('zoomed'); lastTap = 0; return; }
    lastTap = now;
    if (dt < 500 && e.changedTouches && e.changedTouches.length === 1) {
      const dx = e.changedTouches[0].clientX - touchStartX;
      const dy = e.changedTouches[0].clientY - touchStartY;
      if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) {
        if (dx < 0) lightboxNext(); else lightboxPrev();
      }
    }
  }, { passive: true });

  lightboxImg.addEventListener('dblclick', (e) => { e.preventDefault(); lightboxImg.classList.toggle('zoomed'); });

  window.addEventListener('keydown', (e) => {
    const lightboxOpen = lightbox.style.display !== 'none';
    const modalOpen = filterModal && filterModal.style.display !== 'none';
    if (e.key === 'Escape') {
      if (modalOpen) { closeFilterModal(); return; }
      if (lightboxOpen) closeLightbox();
    }
    if (lightboxOpen) {
      if (e.key === 'ArrowLeft') lightboxPrev();
      if (e.key === 'ArrowRight') lightboxNext();
    }
  });
}

// v1/v2 toggle
(function initV2Toggle() {
  const btn = document.getElementById('v2ToggleBtn');
  if (!btn) return;
  function syncBtn() {
    btn.classList.toggle('active', useV2);
    btn.title = useV2 ? '当前在线页面（点击切换为本地）' : '当前本地页面（点击切换为在线）';
    btn.querySelector('.toggle-label').textContent = useV2 ? '在线' : '本地';
  }
  syncBtn();
  btn.addEventListener('click', () => {
    useV2 = !useV2;
    localStorage.setItem('useV2', useV2 ? 'true' : 'false');
    syncBtn();
  });
})();

load();
setupInfiniteScroll();
