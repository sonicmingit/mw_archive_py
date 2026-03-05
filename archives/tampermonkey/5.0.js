// ==UserScript==
// @name         MakerWorld 模型归档助手（本地资料库版）v5.0
// @namespace    http://tampermonkey.net/
// @version      5.0
// @description  采集 MakerWorld 模型：截图、描述、图片、打印配置（实例）详情、3MF 直链，生成 meta.json 供本地 Python 脚本整理。
// @author       sonic
// @match        https://makerworld.com.cn/zh/models/*
// @match        https://makerworld.com/zh/models/*
// @icon         https://makerworld.com.cn/favicon.ico
// @require      https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js
// @grant        GM_download
// @grant        GM_xmlhttpRequest
// @grant        GM_notification
// @grant        GM_registerMenuCommand
// @connect      makerworld.com.cn
// @connect      makerworld.bblmw.cn
// @connect      public-cdn.bblmw.cn
// @connect      *
// ==/UserScript==

(function () {
    'use strict';

    const BTN_ID = 'mw-archive-btn';

    /******************* 基础工具 *******************/
    function log(...args) {
        console.log('[MW-ARCHIVER]', ...args);
    }

    function notify(msg) {
        try {
            GM_notification({
                title: '归档助手',
                text: msg,
                timeout: 4000,
            });
        } catch (e) {
            alert('[归档助手]\n' + msg);
        }
    }

    function sanitizeFilename(name) {
        const cleaned = (name || '').replace(/[\\/:*?"<>|]/g, '_').trim();
        return cleaned || 'file';
    }

    function delay(ms) {
        return new Promise((res) => setTimeout(res, ms));
    }

    function pad2(n) {
        return n < 10 ? '0' + n : '' + n;
    }

    function htmlToText(html) {
        const div = document.createElement('div');
        div.innerHTML = html || '';
        const text = div.textContent || div.innerText || '';
        return text.replace(/\s+/g, ' ').trim();
    }

    function pickExtFromUrl(url, fallback = 'jpg') {
        if (!url) return fallback;
        const clean = url.split('#')[0].split('?')[0];
        const m = clean.match(/\.([a-zA-Z0-9]+)$/);
        return m ? m[1] : fallback;
    }

    /******************* 固定右上角按钮 *******************/
    function createArchiveButton() {
        let btn = document.getElementById(BTN_ID);
        if (btn) return btn;

        btn = document.createElement('button');
        btn.id = BTN_ID;
        btn.innerText = '🚀 归档模型';

        Object.assign(btn.style, {
            position: 'fixed',
            top: '120px',
            right: '40px',
            zIndex: 99999999,
            padding: '10px 18px',
            borderRadius: '8px',
            background: '#ff5722',
            color: '#fff',
            fontSize: '14px',
            border: 'none',
            cursor: 'pointer',
            fontWeight: 'bold',
            boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
        });

        btn.addEventListener('mouseenter', () => {
            btn.style.transform = 'translateY(-1px)';
            btn.style.boxShadow = '0 6px 16px rgba(0,0,0,0.35)';
        });
        btn.addEventListener('mouseleave', () => {
            btn.style.transform = 'translateY(0)';
            btn.style.boxShadow = '0 4px 12px rgba(0,0,0,0.3)';
        });

        btn.addEventListener('click', archiveModel);

        document.body.appendChild(btn);
        return btn;
    }

    function ensureButton() {
        if (!document.getElementById(BTN_ID)) {
            createArchiveButton();
        }
    }

    // React 若卸载按钮，定时重建
    setInterval(ensureButton, 1500);

    /******************* 解析页面数据 *******************/
    function getDesignFromNextData() {
        try {
            const el = document.getElementById('__NEXT_DATA__');
            if (!el) {
                log('未找到 __NEXT_DATA__');
                return null;
            }
            const data = JSON.parse(el.textContent || el.innerText || '{}');
            const design = data?.props?.pageProps?.design;
            if (!design) {
                log('pageProps.design 不存在');
                return null;
            }
            return design;
        } catch (e) {
            log('解析 __NEXT_DATA__ 出错:', e);
            return null;
        }
    }

    function getDesignIdFromUrl() {
        try {
            const m1 = location.pathname.match(/\/models\/(\d+)-/);
            if (m1) return m1[1];
            const m2 = location.href.match(/[?&]id=(\d+)/);
            if (m2) return m2[1];
        } catch (e) {
            log('URL 中解析 ID 失败:', e);
        }
        return null;
    }

    function extractAuthor(design) {
        let name = design.designCreator?.name || design.creatorName || '';
        let username = '';
        let url = '';
        let avatarUrl = '';

        const candidate = design.user || design.author || design.designCreator || design.creator || {};
        if (candidate) {
            name = candidate.nickname || candidate.name || candidate.username || name;
            username = candidate.username || '';
            url = candidate.homepage || candidate.url || '';
            avatarUrl = candidate.avatarUrl || candidate.avatar || candidate.headImg || '';
        }

        if (!url && username) {
            url = `https://makerworld.com.cn/zh/@${username}`;
        }

        // DOM 兜底
        if (!name || !url || !avatarUrl) {
            const authorLinkDom = document.querySelector('a[href*="/zh/@"]');
            if (authorLinkDom) {
                if (!url) {
                    const href = authorLinkDom.getAttribute('href');
                    url = new URL(href, location.origin).href;
                }
                if (!name) {
                    name = (authorLinkDom.textContent || '').trim();
                }
                const img = authorLinkDom.querySelector('img');
                if (img && img.src && !avatarUrl) {
                    avatarUrl = img.src;
                }
            }
        }

        const avatarLocal = avatarUrl ? `author_avatar.${pickExtFromUrl(avatarUrl)}` : '';

        return {
            name,
            url,
            avatarUrl,
            avatarLocal,
        };
    }

    function extractDesignInfo() {
        const design = getDesignFromNextData();
        if (!design) return null;

        const id = design.id || getDesignIdFromUrl();
        const title = design.title || 'unknown_title';
        const tagsOriginal = Array.isArray(design.tagsOriginal) ? design.tagsOriginal : [];
        const tags = Array.isArray(design.tags) && design.tags.length ? design.tags : tagsOriginal;

        const slug = design.slug || '';
        const coverUrl =
            design.coverUrl ||
            design.coverImage ||
            design.cover ||
            design.thumbnail ||
            design.thumbnailUrl ||
            '';

        const counts = {
            likes: design.likeCount || 0,
            favorites: design.collectionCount || design.favoriteCount || design.favCount || 0,
            downloads: design.downloadCount || 0,
            prints: design.printCount || 0,
            views: design.readCount || 0,
        };

        const url = location.href;

        return {
            id,
            title,
            titleTranslated: design.titleTranslated || '',
            author: extractAuthor(design),
            tags,
            tagsOriginal,
            counts,
            instances: Array.isArray(design.instances) ? design.instances : [],
            slug,
            coverUrl,
            url,
            raw: design,
        };
    }

    /******************* 封面截图（只截 .mw-css-1b8wkj） *******************/
    async function captureScreenshot(baseName) {
        try {
            if (typeof html2canvas === 'undefined') {
                log('html2canvas 未加载，跳过截图');
                return;
            }

            const target = document.querySelector('.mw-css-1b8wkj');
            if (!target) {
                log('未找到封面截图区域 .mw-css-1b8wkj，跳过截图');
                return;
            }

            const canvas = await html2canvas(target, {
                backgroundColor: '#ffffff',
                useCORS: true,
                scale: 2,
            });

            const dataUrl = canvas.toDataURL('image/png');
            const filename = `${baseName}_screenshot.png`;

            GM_download({
                url: dataUrl,
                name: filename,
                saveAs: false,
            });

            log('截图已保存:', filename);
        } catch (err) {
            log('截图失败:', err);
        }
    }

    /******************* 描述区：只保留 data-id="1" 内部内容 *******************/
    function extractSummarySection(baseName) {
        const section = document.querySelector('.tab-anchor.mw-css-x172yv[data-id="1"]');
        if (!section) {
            log('找不到描述内容 .tab-anchor.mw-css-x172yv[data-id="1"]');
            return {
                raw: '',
                html: '',
                text: '',
                summaryImages: [],
            };
        }

        // 只要内部内容
        const rawInner = section.innerHTML || '';
        const wrapper = document.createElement('div');
        wrapper.innerHTML = rawInner;

        const summaryImages = [];
        let index = 1;

        const imgNodes = wrapper.querySelectorAll('img');
        imgNodes.forEach((img) => {
            const src = img.getAttribute('src') || img.getAttribute('data-src') || img.src;
            if (!src) return;

            const ext = pickExtFromUrl(src);
            const idxStr = pad2(index);

            const fileName = `summary_img_${idxStr}.${ext}`;
            const relPath = `images/${fileName}`;
            const downloadName = `${baseName}_${fileName}`;

            // HTML 中替换为本地路径，避免当场加载
            img.removeAttribute('src');
            img.setAttribute('data-local-src', './images/' + fileName);

            summaryImages.push({
                index,
                originalUrl: src,
                relPath,
                fileName,
                downloadName,
            });

            index++;
        });

        // 去掉翻译块
        wrapper.querySelectorAll('.translated-text').forEach((n) => n.remove());

        // 将 data-local-src 恢复为 src 字符串输出，避免运行时加载
        const htmlLocal = wrapper.innerHTML.replace(/data-local-src=/g, 'src=');
        const textPlain = htmlToText(rawInner);

        log(`描述区解析：图片 ${summaryImages.length} 张`);

        return {
            raw: rawInner, // 原始 HTML（远程地址）
            html: htmlLocal, // 本地路径版本（./images/summary_img_xx）
            text: textPlain, // 纯文本
            summaryImages,
        };
    }

    /******************* 下载描述区图片 *******************/
    async function downloadSummaryImages(summary) {
        if (!summary || !Array.isArray(summary.summaryImages)) return;
        for (const img of summary.summaryImages) {
            try {
                GM_download({
                    url: img.originalUrl,
                    name: img.downloadName,
                    saveAs: false,
                    onerror: (e) => log('summary 图片下载失败:', img.originalUrl, e),
                });
            } catch (e) {
                log('summary 图片下载异常:', img.originalUrl, e);
            }
            await delay(400);
        }
    }

    /******************* 下载封面 + 设计图（cover 直接使用 design_01） *******************/
    async function downloadCoverAndDesignImages(baseName) {
        const coverAreaImgs = Array.from(document.querySelectorAll('.mw-css-1b8wkj img'));
        const extraImgs = Array.from(
            document.querySelectorAll('.mw-css-1mlkcqi img, .mw-css-h9vdjw img')
        );

        const allRaw = coverAreaImgs.concat(extraImgs);
        // 优先只用 /design/ 路径的图片，若没有则回退全量
        const designOnly = allRaw.filter((img) => {
            const src = img.getAttribute('src') || img.src || '';
            return src.includes('/design/');
        });
        const all = designOnly.length ? designOnly : allRaw;

        if (!all.length) {
            log('未发现设计图 / 封面图图片节点');
            return { cover: null, designImages: [] };
        }

        // 按文件名去重，并优先 query 中包含 w_1000 的版本
        const seenUrl = new Set();
        const bestByName = new Map(); // name -> { src, isW1000, order }
        let order = 0;

        for (const img of all) {
            const src = img.getAttribute('src') || img.src;
            if (!src || seenUrl.has(src)) continue;
            seenUrl.add(src);

            const parts = src.split('#')[0].split('?');
            const base = parts[0];
            const query = parts[1] || '';
            const nameKey = base.split('/').pop() || base;
            const isW1000 = /w[_%2C]*1000/i.test(query);

            const prev = bestByName.get(nameKey);
            if (!prev) {
                bestByName.set(nameKey, { src, isW1000, order: order++ });
            } else if (!prev.isW1000 && isW1000) {
                prev.src = src;
                prev.isW1000 = true;
            }
        }

        const selected = Array.from(bestByName.values()).sort((a, b) => a.order - b.order);
        if (!selected.length) {
            log('未能选出设计图');
            return { cover: null, designImages: [] };
        }

        const designImages = [];
        let designIndex = 1;
        let coverMeta = null;

        log('设计图候选去重后数量:', selected.length);

        for (const item of selected) {
            const src = item.src;
            const ext = pickExtFromUrl(src);
            const idxStr = pad2(designIndex);
            const fileName = `design_${idxStr}.${ext}`;
            const downloadName = `${baseName}_${fileName}`;
            const relPath = `images/${fileName}`;

            try {
                GM_download({
                    url: src,
                    name: downloadName,
                    saveAs: false,
                    onerror: (e) => log('设计图下载失败:', src, e),
                });
            } catch (e) {
                log('设计图下载异常:', src, e);
            }

            const meta = {
                index: designIndex,
                originalUrl: src,
                relPath,
                fileName,
                downloadName,
            };
            designImages.push(meta);

            if (!coverMeta) {
                coverMeta = {
                    originalUrl: src,
                    relPath,
                    fileName,
                    downloadName,
                };
            }

            designIndex++;
            await delay(300);
        }

        log(
            '封面图使用 design_01:',
            coverMeta ? coverMeta.relPath : '无',
            '设计图数量:',
            designImages.length
        );

        return {
            cover: coverMeta,
            designImages,
        };
    }

    /******************* 下载作者头像（如有） *******************/
    async function downloadAuthorAvatar(baseName, author) {
        if (!author || !author.avatarUrl || !author.avatarLocal) {
            return null;
        }
        const downloadName = `${baseName}_${author.avatarLocal}`;
        try {
            GM_download({
                url: author.avatarUrl,
                name: downloadName,
                saveAs: false,
                onerror: (e) => log('作者头像下载失败:', author.avatarUrl, e),
            });
        } catch (e) {
            log('作者头像下载异常:', author.avatarUrl, e);
        }
        await delay(200);
        return {
            relPath: `images/${author.avatarLocal}`,
            downloadName,
        };
    }

    /******************* 实例补充下载：plates 缩略图 / 配图 *******************/
    async function downloadInstancePictures(baseName, instanceId, modelInfo) {
        const plateThumbs = [];
        const extraPictures = [];

        const plates = Array.isArray(modelInfo?.plates) ? modelInfo.plates : [];
        for (const plate of plates) {
            const thumb = plate?.thumbnail?.url;
            if (!thumb) continue;
            const ext = pickExtFromUrl(thumb);
            const fileName = `${baseName}_inst${instanceId}_plate_${pad2(plate.index || 1)}.${ext}`;
            try {
                GM_download({
                    url: thumb,
                    name: fileName,
                    saveAs: false,
                    onerror: (e) => log('plate 缩略图下载失败:', thumb, e),
                });
            } catch (e) {
                log('plate 缩略图下载异常:', thumb, e);
            }
            plateThumbs.push({
                index: plate.index || 0,
                url: thumb,
                relPath: `images/${fileName}`,
                fileName,
            });
            await delay(200);
        }

        const auxPics = Array.isArray(modelInfo?.auxiliaryPictures) ? modelInfo.auxiliaryPictures : [];
        let picIndex = 1;
        for (const pic of auxPics) {
            if (!pic?.url) continue;
            const ext = pickExtFromUrl(pic.url);
            const fileName = `${baseName}_inst${instanceId}_pic_${pad2(picIndex)}.${ext}`;
            try {
                GM_download({
                    url: pic.url,
                    name: fileName,
                    saveAs: false,
                    onerror: (e) => log('实例配图下载失败:', pic.url, e),
                });
            } catch (e) {
                log('实例配图下载异常:', pic.url, e);
            }
            extraPictures.push({
                index: picIndex,
                url: pic.url,
                relPath: `images/${fileName}`,
                fileName,
                isRealLifePhoto: pic.isRealLifePhoto || 0,
            });
            picIndex++;
            await delay(180);
        }

        return { plateThumbs, extraPictures };
    }

    /******************* 3MF 实例：只保存真实 URL，不下载 + 补充配置数据 *******************/
    async function fetchInstanceDirectUrl(instanceId) {
        const apiUrl = `${location.origin}/api/v1/design-service/instance/${instanceId}/f3mf?type=download&fileType=`;
        try {
            const res = await fetch(apiUrl, {
                method: 'GET',
                credentials: 'include',
            });

            const text = await res.text();
            let obj = null;
            try {
                obj = JSON.parse(text);
            } catch (e) {
                log('[INST] 3MF 接口返回非 JSON，前 200 字符:', text.slice(0, 200));
                return null;
            }

            if (obj && obj.url) {
                log('[INST] 3MF 直链获取成功 id=', instanceId);
                return {
                    name: obj.name || '',
                    url: obj.url,
                };
            }

            const textLower = text.toLowerCase();
            if (textLower.includes('robot') || textLower.includes('captcha')) {
                log('[INST] 触发机器人校验，响应:', text.slice(0, 200));
                notify(
                    '3MF 下载接口触发机器人校验：\n已跳过 3MF 直链获取，请在浏览器中手动下载一次后再试。'
                );
                return {
                    name: '',
                    url: '',
                };
            }

            log('[INST] 未获取到 3MF url，响应前 200 字符:', text.slice(0, 200));
            return null;
        } catch (e) {
            log('[INST] 获取 3MF 直链异常:', e);
            return null;
        }
    }

    async function buildInstancesInfo(designInfo, baseName) {
        const rawInstances = Array.isArray(designInfo.instances) ? designInfo.instances : [];
        if (!rawInstances.length) {
            log('design.instances 为空，跳过 3MF 信息解析');
            return [];
        }

        const result = [];
        log('开始解析实例列表，总数:', rawInstances.length);

        for (const inst of rawInstances) {
            const ext = inst.extention || {};
            const modelInfo = ext.modelInfo || {};
            const plates = Array.isArray(modelInfo.plates) ? modelInfo.plates : [];
            const instanceFilaments = Array.isArray(inst.instanceFilaments) ? inst.instanceFilaments : [];

            const base = {
                id: inst.id,
                profileId: inst.profileId,
                title: inst.title,
                titleTranslated: inst.titleTranslated || '',
                publishTime: inst.publishTime || '',
                downloadCount: inst.downloadCount || 0,
                printCount: inst.printCount || 0,
                prediction: inst.prediction || modelInfo.prediction || null,
                weight: inst.weight || modelInfo.weight || null,
                materialCnt: inst.materialCnt || 0,
                materialColorCnt: inst.materialColorCnt || 0,
                needAms: !!inst.needAms,
                plates: [],
                pictures: [],
                instanceFilaments,
                summary: inst.summary || '',
                summaryTranslated: inst.summaryTranslated || '',
                name: '',
                apiUrl: `${location.origin}/api/v1/design-service/instance/${inst.id}/f3mf?type=download&fileType=`,
                downloadUrl: '',
            };

            // 下载 plate 缩略图 / 配图
            const pics = await downloadInstancePictures(baseName, inst.id, modelInfo);

            base.pictures = pics.extraPictures;

            if (plates.length) {
                plates.forEach((p, idx) => {
                    const thumb = pics.plateThumbs.find((t) => t.index === p.index);
                    base.plates.push({
                        index: p.index || idx + 1,
                        prediction: p.prediction || null,
                        weight: p.weight || null,
                        filaments: Array.isArray(p.filaments) ? p.filaments : [],
                        thumbnailUrl: p.thumbnail?.url || thumb?.url || '',
                        thumbnailRelPath: thumb?.relPath || '',
                        thumbnailFile: thumb?.fileName || '',
                    });
                });
            }

            const direct = await fetchInstanceDirectUrl(inst.id);
            if (direct && direct.url) {
                base.name = direct.name || '';
                base.downloadUrl = direct.url;
            }

            result.push(base);
            await delay(800); // 稍微慢一点，避免触发风控
        }

        log('实例信息解析完成，数量:', result.length);
        return result;
    }

    /******************* 保存 meta.json *******************/
    function saveMetaJson(baseName, designInfo, summary, imagesMeta, instancesInfo) {
        const stats = {
            likes: designInfo.counts?.likes ?? designInfo.likeCount ?? 0,
            favorites: designInfo.counts?.favorites ?? designInfo.favoriteCount ?? 0,
            downloads: designInfo.counts?.downloads ?? designInfo.downloadCount ?? 0,
            prints: designInfo.counts?.prints ?? designInfo.prints ?? 0,
            views: designInfo.counts?.views ?? designInfo.views ?? 0,
        };

        const imagesDesignList = Array.isArray(imagesMeta.designImages)
            ? imagesMeta.designImages.map((d) => d.fileName)
            : [];

        const summaryImageList = Array.isArray(summary.summaryImages)
            ? summary.summaryImages.map((i) => i.fileName)
            : [];

        const coverLocalName = imagesMeta.cover ? imagesMeta.cover.fileName : '';
        const authorAvatarLocal = designInfo.author?.avatarLocal || '';
        const authorRelPath = authorAvatarLocal ? `images/${authorAvatarLocal}` : '';

        const meta = {
            baseName,
            url: designInfo.url || location.href,
            id: designInfo.id,
            slug: designInfo.slug || '',
            title: designInfo.title,
            titleTranslated: designInfo.titleTranslated || '',
            coverUrl: designInfo.coverUrl || imagesMeta.cover?.originalUrl || '',
            tags: designInfo.tags || [],
            tagsOriginal: designInfo.tagsOriginal || [],
            stats,
            cover: {
                url: imagesMeta.cover?.originalUrl || designInfo.coverUrl || '',
                localName: coverLocalName,
                relPath: imagesMeta.cover ? imagesMeta.cover.relPath : '',
            },
            author: {
                name: designInfo.author?.name || designInfo.author || '',
                url: designInfo.author?.url || '',
                avatarUrl: designInfo.author?.avatarUrl || '',
                avatarLocal: authorAvatarLocal,
                avatarRelPath: authorRelPath,
            },
            images: {
                cover: coverLocalName,
                design: imagesDesignList,
                summary: summaryImageList,
            },
            designImages: Array.isArray(imagesMeta.designImages)
                ? imagesMeta.designImages.map((d) => ({
                    index: d.index,
                    originalUrl: d.originalUrl,
                    relPath: d.relPath,
                    fileName: d.fileName,
                }))
                : [],
            summaryImages: Array.isArray(summary.summaryImages)
                ? summary.summaryImages.map((i) => ({
                    index: i.index,
                    originalUrl: i.originalUrl,
                    relPath: i.relPath,
                    fileName: i.fileName,
                }))
                : [],
            summary: {
                raw: summary.raw || '',
                html: summary.html || '',
                text: summary.text || '',
            },
            instances: instancesInfo.map((inst) => ({
                id: inst.id,
                profileId: inst.profileId,
                title: inst.title,
                titleTranslated: inst.titleTranslated || '',
                publishTime: inst.publishTime || '',
                downloadCount: inst.downloadCount || 0,
                printCount: inst.printCount || 0,
                prediction: inst.prediction,
                weight: inst.weight,
                materialCnt: inst.materialCnt,
                materialColorCnt: inst.materialColorCnt,
                needAms: inst.needAms,
                plates: inst.plates || [],
                pictures: inst.pictures || [],
                instanceFilaments: inst.instanceFilaments || [],
                summary: inst.summary || '',
                summaryTranslated: inst.summaryTranslated || '',
                name: inst.name || '',
                downloadUrl: inst.downloadUrl || '',
                apiUrl: inst.apiUrl,
            })),
            generatedAt: new Date().toISOString(),
            note: '本文件包含结构化数据与打印配置详情。后续请使用本地 Python 脚本根据 meta.json + 下载文件重新整理目录并生成页面。',
        };

        const jsonStr = JSON.stringify(meta, null, 2);

        GM_download({
            url: 'data:application/json;charset=utf-8,' + encodeURIComponent(jsonStr),
            name: `${baseName}_meta.json`,
            saveAs: false,
        });

        log('[META] meta.json 已保存');
    }

    /******************* 总流程 *******************/
    async function archiveModel() {
        try {
            log('====== MakerWorld 模型归档助手 v5.0 开始 ======');

            const designInfo = extractDesignInfo();
            if (!designInfo || !designInfo.id) {
                notify('未能获取模型信息（ID 或 __NEXT_DATA__ 缺失），请确认当前页面为模型详情页。');
                log('extractDesignInfo 失败:', designInfo);
                return;
            }

            const designId = designInfo.id;
            const baseName = `MW_${designId}_${sanitizeFilename(designInfo.title || designInfo.slug || 'model')}`;

            log('开始归档模型:', designInfo.title, 'ID:', designId, 'Base:', baseName);

            // 1. 截图
            log('步骤1: 截图...');
            await captureScreenshot(baseName);

            // 2. 描述区 summary
            log('步骤2: 解析描述与图片...');
            const summary = extractSummarySection(baseName);

            // 3. 封面 + 设计图
            log('步骤3: 下载封面/设计图...');
            const imagesMeta =
                (await downloadCoverAndDesignImages(baseName)) || { cover: null, designImages: [] };

            // 4. 描述区图片
            log('步骤4: 下载描述图片...');
            await downloadSummaryImages(summary);

            // 5. 作者头像
            log('步骤5: 下载作者头像...');
            await downloadAuthorAvatar(baseName, designInfo.author);

            // 6. 3MF 实例 + 打印配置详情
            log('步骤6: 拉取打印配置/3MF 直链...');
            const instancesInfo = await buildInstancesInfo(designInfo, baseName);

            // 7. 生成 meta.json
            log('步骤7: 保存 meta.json...');
            saveMetaJson(
                baseName,
                designInfo,
                summary,
                {
                    cover: imagesMeta.cover,
                    designImages: imagesMeta.designImages,
                },
                instancesInfo
            );

            const doneMsg =
                `模型已采集：${designInfo.title}\n` +
                `请到浏览器下载目录中查找以「${baseName}_」开头的文件，后续用 Python 脚本整理。`;
            notify(doneMsg);
            alert(doneMsg);

            log('====== MakerWorld 模型归档助手 v5.0 完成 ======');
        } catch (e) {
            log('归档过程发生异常:', e);
            notify('归档过程中发生异常，请打开控制台查看详细日志。');
        }
    }

    /******************* 绑定按钮 & 菜单 *******************/
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', createArchiveButton);
    } else {
        createArchiveButton();
    }

    if (typeof GM_registerMenuCommand === 'function') {
        GM_registerMenuCommand('🚀 归档当前模型', () => {
            archiveModel();
        });
    }
})();
