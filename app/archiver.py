import json
import re
import shutil
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

"""
archiver.py (app2)
提取自 mw_fetch5.0.py，作为可导入模块使用：
- 使用 archive_model(url, cookie, download_dir, logs_dir, logger=None)
- 不包含全局 URL/COOKIE/OUT_DIR 配置
- 保持 mw_fetch5.0 的采集、curl 兜底、3MF 获取、实例/图片处理逻辑
"""

import requests
from bs4 import BeautifulSoup


def log(*args):
    print("[MW-FETCH]", *args)


def log_section(title: str):
    log("")
    log("=" * 10, title, "=" * 10)


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name)


def pick_ext_from_url(url: str, fallback: str = "jpg") -> str:
    clean = url.split("#")[0].split("?")[0]
    m = re.search(r"\.([A-Za-z0-9]+)$", clean)
    return m.group(1) if m else fallback


def parse_cookies(cookie_str: str) -> Dict[str, str]:
    cookie_str = cookie_str.strip()
    # 兼容带前缀 "Cookie:" 的整行
    if cookie_str.lower().startswith("cookie:"):
        cookie_str = cookie_str.split(":", 1)[1].strip()
    cookies = {}
    for part in cookie_str.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


def download_file(session: requests.Session, url: str, dest: Path):
    if dest.exists():
        log("存在，跳过：", dest)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    resp = session.get(url, timeout=30, stream=True)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        shutil.copyfileobj(resp.raw, f)
    log("已下载：", dest)


def pick_instance_filename(inst: dict, name_hint: str = "") -> str:
    base = sanitize_filename(inst.get("title") or inst.get("name") or str(inst.get("id") or "model"))
    if not base:
        base = str(inst.get("id") or "model")
    ext = Path(name_hint).suffix if name_hint else ""
    if not ext:
        ext = ".3mf"
    elif not ext.startswith("."):
        ext = "." + ext
    return f"{base}{ext}"


def fetch_html_with_requests(session: requests.Session, url: str, raw_cookie: str) -> Optional[str]:
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "User-Agent": session.headers.get("User-Agent", "Mozilla/5.0 (MW-Fetcher)"),
    }
    if raw_cookie:
        headers["Cookie"] = raw_cookie
    try:
        resp = session.get(url, timeout=30, headers=headers)
    except Exception as e:
        log("requests 获取页面失败:", e)
        return None
    if resp.status_code >= 400:
        log("requests 获取页面状态异常:", resp.status_code)
        return None
    return resp.text


def fetch_html_with_curl(url: str, raw_cookie: str) -> str:
    """
    备用：使用 curl 拉取页面，尽量复刻浏览器最小头。
    """
    cmd = [
        "curl",
        "-sSL",
        "--compressed",
        "-H",
        "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "-H",
        "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
        "-H",
        "Cache-Control: no-cache",
        "-H",
        "Connection: keep-alive",
        "-H",
        f"Cookie: {raw_cookie}",
        "-H",
        "Pragma: no-cache",
        "-H",
        "Upgrade-Insecure-Requests: 1",
        "-H",
        "Sec-Fetch-Dest: document",
        "-H",
        "Sec-Fetch-Mode: navigate",
        "-H",
        "Sec-Fetch-Site: none",
        "-H",
        "Sec-Fetch-User: ?1",
        "-H",
        "User-Agent: Mozilla/5.0 (MW-Fetcher-curl)",
        url,
    ]
    log("尝试 curl 获取页面:", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=False)
    if result.returncode != 0:
        err_msg = result.stderr.decode(errors="ignore") if result.stderr else ""
        raise RuntimeError(f"curl 失败 code={result.returncode} stderr={err_msg[:300]}")

    stdout = result.stdout or b""
    log("curl 返回长度:", len(stdout))

    # 尝试直接 utf-8 解码
    try:
        return stdout.decode("utf-8")
    except Exception:
        # 若仍是 gzip/其它编码，尝试解压
        try:
            import gzip
            return gzip.decompress(stdout).decode("utf-8", errors="ignore")
        except Exception:
            return stdout.decode("utf-8", errors="ignore")


def _json_loads_maybe(raw: str) -> Optional[object]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def extract_next_data(html_text: str) -> dict:
    patterns = [
        r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        r'__NEXT_DATA__\s*=\s*({.*?})\s*;',
        r'window\.__NEXT_DATA__\s*=\s*({.*?})\s*;',
        r'__NUXT__\s*=\s*({.*?})\s*;',
        r'window\.__NUXT__\s*=\s*({.*?})\s*;',
    ]
    for pattern in patterns:
        m = re.search(pattern, html_text, re.S)
        if not m:
            continue
        raw = (m.group(1) or "").strip()
        raw = raw.rstrip(";")
        data = _json_loads_maybe(raw)
        if data is not None:
            return data
    parse_patterns = [
        r'__NEXT_DATA__\s*=\s*JSON\.parse\((\".*?\")\)\s*;',
        r"__NEXT_DATA__\s*=\s*JSON\.parse\(('.*?')\)\s*;",
        r'__NUXT__\s*=\s*JSON\.parse\((\".*?\")\)\s*;',
        r"__NUXT__\s*=\s*JSON\.parse\(('.*?')\)\s*;",
    ]
    for pattern in parse_patterns:
        m = re.search(pattern, html_text, re.S)
        if not m:
            continue
        raw = (m.group(1) or "").strip()
        parsed = _json_loads_maybe(raw)
        if isinstance(parsed, str):
            data = _json_loads_maybe(parsed)
            if data is not None:
                return data
    raise RuntimeError("未找到 __NEXT_DATA__")


def _get_nested(obj: dict, keys: List[str]):
    cur = obj
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _score_design_candidate(obj: dict) -> int:
    if not isinstance(obj, dict):
        return -1
    score = 0
    if isinstance(obj.get("instances"), list):
        score += 3
    if "designExtension" in obj or "summary" in obj or "summaryHtml" in obj:
        score += 2
    if "tags" in obj or "tagsOriginal" in obj:
        score += 1
    if "coverUrl" in obj or "coverImage" in obj or "thumbnail" in obj or "thumbnailUrl" in obj:
        score += 1
    if "likeCount" in obj or "downloadCount" in obj or "printCount" in obj:
        score += 1
    if "designCreator" in obj or "creatorName" in obj or "author" in obj or "user" in obj:
        score += 1
    if obj.get("id") is not None and obj.get("title"):
        score += 1
    return score


def _find_best_design(obj: object) -> Optional[dict]:
    best = None
    best_score = -1
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if "design" in cur and isinstance(cur.get("design"), dict):
                score = _score_design_candidate(cur["design"])
                if score > best_score:
                    best = cur["design"]
                    best_score = score
            score = _score_design_candidate(cur)
            if score > best_score:
                best = cur
                best_score = score
            for val in cur.values():
                stack.append(val)
        elif isinstance(cur, list):
            stack.extend(cur)
    if best_score >= 2:
        return best
    return None


def extract_design_from_next_data(next_data: dict) -> Optional[dict]:
    if not isinstance(next_data, dict):
        return None
    paths = [
        ["props", "pageProps", "design"],
        ["props", "pageProps", "data", "design"],
        ["props", "pageProps", "pageData", "design"],
        ["props", "pageProps", "payload", "design"],
        ["props", "pageProps", "designDetail"],
        ["props", "pageProps", "model"],
        ["props", "pageProps", "detail"],
    ]
    for path in paths:
        candidate = _get_nested(next_data, path)
        if isinstance(candidate, dict):
            if "design" in candidate and isinstance(candidate.get("design"), dict):
                return candidate["design"]
            return candidate
    page_props = _get_nested(next_data, ["props", "pageProps"]) or next_data.get("pageProps")
    return _find_best_design(page_props or next_data)


