/**
 * model.js — v2 模型详情页前端渲染
 * 读取 meta.json 并动态生成所有页面内容
 */
(function () {
    'use strict';

    // ============ 工具函数 ============

    /** 从 URL 路径解析 modelDir */
    function getModelDir() {
        var parts = location.pathname.split('/').filter(Boolean);
        // 路由: /v2/files/{modelDir}
        var idx = parts.indexOf('v2');
        if (idx >= 0 && parts[idx + 1] === 'files' && parts.length > idx + 2) {
            return decodeURIComponent(parts[idx + 2]);
        }
        // 路由: /files/{modelDir}/index.html
        var filesIdx = parts.indexOf('files');
        if (filesIdx >= 0 && parts.length > filesIdx + 1) {
            return decodeURIComponent(parts[filesIdx + 1]);
        }
        return '';
    }

    /** 构建模型文件目录下的相对资源 URL */
    function fileUrl(modelDir, relPath) {
        if (window.__OFFLINE_META__) {
            return './' + relPath;
        }
        // 使用 API 路由替代 StaticFiles，避免中文/特殊字符路径编码问题
        return '/api/models/' + encodeURIComponent(modelDir) + '/file/' + relPath;
    }

    /** HTML 转义 */
    function esc(str) {
        if (!str) return '';
        var d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    }

    /** 格式化时长（秒） */
    function formatDuration(seconds) {
        var sec = parseInt(seconds, 10);
        if (isNaN(sec) || sec <= 0) return '';
        var hours = sec / 3600;
        if (hours >= 1) return hours.toFixed(1) + ' h';
        return (sec / 60).toFixed(1) + ' min';
    }

    /** 格式化日期 */
    function formatDate(dateStr) {
        if (!dateStr) return '';
        try {
            var clean = String(dateStr).replace('Z', '+00:00');
            var d = new Date(clean);
            if (isNaN(d.getTime())) return dateStr;
            return d.toISOString().slice(0, 10);
        } catch (e) {
            return dateStr || '';
        }
    }

    /** 提取文件名 */
    function toName(item) {
        if (!item) return null;
        var parts = String(item).replace(/\\/g, '/').split('/');
        return parts[parts.length - 1] || null;
    }

    /** 移除命名前缀（与 archiver.py 逻辑一致） */
    function stripPrefix(name, baseName) {
        if (!name || !baseName) return name;
        var prefix = baseName + '_';
        if (name.startsWith(prefix)) {
            return name.substring(prefix.length);
        }
        return name;
    }

    // ============ 数据标准化 ============

    function normalizeStats(meta) {
        var stats = meta.stats || meta.counts || {};
        return {
            likes: stats.likes || stats.like || 0,
            favorites: stats.favorites || stats.favorite || 0,
            downloads: stats.downloads || stats.download || 0,
            prints: stats.prints || stats.print || 0,
            views: stats.views || stats.read || stats.reads || 0,
        };
    }

    function normalizeAuthor(meta) {
        var a = meta.author;
        if (typeof a === 'string') return { name: a, url: '', avatar: null };
        if (!a || typeof a !== 'object') return { name: '', url: '', avatar: null };
        var avatarRel = a.avatarRelPath || a.avatar_local_path || '';
        if (!avatarRel && (a.avatarLocal || a.avatar_local)) {
            avatarRel = 'images/' + (a.avatarLocal || a.avatar_local);
        }
        return {
            name: a.name || '',
            url: a.url || '',
            avatar: avatarRel || null,
        };
    }

    function normalizeSource(meta) {
        var source = String((meta && meta.source) || '').trim().toLowerCase();
        if (source === 'mw_cn' || source === 'mw_global' || source === 'localmodel' || source === 'others') {
            return source;
        }
        var url = String((meta && meta.url) || '').trim().toLowerCase();
        if (url.indexOf('makerworld.com/') >= 0 && url.indexOf('makerworld.com.cn') < 0) {
            return 'mw_global';
        }
        return 'mw_cn';
    }

    function formatSourceLabel(source) {
        if (source === 'mw_global') return 'MakerWorld 国际';
        if (source === 'localmodel') return '手动导入';
        if (source === 'others') return '其他来源';
        return 'MakerWorld 国内';
    }

    function normalizeImages(meta) {
        var raw = meta.images;
        var design = [], summary = [], cover = null;

        if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
            design = (raw.design || []).map(toName).filter(Boolean);
            summary = (raw.summary || []).map(toName).filter(Boolean);
            cover = toName(raw.cover);
        } else if (Array.isArray(raw)) {
            design = raw.map(toName).filter(Boolean);
        }

        if (!design.length && meta.designImages) {
            meta.designImages.forEach(function (item) {
                if (typeof item === 'object') {
                    var n = toName(item.fileName || item.localName || item.relPath);
                    if (n) design.push(n);
                }
            });
        }

        if (!summary.length && meta.summaryImages) {
            meta.summaryImages.forEach(function (item) {
                if (typeof item === 'object') {
                    var n = toName(item.fileName || item.relPath);
                    if (n) summary.push(n);
                } else if (typeof item === 'string') {
                    var n2 = toName(item);
                    if (n2) summary.push(n2);
                }
            });
        }

        if (!cover) {
            var ci = meta.cover || {};
            cover = toName(ci.relPath || ci.localName);
        }

        return { design: design, summary: summary, cover: cover };
    }

    // ============ 实例文件名计算 ============

    function pickInstanceFilename(inst, nameHint) {
        // 优先使用已明确指定的文件名
        var explicit = toName((inst && (inst.fileName || inst.name || inst.sourceFileName || inst.localName)) || '');
        if (explicit) return explicit;

        // 优先按真实文件名字段推断，避免回退到 title 造成错链
        var baseName = (inst && (inst.name || inst.sourceFileName || inst.fileName)) || '';
        if (!baseName && inst) baseName = String(inst.id || 'model');
        // 简单 sanitize：去除文件系统不允许的字符
        var base = String(baseName).replace(/[\\/:*?"<>|]/g, '_').replace(/\s+$/, '');
        if (!base) base = String((inst && inst.id) || 'model');
        // 如果 base 本身就带 .3mf 后缀，先去掉
        if (/\.3mf$/i.test(base)) base = base.slice(0, -4);

        // 从 nameHint 推断扩展名
        var ext = '';
        var hint = nameHint || (inst && (inst.name || inst.sourceFileName)) || '';
        if (hint && hint.indexOf('.') > -1) {
            ext = '.' + hint.split('.').pop();
        }
        if (!ext) {
            ext = '.3mf';
        } else if (!ext.startsWith('.')) {
            ext = '.' + ext;
        }
        return base + ext;
    }

    function pickInstanceFilenameStrict(inst) {
        var n = toName((inst && (inst.fileName || inst.name || inst.sourceFileName || inst.localName)) || '');
        return n || '';
    }

    // ============ DOM 渲染 ============

    var MODEL_DIR = '';
    var OFFLINE_API_BASE_KEY = 'mw_offline_api_base';
    var DEFAULT_OFFLINE_API_BASE = 'http://127.0.0.1:8000';

    function normalizeApiBase(raw) {
        var v = String(raw || '').trim();
        if (!v) return '';
        return v.replace(/\/+$/, '');
    }

    function getOfflineApiBase() {
        var fromQuery = '';
        var fromMeta = '';
        var fromStorage = '';

        try {
            var q = new URLSearchParams(location.search || '');
            fromQuery = normalizeApiBase(q.get('apiBase') || '');
        } catch (_) { }

        try {
            var m = window.__OFFLINE_META__ || {};
            fromMeta = normalizeApiBase(m.apiBase || m.api_base || '');
        } catch (_) { }

        try {
            fromStorage = normalizeApiBase(localStorage.getItem(OFFLINE_API_BASE_KEY) || '');
        } catch (_) { }

        var chosen = fromQuery || fromMeta || fromStorage || DEFAULT_OFFLINE_API_BASE;
        chosen = normalizeApiBase(chosen);
        try {
            if (chosen) localStorage.setItem(OFFLINE_API_BASE_KEY, chosen);
        } catch (_) { }
        return chosen;
    }

    function apiUrl(path) {
        var p = String(path || '');
        if (location.protocol === 'file:') {
            var base = getOfflineApiBase();
            return base ? (base + p) : p;
        }
        return p;
    }

    function canUseBackendApi() {
        if (!MODEL_DIR) return false;
        if (location.protocol === 'file:') return false;
        return true;
    }

    function getOfflineFileList(kind) {
        try {
            var meta = window.__OFFLINE_META__ || {};
            var offline = meta.offlineFiles || {};
            var arr = null;
            if (kind === 'attachments') {
                if (Array.isArray(offline.attachments)) arr = offline.attachments;
                else if (Array.isArray(meta.attachments)) arr = meta.attachments;
                else if (Array.isArray(meta.attachmentFiles)) arr = meta.attachmentFiles;
            } else if (kind === 'printed') {
                if (Array.isArray(offline.printed)) arr = offline.printed;
                else if (Array.isArray(meta.printed)) arr = meta.printed;
                else if (Array.isArray(meta.printedFiles)) arr = meta.printedFiles;
            }
            if (!Array.isArray(arr)) return null;
            return arr.filter(function (x) { return typeof x === 'string' && x.trim(); });
        } catch (_) {
            return null;
        }
    }

    function renderTitle(meta) {
        var el = document.getElementById('titleSection');
        var title = esc(meta.title || '');
        var url = meta.url || '';
        el.innerHTML = title +
            (url ? ' <a class="origin-link" href="' + esc(url) + '" target="_blank" rel="noreferrer">原文链接</a>' : '');
        document.title = meta.title || '模型详情';
    }

    function renderAuthor(meta) {
        var author = normalizeAuthor(meta);
        var el = document.getElementById('authorSection');
        var html = '';
        if (author.avatar) {
            html += '<img class="avatar" src="' + fileUrl(MODEL_DIR, author.avatar) + '" alt="avatar">';
        }
        html += '作者：';
        if (author.url) {
            html += '<a href="' + esc(author.url) + '" target="_blank" rel="noreferrer">' + esc(author.name) + '</a>';
        } else {
            html += esc(author.name);
        }
        el.innerHTML = html;
    }

    function renderHero(meta, images) {
        var el = document.getElementById('heroImage');
        // 优先 screenshot, 然后 cover, 然后第一张 design
        var src = '';
        // 尝试 screenshot（可能是 .png .jpg .webp）
        var exts = ['png', 'jpg', 'jpeg', 'webp'];
        for (var i = 0; i < exts.length; i++) {
            // 我们先构建 URL，后面 onerror 处理
            if (i === 0) src = fileUrl(MODEL_DIR, 'screenshot.png');
        }
        if (images.cover) {
            // 用 cover 作为 fallback
            el.onerror = function () {
                this.onerror = null;
                this.src = fileUrl(MODEL_DIR, 'images/' + images.cover);
            };
        } else if (images.design.length) {
            el.onerror = function () {
                this.onerror = null;
                this.src = fileUrl(MODEL_DIR, 'images/' + images.design[0]);
            };
        }
        el.src = src;
    }

    function renderCollectDate(meta) {
        var el = document.getElementById('collectDate');
        var ts = meta.collectDate; // Unix timestamp from server
        if (!ts) {
            el.textContent = '';
            return;
        }
        var d = new Date(ts * 1000);
        var dateStr = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
        el.innerHTML = '<i class="far fa-calendar-alt"></i> 采集于 ' + dateStr;
    }

    function renderSource(meta) {
        var el = document.getElementById('sourceBadge');
        if (!el) return;
        var source = normalizeSource(meta);
        el.textContent = formatSourceLabel(source);
        el.className = 'source-badge source-badge--' + source;
    }

    function renderStats(meta) {
        var source = normalizeSource(meta);
        var isOthers = source === 'others' || source === 'localmodel';
        if (isOthers) return;
        var stats = normalizeStats(meta);
        var el = document.getElementById('statsSection');

        var frags = [
            '<div class="stat-item"><div class="stat-val">' + stats.downloads + '</div><div class="stat-lbl">下载</div></div>',
            '<div class="stat-item"><div class="stat-val">' + stats.likes + '</div><div class="stat-lbl">点赞</div></div>',
            '<div class="stat-item"><div class="stat-val">' + (stats.prints || '-') + '</div><div class="stat-lbl">打印</div></div>'
        ];

        var iconsHtml = '<div class="stats-icons-row">' +
            '<span class="stat-chip" title="收藏"><i class="fas fa-star"></i> ' + stats.favorites + '</span>' +
            '<span class="stat-chip" title="浏览"><i class="fas fa-eye"></i> ' + stats.views + '</span>' +
            '</div>';

        el.innerHTML = '<div class="stats">' + frags.join('') + '</div>' + iconsHtml;
    }

    function renderTags(meta) {
        var tags = meta.tags || meta.tagsOriginal || [];
        var block = document.getElementById('tagsBlock');
        var el = document.getElementById('tagList');
        if (!tags.length) {
            block.classList.add('hidden');
            el.innerHTML = '';
            return;
        }
        block.classList.remove('hidden');
        el.innerHTML = tags.map(function (t) {
            return '<span>' + esc(t) + '</span>';
        }).join('\n');
    }

    function renderSummary(meta) {
        var s = meta.summary || {};
        var html = s.html || s.raw || '';
        // 移除翻译文本
        html = html.replace(/<div[^>]*class="[^"]*translated-text[^"]*"[^>]*>.*?<\/div>/gis, '');
        // 修正 summary 中的图片路径 — 如果 src 是相对路径则映射到 /files/{modelDir}/images/
        html = html.replace(/src="(?!https?:\/\/|\/)(.*?)"/g, function (match, p1) {
            return 'src="' + fileUrl(MODEL_DIR, 'images/' + toName(p1)) + '"';
        });
        document.getElementById('summaryContent').innerHTML = html;
    }

    // ============ 实例卡片 ============

    function buildInstanceHtml(inst, baseName) {
        var title = inst.title || inst.name || '实例 ' + (inst.id || '');
        var publish = formatDate(inst.publishTime || '');
        var summary = inst.summary || '';
        var dls = inst.downloadCount || 0;
        var prints = inst.printCount || 0;
        var weight = inst.weight || '';
        var prediction = inst.prediction;
        var timeStr = prediction ? formatDuration(prediction) : '';
        var plates = inst.plates || [];
        var plateCnt = plates.length;
        var pictures = inst.pictures || [];
        var filaments = inst.instanceFilaments || [];

        var isFileProtocol = location.protocol === 'file:';
        var isOfflineMetaPage = !isFileProtocol && !!window.__OFFLINE_META__;
        var hasInstId = inst && inst.id !== undefined && inst.id !== null && String(inst.id).trim() !== '';
        var hasModelDir = !!String(MODEL_DIR || '').trim();

        // 关键规则：
        // 1) 直开 file:// 与 /files 离线页（内嵌 __OFFLINE_META__）都严格用真实文件名字段
        // 2) 在线模式才允许兼容推断
        var fileName = (isFileProtocol || isOfflineMetaPage)
            ? pickInstanceFilenameStrict(inst)
            : pickInstanceFilename(inst, inst.name || '');

        var dlHrefLocal = '';
        if (!isFileProtocol && hasInstId && hasModelDir) {
            // HTTP 场景优先实例下载接口，避免任何 title/name 偏差
            dlHrefLocal = apiUrl('/api/models/' + encodeURIComponent(MODEL_DIR) + '/instances/' + encodeURIComponent(String(inst.id)) + '/download');
        } else if (!isFileProtocol && fileName && hasModelDir) {
            // 兜底走后端文件接口（仍不直接拼 /files 路径）
            dlHrefLocal = apiUrl('/api/models/' + encodeURIComponent(MODEL_DIR) + '/file/instances/' + encodeURIComponent(fileName));
        } else if (fileName) {
            // 仅 file:// 场景使用相对本地路径
            dlHrefLocal = fileUrl(MODEL_DIR, 'instances/' + fileName);
        }

        function toHex(str) {
            var utf8Str = unescape(encodeURIComponent(str));
            var hex = '';
            for (var i = 0; i < utf8Str.length; i++) {
                var h = utf8Str.charCodeAt(i).toString(16);
                if (h.length === 1) h = '0' + h;
                hex += h;
            }
            return hex;
        }
        var rawRelPath = MODEL_DIR + '/instances/' + (fileName || '');
        // 仅在线模式显示 Bambu 打印按钮：
        // - v2 在线页（无 __OFFLINE_META__）显示
        // - /files 离线页与 file:// 直开隐藏
        var showBambuButton = !isFileProtocol && !isOfflineMetaPage;

        var bambuProxyUrl = '';
        if (!isFileProtocol && hasInstId && hasModelDir) {
            bambuProxyUrl = apiUrl('/api/bambu/model/' + encodeURIComponent(MODEL_DIR) + '/instance/' + encodeURIComponent(String(inst.id)) + '.3mf');
        } else if (!isFileProtocol && fileName && hasModelDir) {
            bambuProxyUrl = apiUrl('/api/models/' + encodeURIComponent(MODEL_DIR) + '/file/instances/' + encodeURIComponent(fileName));
        } else if (isFileProtocol) {
            bambuProxyUrl = fileName ? new URL(fileUrl(MODEL_DIR, 'instances/' + fileName), window.location.href).href : '';
        } else {
            bambuProxyUrl = window.location.origin + '/api/bambu/download/' + toHex(rawRelPath) + '.3mf';
        }
        // Bambu Studio 需要可直接访问的绝对 http(s) URL，不能是相对路径
        var bambuProxyUrlAbs = String(bambuProxyUrl || '');
        if (bambuProxyUrlAbs && !/^https?:\/\//i.test(bambuProxyUrlAbs)) {
            bambuProxyUrlAbs = window.location.origin + bambuProxyUrlAbs;
        }

        // 耗材 chips
        var chipsHtml = '';
        if (filaments.length) {
            var chips = filaments.map(function (f) {
                var typ = f.type || '';
                var usedG = f.usedG || f.usedg || '';
                var col = f.color || '';
                var dot = col ? '<span class="color-dot" style="background:' + esc(col) + '"></span>' : '';
                return '<span class="chip">' + dot + esc(typ) + ' ' + usedG + 'g</span>';
            });
            chipsHtml = '<div class="chips">' + chips.join('\n') + '</div>';
        }

        // 盘片弹窗使用的详细 HTML
        var platesDataHtml = '';
        if (plates.length) {
            platesDataHtml = plates.map(function (p) {
                var th = toName(p.thumbnailRelPath || '');
                var localTh = stripPrefix(th, baseName);
                var pred = p.prediction ? formatDuration(p.prediction) : '';
                var w = p.weight ? p.weight + ' g' : '';

                var fs = p.filaments || [];
                var fsHtml = '';
                if (fs.length) {
                    fsHtml = '<div class="plate-row-filaments">' + fs.map(function (f) {
                        var col = f.color ? '<span class="color-dot" style="background:' + esc(f.color) + ';width:12px;height:12px;margin-right:4px;"></span>' : '';
                        return '<span class="chip" style="font-size:12px;">' + col + esc(f.type || '') + ' | ' + (f.usedG || f.usedg || '') + ' g</span>';
                    }).join('') + '</div>';
                }

                var imgSrc = localTh ? fileUrl(MODEL_DIR, 'images/' + localTh) : '';
                var spoolIcon = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: text-bottom; margin-right: 4px;"><path d="M4.5 12c0-4.142 1.567-7.5 3.5-7.5s3.5 3.358 3.5 7.5-1.567 7.5-3.5 7.5-3.5-3.358-3.5-7.5z"/><path d="M11 4.5h5c1.933 0 3.5 3.358 3.5 7.5s-1.567 7.5-3.5 7.5h-5"/><circle cx="8" cy="12" r="1.5"/></svg>';
                return '<div class="plate-row">' +
                    '<div class="plate-row-img">' +
                    '<div class="p-index">盘 ' + (p.index || '') + '</div>' +
                    (imgSrc ? '<img src="' + imgSrc + '" alt="plate ' + p.index + '">' : '') +
                    '</div>' +
                    '<div class="plate-row-info">' +
                    '<div class="plate-row-stats">' +
                    (pred ? '<span><i class="far fa-clock"></i> ' + pred + '</span>' : '') +
                    (w ? '<span>' + spoolIcon + w + '</span>' : '') +
                    '</div>' +
                    fsHtml +
                    '</div>' +
                    '</div>';
            }).join('').replace(/"/g, '&quot;'); // 转义双引号以便存入 data 属性
        }

        // 实例配图
        var picsHtml = '';
        if (pictures.length) {
            var imgs = pictures.map(function (pic) {
                var rel = stripPrefix(toName(pic.relPath || ''), baseName);
                if (!rel) return '';
                return '<img class="inst-thumb zoomable" src="' + fileUrl(MODEL_DIR, 'images/' + rel) + '" alt="pic ' + (pic.index || '') + '" style="width:80px;height:80px;object-fit:cover;border-radius:4px;cursor:zoom-in;">';
            }).filter(Boolean);
            if (imgs.length) picsHtml = '<div class="thumbs" style="padding:0;background:transparent;">' + imgs.join('') + '</div>';
        }

        // 统计（others 来源隐藏）
        var statsHtml = '<div class="inst-meta">' +
            '<span class="meta-item" title="下载次数"><i class="fas fa-download"></i> ' + dls + '</span>' +
            '<span class="meta-item" title="打印次数"><i class="fas fa-print"></i> ' + prints + '</span>' +
            '<span class="meta-item" title="预计打印时间"><i class="far fa-clock"></i> ' + timeStr + '</span>' +
            '<span class="meta-item" title="重量"><i class="fas fa-weight-hanging"></i> ' + weight + ' g</span>' +
            '</div>';

        return '<div class="inst-card">' +
            '<div class="inst-header">' +
            '<div class="inst-title-area">' +
            '<strong>' + esc(title) + '</strong>' +
            '<span class="inst-publish">' + (publish ? publish : '') +
            (plateCnt ? '<span class="meta-badge" style="margin-left:8px;"><i class="fas fa-puzzle-piece"></i> ' + plateCnt + ' 盘</span>' : '') +
            '</span>' +
            '</div>' +
            (dlHrefLocal ? '<div class="inst-actions">' +
                (platesDataHtml ? '<button class="inst-btn inst-details" onclick="openPlatesModal(this)" data-plates="' + platesDataHtml + '"><i class="fas fa-list"></i> 详情</button>' : '') +
                (showBambuButton ? '<a class="inst-btn inst-bambu" href="bambustudio://open?file=' + encodeURIComponent(bambuProxyUrlAbs) + '" title="在 Bambu Studio 中打开"><i class="fas fa-cube"></i> 打印</a>' : '') +
                '<a class="inst-btn inst-local" href="' + dlHrefLocal + '" target="_blank" rel="noreferrer" title="下载资源"><i class="fas fa-download"></i> 下载</a>' +
                '</div>' : '') +
            '</div>' +
            statsHtml +
            chipsHtml +
            picsHtml +
            (summary ? '<div style="margin-top:12px;font-size:13px;color:var(--text-secondary);">' + summary + '</div>' : '') +
            '</div>';
    }

    function renderInstances(meta) {
        var instances = meta.instances || [];
        var el = document.getElementById('instanceList');
        if (!instances.length) { el.innerHTML = ''; return; }
        el.innerHTML = instances.map(function (inst) {
            return buildInstanceHtml(inst, meta.baseName);
        }).join('\n');
    }

    // ============ 设计图轮播 ============

    function renderCarousel(images) {
        var designImgs = images.design || [];
        var el = document.getElementById('carouselSection');
        if (!designImgs.length) { el.innerHTML = ''; return; }

        var imgTags = designImgs.map(function (fn) {
            return '<img src="' + fileUrl(MODEL_DIR, 'images/' + fn) + '" alt="design image">';
        }).join('\n');

        var thumbTags = designImgs.map(function (fn, i) {
            return '<img data-idx="' + i + '" src="' + fileUrl(MODEL_DIR, 'images/' + fn) + '" alt="thumb ' + (i + 1) + '">';
        }).join('\n');

        el.innerHTML =
            '<div class="carousel" id="designCarousel">' +
            '<div class="carousel-track">' + imgTags + '</div>' +
            '<button class="carousel-btn prev" type="button">◀</button>' +
            '<button class="carousel-btn next" type="button">▶</button>' +
            '</div>' +
            '<div class="thumbs" id="designThumbs">' + thumbTags + '</div>';

        initCarousel();
    }

    function initCarousel() {
        var carousel = document.getElementById('designCarousel');
        if (!carousel) return;
        var track = carousel.querySelector('.carousel-track');
        var slides = carousel.querySelectorAll('.carousel-track > img');
        var prevBtn = carousel.querySelector('.prev');
        var nextBtn = carousel.querySelector('.next');
        var thumbs = document.querySelectorAll('#designThumbs img');
        if (!track || slides.length === 0) return;

        var index = 0;
        function update() {
            var width = carousel.clientWidth;
            track.style.transform = 'translateX(' + (-index * width) + 'px)';
            thumbs.forEach(function (t, i) {
                if (i === index) t.classList.add('active');
                else t.classList.remove('active');
            });
        }
        function go(delta) {
            index = (index + delta + slides.length) % slides.length;
            update();
        }
        window.addEventListener('resize', update);
        prevBtn.addEventListener('click', function () { go(-1); });
        nextBtn.addEventListener('click', function () { go(1); });
        thumbs.forEach(function (t, i) {
            t.addEventListener('click', function () {
                index = i;
                update();
            });
        });
        update();
    }

    // ============ 灯箱 ============

    function initLightbox() {
        var overlay = document.getElementById('imgLightbox');
        var overlayImg = overlay ? overlay.querySelector('img') : null;
        if (!overlay || !overlayImg) return;

        var currentImages = [];
        var currentIndex = -1;

        function showImage(index) {
            if (currentImages.length === 0) return;
            if (index < 0) index = currentImages.length - 1;
            if (index >= currentImages.length) index = 0;
            currentIndex = index;
            overlayImg.src = currentImages[currentIndex].src;
        }

        document.addEventListener('click', function (e) {
            var target = e.target;

            // Handle lightbox navigation arrows
            if (target.closest('.lb-prev')) {
                e.preventDefault();
                showImage(currentIndex - 1);
                return;
            }
            if (target.closest('.lb-next')) {
                e.preventDefault();
                showImage(currentIndex + 1);
                return;
            }

            if (!(target instanceof HTMLImageElement)) return;
            if (!target.classList.contains('zoomable')) return;

            currentImages = Array.from(document.querySelectorAll('img.zoomable'));
            currentIndex = currentImages.indexOf(target);
            if (currentIndex === -1) {
                currentImages.push(target);
                currentIndex = currentImages.length - 1;
            }

            overlayImg.src = target.src;
            overlay.classList.add('show');
        });

        overlay.addEventListener('click', function (e) {
            // Close if clicked outside arrows or image
            if (e.target === overlay || e.target === overlayImg) {
                overlay.classList.remove('show');
                overlayImg.src = '';
            }
        });

        // Keyboard arrows support
        document.addEventListener('keydown', function (e) {
            if (!overlay.classList.contains('show')) return;
            if (e.key === 'ArrowLeft') showImage(currentIndex - 1);
            else if (e.key === 'ArrowRight') showImage(currentIndex + 1);
            else if (e.key === 'Escape') {
                overlay.classList.remove('show');
                overlayImg.src = '';
            }
        });
    }

    // ============ Bambu 打开防重入 ============
    function initBambuOpenGuard() {
        if (window.__mw_bambu_guard_inited) return;
        window.__mw_bambu_guard_inited = true;

        var lastHref = '';
        var lastTs = 0;

        document.addEventListener('click', function (e) {
            var target = e.target;
            if (!target || !target.closest) return;
            var link = target.closest('a.inst-bambu');
            if (!link) return;

            var href = String(link.getAttribute('href') || '');
            if (!/^bambustudio:\/\//i.test(href)) return;

            // 统一由脚本触发，避免浏览器偶发重复拉起协议
            e.preventDefault();
            e.stopPropagation();

            var now = Date.now();
            if (href === lastHref && (now - lastTs) < 1500) {
                return;
            }
            lastHref = href;
            lastTs = now;
            window.location.href = href;
        }, true);
    }

    // ============ 附件 ============

    function initAttachments() {
        var listEl = document.getElementById('attachList');
        var msgEl = document.getElementById('attachMsg');
        var inputEl = document.getElementById('attachInput');
        var btnEl = document.getElementById('attachUploadBtn');
        if (!listEl) return;

        function setMsg(text, isError) {
            if (!msgEl) return;
            msgEl.textContent = text || '';
            if (isError) msgEl.classList.add('error');
            else msgEl.classList.remove('error');
        }

        function renderList(files) {
            listEl.innerHTML = '';
            if (!files || !files.length) {
                var li = document.createElement('li');
                li.className = 'attach-empty';
                li.textContent = '暂无附件';
                listEl.appendChild(li);
                return;
            }
            files.forEach(function (name) {
                var li = document.createElement('li');
                var link = document.createElement('a');
                link.href = fileUrl(MODEL_DIR, 'file/' + encodeURIComponent(name));
                link.textContent = name;
                link.setAttribute('download', name);
                li.appendChild(link);
                listEl.appendChild(li);
            });
        }

        function loadList() {
            function loadFromLocalIndex() {
                var metaList = getOfflineFileList('attachments');
                if (metaList !== null) {
                    renderList(metaList);
                    setMsg('离线模式：已从页面元数据加载附件');
                    return;
                }
                fetch('./file/_index.json')
                    .then(function (res) { return res.ok ? res.json() : Promise.reject(res.status); })
                    .then(function (data) {
                        renderList((data && data.files) || []);
                        setMsg('离线模式：已从本地清单加载附件');
                    })
                    .catch(function () {
                        renderList([]);
                        setMsg('离线模式未找到附件清单（_index.json）', true);
                    });
            }
            if (location.protocol === 'file:') {
                var quickMetaList = getOfflineFileList('attachments');
                if (quickMetaList !== null) {
                    renderList(quickMetaList);
                    setMsg('离线模式：已从页面元数据加载附件');
                    return;
                }
            }
            if (!canUseBackendApi()) {
                loadFromLocalIndex();
                return;
            }
            fetch(apiUrl('/api/models/' + encodeURIComponent(MODEL_DIR) + '/attachments'))
                .then(function (res) { return res.ok ? res.json() : Promise.reject(res.status); })
                .then(function (data) {
                    renderList((data && data.files) || []);
                    setMsg('');
                })
                .catch(function () {
                    if (location.protocol === 'file:') {
                        loadFromLocalIndex();
                        return;
                    }
                    renderList([]);
                    setMsg('附件列表加载失败', true);
                });
        }
        loadList();

        if (!btnEl || !inputEl) return;
        btnEl.addEventListener('click', async function () {
            if (!canUseBackendApi()) {
                setMsg('当前页面不支持上传，请通过本地服务地址访问', true);
                return;
            }
            var files = inputEl.files ? Array.from(inputEl.files) : [];
            if (!files.length) { setMsg('请选择附件', true); return; }
            btnEl.disabled = true;
            var success = 0, failed = 0;
            setMsg('上传中... (0/' + files.length + ')');
            for (var fi = 0; fi < files.length; fi++) {
                var fd = new FormData();
                fd.append('file', files[fi]);
                try {
                    var res = await fetch(apiUrl('/api/models/' + encodeURIComponent(MODEL_DIR) + '/attachments'), {
                        method: 'POST', body: fd,
                    });
                    if (!res.ok) throw new Error('upload failed');
                    success++;
                } catch (e) { failed++; }
                setMsg('上传中... (' + (success + failed) + '/' + files.length + ')');
            }
            inputEl.value = '';
            loadList();
            if (failed === 0) setMsg('上传成功');
            else if (success === 0) setMsg('上传失败', true);
            else setMsg('部分成功 ' + success + '/' + files.length, true);
            btnEl.disabled = false;
        });
    }

    // ============ 打印成品 ============

    function initPrinted() {
        var listEl = document.getElementById('printedList');
        var msgEl = document.getElementById('printedMsg');
        var inputEl = document.getElementById('printedInput');
        var btnEl = document.getElementById('printedUploadBtn');
        if (!listEl) return;

        function setMsg(text, isError) {
            if (!msgEl) return;
            msgEl.textContent = text || '';
            if (isError) msgEl.classList.add('error');
            else msgEl.classList.remove('error');
        }

        function renderList(files) {
            listEl.innerHTML = '';
            if (!files || !files.length) {
                var empty = document.createElement('div');
                empty.className = 'printed-empty';
                empty.textContent = '暂无图片';
                listEl.appendChild(empty);
                return;
            }
            files.forEach(function (name) {
                var item = document.createElement('div');
                item.className = 'printed-item';
                var img = document.createElement('img');
                img.className = 'zoomable';
                img.src = fileUrl(MODEL_DIR, 'printed/' + encodeURIComponent(name));
                img.alt = name;
                var caption = document.createElement('div');
                caption.className = 'printed-caption';
                caption.textContent = name;
                item.appendChild(img);
                item.appendChild(caption);
                listEl.appendChild(item);
            });
        }

        function loadList() {
            function loadFromLocalIndex() {
                var metaList = getOfflineFileList('printed');
                if (metaList !== null) {
                    renderList(metaList);
                    setMsg('离线模式：已从页面元数据加载图片');
                    return;
                }
                fetch('./printed/_index.json')
                    .then(function (res) { return res.ok ? res.json() : Promise.reject(res.status); })
                    .then(function (data) {
                        renderList((data && data.files) || []);
                        setMsg('离线模式：已从本地清单加载图片');
                    })
                    .catch(function () {
                        renderList([]);
                        setMsg('离线模式未找到图片清单（_index.json）', true);
                    });
            }
            if (location.protocol === 'file:') {
                var quickMetaList = getOfflineFileList('printed');
                if (quickMetaList !== null) {
                    renderList(quickMetaList);
                    setMsg('离线模式：已从页面元数据加载图片');
                    return;
                }
            }
            if (!canUseBackendApi()) {
                loadFromLocalIndex();
                return;
            }
            fetch(apiUrl('/api/models/' + encodeURIComponent(MODEL_DIR) + '/printed'))
                .then(function (res) { return res.ok ? res.json() : Promise.reject(res.status); })
                .then(function (data) {
                    renderList((data && data.files) || []);
                    setMsg('');
                })
                .catch(function () {
                    if (location.protocol === 'file:') {
                        loadFromLocalIndex();
                        return;
                    }
                    renderList([]);
                    setMsg('图片列表加载失败', true);
                });
        }
        loadList();

        if (!btnEl || !inputEl) return;
        btnEl.addEventListener('click', async function () {
            if (!canUseBackendApi()) {
                setMsg('当前页面不支持上传，请通过本地服务地址访问', true);
                return;
            }
            var files = inputEl.files ? Array.from(inputEl.files) : [];
            if (!files.length) { setMsg('请选择图片', true); return; }
            btnEl.disabled = true;
            var success = 0, failed = 0;
            setMsg('上传中... (0/' + files.length + ')');
            for (var fi = 0; fi < files.length; fi++) {
                var fd = new FormData();
                fd.append('file', files[fi]);
                try {
                    var res = await fetch(apiUrl('/api/models/' + encodeURIComponent(MODEL_DIR) + '/printed'), {
                        method: 'POST', body: fd,
                    });
                    if (!res.ok) throw new Error('upload failed');
                    success++;
                } catch (e) { failed++; }
                setMsg('上传中... (' + (success + failed) + '/' + files.length + ')');
            }
            inputEl.value = '';
            loadList();
            if (failed === 0) setMsg('上传成功');
            else if (success === 0) setMsg('上传失败', true);
            else setMsg('部分成功 ' + success + '/' + files.length, true);
            btnEl.disabled = false;
        });
    }

    // ============ 在线追加打印配置 ============

    function initInstanceImport() {
        var bar = document.getElementById('instanceAdminBar');
        var openBtn = document.getElementById('instanceImportOpenBtn');
        var modal = document.getElementById('instanceImportModal');
        var closeBtn = document.getElementById('instanceImportCloseBtn');
        var cancelBtn = document.getElementById('instanceImportCancelBtn');
        var fileInput = document.getElementById('instanceImportFileInput');
        var parseBtn = document.getElementById('instanceImportParseBtn');
        var preview = document.getElementById('instanceImportPreview');
        var sourceNameEl = document.getElementById('instanceImportSourceName');
        var titleInput = document.getElementById('instanceImportTitleInput');
        var summaryInput = document.getElementById('instanceImportSummaryInput');
        var picsEl = document.getElementById('instanceImportPics');
        var platesEl = document.getElementById('instanceImportPlates');
        var saveBtn = document.getElementById('instanceImportSaveBtn');
        var msgEl = document.getElementById('instanceImportMsg');
        if (!bar || !openBtn || !modal || !closeBtn || !cancelBtn || !fileInput || !parseBtn || !saveBtn) return;

        var parsedFile = null;
        var parseDraftSessionId = '';

        function normalize3mfName(name) {
            return String(name || '').replace(/^s\d+_/i, '');
        }

        function normalizeSessionId(value) {
            var sid = String(value || '').trim();
            return /^[a-f0-9]{32}$/.test(sid) ? sid : '';
        }

        async function discardParseDraft(sessionId) {
            var sid = normalizeSessionId(sessionId);
            if (!sid) return;
            try {
                await fetch(apiUrl('/api/manual/drafts/' + encodeURIComponent(sid)), {
                    method: 'DELETE'
                });
            } catch (_) { }
            if (parseDraftSessionId === sid) parseDraftSessionId = '';
        }

        function stem(name) {
            var n = normalize3mfName(name);
            var i = n.lastIndexOf('.');
            return i > 0 ? n.slice(0, i) : n;
        }

        function renderImageList(el, items, type) {
            if (!el) return;
            el.innerHTML = '';
            if (!items || !items.length) {
                var empty = document.createElement('div');
                empty.className = 'inst-import-gallery-item';
                empty.innerHTML = '<div class="caption">无</div>';
                el.appendChild(empty);
                return;
            }
            items.forEach(function (item, idx) {
                var url = '';
                var cap = '';
                if (type === 'pic') {
                    url = item && item.previewUrl ? item.previewUrl : '';
                    cap = '图 ' + (idx + 1);
                } else {
                    url = item && item.thumbnailPreviewUrl ? item.thumbnailPreviewUrl : '';
                    cap = '盘 ' + (item && item.index ? item.index : (idx + 1));
                }
                if (!url) return;
                var wrap = document.createElement('div');
                wrap.className = 'inst-import-gallery-item';
                var img = document.createElement('img');
                img.src = url;
                img.alt = cap;
                var caption = document.createElement('div');
                caption.className = 'caption';
                caption.textContent = cap;
                wrap.appendChild(img);
                wrap.appendChild(caption);
                el.appendChild(wrap);
            });
            if (!el.children.length) {
                var empty2 = document.createElement('div');
                empty2.className = 'inst-import-gallery-item';
                empty2.innerHTML = '<div class="caption">无</div>';
                el.appendChild(empty2);
            }
        }

        function setMsg(text, isError) {
            if (!msgEl) return;
            msgEl.textContent = text || '';
            if (isError) msgEl.classList.add('error');
            else msgEl.classList.remove('error');
        }

        function resetModal() {
            parsedFile = null;
            parseDraftSessionId = '';
            fileInput.value = '';
            if (preview) preview.classList.add('hidden');
            if (sourceNameEl) sourceNameEl.textContent = '-';
            if (titleInput) titleInput.value = '';
            if (summaryInput) summaryInput.value = '';
            renderImageList(picsEl, [], 'pic');
            renderImageList(platesEl, [], 'plate');
            saveBtn.disabled = true;
            setMsg('');
        }

        function openModal() {
            resetModal();
            modal.classList.add('active');
            modal.setAttribute('aria-hidden', 'false');
            document.body.style.overflow = 'hidden';
        }

        function closeModal() {
            var sid = parseDraftSessionId;
            modal.classList.remove('active');
            modal.setAttribute('aria-hidden', 'true');
            document.body.style.overflow = '';
            resetModal();
            discardParseDraft(sid);
        }

        if (!canUseBackendApi() || location.protocol === 'file:') {
            bar.classList.add('hidden');
            return;
        }
        bar.classList.remove('hidden');

        openBtn.addEventListener('click', openModal);
        closeBtn.addEventListener('click', closeModal);
        cancelBtn.addEventListener('click', closeModal);
        modal.addEventListener('click', function (e) {
            if (e.target === modal) closeModal();
        });

        parseBtn.addEventListener('click', async function () {
            var f = fileInput.files && fileInput.files[0];
            if (!f) {
                setMsg('请先选择 3MF 文件', true);
                return;
            }
            if (!/\.3mf$/i.test(f.name || '')) {
                setMsg('仅支持 .3mf 文件', true);
                return;
            }
            parseBtn.disabled = true;
            setMsg('正在识别配置信息...');
            try {
                var prevSid = parseDraftSessionId;
                var fd = new FormData();
                fd.append('files', f);
                var res = await fetch(apiUrl('/api/manual/3mf/parse'), {
                    method: 'POST',
                    body: fd
                });
                if (!res.ok) {
                    var txt = await res.text();
                    throw new Error(txt || ('HTTP ' + res.status));
                }
                var data = await res.json();
                var draft = data && data.draft ? data.draft : null;
                var inst = draft && Array.isArray(draft.instances) ? draft.instances[0] : null;
                if (!inst) throw new Error('未识别到实例配置');
                var newSid = normalizeSessionId(draft && draft.sessionId ? draft.sessionId : '');
                parseDraftSessionId = newSid;
                if (prevSid && prevSid !== newSid) {
                    discardParseDraft(prevSid);
                }
                parsedFile = f;
                if (preview) preview.classList.remove('hidden');
                if (sourceNameEl) sourceNameEl.textContent = normalize3mfName(inst.sourceFileName || inst.name || f.name);
                if (titleInput) titleInput.value = inst.title || stem(f.name);
                if (summaryInput) summaryInput.value = inst.summary || '';
                renderImageList(picsEl, inst.pictures || [], 'pic');
                renderImageList(platesEl, inst.plates || [], 'plate');
                saveBtn.disabled = false;
                setMsg('识别完成，可修改后保存');
            } catch (e) {
                setMsg('识别失败：' + (e.message || e), true);
            } finally {
                parseBtn.disabled = false;
            }
        });

        saveBtn.addEventListener('click', async function () {
            var f = parsedFile || (fileInput.files && fileInput.files[0]);
            if (!f) {
                setMsg('请先选择并识别 3MF 文件', true);
                return;
            }
            var title = titleInput ? String(titleInput.value || '').trim() : '';
            var summary = summaryInput ? String(summaryInput.value || '').trim() : '';
            if (!title) {
                setMsg('配置标题不能为空', true);
                return;
            }
            saveBtn.disabled = true;
            parseBtn.disabled = true;
            setMsg('正在保存配置...');
            try {
                var fd2 = new FormData();
                fd2.append('file', f);
                fd2.append('title', title);
                fd2.append('summary', summary);
                var res2 = await fetch(apiUrl('/api/models/' + encodeURIComponent(MODEL_DIR) + '/instances/import-3mf'), {
                    method: 'POST',
                    body: fd2
                });
                if (!res2.ok) {
                    var txt2 = await res2.text();
                    throw new Error(txt2 || ('HTTP ' + res2.status));
                }
                var data2 = await res2.json();
                setMsg((data2 && data2.message) || '已追加打印配置');
                if (parseDraftSessionId) {
                    discardParseDraft(parseDraftSessionId);
                }
                setTimeout(function () {
                    closeModal();
                    location.reload();
                }, 450);
            } catch (e2) {
                setMsg('保存失败：' + (e2.message || e2), true);
                saveBtn.disabled = false;
                parseBtn.disabled = false;
            }
        });
    }

    // ============ 主入口 ============

    async function main() {
        var meta;
        if (window.__OFFLINE_META__) {
            meta = window.__OFFLINE_META__;
            MODEL_DIR = meta.dir || meta.baseName || getModelDir();
        } else {
            MODEL_DIR = getModelDir();
            if (!MODEL_DIR) {
                showError('无法从 URL 解析模型目录');
                return;
            }

            try {
                var res = await fetch(apiUrl('/api/v2/models/' + encodeURIComponent(MODEL_DIR) + '/meta'));
                if (!res.ok) throw new Error('HTTP ' + res.status);
                meta = await res.json();
            } catch (e) {
                showError('请求模型数据失败：' + e.message);
                return;
            }
        }

        try {
            var images = normalizeImages(meta);

            // 渲染各区域
            renderTitle(meta);
            renderAuthor(meta);
            renderSource(meta);
            renderHero(meta, images);
            renderCollectDate(meta);
            renderStats(meta);
            renderTags(meta);
            renderInstances(meta);
            renderCarousel(images);
            renderSummary(meta);

            // 显示主内容，隐藏加载状态
            document.getElementById('loadingState').classList.add('hidden');
            document.getElementById('mainContent').classList.remove('hidden');

            // 初始化交互
            initLightbox();
            initAttachments();
            initPrinted();
            initInstanceImport();
            initBambuOpenGuard();

            // 仅在 file:// 直开且无法调用本地 API 时隐藏上传区块
            if (!canUseBackendApi()) {
                var attachUpload = document.getElementById('attachUploadBtn');
                var printedUpload = document.getElementById('printedUploadBtn');
                if (attachUpload && attachUpload.parentElement) attachUpload.parentElement.style.display = 'none';
                if (printedUpload && printedUpload.parentElement) printedUpload.parentElement.style.display = 'none';
            }
        } catch (e) {
            showError('加载模型数据失败：' + e.message);
        }
    }

    function showError(msg) {
        document.getElementById('loadingState').classList.add('hidden');
        var el = document.getElementById('errorState');
        el.textContent = msg;
        el.classList.remove('hidden');
    }

    // 启动
    /* 分盘弹窗控制逻辑 */
    window.openPlatesModal = function (btn) {
        var platesHtml = btn.getAttribute('data-plates');
        var modal = document.getElementById('platesModal');
        var body = document.getElementById('platesModalBody');
        var preview = document.getElementById('platesModalPreview');
        body.innerHTML = platesHtml;
        modal.classList.add('active');

        // 初始化侧边栏交互逻辑
        var rows = body.querySelectorAll('.plate-row');
        function selectRow(row) {
            rows.forEach(r => r.classList.remove('active'));
            row.classList.add('active');
            var img = row.querySelector('.plate-row-img img');
            if (img) {
                preview.innerHTML = '<img src="' + img.src + '" alt="preview">';
            } else {
                preview.innerHTML = '<div style="color:#666;">暂无预览</div>';
            }
        }

        rows.forEach(function (row) {
            row.addEventListener('click', function () {
                selectRow(this);
            });
        });

        // 默认选中第一项
        if (rows.length > 0) {
            selectRow(rows[0]);
        } else {
            preview.innerHTML = '';
        }
    };

    document.getElementById('platesModalClose').addEventListener('click', function () {
        document.getElementById('platesModal').classList.remove('active');
    });

    document.getElementById('platesModal').addEventListener('click', function (e) {
        if (e.target === this) {
            this.classList.remove('active');
        }
    });

    // 页面主入口
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', main);
    } else {
        main();
    }
})();
