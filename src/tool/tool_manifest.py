#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

PART_STR_TUPLE = ("part_1.5", "part_2.0", "part_2.5", "part_3.0", "part_3.5", "part_4.0")
MANIFEST_KEY_STR_SET = {"project", "assets", "config", "python", "output", "tool", "parts"}
EXPECTED_ERROR_TUPLE = (FileNotFoundError, FileExistsError, ValueError, ImportError)


BANNER_DASH_INT = 16


def print_banner(script_str: str) -> None:
    dash_str = "-" * BANNER_DASH_INT
    print(f"\n{dash_str} {script_str} {dash_str}\n", flush=True)


def warn(msg_str: str) -> None:
    print(f"[Warn] {msg_str}", file=sys.stderr, flush=True)


def info(msg_str: str) -> None:
    print(f"[Info] {msg_str}", flush=True)


def success(msg_str: str) -> None:
    print(f"\n[Success] {msg_str}", flush=True)


def is_ts_str(ts_str: str) -> bool:
    if not re.fullmatch(r"\d{12}", ts_str):
        return False
    try:
        datetime.strptime(ts_str, "%Y%m%d%H%M")
    except ValueError:
        return False
    return True


def check_min_args(start_min_str: str, end_min_str: str) -> None:
    for label_str, minute_str in (("START_MIN", start_min_str), ("END_MIN", end_min_str)):
        if not is_ts_str(minute_str):
            raise ValueError(f"[Error] {label_str} 必須是完整且合法的 12 位 YYYYMMDDHHMM（例如 202605211300），"
                             f"收到：{minute_str!r}")
    if start_min_str > end_min_str:
        raise ValueError(f"[Error] START_MIN({start_min_str}) 不可晚於 END_MIN({end_min_str})")


def get_abs_path_from_base_and_str(base_dir_path: Path, path_str: str) -> Path:
    return Path(os.path.abspath(base_dir_path / Path(path_str).expanduser()))


def get_manifest_dict_from_path(manifest_path: Path) -> dict:
    manifest_path = Path(os.path.abspath(Path(manifest_path).expanduser()))
    if not manifest_path.is_file():
        raise FileNotFoundError(f"[Error] 找不到 manifest：{manifest_path}")
    try:
        manifest_obj = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error_obj:
        raise ValueError(f"[Error] manifest 不是合法的 JSON：{manifest_path}（{error_obj}）") from error_obj
    if not isinstance(manifest_obj, dict):
        raise ValueError("[Error] manifest 最外層必須是 JSON 物件 {...}")
    if set(manifest_obj) != MANIFEST_KEY_STR_SET:
        raise ValueError(f"[Error] manifest 的欄位必須剛好是 {sorted(MANIFEST_KEY_STR_SET)}；"
                         f"缺少 {sorted(MANIFEST_KEY_STR_SET - set(manifest_obj))}、多出 {sorted(set(manifest_obj) - MANIFEST_KEY_STR_SET)}")
    for key_str in sorted(MANIFEST_KEY_STR_SET - {"parts"}):
        if not (isinstance(manifest_obj[key_str], str) and manifest_obj[key_str]):
            raise ValueError(f"[Error] manifest 的 {key_str} 必須是非空字串（路徑）")
    parts_obj = manifest_obj["parts"]
    if not (isinstance(parts_obj, dict) and set(parts_obj) == set(PART_STR_TUPLE)
            and all(isinstance(path_str, str) and path_str for path_str in parts_obj.values())):
        raise ValueError(f"[Error] manifest 的 parts 必須是 {{part 名稱: 資料夾路徑}}，名稱剛好是 {list(PART_STR_TUPLE)}")
    project_dir_path = get_abs_path_from_base_and_str(manifest_path.parent, manifest_obj["project"])
    if not project_dir_path.is_dir():
        raise FileNotFoundError(f"[Error] manifest 的 project 資料夾不存在：{project_dir_path}")
    return {"manifest_path": manifest_path, "project_dir_path": project_dir_path,
            "assets_dir_path": get_abs_path_from_base_and_str(project_dir_path, manifest_obj["assets"]),
            "config_path": get_abs_path_from_base_and_str(project_dir_path, manifest_obj["config"]),
            "python_path": get_abs_path_from_base_and_str(project_dir_path, manifest_obj["python"]),
            "output_dir_path": get_abs_path_from_base_and_str(project_dir_path, manifest_obj["output"]),
            "tool_dir_path": get_abs_path_from_base_and_str(project_dir_path, manifest_obj["tool"]),
            "part_dir_path_dict": {part_str: get_abs_path_from_base_and_str(project_dir_path, path_str)
                                   for part_str, path_str in parts_obj.items()}}


def get_args_ns_from_argv_strs(prog_str: str, usage_str: str, argv_strs: list[str], part_range_bool: bool = False) -> argparse.Namespace:
    parser_obj = argparse.ArgumentParser(prog=prog_str, description=usage_str,
                                         formatter_class=argparse.RawDescriptionHelpFormatter)
    parser_obj.add_argument("manifest", metavar="MANIFEST_JSON", help="manifest.json 的路徑（相對於目前的工作目錄，或絕對）")
    parser_obj.add_argument("start_min", metavar="START_MIN", help="起始分鐘 YYYYMMDDHHMM（含）")
    parser_obj.add_argument("end_min", metavar="END_MIN", help="結束分鐘 YYYYMMDDHHMM（含）")
    if part_range_bool:
        parser_obj.add_argument("--start", metavar="PART", default=None,
                                help="只從這個 part 開始跑（含），例如 2.5 或 part_2.5；預設從 part_1.5")
        parser_obj.add_argument("--end", metavar="PART", default=None,
                                help="只跑到這個 part 為止（含），例如 3.5 或 part_3.5；預設跑到 part_4.0")
    args_ns = parser_obj.parse_args(argv_strs)
    check_min_args(args_ns.start_min, args_ns.end_min)
    args_ns.manifest_dict = get_manifest_dict_from_path(Path(args_ns.manifest))
    info(f"範圍 {args_ns.start_min} ~ {args_ns.end_min}")
    info(f"manifest：{args_ns.manifest_dict['manifest_path']}")
    return args_ns


def run_main_stage(run_func: Callable[[list[str]], None], argv_strs: list[str]) -> None:
    try:
        run_func(argv_strs)
    except KeyboardInterrupt:
        print("\n[Error] 使用者中斷（Ctrl-C），立即結束", file=sys.stderr, flush=True)
        sys.exit(130)
    except EXPECTED_ERROR_TUPLE as error_obj:
        msg_str = str(error_obj)
        print("\n" + (msg_str if msg_str.startswith("[Error]") else f"[Error] {msg_str}"), file=sys.stderr, flush=True)
        sys.exit(1)
    except Exception as error_obj:
        traceback.print_exc()
        print(f"\n[Error] 非預期的錯誤：{type(error_obj).__name__}: {error_obj}", file=sys.stderr, flush=True)
        sys.exit(1)