def _parse_design_id(url: str) -> Optional[int]:
    if not url:
        return None
    m = re.search(r"/models/(\d+)", url)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _extract_api_host(html_text: str) -> Optional[str]:
    if not html_text:
        return None
    m = re.search(r'API_HOST"\s*:\s*"([^"]+)"', html_text)
    if not m:
        m = re.search(r"API_HOST'\s*:\s*'([^']+)'", html_text)
    if not m:
        return None
    host = (m.group(1) or "").strip()
    if not host:
        return None
    if host.startswith("http://") or host.startswith("https://"):
        return host
    return f"https://{host}"


def _is_cloudflare_challenge(html_text: str) -> bool:
    if not html_text:
        return False
    lowered = html_text.lower()
    markers = [
        "just a moment",
        "cf_chl",
        "challenge-platform",
        "/cdn-cgi/challenge",
        "cloudflare",
        "attention required",
        "checking your browser",
        "enable javascript and cookies to continue",
    ]
    return any(m in lowered for m in markers)


def _unwrap_design_payload(payload: object) -> Optional[dict]:
    if not isinstance(payload, dict):
        return _find_best_design(payload)
    direct = _find_best_design(payload)
    if direct:
        return direct
    for key in ["data", "design", "result", "detail", "model", "info"]:
        candidate = payload.get(key)
        if isinstance(candidate, dict):
            if "design" in candidate and isinstance(candidate.get("design"), dict):
                return candidate["design"]
            picked = _find_best_design(candidate)
            if picked:
                return picked
    return None


def fetch_design_from_api(
    session: requests.Session,
    raw_cookie: str,
    url: str,
    api_host_hint: Optional[str] = None,
) -> Optional[dict]:
    design_id = _parse_design_id(url)
    if not design_id:
        return None
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else "https://makerworld.com.cn"
    base_candidates = []
    if api_host_hint:
        base_candidates.append(api_host_hint)
    base_candidates.append(origin)
    base_candidates.append("https://api.bambulab.cn")
    base_candidates.append("https://api.bambulab.com")
    bases = []
    for base in base_candidates:
        if not base:
            continue
        if base not in bases:
            bases.append(base)

    path_templates = [
        "/api/v1/design-service/design/{id}",
        "/api/v1/design-service/design/{id}/detail",
        "/api/v1/design-service/design/{id}/detail?source=web",
        "/api/v1/design-service/design/{id}?lang=zh",
        "/v1/design-service/design/{id}",
        "/v1/design-service/design/{id}/detail",
    ]
    prefixes = ["", "/makerworld"]
    endpoints = []
    for base in bases:
        for prefix in prefixes:
            for path in path_templates:
                endpoints.append(f"{base.rstrip('/')}{prefix}{path.format(id=design_id)}")
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": url,
        "User-Agent": session.headers.get("User-Agent", "Mozilla/5.0 (MW-Fetcher)"),
    }
    if raw_cookie:
        headers["Cookie"] = raw_cookie
    for api_url in endpoints:
        try:
            resp = session.get(api_url, timeout=30, headers=headers)
        except Exception:
            continue
        if resp.status_code >= 400:
            continue
        try:
            payload = resp.json()
        except Exception:
            continue
        design = _unwrap_design_payload(payload)
        if design:
            return design
    return None


def parse_summary(design: dict, base_name: str, session: requests.Session, out_dir: Path):
    raw_html = (
        design.get("summary")
        or design.get("summaryHtml")
        or design.get("summary_html")
        or design.get("summaryContent")
        or design.get("description")
        or design.get("desc")
        or ""
    )
    if isinstance(raw_html, dict):
        raw_html = raw_html.get("html") or raw_html.get("raw") or raw_html.get("text") or ""
    soup = BeautifulSoup(raw_html, "html.parser")
    summary_images = []
    idx = 1
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if not src:
            continue
        ext = pick_ext_from_url(src)
        name = f"summary_img_{idx:02d}.{ext}"
        img["src"] = f"./images/{name}"
        summary_images.append(
            {
                "index": idx,
                "originalUrl": src,
                "relPath": f"images/{name}",
                "fileName": name,
            }
        )
        # 下载
        download_file(session, src, out_dir / name)
        idx += 1

    html_local = str(soup)
    text_plain = " ".join(soup.get_text().split())

    return {
        "raw": raw_html,
        "html": html_local,
        "text": text_plain,
        "summaryImages": summary_images,
    }


def extract_author(design: dict, html_text: str = None):
    creator = design.get("designCreator") or {}
    name = creator.get("name") or design.get("creatorName") or ""
    username = creator.get("username") or creator.get("handle") or design.get("creatorUsername") or ""
    url = ""
    avatar_url = ""
    cand = design.get("user") or design.get("author") or design.get("designCreator") or design.get("creator") or {}
    if isinstance(cand, dict):
        name = cand.get("nickname") or cand.get("name") or cand.get("username") or name
        username = cand.get("username") or cand.get("userName") or cand.get("slug") or cand.get("handle") or username
        url = cand.get("homepage") or cand.get("url") or ""
        avatar_url = cand.get("avatarUrl") or cand.get("avatar") or cand.get("headImg") or ""
    elif isinstance(cand, str) and not name:
        name = cand
    # 兜底从 design 层获取用户名
    if not username:
        username = design.get("creatorName") or design.get("creatorUsername") or username

    # HTML 兜底，从页面 a[href*="/zh/@"] 获取
    if (not url or not avatar_url or not name) and html_text:
        try:
            soup = BeautifulSoup(html_text, "html.parser")
            link = soup.find("a", href=re.compile(r"/zh/@"))
            if link:
                href = link.get("href") or ""
                if href and not url:
                    url = urljoin("https://makerworld.com.cn", href)
                if not name:
                    name = (link.get_text() or "").strip()
                if not avatar_url:
                    img = link.find("img")
                    if img and img.get("src"):
                        avatar_url = img.get("src")
        except Exception as e:
            log("解析作者 DOM 失败:", e)

    # 仍无 url 时，用用户名兜底
    if not url and username:
        url = f"https://makerworld.com.cn/zh/@{username}"
    avatar_local = f"author_avatar.{pick_ext_from_url(avatar_url)}" if avatar_url else ""
    return {
        "name": name,
        "url": url,
        "avatarUrl": avatar_url,
        "avatarLocal": avatar_local,
    }


def _normalize_design_pictures(design: dict) -> List[dict]:
    pics = design.get("designExtension", {}).get("design_pictures")
    if isinstance(pics, list) and pics:
        return pics
    for key in ["designPictures", "design_pictures", "designImages", "images", "pictures"]:
        cand = design.get(key)
        if isinstance(cand, list) and cand:
            return cand
    cover_url = design.get("coverUrl") or design.get("coverImage") or design.get("thumbnail") or design.get("thumbnailUrl")
    if cover_url:
        return [{"url": cover_url}]
    return []


def collect_design_images(design: dict, session: requests.Session, out_dir: Path, base_name: str):
    pics = _normalize_design_pictures(design)
    if not pics:
        return [], None
    design_images = []
    cover_meta = None
    for idx, p in enumerate(pics, start=1):
        url = ""
        if isinstance(p, str):
            url = p
        elif isinstance(p, dict):
            url = p.get("url") or p.get("imageUrl") or p.get("src") or p.get("originalUrl") or ""
        if not url:
            continue
        ext = pick_ext_from_url(url)
        fname = f"design_{idx:02d}.{ext}"
        rel = f"images/{fname}"
        download_file(session, url, out_dir / fname)
        meta = {
            "index": idx,
            "originalUrl": url,
            "relPath": rel,
            "fileName": fname,
        }
        design_images.append(meta)
        if cover_meta is None:
            cover_meta = meta
    return design_images, cover_meta


