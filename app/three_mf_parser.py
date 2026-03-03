import html
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def sanitize_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", (name or "").strip())


def unescape_text(value: str) -> str:
    text = value or ""
    for _ in range(2):
        nt = html.unescape(text)
        if nt == text:
            break
        text = nt
    return text


def _norm(path: str) -> str:
    return (path or "").replace("\\", "/").lstrip("/")


def _parse_metadata(model_xml: str) -> Dict[str, str]:
    try:
        root = ET.fromstring(model_xml)
    except Exception:
        return {}
    out: Dict[str, str] = {}
    for node in root.findall(".//{*}metadata"):
        key = (node.attrib.get("name") or "").strip()
        if not key:
            continue
        out[key] = node.text or node.attrib.get("value") or ""
    return out


def _parse_plate_entries(model_settings_xml: str) -> List[Dict[str, str]]:
    if not model_settings_xml:
        return []
    try:
        root = ET.fromstring(model_settings_xml)
    except Exception:
        return []
    out = []
    for plate in root.findall(".//plate"):
        item = {
            "plater_id": "",
            "plater_name": "",
            "thumbnail_file": "",
            "thumbnail_no_light_file": "",
        }
        for md in plate.findall("./metadata"):
            key = (md.attrib.get("key") or "").strip()
            val = (md.attrib.get("value") or "").strip()
            if key in item:
                item[key] = val
        if item["plater_id"] or item["thumbnail_file"]:
            out.append(item)
    return out


def _iter_prefixed_image_paths(names: List[str], prefix: str) -> List[str]:
    p = prefix.rstrip("/") + "/"
    out = []
    for name in names:
        n = _norm(name)
        if not n.lower().startswith(p.lower()):
            continue
        ext = Path(n).suffix.lower()
        if ext in IMAGE_EXTS:
            out.append(n)
    return sorted(out)


class ThreeMFPackage:
    def __init__(self, file_bytes: bytes):
        self._zip = zipfile.ZipFile(io.BytesIO(file_bytes), "r")
        self.names = [n for n in self._zip.namelist() if not n.endswith("/")]

    def close(self):
        self._zip.close()

    def exists(self, rel_path: str) -> bool:
        rel = _norm(rel_path)
        return rel in self.names

    def read_bytes(self, rel_path: str) -> bytes:
        return self._zip.read(_norm(rel_path))

    def read_text(self, rel_path: str, encoding: str = "utf-8") -> str:
        return self.read_bytes(rel_path).decode(encoding, errors="replace")

    def list_paths(self, prefix: str = "") -> List[str]:
        p = _norm(prefix)
        if not p:
            return list(self.names)
        p = p.rstrip("/") + "/"
        return [n for n in self.names if n.lower().startswith(p.lower())]


