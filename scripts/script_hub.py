#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
脚本说明：
- 动态扫描 scripts 目录下的 Python 脚本，集中展示功能摘要。
- 支持交互式选择执行，也支持通过命令行直接指定目标脚本。
- 统一入口后，只需运行本脚本即可选择当前可用的辅助脚本。

用法：
  python scripts/script_hub.py
  python scripts/script_hub.py --list
  python scripts/script_hub.py --run rebuild_index_from_meta.py
  python scripts/script_hub.py --run 2 -- --dry-run
"""

from __future__ import print_function

import argparse
import os
import re
import subprocess
import sys


SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPTS_DIR)
SELF_NAME = os.path.basename(__file__)

try:
    text_type = unicode
    binary_type = str
except NameError:
    text_type = str
    binary_type = bytes


class ScriptEntry(object):
    def __init__(self, name, path, title, summary):
        self.name = name
        self.path = path
        self.title = title
        self.summary = summary


def to_console_text(value):
    if isinstance(value, text_type):
        return value
    if isinstance(value, binary_type):
        try:
            return value.decode("utf-8")
        except Exception:
            return value.decode("utf-8", "ignore")
    try:
        return text_type(value)
    except Exception:
        return text_type(str(value), "utf-8", "ignore")


def write_line(value="", stream=None):
    target = stream or sys.stdout
    text = to_console_text(value)
    encoding = getattr(target, "encoding", None) or "utf-8"
    try:
        target.write(text + "\n")
    except Exception:
        if sys.version_info[0] < 3:
            target.write((text + "\n").encode(encoding, "replace"))
        else:
            target.write((text + "\n").encode(encoding, "replace").decode(encoding, "replace"))


def normalize_text(value):
    return " ".join(to_console_text(value or "").strip().split())


def extract_docstring(path):
    try:
        with open(path, "rb") as fh:
            source = fh.read()
        try:
            text = source.decode("utf-8")
        except Exception:
            text = source.decode("utf-8", "ignore")

        match = re.search(r'^[ \t\r\n]*(?:#.*\n\s*)*(?P<quote>"""|\'\'\')(?P<body>.*?)(?P=quote)', text, re.S)
        if not match:
            return ""
        return match.group("body").strip()
    except Exception:
        return ""


def build_summary_from_docstring(docstring):
    text = to_console_text(docstring or "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return u"无说明", u"未提供脚本说明"

    skip_labels = set([u"脚本说明", u"用法", u"用途", u"常用示例", u"特点"])
    useful = []
    for line in lines:
        cleaned = normalize_text(line.lstrip("- ").rstrip(u"：:"))
        if not cleaned:
            continue
        if cleaned in skip_labels:
            continue
        if cleaned.startswith("python ") or cleaned.startswith("python3 "):
            continue
        useful.append(cleaned)

    if not useful:
        return u"无说明", u"未提供脚本说明"

    title = useful[0]
    summary = ""
    for cleaned in useful[1:]:
        summary = cleaned
        break

    if not summary:
        summary = title
    return title, summary


def iter_script_paths():
    names = []
    for item in os.listdir(SCRIPTS_DIR):
        if not item.lower().endswith(".py"):
            continue
        if item == SELF_NAME:
            continue
        names.append(item)
    for name in sorted(names, key=lambda item: item.lower()):
        yield os.path.join(SCRIPTS_DIR, name)


def load_scripts():
    entries = []
    for path in iter_script_paths():
        docstring = extract_docstring(path)
        title, summary = build_summary_from_docstring(docstring)
        entries.append(ScriptEntry(os.path.basename(path), path, title, summary))
    return entries


def print_scripts(entries):
    write_line("")
    write_line(u"可执行脚本列表")
    write_line("")
    for index, entry in enumerate(entries, start=1):
        write_line("{0:>2}. {1}".format(index, entry.name))
        write_line(u"    功能: " + to_console_text(entry.title))
        write_line(u"    摘要: " + to_console_text(entry.summary))
    write_line("")


def find_entry(entries, selector):
    raw = str(selector or "").strip()
    if not raw:
        return None

    if raw.isdigit():
        index = int(raw)
        if 1 <= index <= len(entries):
            return entries[index - 1]

    lowered = raw.lower()
    for entry in entries:
        if entry.name.lower() == lowered:
            return entry
    for entry in entries:
        stem = os.path.splitext(entry.name)[0].lower()
        if stem == lowered:
            return entry
    return None


def prompt_select(entries):
    while True:
        try:
            choice = raw_input(u"请输入脚本编号或文件名，直接回车退出: ").strip()
        except NameError:
            choice = input(u"请输入脚本编号或文件名，直接回车退出: ").strip()
        if not choice:
            return None
        entry = find_entry(entries, choice)
        if entry:
            return entry
        write_line(u"未匹配到脚本，请重新输入。")
        write_line("")


def parse_extra_args(raw_args):
    args = list(raw_args or [])
    if args and args[0] == "--":
        return args[1:]
    return args


def prompt_extra_args():
    try:
        raw = raw_input(u"如需附加参数请输入，多个参数用空格分隔；直接回车表示无参数: ").strip()
    except NameError:
        raw = input(u"如需附加参数请输入，多个参数用空格分隔；直接回车表示无参数: ").strip()
    if not raw:
        return []
    return raw.split()


def resolve_runner_python():
    candidates = [
        os.path.join(REPO_ROOT, ".venv", "Scripts", "python.exe"),
        "python3",
        sys.executable,
    ]
    for candidate in candidates:
        if not candidate:
            continue
        if os.path.isfile(candidate):
            return candidate
        try:
            completed = subprocess.Popen(
                [candidate, "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=REPO_ROOT,
            )
            completed.communicate()
            if completed.returncode == 0:
                return candidate
        except Exception:
            continue
    return sys.executable


def format_command(parts):
    formatted = []
    for part in parts:
        text = str(part)
        if " " in text:
            formatted.append('"{0}"'.format(text))
        else:
            formatted.append(text)
    return " ".join(formatted)


def run_script(entry, extra_args):
    runner_python = resolve_runner_python()
    cmd = [runner_python, entry.path] + list(extra_args or [])
    write_line("")
    write_line(u"即将执行:")
    write_line(format_command(cmd))
    write_line("")
    completed = subprocess.Popen(cmd, cwd=REPO_ROOT)
    completed.communicate()
    return int(completed.returncode or 0)


def build_parser():
    parser = argparse.ArgumentParser(description=u"scripts 目录统一脚本入口")
    parser.add_argument("--list", action="store_true", help=u"仅列出可执行脚本")
    parser.add_argument("--run", default="", help=u"按编号、文件名或不带扩展名执行目标脚本")
    parser.add_argument("extra", nargs=argparse.REMAINDER, help=u"传递给目标脚本的额外参数，前面可加 --")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    entries = load_scripts()

    if not entries:
        write_line(u"scripts 目录下未找到可执行的 Python 脚本。", stream=sys.stderr)
        return 1

    if args.list:
        print_scripts(entries)
        return 0

    selected = find_entry(entries, args.run) if args.run else None
    extra_args = parse_extra_args(args.extra)

    if selected is None:
        print_scripts(entries)
        selected = prompt_select(entries)
        if selected is None:
            write_line(u"已取消。")
            return 0
        if not extra_args:
            extra_args = prompt_extra_args()

    return run_script(selected, extra_args)


if __name__ == "__main__":
    raise SystemExit(main())