def fetch_instance_3mf(session: requests.Session, inst_id: int, raw_cookie: str, api_url: str = None):
    """
    获取实例的 3MF 下载地址，允许外部传入 api_url（若为空则使用默认实例接口）。
    """
    api_url = api_url or f"https://makerworld.com.cn/api/v1/design-service/instance/{inst_id}/f3mf?type=download&fileType="
    try:
        r = session.get(
            api_url,
            timeout=30,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://makerworld.com.cn/",
                "Cookie": raw_cookie,
                "Accept-Encoding": "identity",
                "User-Agent": session.headers.get("User-Agent", "Mozilla/5.0 (MW-Fetcher)"),
            },
        )
        log("[3MF] GET", api_url, "status", r.status_code)
        text_preview = r.text[:200] if r.text else ""
        log("[3MF] 响应前 200 字符:", text_preview)
        r.raise_for_status()
        data = r.json()
        return data.get("name") or "", data.get("url") or ""
    except Exception as e:
        log("3MF 获取失败(尝试 curl)", inst_id, e)
        # 再用 curl 试一次，带同样的 Cookie
        cmd = [
            "curl",
            "-sSL",
            "-H",
            "Accept: application/json, text/plain, */*",
            "-H",
            "Accept-Encoding: identity",
            "-H",
            f"Cookie: {raw_cookie}",
            "-H",
            "Referer: https://makerworld.com.cn/",
            "-H",
            f"User-Agent: {session.headers.get('User-Agent', 'Mozilla/5.0 (MW-Fetcher-curl)')}",
            api_url,
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=False)
            if res.returncode != 0:
                err_msg = res.stderr.decode(errors="ignore") if res.stderr else ""
                log("3MF curl 失败 code=", res.returncode, "stderr:", err_msg[:200])
                return "", ""
            body = res.stdout or b""
            preview = body[:200]
            log("3MF curl 返回长度:", len(body), "前 200 字符:", preview)
            try:
                data = json.loads(body.decode("utf-8", errors="ignore"))
                return data.get("name") or "", data.get("url") or ""
            except Exception as je:
                log("3MF curl JSON 解析失败:", je)
                return "", ""
        except Exception as ce:
            log("3MF curl 调用异常:", ce)
            return "", ""


def collect_instance_media(inst: dict, session: requests.Session, out_dir: Path, base_name: str):
    model_info = (
        inst.get("extention", {}).get("modelInfo")
        or inst.get("extension", {}).get("modelInfo")
        or inst.get("modelInfo")
        or {}
    )
    plates = model_info.get("plates") or model_info.get("plateList") or []
    aux_pics = model_info.get("auxiliaryPictures") or model_info.get("pictures") or inst.get("pictures") or inst.get("auxiliaryPictures") or []
    plate_out = []
    pics_out = []
    # plates thumbs
    for p in plates:
        thumb = p.get("thumbnail", {}).get("url") or p.get("thumbnailUrl") or p.get("url")
        if not thumb:
            continue
        ext = pick_ext_from_url(thumb)
        fname = f"{base_name}_inst{inst.get('id')}_plate_{int(p.get('index',0)):02d}.{ext}"
        download_file(session, thumb, out_dir / fname)
        plate_out.append({
            "index": p.get("index", 0),
            "prediction": p.get("prediction"),
            "weight": p.get("weight"),
            "filaments": p.get("filaments") or [],
            "thumbnailUrl": thumb,
            "thumbnailRelPath": f"images/{fname}",
            "thumbnailFile": fname,
        })
    # auxiliary pictures
    pic_idx = 1
    for pic in aux_pics:
        url = ""
        is_real = 0
        if isinstance(pic, str):
            url = pic
        elif isinstance(pic, dict):
            url = pic.get("url") or pic.get("imageUrl") or pic.get("src") or ""
            is_real = pic.get("isRealLifePhoto", 0)
        if not url:
            continue
        ext = pick_ext_from_url(url)
        fname = f"{base_name}_inst{inst.get('id')}_pic_{pic_idx:02d}.{ext}"
        download_file(session, url, out_dir / fname)
        pics_out.append({
            "index": pic_idx,
            "url": url,
            "relPath": f"images/{fname}",
            "fileName": fname,
            "isRealLifePhoto": is_real,
        })
        pic_idx += 1
    if not pics_out:
        cover = inst.get("cover") or inst.get("coverUrl")
        if cover:
            ext = pick_ext_from_url(cover)
            fname = f"{base_name}_inst{inst.get('id')}_pic_{pic_idx:02d}.{ext}"
            download_file(session, cover, out_dir / fname)
            pics_out.append({
                "index": pic_idx,
                "url": cover,
                "relPath": f"images/{fname}",
                "fileName": fname,
                "isRealLifePhoto": 0,
            })
    return plate_out, pics_out


def extract_instances(design: dict) -> List[dict]:
    for key in ["instances", "instanceList", "modelInstances", "profiles", "printProfiles", "printingProfiles"]:
        cand = design.get(key)
        if isinstance(cand, list) and cand:
            return cand
    return []


def build_meta(design: dict, summary: dict, design_images: List[dict], cover_meta: Optional[dict], instances: List[dict], author: dict, base_name: str):
    counts = design.get("counts") or {}
    stats = {
        "likes": design.get("likeCount") or counts.get("likes") or 0,
        "favorites": design.get("collectionCount") or design.get("favoriteCount") or design.get("favCount") or counts.get("favorites") or 0,
        "downloads": design.get("downloadCount") or counts.get("downloads") or 0,
        "prints": design.get("printCount") or counts.get("prints") or 0,
        "views": design.get("readCount") or counts.get("views") or 0,
    }
    images_design_list = [d["fileName"] for d in design_images]
    summary_image_list = [i["fileName"] for i in summary.get("summaryImages", [])]
    cover_local = cover_meta["fileName"] if cover_meta else ""
    cover_url = (
        design.get("coverUrl")
        or design.get("coverImage")
        or design.get("thumbnail")
        or design.get("thumbnailUrl")
        or (cover_meta.get("originalUrl") if cover_meta else "")
    )
    author_avatar_local = author.get("avatarLocal") or ""
    author_rel = f"images/{author_avatar_local}" if author_avatar_local else ""

    return {
        "baseName": base_name,
        "url": design.get("url") or "",
        "id": design.get("id"),
        "slug": design.get("slug") or "",
        "title": design.get("title") or "",
        "titleTranslated": design.get("titleTranslated") or "",
        "coverUrl": cover_url,
        "tags": design.get("tags") or [],
        "tagsOriginal": design.get("tagsOriginal") or [],
        "stats": stats,
        "cover": {
            "url": cover_url if cover_meta is None else cover_meta["originalUrl"],
            "localName": cover_local,
            "relPath": cover_meta["relPath"] if cover_meta else "",
        },
        "author": {
            "name": author.get("name") or "",
            "url": author.get("url") or "",
            "avatarUrl": author.get("avatarUrl") or "",
            "avatarLocal": author_avatar_local,
            "avatarRelPath": author_rel,
        },
        "images": {
            "cover": cover_local,
            "design": images_design_list,
            "summary": summary_image_list,
        },
        "designImages": design_images,
        "summaryImages": summary.get("summaryImages", []),
        "summary": {
            "raw": summary.get("raw", ""),
            "html": summary.get("html", ""),
            "text": summary.get("text", ""),
        },
        "instances": instances,
        "generatedAt": Path().absolute().as_posix(),
        "note": "本文件包含结构化数据与打印配置详情。",
    }


# ============ 本地归档与页面生成（集成 5.0.py 逻辑） ============
REBUILD_SESSION = requests.Session()
REBUILD_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (MW-Fetcher-Rebuild)"
})


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def possible_prefixes(base_name: str):
    prefixes = {base_name}
    if base_name.endswith("_"):
        prefixes.add(base_name.rstrip("_"))
    else:
        prefixes.add(base_name + "_")
    return prefixes


def iter_patterns(root: Path, base_name: str, middles):
    for prefix in possible_prefixes(base_name):
        for mid in middles:
            yield from root.glob(prefix + mid)