def parse_3mf_to_session(
    file_bytes: bytes,
    original_name: str,
    session_dir: Path,
    slot: int,
) -> Dict:
    images_dir = session_dir / "images"
    inst_dir = session_dir / "instances"
    file_dir = session_dir / "file"
    images_dir.mkdir(parents=True, exist_ok=True)
    inst_dir.mkdir(parents=True, exist_ok=True)
    file_dir.mkdir(parents=True, exist_ok=True)

    src_name = sanitize_name(original_name) or f"instance_{slot}.3mf"
    if not src_name.lower().endswith(".3mf"):
        src_name += ".3mf"
    stored_3mf = f"s{slot:02d}_{src_name}"
    (inst_dir / stored_3mf).write_bytes(file_bytes)

    pkg = ThreeMFPackage(file_bytes)
    try:
        model_xml = pkg.read_text("3D/3dmodel.model") if pkg.exists("3D/3dmodel.model") else ""
        md = _parse_metadata(model_xml) if model_xml else {}

        model_title = unescape_text(md.get("Title", "")) or Path(original_name).stem
        profile_title = unescape_text(md.get("ProfileTitle", "")) or model_title
        designer = unescape_text(md.get("Designer", "") or md.get("ProfileUserName", ""))
        description_html = unescape_text(md.get("Description", "") or "")
        profile_desc_html = unescape_text(md.get("ProfileDescription", "") or "")
        creation_date = md.get("CreationDate", "") or md.get("ModificationDate", "")

        all_names = pkg.list_paths("")

        # 模型图与配置图分开处理
        model_pics = _iter_prefixed_image_paths(all_names, "Auxiliaries/Model Pictures")
        profile_pics = _iter_prefixed_image_paths(all_names, "Auxiliaries/Profile Pictures")
        cover_src = model_pics[0] if model_pics else (profile_pics[0] if profile_pics else "")
        if not cover_src:
            candidates = [
                _norm(md.get("Thumbnail_Middle", "")),
                _norm(md.get("Thumbnail_Small", "")),
                "Auxiliaries/.thumbnails/thumbnail_middle.png",
                "Auxiliaries/.thumbnails/thumbnail_3mf.png",
            ]
            for c in candidates:
                if c and pkg.exists(c):
                    cover_src = c
                    break

        # 项目图优先：Auxiliaries/Model Pictures；兜底 Metadata 图片
        design_srcs = list(model_pics)
        if not design_srcs:
            md_imgs = _iter_prefixed_image_paths(all_names, "Metadata")
            prefer = []
            for n in md_imgs:
                ln = n.lower()
                if "/pick_" in ln or "/top_" in ln or "/plate_" in ln:
                    prefer.append(n)
            design_srcs = sorted(prefer)[:12] if prefer else sorted(md_imgs)[:12]

        src_to_local: Dict[str, str] = {}
        design_names: List[str] = []
        for i, src in enumerate(design_srcs, start=1):
            ext = Path(src).suffix.lower() or ".jpg"
            local_name = f"s{slot:02d}_design_{i:02d}{ext}"
            (images_dir / local_name).write_bytes(pkg.read_bytes(src))
            design_names.append(local_name)
            src_to_local[_norm(src)] = local_name

        profile_names: List[str] = []
        for i, src in enumerate(profile_pics, start=1):
            ext = Path(src).suffix.lower() or ".jpg"
            local_name = f"s{slot:02d}_profile_{i:02d}{ext}"
            (images_dir / local_name).write_bytes(pkg.read_bytes(src))
            profile_names.append(local_name)
            src_to_local[_norm(src)] = local_name

        cover_name = ""
        norm_cover = _norm(cover_src) if cover_src else ""
        if norm_cover and norm_cover in src_to_local:
            cover_name = src_to_local[norm_cover]
        elif cover_src and pkg.exists(cover_src):
            ext = Path(cover_src).suffix.lower() or ".jpg"
            cover_name = f"s{slot:02d}_cover{ext}"
            (images_dir / cover_name).write_bytes(pkg.read_bytes(cover_src))

        model_settings_text = pkg.read_text("Metadata/model_settings.config") if pkg.exists("Metadata/model_settings.config") else ""
        plate_entries = _parse_plate_entries(model_settings_text)
        plates = []
        for i, p in enumerate(plate_entries, start=1):
            src = _norm(p.get("thumbnail_file", ""))
            if not src or not pkg.exists(src):
                continue
            ext = Path(src).suffix.lower() or ".png"
            local_name = f"s{slot:02d}_plate_{i:02d}{ext}"
            (images_dir / local_name).write_bytes(pkg.read_bytes(src))
            plates.append({
                "index": i,
                "prediction": 0,
                "weight": 0,
                "filaments": [],
                "thumbnailUrl": "",
                "thumbnailRelPath": f"images/{local_name}",
                "thumbnailFile": local_name,
            })

        if not cover_name and design_names:
            cover_name = design_names[0]

        # 附件提取
        attachment_roots = [
            "Auxiliaries/Others",
            "Auxiliaries/Assembly Guide",
            "Auxiliaries/Bill of Materials",
        ]
        attachment_names: List[str] = []
        att_idx = 1
        for root_dir in attachment_roots:
            for rel in sorted(pkg.list_paths(root_dir)):
                rel_norm = _norm(rel)
                base = sanitize_name(Path(rel_norm).name) or "attachment"
                local_name = f"s{slot:02d}_att_{att_idx:02d}_{base}"
                (file_dir / local_name).write_bytes(pkg.read_bytes(rel_norm))
                attachment_names.append(local_name)
                att_idx += 1

        summary_text = re.sub(r"<[^>]+>", "", description_html).strip()
        profile_summary = re.sub(r"<[^>]+>", "", profile_desc_html).strip()

        project_settings = {}
        if pkg.exists("Metadata/project_settings.config"):
            try:
                project_settings = json.loads(pkg.read_text("Metadata/project_settings.config"))
            except Exception:
                project_settings = {}

        return {
            "sourceName": original_name,
            "instanceFile": stored_3mf,
            "modelTitle": model_title,
            "profileTitle": profile_title,
            "designer": designer,
            "descriptionHtml": description_html,
            "summaryText": summary_text,
            "profileDescriptionHtml": profile_desc_html,
            "profileSummaryText": profile_summary,
            "creationDate": creation_date,
            "coverFile": cover_name,
            "designFiles": design_names,
            "profilePictureFiles": profile_names,
            "attachments": attachment_names,
            "plates": plates,
            "projectSettings": project_settings if isinstance(project_settings, dict) else {},
            "metadata": {
                "Application": md.get("Application", ""),
                "BambuStudio:3mfVersion": md.get("BambuStudio:3mfVersion", ""),
                "DesignProfileId": md.get("DesignProfileId", ""),
                "DesignModelId": md.get("DesignModelId", ""),
            },
        }
    finally:
        pkg.close()