def glob_with_prefix_or_plain(root: Path, base_name: str, middles):
    seen = set()
    # 先匹配无前缀
    for mid in middles:
        for p in root.glob(mid):
            if p in seen:
                continue
            seen.add(p)
            yield p
    # 再匹配带前缀
    for p in iter_patterns(root, base_name, middles):
        if p in seen:
            continue
        seen.add(p)
        yield p


def strip_prefix(name: str, base_name: str) -> str:
    for prefix in sorted(possible_prefixes(base_name), key=len, reverse=True):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


STYLE_CSS = """
body {
  font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
  margin: 0;
  padding: 0;
  background: #f5f5f5;
  color: #222;
}

.container {
  max-width: 980px;
  margin: 24px auto 40px;
  padding: 24px;
  background: #ffffff;
  box-shadow: 0 0 12px rgba(0,0,0,0.06);
  border-radius: 10px;
}

h1.title {
  font-size: 26px;
  margin: 0 0 8px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.title a.origin-link {
  font-size: 14px;
  text-decoration: none;
  color: #1976d2;
}

.title a.origin-link::before {
  content: "↗ ";
}

.author {
  margin: 4px 0 14px;
  font-size: 14px;
  color: #555;
  display: flex;
  align-items: center;
  gap: 10px;
}

.author img.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  object-fit: cover;
}

.hero {
  width: 100%;
  max-height: 540px;
  object-fit: contain;
  border-radius: 8px;
  margin-bottom: 12px;
  background: #000;
}

.collect-date {
  font-size: 13px;
  color: #777;
  margin: 0 0 16px;
}

.section-title {
  font-size: 18px;
  margin: 22px 0 10px;
  border-left: 4px solid #1976d2;
  padding-left: 10px;
}

.stats {
  margin: 6px 0 14px;
  color: #666;
  font-size: 14px;
}

.tag-list span {
  display: inline-block;
  background: #e3f2fd;
  padding: 4px 10px;
  margin: 4px 6px 0 0;
  border-radius: 14px;
  font-size: 13px;
}

.summary img {
  max-width: 100%;
  border-radius: 6px;
  margin: 6px 0;
}

.attachments {
  margin-bottom: 10px;
}

.printed {
  margin-bottom: 10px;
}

.printed-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 10px;
}

.printed-item {
  width: 160px;
}

.printed-item img {
  width: 100%;
  height: 120px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid #eee;
  background: #000;
  cursor: zoom-in;
}

.printed-caption {
  font-size: 12px;
  color: #555;
  margin-top: 4px;
  word-break: break-all;
}

.printed-empty {
  color: #888;
  font-size: 13px;
  margin-top: 6px;
}

.attach-upload {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.attach-upload input[type="file"] {
  font-size: 13px;
}

.attach-btn {
  background: #1976d2;
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 6px 12px;
  cursor: pointer;
  font-size: 13px;
}

.attach-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.attach-msg {
  font-size: 12px;
  color: #666;
}

.attach-msg.error {
  color: #b00020;
}

.attach-list {
  list-style: none;
  padding-left: 0;
  margin: 10px 0 0;
}

.attach-list li {
  margin: 4px 0;
  font-size: 13px;
}

.attach-list a {
  color: #1976d2;
  text-decoration: none;
}

.attach-list a:hover {
  text-decoration: underline;
}

.attach-empty {
  color: #888;
}

.instances .inst-card {
  border: 1px solid #e6e6e6;
  padding: 12px;
  border-radius: 10px;
  margin-bottom: 12px;
  transition: box-shadow 0.2s ease, transform 0.2s ease;
}

.instances .inst-card:hover {
  box-shadow: 0 6px 18px rgba(0,0,0,0.08);
  transform: translateY(-2px);
}

.inst-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 13px;
  color: #555;
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 12px;
  background: #f7f7f7;
  border: 1px solid #eee;
}

.meta-item:hover {
  background: #eef5ff;
  border-color: #d0e0ff;
}

.meta-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  margin-left: 6px;
  border-radius: 12px;
  background: #e8f5e9;
  color: #1b5e20;
  font-size: 12px;
  border: 1px solid #c8e6c9;
}

.inst-download {
  margin-left: 6px;
  font-size: 12px;
  text-decoration: none;
  background: #1976d2;
  color: #fff;
  padding: 2px 8px;
  border-radius: 10px;
}

.inst-download:hover {
  background: #0f5fb6;
}

.inst-btn {
  margin-left: 6px;
  font-size: 12px;
  text-decoration: none;
  background: #1976d2;
  color: #fff;
  padding: 2px 8px;
  border-radius: 10px;
}

.inst-btn.alt {
  background: #6c757d;
}

.inst-btn:hover {
  opacity: 0.9;
}

.inst-thumb {
  width: 140px;
  height: 140px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid #eee;
  background: #000;
  cursor: zoom-in;
}

.plates {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 10px;
}

.plate-item {
  width: 120px;
  border: 1px solid #eee;
  border-radius: 8px;
  padding: 6px;
  font-size: 12px;
}

.plate-item img {
  width: 100%;
  height: 70px;
  object-fit: contain;
  border-radius: 6px;
  background: #000;
  cursor: zoom-in;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.chip {
  display: inline-block;
  padding: 2px 8px 2px 6px;
  border-radius: 12px;
  font-size: 12px;
  background: #f0f0f0;
  border: 1px solid #e8e8e8;
}

.chip .color-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: 6px;
  border: 1px solid #ccc;
  vertical-align: middle;
}

.thumbs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 6px 0 12px;
}

.thumbs img {
  width: 82px;
  height: 82px;
  object-fit: cover;
  border-radius: 6px;
  border: 2px solid transparent;
  background: #000;
}

.thumbs img.active {
  border-color: #1976d2;
  box-shadow: 0 0 6px rgba(25, 118, 210, 0.6);
}

.zoomable {
  cursor: zoom-in;
}

.lightbox {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.8);
  display: none;
  align-items: center;
  justify-content: center;
  z-index: 999999;
}

.lightbox img {
  max-width: 90vw;
  max-height: 90vh;
  border-radius: 10px;
  box-shadow: 0 12px 32px rgba(0,0,0,0.4);
}

.lightbox.show {
  display: flex;
}
.carousel {
  position: relative;
  margin: 10px 0 20px;
  overflow: hidden;
  border-radius: 8px;
  background: #000;
}

.carousel-track {
  display: flex;
  transition: transform 0.3s ease;
}

.carousel img {
  width: 100%;
  max-height: 480px;
  object-fit: contain;
  flex-shrink: 0;
  background: #000;
}

.carousel-btn {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 32px;
  height: 32px;
  border-radius: 16px;
  border: none;
  background: rgba(0,0,0,0.45);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.carousel-btn:hover {
  background: rgba(0,0,0,0.7);
}

.carousel-btn.prev {
  left: 10px;
}

.carousel-btn.next {
  right: 10px;
}
""".strip()


def normalize_stats(meta: dict) -> dict:
    stats = meta.get("stats") or meta.get("counts") or {}
    likes = stats.get("likes") or stats.get("like") or 0
    favorites = stats.get("favorites") or stats.get("favorite") or 0
    downloads = stats.get("downloads") or stats.get("download") or 0
    prints = stats.get("prints") or stats.get("print") or 0
    views = stats.get("views") or stats.get("read") or stats.get("reads") or 0
    return {
        "likes": likes,
        "favorites": favorites,
        "downloads": downloads,
        "prints": prints,
        "views": views,
    }


def normalize_author(meta: dict) -> dict:
    author_raw = meta.get("author")
    if isinstance(author_raw, str):
        return {"name": author_raw, "url": "", "avatar": None}
    if not isinstance(author_raw, dict):
        return {"name": "", "url": "", "avatar": None}

    avatar_local = author_raw.get("avatarLocal") or author_raw.get("avatar_local")
    avatar_rel = author_raw.get("avatarRelPath") or author_raw.get("avatar_local_path")
    if not avatar_rel and avatar_local:
        avatar_rel = f"images/{avatar_local}"

    return {
        "name": author_raw.get("name") or "",
        "url": author_raw.get("url") or "",
        "avatar": avatar_rel,
    }


def normalize_images(meta: dict) -> dict:
    images_raw = meta.get("images")
    design = []
    summary = []
    cover = None

    def to_name(item):
        if not item:
            return None
        return Path(item).name

    if isinstance(images_raw, dict):
        design = [to_name(x) for x in images_raw.get("design", []) if to_name(x)]
        summary = [to_name(x) for x in images_raw.get("summary", []) if to_name(x)]
        cover = to_name(images_raw.get("cover"))
    elif isinstance(images_raw, list):
        design = [to_name(x) for x in images_raw if to_name(x)]

    if not design and meta.get("designImages"):
        for item in meta.get("designImages", []):
            if isinstance(item, dict):
                val = item.get("fileName") or item.get("localName") or item.get("relPath")
                name = to_name(val)
                if name:
                    design.append(name)

    if not summary and meta.get("summaryImages"):
        for item in meta.get("summaryImages", []):
            if isinstance(item, dict):
                val = item.get("fileName") or item.get("relPath")
                name = to_name(val)
                if name:
                    summary.append(name)
            elif isinstance(item, str):
                name = to_name(item)
                if name:
                    summary.append(name)

    if not cover:
        cover_info = meta.get("cover") or {}
        cover = to_name(cover_info.get("relPath") or cover_info.get("localName"))

    return {"design": design, "summary": summary, "cover": cover}


def format_duration(seconds):
    try:
        sec = int(seconds)
    except Exception:
        return ""
    hours = sec / 3600.0
    if hours >= 1:
        return f"{hours:.1f} h"
    mins = sec / 60.0
    return f"{mins:.1f} min"


def format_date(date_str):
    try:
        if not date_str:
            return ""
        clean = date_str.replace("Z", "+00:00") if str(date_str).endswith("Z") else str(date_str)
        return str(datetime.fromisoformat(clean).date())
    except Exception:
        return date_str or ""


def build_instance_html(inst, assets):
    title = inst.get("title") or inst.get("name") or f"实例 {inst.get('id')}"
    publish = format_date(inst.get("publishTime") or "")
    summary = inst.get("summary") or ""
    dls = inst.get("downloadCount") or 0
    prints = inst.get("printCount") or 0
    weight = inst.get("weight") or ""
    prediction = inst.get("prediction")
    time_str = format_duration(prediction) if prediction else ""
    plates = inst.get("plates") or []
    plate_cnt = len(plates)
    pictures = inst.get("pictures") or []
    filaments = inst.get("instanceFilaments") or []

    base_name = assets.get("base_name") or ""

    def local_name(rel):
        if not rel:
            return ""
        try:
            name = Path(rel).name
        except Exception:
            name = rel
        return strip_prefix(name, base_name) if base_name else name

    file_name = pick_instance_filename(inst, inst.get("name") or "")
    dl_href_local = "./instances/" + file_name if file_name else ""

    chips = []
    for f in filaments:
        typ = f.get("type") or ""
        used_g = f.get("usedG") or f.get("usedg") or ""
        col = f.get("color") or ""
        dot = f'<span class="color-dot" style="background:{col}"></span>' if col else ""
        chips.append(f"{dot}{typ} {used_g}g".strip())

    chips_html = "\n".join(f'<span class="chip">{c}</span>' for c in chips)

    plates_html = ""
    if plates:
        blocks = []
        for p in plates:
            th = local_name(p.get("thumbnailRelPath") or "")
            pred = format_duration(p.get("prediction")) if p.get("prediction") else ""
            w = p.get("weight")
            fs = p.get("filaments") or []
            fs_html = " ".join(f'{f.get("type")} {f.get("usedG","")}g' for f in fs if f)
            blocks.append(
                f'<div class="plate-item"><img class="zoomable" src="{("./images/"+th) if th else ""}" alt="plate {p.get("index")}">'
                f'<div>Plate {p.get("index")}</div>'
                f'<div>{pred} {str(w)+" g" if w else ""}</div>'
                f'<div>{fs_html}</div>'
                f'</div>'
            )
        plates_html = '<div class="plates">' + "".join(blocks) + "</div>"

    pics_html = ""
    if pictures:
        imgs = []
        for pic in pictures:
            rel = local_name(pic.get("relPath") or "")
            if rel:
                imgs.append(f'<img class="inst-thumb zoomable" src="./images/{rel}" alt="pic {pic.get("index")}">')
        if imgs:
            pics_html = '<div class="thumbs">' + "".join(imgs) + "</div>"

    hide_inst_stats = bool(assets.get("hide_inst_stats"))
    stats_html = ""
    if not hide_inst_stats:
        stats_html = f'<div class="inst-meta"><span class="meta-item" title="下载次数">⬇️ {dls}</span><span class="meta-item" title="打印次数">🖨️ {prints}</span><span class="meta-item" title="预计打印时间">⏱️ {time_str}</span><span class="meta-item" title="重量">⚖️ {weight} g</span></div>'

    return f"""
<div class="inst-card">
  <div class="inst-meta">
    <div>
      <strong>{title}</strong>
      {"<a class='inst-btn inst-local' href='"+dl_href_local+"' target='_blank' rel='noreferrer'>📥 下载</a>" if dl_href_local else ""}
      {"<span class='meta-badge' title='打印盘数'>🧩 "+str(plate_cnt)+" 盘</span>" if plate_cnt else ""}
    </div>
    {"<div>发布于 "+publish+"</div>" if publish else ""}
  </div>
  {stats_html}
  {"<div class='chips'>"+chips_html+"</div>" if chips_html else ""}
  {pics_html}
  {plates_html}
  {"<div style='margin-top:8px;font-size:13px;color:#444;'>"+summary+"</div>" if summary else ""}
</div>
""".strip()