def build_draft_payload(session_id: str, parsed_items: List[Dict]) -> Dict:
    title = ""
    summary = ""
    summary_html = ""
    designer = ""
    cover = ""
    design_files: List[str] = []
    attachments: List[str] = []
    instances = []

    for i, item in enumerate(parsed_items, start=1):
        if not title:
            title = (item.get("modelTitle") or "").strip()
        if not summary:
            summary = (item.get("summaryText") or item.get("profileSummaryText") or "").strip()
        if not summary_html:
            summary_html = (item.get("descriptionHtml") or item.get("profileDescriptionHtml") or "").strip()
        if not designer:
            designer = (item.get("designer") or "").strip()
        if not cover and item.get("coverFile"):
            cover = item.get("coverFile")
        if not design_files and item.get("designFiles"):
            design_files = list(item.get("designFiles") or [])
        for fn in (item.get("attachments") or []):
            if fn and fn not in attachments:
                attachments.append(fn)

        pic_files = list(item.get("profilePictureFiles") or item.get("designFiles") or [])
        pics = []
        for pi, fn in enumerate(pic_files[:6], start=1):
            pics.append({
                "index": pi,
                "url": "",
                "relPath": f"images/{fn}",
                "fileName": fn,
                "isRealLifePhoto": 0,
            })

        instances.append({
            "index": i,
            "title": item.get("profileTitle") or item.get("modelTitle") or f"实例 {i}",
            "summary": item.get("profileSummaryText") or "",
            "name": item.get("instanceFile"),
            "sourceFileName": item.get("sourceName") or "",
            "publishTime": item.get("creationDate") or "",
            "downloadCount": 0,
            "printCount": 0,
            "prediction": 0,
            "weight": 0,
            "materialCnt": 0,
            "materialColorCnt": 0,
            "needAms": False,
            "plates": item.get("plates") or [],
            "pictures": pics,
            "instanceFilaments": [],
            "summaryTranslated": "",
            "titleTranslated": "",
            "downloadUrl": "",
            "apiUrl": "",
        })

    if not title:
        title = "3MF 导入模型"

    return {
        "sessionId": session_id,
        "title": title,
        "summary": summary,
        "summaryHtml": summary_html,
        "designer": designer,
        "coverFile": cover,
        "designFiles": design_files,
        "attachments": attachments,
        "instances": instances,
    }


def tmp_url(prefix: str, session_id: str, rel: str) -> str:
    rel_norm = _norm(rel)
    return f"/tmp/{prefix}/{session_id}/{rel_norm}"


def attach_preview_urls(payload: Dict, prefix: str = "manual_drafts") -> Dict:
    out = dict(payload or {})
    sid = out.get("sessionId") or ""
    cover = out.get("coverFile") or ""
    out["coverUrl"] = tmp_url(prefix, sid, f"images/{cover}") if cover else ""
    out["designUrls"] = [tmp_url(prefix, sid, f"images/{x}") for x in (out.get("designFiles") or [])]
    out["attachmentUrls"] = [
        {
            "name": str(x),
            "url": tmp_url(prefix, sid, f"file/{x}"),
        }
        for x in (out.get("attachments") or [])
    ]

    instances = []
    for inst in out.get("instances") or []:
        i2 = dict(inst)
        i2["fileUrl"] = tmp_url(prefix, sid, f"instances/{inst.get('name')}")
        pics = []
        for p in i2.get("pictures") or []:
            p2 = dict(p)
            fn = p2.get("fileName") or Path(p2.get("relPath") or "").name
            p2["previewUrl"] = tmp_url(prefix, sid, f"images/{fn}") if fn else ""
            pics.append(p2)
        i2["pictures"] = pics
        plates = []
        for pl in i2.get("plates") or []:
            pl2 = dict(pl)
            fn = pl2.get("thumbnailFile") or Path(pl2.get("thumbnailRelPath") or "").name
            pl2["thumbnailPreviewUrl"] = tmp_url(prefix, sid, f"images/{fn}") if fn else ""
            plates.append(pl2)
        i2["plates"] = plates
        instances.append(i2)
    out["instances"] = instances
    return out