def build_index_html(meta: dict, assets: dict) -> str:
    title = meta.get("title", "")
    url = meta.get("url", "")
    tags = meta.get("tags") or meta.get("tagsOriginal") or []
    stats = normalize_stats(meta)
    summary_meta = meta.get("summary") or {}
    summary_html_raw = summary_meta.get("html") or summary_meta.get("raw") or ""
    summary_html = re.sub(
        r'<div[^>]*class="[^"]*translated-text[^"]*"[^>]*>.*?</div>',
        "",
        summary_html_raw,
        flags=re.S | re.I,
    )
    images = normalize_images(meta)
    author = normalize_author(meta)

    like_count = stats.get("likes") or 0
    fav_count = stats.get("favorites") or 0
    dl_count = stats.get("downloads") or 0
    print_count = stats.get("prints") or 0
    view_count = stats.get("views") or 0

    tags_html = ""
    if tags:
        tags_html = "\n".join(
            f'<span>{t}</span>' for t in tags
        )

    design_imgs = assets.get("design_files") or images.get("design") or []
    thumbs_html = ""
    carousel_html = ""
    if design_imgs:
        img_tags = "\n".join(
            f'<img src="./images/{fn}" alt="design image">'
            for fn in design_imgs
        )
        thumbs_html = "\n".join(
            f'<img data-idx="{i}" src="./images/{fn}" alt="thumb {i+1}">'
            for i, fn in enumerate(design_imgs)
        )
        carousel_html = f"""
<div class="carousel" id="designCarousel">
  <div class="carousel-track">
    {img_tags}
  </div>
  <button class="carousel-btn prev" type="button">◀</button>
  <button class="carousel-btn next" type="button">▶</button>
</div>
<div class="thumbs" id="designThumbs">
  {thumbs_html}
</div>
""".strip()

    hero_src = assets.get("hero") or "screenshot.png"
    avatar_src = assets.get("avatar")
    collected_date = assets.get("collected_date", "")
    collected_div = f'<div class="collect-date">采集日期：{collected_date}</div>' if collected_date else ""

    author_name = author.get("name", "")
    author_url = author.get("url", "")

    stats_fragments = [f"👍 {like_count}", f"⭐ {fav_count}", f"⬇️ {dl_count}"]
    if print_count:
        stats_fragments.append(f"🖨️ {print_count}")
    if view_count:
        stats_fragments.append(f"👀 {view_count}")
    stats_line = "　".join(stats_fragments)
    hide_stats = bool(assets.get("hide_stats")) or meta.get("source") == "others"
    stats_html = f'<div class="stats">\n    {stats_line}\n  </div>' if not hide_stats else ""

    origin_link = f'<a class="origin-link" href="{url}" target="_blank" rel="noreferrer">原文链接</a>' if url else ""
    avatar_html = f'<img class="avatar" src="{avatar_src}" alt="avatar">' if avatar_src else ""
    author_display = (
        f'<a href="{author_url}" target="_blank" rel="noreferrer">{author_name}</a>'
        if author_url else author_name
    )

    instances = meta.get("instances") or []
    inst_html = ""
    if instances:
        blocks = []
        for inst in instances:
            blocks.append(build_instance_html(inst, assets))
        inst_html = "\n".join(blocks)

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<link rel="stylesheet" href="./style.css">
</head>
<body>
<div class="container">

  <h1 class="title">
    {title}
    {origin_link}
  </h1>

  <div class="author">
    {avatar_html}
    作者：
    {author_display}
  </div>

  <img class="hero" src="{hero_src}" alt="screenshot">
  {collected_div}

  {stats_html}

  <div class="section-title">标签</div>
  <div class="tag-list">
    {tags_html}
  </div>

  <div class="section-title">打印配置 / 实例</div>
  <div class="instances">
    {inst_html}
  </div>

  <div class="section-title">简介</div>

  <!-- 设计图片轮播 -->
  {carousel_html}

  <!-- 描述内容（带本地图片路径） -->
  <div class="summary">
    {summary_html}
  </div>

  <div class="section-title">附件</div>
  <div class="attachments">
    <div class="attach-upload">
      <input type="file" id="attachInput" multiple>
      <button class="attach-btn" type="button" id="attachUploadBtn">上传附件</button>
      <span class="attach-msg" id="attachMsg"></span>
    </div>
    <ul class="attach-list" id="attachList"></ul>
  </div>

  <div class="section-title">打印成品</div>
  <div class="printed">
    <div class="attach-upload">
      <input type="file" id="printedInput" multiple accept="image/*">
      <button class="attach-btn" type="button" id="printedUploadBtn">上传图片</button>
      <span class="attach-msg" id="printedMsg"></span>
    </div>
    <div class="printed-grid" id="printedList"></div>
  </div>

</div>

<div class="lightbox" id="imgLightbox">
  <img src="" alt="preview">
</div>

<script>
(function() {{
  const carousel = document.getElementById('designCarousel');
  if (!carousel) return;
  const track = carousel.querySelector('.carousel-track');
  const slides = carousel.querySelectorAll('img');
  const prevBtn = carousel.querySelector('.prev');
  const nextBtn = carousel.querySelector('.next');
  const thumbs = document.querySelectorAll('#designThumbs img');
  if (!track || slides.length === 0) return;

  let index = 0;
  function update() {{
    const width = carousel.clientWidth;
    track.style.transform = 'translateX(' + (-index * width) + 'px)';
    thumbs.forEach((t, i) => {{
      if (i === index) t.classList.add('active');
      else t.classList.remove('active');
    }});
  }}

  function go(delta) {{
    index = (index + delta + slides.length) % slides.length;
    update();
  }}

  window.addEventListener('resize', update);
  prevBtn.addEventListener('click', function() {{ go(-1); }});
  nextBtn.addEventListener('click', function() {{ go(1); }});
  thumbs.forEach((t, i) => {{
    t.addEventListener('click', function() {{
      index = i;
      update();
    }});
  }});

  update();
}})();

(function() {{
  const overlay = document.getElementById('imgLightbox');
  const overlayImg = overlay ? overlay.querySelector('img') : null;
  if (!overlay || !overlayImg) return;
  document.addEventListener('click', (event) => {{
    const target = event.target;
    if (!(target instanceof HTMLImageElement)) return;
    if (!target.classList.contains('zoomable')) return;
    overlayImg.src = target.src;
    overlay.classList.add('show');
  }});
  overlay.addEventListener('click', () => {{
    overlay.classList.remove('show');
    overlayImg.src = '';
  }});
}})();

(function() {{
  // 动态切换实例本地/远程下载按钮：若本地文件存在则优先显示下载，否则显示原始地址
  const cards = document.querySelectorAll('.inst-card');
  cards.forEach((card) => {{
    const localBtn = card.querySelector('.inst-local');
    const remoteBtn = card.querySelector('.inst-remote');
    if (!localBtn || !remoteBtn) return;
    const localHref = localBtn.getAttribute('data-href');
    const showLocal = () => {{
      localBtn.classList.remove('hidden');
      remoteBtn.classList.add('hidden');
    }};
    const showRemote = () => {{
      localBtn.classList.add('hidden');
      remoteBtn.classList.remove('hidden');
    }};
    // file:// 场景下 HEAD/GET 会被 CORS 拦截，直接按是否有本地路径决定
    if (location.protocol === 'file:') {{
      if (localHref && localHref !== '#') showLocal();
      else showRemote();
      return;
    }}
    if (!localHref || localHref === '#') {{
      showRemote();
      return;
    }}
    fetch(localHref, {{ method: 'HEAD' }})
      .then((res) => {{
        if (res.ok) showLocal();
        else showRemote();
      }})
      .catch(() => showRemote());
  }});
}})();

(function() {{
  const listEl = document.getElementById('attachList');
  const msgEl = document.getElementById('attachMsg');
  const inputEl = document.getElementById('attachInput');
  const btnEl = document.getElementById('attachUploadBtn');
  if (!listEl) return;

  function setMsg(text, isError) {{
    if (!msgEl) return;
    msgEl.textContent = text || '';
    if (isError) msgEl.classList.add('error');
    else msgEl.classList.remove('error');
  }}

  function getModelDir() {{
    const path = window.location.pathname || '';
    const parts = path.split('/').filter(Boolean);
    const filesIdx = parts.indexOf('files');
    if (filesIdx >= 0 && parts.length > filesIdx + 1) return decodeURIComponent(parts[filesIdx + 1]);
    if (parts.length >= 2) return decodeURIComponent(parts[parts.length - 2]);
    return '';
  }}

  const modelDir = getModelDir();
  if (!modelDir) {{
    setMsg('无法识别模型目录', true);
    return;
  }}

  function renderList(files) {{
    listEl.innerHTML = '';
    if (!files || files.length === 0) {{
      const li = document.createElement('li');
      li.className = 'attach-empty';
      li.textContent = '暂无附件';
      listEl.appendChild(li);
      return;
    }}
    files.forEach((name) => {{
      const li = document.createElement('li');
      const link = document.createElement('a');
      link.href = './file/' + encodeURIComponent(name);
      link.textContent = name;
      link.setAttribute('download', name);
      li.appendChild(link);
      listEl.appendChild(li);
    }});
  }}

  function loadList() {{
    if (location.protocol === 'file:') {{
      renderList([]);
      setMsg('请通过本地服务打开页面以查看附件列表', true);
      return;
    }}
    fetch('/api/models/' + encodeURIComponent(modelDir) + '/attachments')
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((data) => {{
        renderList((data && data.files) || []);
        setMsg('');
      }})
      .catch(() => {{
        renderList([]);
        setMsg('附件列表加载失败', true);
      }});
  }}

  loadList();

  if (!btnEl || !inputEl) return;
  btnEl.addEventListener('click', async () => {{
    const files = inputEl.files ? Array.from(inputEl.files) : [];
    if (!files.length) {{
      setMsg('请选择附件', true);
      return;
    }}
    if (location.protocol === 'file:') {{
      setMsg('请通过本地服务打开页面以便上传', true);
      return;
    }}
    btnEl.disabled = true;
    let success = 0;
    let failed = 0;
    setMsg(`上传中... (0/${{files.length}})`);
    for (const file of files) {{
      const fd = new FormData();
      fd.append('file', file);
      try {{
        const res = await fetch('/api/models/' + encodeURIComponent(modelDir) + '/attachments', {{
          method: 'POST',
          body: fd,
        }});
        if (!res.ok) throw new Error('upload failed');
        success += 1;
      }} catch (e) {{
        failed += 1;
      }}
      setMsg(`上传中... (${{success + failed}}/${{files.length}})`);
    }}
    inputEl.value = '';
    loadList();
    if (failed === 0) setMsg('上传成功');
    else if (success === 0) setMsg('上传失败', true);
    else setMsg(`部分成功 ${{success}}/${{files.length}}`, true);
    btnEl.disabled = false;
  }});
}})();

(function() {{
  const listEl = document.getElementById('printedList');
  const msgEl = document.getElementById('printedMsg');
  const inputEl = document.getElementById('printedInput');
  const btnEl = document.getElementById('printedUploadBtn');
  if (!listEl) return;

  function setMsg(text, isError) {{
    if (!msgEl) return;
    msgEl.textContent = text || '';
    if (isError) msgEl.classList.add('error');
    else msgEl.classList.remove('error');
  }}

  function getModelDir() {{
    const path = window.location.pathname || '';
    const parts = path.split('/').filter(Boolean);
    const filesIdx = parts.indexOf('files');
    if (filesIdx >= 0 && parts.length > filesIdx + 1) return decodeURIComponent(parts[filesIdx + 1]);
    if (parts.length >= 2) return decodeURIComponent(parts[parts.length - 2]);
    return '';
  }}

  const modelDir = getModelDir();
  if (!modelDir) {{
    setMsg('无法识别模型目录', true);
    return;
  }}

  function renderList(files) {{
    listEl.innerHTML = '';
    if (!files || files.length === 0) {{
      const empty = document.createElement('div');
      empty.className = 'printed-empty';
      empty.textContent = '暂无图片';
      listEl.appendChild(empty);
      return;
    }}
    files.forEach((name) => {{
      const item = document.createElement('div');
      item.className = 'printed-item';
      const img = document.createElement('img');
      img.className = 'zoomable';
      img.src = './printed/' + encodeURIComponent(name);
      img.alt = name;
      const caption = document.createElement('div');
      caption.className = 'printed-caption';
      caption.textContent = name;
      item.appendChild(img);
      item.appendChild(caption);
      listEl.appendChild(item);
    }});
  }}

  function loadList() {{
    if (location.protocol === 'file:') {{
      renderList([]);
      setMsg('请通过本地服务打开页面以查看图片列表', true);
      return;
    }}
    fetch('/api/models/' + encodeURIComponent(modelDir) + '/printed')
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((data) => {{
        renderList((data && data.files) || []);
        setMsg('');
      }})
      .catch(() => {{
        renderList([]);
        setMsg('图片列表加载失败', true);
      }});
  }}

  loadList();

  if (!btnEl || !inputEl) return;
  btnEl.addEventListener('click', async () => {{
    const files = inputEl.files ? Array.from(inputEl.files) : [];
    if (!files.length) {{
      setMsg('请选择图片', true);
      return;
    }}
    if (location.protocol === 'file:') {{
      setMsg('请通过本地服务打开页面以便上传', true);
      return;
    }}
    btnEl.disabled = true;
    let success = 0;
    let failed = 0;
    setMsg(`上传中... (0/${{files.length}})`);
    for (const file of files) {{
      const fd = new FormData();
      fd.append('file', file);
      try {{
        const res = await fetch('/api/models/' + encodeURIComponent(modelDir) + '/printed', {{
          method: 'POST',
          body: fd,
        }});
        if (!res.ok) throw new Error('upload failed');
        success += 1;
      }} catch (e) {{
        failed += 1;
      }}
      setMsg(`上传中... (${{success + failed}}/${{files.length}})`);
    }}
    inputEl.value = '';
    loadList();
    if (failed === 0) setMsg('上传成功');
    else if (success === 0) setMsg('上传失败', true);
    else setMsg(`部分成功 ${{success}}/${{files.length}}`, true);
    btnEl.disabled = false;
  }});
}})();
</script>

</body>
</html>
"""
    return html


def rebuild_once(meta_path: Path):
    with meta_path.open("r", encoding="utf-8") as f:
        meta = json.load(f)

    base_name = meta.get("baseName") or meta_path.stem.replace("_meta", "")
    work_dir = meta_path.parent / base_name
    ensure_dir(work_dir)

    log("归档生成页面:", base_name)

    # 1. 写/移动 meta.json 到目标目录，仅保留目标目录一份
    target_meta = work_dir / "meta.json"
    if not target_meta.exists():
        shutil.move(str(meta_path), str(target_meta))
    else:
        if meta_path.resolve() != target_meta.resolve() and meta_path.exists():
            try:
                meta_path.unlink()
            except Exception:
                pass

    # 2. 准备子目录
    images_dir = work_dir / "images"
    instances_dir = work_dir / "instances"
    ensure_dir(images_dir)
    ensure_dir(instances_dir)

    # 3. 移动 screenshot
    screenshot_file = None
    for p in glob_with_prefix_or_plain(meta_path.parent, base_name, ["_screenshot.*", "screenshot.*"]):
        dst = work_dir / f"screenshot{p.suffix.lower()}"
        if not dst.exists():
            log("移动 screenshot:", p, "->", dst)
            shutil.move(str(p), str(dst))
        screenshot_file = dst
        break
    if not screenshot_file:
        existing = next(iter(work_dir.glob("screenshot.*")), None)
        if existing:
            screenshot_file = existing

    # 4. 封面图 & 作者头像 & design & summary images
    for p in glob_with_prefix_or_plain(meta_path.parent, base_name, ["_cover.*", "cover.*"]):
        dst = images_dir / f"cover{p.suffix.lower()}"
        if not dst.exists():
            log("移动 cover:", p, "->", dst)
            shutil.move(str(p), str(dst))
        break

    for p in glob_with_prefix_or_plain(meta_path.parent, base_name, ["_author_avatar.*", "author_avatar.*"]):
        dst = images_dir / f"author_avatar{p.suffix.lower()}"
        if not dst.exists():
            log("移动 author_avatar:", p, "->", dst)
            shutil.move(str(p), str(dst))
        break

    for p in glob_with_prefix_or_plain(meta_path.parent, base_name, ["_design_*", "design_*"]):
        new_name = strip_prefix(p.name, base_name)
        dst = images_dir / new_name
        if not dst.exists():
            log("移动 design 图片:", p, "->", dst)
            shutil.move(str(p), str(dst))

    for p in glob_with_prefix_or_plain(meta_path.parent, base_name, ["_summary_img_*", "summary_img_*"]):
        new_name = strip_prefix(p.name, base_name)
        dst = images_dir / new_name
        if not dst.exists():
            log("移动 summary 图片:", p, "->", dst)
            shutil.move(str(p), str(dst))

    # 5. 实例配图/plate 缩略图
    for p in glob_with_prefix_or_plain(meta_path.parent, base_name, ["_inst*_*"]):
        new_name = strip_prefix(p.name, base_name)
        dst = images_dir / new_name
        if not dst.exists():
            log("移动实例图片:", p, "->", dst)
            shutil.move(str(p), str(dst))

    # 6. 下载 3MF 到 instances 目录
    instances = meta.get("instances", []) or []
    inst_files = []
    for inst in instances:
        url = inst.get("downloadUrl")
        if not url:
            continue
        fn = pick_instance_filename(inst, inst.get("name") or "")
        dest = instances_dir / fn

        download_file(REBUILD_SESSION, url, dest)
        inst_files.append({
            "id": inst.get("id"),
            "title": inst.get("title") or inst.get("name") or str(inst.get("id")),
            "file": dest.name,
        })

    # 7. 写入 style.css
    style_path = work_dir / "style.css"
    style_path.write_text(STYLE_CSS, encoding="utf-8")

    # 8. 生成 index.html
    design_files = sorted([p.name for p in images_dir.glob("design_*")])
    cover_file = next(iter(images_dir.glob("cover.*")), None)
    avatar_file = next(iter(images_dir.glob("author_avatar.*")), None)

    hero_file = screenshot_file or cover_file or (images_dir / design_files[0] if design_files else None)
    hero_rel = hero_file.relative_to(work_dir).as_posix() if hero_file else "screenshot.png"

    assets = {
        "design_files": design_files,
        "hero": f"./{hero_rel}",
        "avatar": f"./{avatar_file.relative_to(work_dir).as_posix()}" if avatar_file else None,
        "collected_date": datetime.now().strftime("%Y-%m-%d"),
        "instance_files": inst_files,
        "base_name": base_name,
    }

    index_html = build_index_html(meta, assets)
    (work_dir / "index.html").write_text(index_html, encoding="utf-8")

    log("完成归档:", work_dir)


def archive_model(url: str, cookie: str, download_dir: Path, logs_dir: Path, logger=None):
    """
    对外主入口：采集 + 下载文件 + 生成 meta/index.html/style.css
    返回: {base_name, work_dir, missing_3mf}
    """
    # 采集阶段
    out_root = download_dir.resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (MW-Fetcher)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    })
    raw_cookie_header = (cookie or "").strip()
    parsed_cookies = parse_cookies(raw_cookie_header)
    sess.cookies.update(parsed_cookies)

    fetch_url = url.split("#", 1)[0]
    log(logger, "获取页面:", fetch_url)
    log(logger, "请求头:", sess.headers)
    log(logger, "请求 Cookie 头(前 300 字符):", raw_cookie_header[:300])

    # 优先用 requests 拉取页面，失败再回退 curl
    html_text = fetch_html_with_requests(sess, fetch_url, raw_cookie_header)
    if not html_text:
        html_text = fetch_html_with_curl(fetch_url, raw_cookie_header)
    elif "__NEXT_DATA__" not in html_text and "__NUXT__" not in html_text:
        log(logger, "requests 页面未包含 __NEXT_DATA__，尝试 curl 回退")
        html_text = fetch_html_with_curl(fetch_url, raw_cookie_header)

    if "__NEXT_DATA__" not in html_text and "__NUXT__" not in html_text:
        log(logger, "页面未包含 __NEXT_DATA__，前 300 字符:", (html_text or "")[:300])
    if _is_cloudflare_challenge(html_text):
        log(logger, "检测到 Cloudflare 验证页面，可能需要更新 cookie 中的 cf_clearance")

    design = None
    try:
        data = extract_next_data(html_text)
        design = extract_design_from_next_data(data)
        if design is None:
            log(logger, "未能从 __NEXT_DATA__ 定位 design，尝试 API 获取")
    except Exception as e:
        log(logger, "解析 __NEXT_DATA__ 失败，尝试 API 获取:", e)

    if design is None:
        api_host_hint = _extract_api_host(html_text)
        design = fetch_design_from_api(sess, raw_cookie_header, fetch_url, api_host_hint=api_host_hint)

    if design is None:
        if _is_cloudflare_challenge(html_text):
            raise RuntimeError("页面被 Cloudflare 验证拦截，请更新 cookie（含 cf_clearance）后重试")
        raise RuntimeError("未能解析模型数据，请确认 cookie/页面结构")

    design["url"] = url

    design_id = design.get("id") or _parse_design_id(url)
    if design_id is None:
        raise RuntimeError("未获取到模型 ID")
    title = design.get("title") or "model"
    base_name = f"MW_{design_id}_{sanitize_filename(title)}"
    images_dir = out_root

    author = extract_author(design, html_text)
    if author.get("avatarUrl"):
        ext = pick_ext_from_url(author["avatarUrl"])
        fname = f"author_avatar.{ext}"
        download_file(sess, author["avatarUrl"], images_dir / fname)
        author["avatarLocal"] = fname
        author["avatarRelPath"] = f"images/{fname}"

    summary = parse_summary(design, base_name, sess, images_dir)
    design_images, cover_meta = collect_design_images(design, sess, images_dir, base_name)

    parsed_origin = urlparse(fetch_url)
    origin = f"{parsed_origin.scheme}://{parsed_origin.netloc}" if parsed_origin.scheme and parsed_origin.netloc else "https://makerworld.com.cn"

    inst_list = []
    for inst in extract_instances(design):
        inst_id = inst.get("id") or inst.get("instanceId")
        if inst_id is None:
            continue
        plates, pics = collect_instance_media(inst, sess, images_dir, base_name)
        api_url = inst.get("apiUrl") or f"{origin}/api/v1/design-service/instance/{inst_id}/f3mf?type=download&fileType="
        name3mf, url3mf = fetch_instance_3mf(
            sess,
            inst_id,
            raw_cookie_header,
            api_url,
        )
        inst_list.append({
            "id": inst_id,
            "profileId": inst.get("profileId") or inst.get("profile_id") or inst.get("profileID"),
            "title": inst.get("title") or inst.get("name"),
            "titleTranslated": inst.get("titleTranslated") or "",
            "publishTime": inst.get("publishTime") or inst.get("publishedAt") or "",
            "downloadCount": inst.get("downloadCount") or 0,
            "printCount": inst.get("printCount") or 0,
            "prediction": inst.get("prediction"),
            "weight": inst.get("weight"),
            "materialCnt": inst.get("materialCnt"),
            "materialColorCnt": inst.get("materialColorCnt"),
            "needAms": inst.get("needAms"),
            "plates": plates,
            "pictures": pics,
            "instanceFilaments": inst.get("instanceFilaments") or [],
            "summary": inst.get("summary") or "",
            "summaryTranslated": inst.get("summaryTranslated") or "",
            "name": name3mf,
            "downloadUrl": url3mf,
            "apiUrl": api_url,
        })

    meta = build_meta(design, summary, design_images, cover_meta, inst_list, author, base_name)
    meta_path = out_root / f"{base_name}_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log(logger, "已保存 meta:", meta_path)

    # 归档整理
    log_section("归档整理阶段")
    try:
        rebuild_once(meta_path)
    except Exception as e:
        log(logger, "归档/生成本地页面失败:", e)

    # 缺失 3MF 记录（仅记录，没有下载 3mf）
    missing_3mf = [inst for inst in inst_list if not inst.get("downloadUrl")]
    if missing_3mf:
        logs_dir.mkdir(parents=True, exist_ok=True)
        missing_log = logs_dir / "missing_3mf.log"
        with missing_log.open("a", encoding="utf-8") as f:
            for m in missing_3mf:
                f.write(f"{datetime.now().isoformat()}\t{base_name}\t{m['id']}\t{m.get('title','')}\tcookie失效\n")
        log(logger, "缺失 3MF 已记录:", missing_log)

    work_dir = meta_path.parent / (meta.get("baseName") or meta_path.stem.replace("_meta", ""))
    return {"base_name": base_name, "work_dir": str(work_dir.resolve()), "missing_3mf": missing_3mf}


if __name__ == "__main__":
    log("此模块用于被导入调用，不建议直接运行。")
    sys.exit(0)
