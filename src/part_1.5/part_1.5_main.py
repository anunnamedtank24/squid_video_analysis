#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True

USAGE_STR = "part_1.5：檢查時間參數與 assets（mp4）是否合法，並寫出 files.json 給後面的 part 使用。\n用法：python src/part_1.5/part_1.5_main.py MANIFEST_JSON START_MIN END_MIN"


def get_tool_dir_str_from_argv_strs(argv_strs: list[str]) -> str:
    try:
        manifest_path = Path(os.path.abspath(Path(argv_strs[0]).expanduser()))
        manifest_dict = json.loads(manifest_path.read_text(encoding="utf-8"))
        project_dir_path = Path(os.path.abspath(manifest_path.parent / Path(manifest_dict["project"]).expanduser()))
        return os.path.abspath(project_dir_path / Path(manifest_dict["tool"]).expanduser())
    except (IndexError, OSError, ValueError, KeyError, TypeError) as error_obj:
        sys.exit(f"[Error] 無法由 manifest 找到 tool 資料夾（{type(error_obj).__name__}: {error_obj}）\n{USAGE_STR}")


sys.path.insert(0, get_tool_dir_str_from_argv_strs(sys.argv[1:]))

from tool_manifest import print_banner

if __name__ == "__main__":
    print_banner("part_1.5_main.py")

from tool_main import (WhType, check_assets_dir_path, check_deps_are_available, get_config_dict_from_path,
                       get_first_bgr_arr_from_mp4_path, get_minute_strs_from_range, get_now_str,
                       get_param_dict_from_config_dict, get_part_dir_path, get_probe_dict_from_mp4_path,
                       get_range_dir_path, get_ts_to_mp4_paths_dict_from_assets_dir_path, run_overwrite_prompt_stage,
                       run_prepare_part_dir_stage, save_json_obj_to_path)
from tool_manifest import (get_args_ns_from_argv_strs, info, run_main_stage, success)

PART_STR = "part_1.5"
DEFAULT_PARAM_DICT: dict = {
    "duration_s": 60.0,
    "tolerance_s": 2.0,
}
RULE_DICT_DICT: dict[str, dict] = {
    "duration_s": {"type": "float", "min": 0, "min_open": True},
    "tolerance_s": {"type": "float", "min": 0},
}


def check_range_in_ts_strs(start_min_str: str, end_min_str: str, ts_strs: list[str]) -> None:
    if not ts_strs:
        raise FileNotFoundError("[Error] assets 底下找不到任何 mp4。預期結構：assets/{任意}/{YYYYMMDDHH}/NN{...}.mp4")
    if start_min_str < ts_strs[0] or end_min_str > ts_strs[-1]:
        hour_strs = sorted({ts_str[:10] for ts_str in ts_strs})
        raise ValueError(f"[Error] 範圍 {start_min_str} ~ {end_min_str} 超出 assets 內實際有 mp4 的範圍 "
                         f"{ts_strs[0]} ~ {ts_strs[-1]}（小時資料夾：{', '.join(hour_strs)}）")


def check_each_minute_has_one_mp4(minute_strs: list[str], ts_to_mp4_paths_dict: dict[str, list[Path]]) -> None:
    missing_strs = [ts_str for ts_str in minute_strs if ts_str not in ts_to_mp4_paths_dict]
    if missing_strs:
        raise FileNotFoundError(f"[Error] 範圍內有 {len(missing_strs)} 分鐘沒有 mp4：{missing_strs[:10]}"
                                f"{'…' if len(missing_strs) > 10 else ''}")
    dup_strs = [f"{ts_str}（{len(ts_to_mp4_paths_dict[ts_str])} 個：{[mp4_path.name for mp4_path in ts_to_mp4_paths_dict[ts_str]]}）"
                for ts_str in minute_strs if len(ts_to_mp4_paths_dict[ts_str]) != 1]
    if dup_strs:
        raise ValueError(f"[Error] 每分鐘必須剛好一個 mp4，但有 {len(dup_strs)} 分鐘重複：{dup_strs[:5]}")


def get_minute_dict_from_mp4_path(mp4_path: Path, param_dict: dict) -> dict:
    probe_dict = get_probe_dict_from_mp4_path(mp4_path)
    get_first_bgr_arr_from_mp4_path(mp4_path)
    low_float, high_float = param_dict["duration_s"] - param_dict["tolerance_s"], param_dict["duration_s"] + param_dict["tolerance_s"]
    if not low_float <= probe_dict["duration_s"] <= high_float:
        raise ValueError(f"[Error] {mp4_path} 長度 {probe_dict['duration_s']} 秒，不在 {low_float} ~ {high_float} 秒之間"
                         f"（config.json 的 part_1.5.duration_s={param_dict['duration_s']}、tolerance_s={param_dict['tolerance_s']}）")
    return {key_str: probe_dict[key_str] for key_str in ("width", "height", "fps", "frames", "duration_s")}


def check_same_frame_wh(ts_to_minute_dict: dict[str, dict]) -> WhType:
    ts_to_wh_dict = {ts_str: (minute_dict["width"], minute_dict["height"]) for ts_str, minute_dict in ts_to_minute_dict.items()}
    first_ts_str = next(iter(ts_to_wh_dict))
    for ts_str, frame_wh in ts_to_wh_dict.items():
        if frame_wh != ts_to_wh_dict[first_ts_str]:
            raise ValueError(f"[Error] 解析度不一致：{first_ts_str} 是 {ts_to_wh_dict[first_ts_str][0]}×{ts_to_wh_dict[first_ts_str][1]}，"
                             f"{ts_str} 是 {frame_wh[0]}×{frame_wh[1]}（四邊形只選一次，所有分鐘必須相同解析度）")
    return ts_to_wh_dict[first_ts_str]


def get_files_dict_from_stage_results(assets_dir_path: Path, ts_to_mp4_paths_dict: dict[str, list[Path]],
                                      ts_to_minute_dict: dict[str, dict], frame_wh: WhType) -> dict:
    return {"assets_dir": str(assets_dir_path.resolve()), "frame_size": list(frame_wh),
            "minutes": {ts_str: {"path": ts_to_mp4_paths_dict[ts_str][0].resolve().relative_to(assets_dir_path.resolve()).as_posix(),
                                 **minute_dict} for ts_str, minute_dict in ts_to_minute_dict.items()}}


def get_meta_dict_from_stage_results(args_ns: object, param_dict: dict, files_dict: dict) -> dict:
    duration_floats = [minute_dict["duration_s"] for minute_dict in files_dict["minutes"].values()]
    return {"kind": PART_STR, "start_min": args_ns.start_min, "end_min": args_ns.end_min, "params": param_dict,
            "inputs": {"assets_dir": files_dict["assets_dir"]}, "frame_size": files_dict["frame_size"],
            "stats": {"minutes": len(duration_floats), "duration_min_s": min(duration_floats),
                      "duration_max_s": max(duration_floats)},
            "created_at": get_now_str()}


def run_all_stages(argv_strs: list[str]) -> None:
    check_deps_are_available()
    args_ns = get_args_ns_from_argv_strs("part_1.5", USAGE_STR, argv_strs)
    manifest_dict = args_ns.manifest_dict
    config_dict = get_config_dict_from_path(manifest_dict["config_path"])
    param_dict = get_param_dict_from_config_dict(config_dict, "part_1.5", DEFAULT_PARAM_DICT, RULE_DICT_DICT)

    assets_dir_path = manifest_dict["assets_dir_path"]
    check_assets_dir_path(assets_dir_path)
    info(f"掃描 assets：{assets_dir_path}")
    ts_to_mp4_paths_dict = get_ts_to_mp4_paths_dict_from_assets_dir_path(assets_dir_path)
    ts_strs = sorted(ts_to_mp4_paths_dict)
    if ts_strs:
        info(f"找到 {len(ts_strs)} 個分鐘的 mp4，可用範圍 {ts_strs[0]} ~ {ts_strs[-1]}")
    check_range_in_ts_strs(args_ns.start_min, args_ns.end_min, ts_strs)
    minute_strs = get_minute_strs_from_range(args_ns.start_min, args_ns.end_min)
    check_each_minute_has_one_mp4(minute_strs, ts_to_mp4_paths_dict)
    info(f"範圍 {args_ns.start_min} ~ {args_ns.end_min}：{len(minute_strs)} 分鐘，每分鐘一個 mp4，檔案齊全")

    run_overwrite_prompt_stage(get_range_dir_path(manifest_dict, args_ns.start_min, args_ns.end_min))
    part_dir_path = get_part_dir_path(manifest_dict, args_ns.start_min, args_ns.end_min, PART_STR)
    run_prepare_part_dir_stage(part_dir_path)

    info(f"逐一檢查 mp4（長度 {param_dict['duration_s']}±{param_dict['tolerance_s']} 秒、可解碼）。網路硬碟會比較慢…")
    ts_to_minute_dict: dict[str, dict] = {}
    for index_int, ts_str in enumerate(minute_strs, start=1):
        minute_dict = get_minute_dict_from_mp4_path(ts_to_mp4_paths_dict[ts_str][0], param_dict)
        ts_to_minute_dict[ts_str] = minute_dict
        info(f"({index_int}/{len(minute_strs)}) {ts_str}  {minute_dict['width']}×{minute_dict['height']}  "
             f"{minute_dict['fps']} fps  {minute_dict['frames']} 幀  {minute_dict['duration_s']} 秒  OK")
    frame_wh = check_same_frame_wh(ts_to_minute_dict)
    info(f"所有 mp4 解析度一致：{frame_wh[0]}×{frame_wh[1]}")

    files_dict = get_files_dict_from_stage_results(assets_dir_path, ts_to_mp4_paths_dict, ts_to_minute_dict, frame_wh)
    save_json_obj_to_path(files_dict, part_dir_path / "files.json")
    save_json_obj_to_path(get_meta_dict_from_stage_results(args_ns, param_dict, files_dict), part_dir_path / "meta.json")
    success(f"part_1.5 完成：{len(minute_strs)} 分鐘全部合格。輸出：{part_dir_path}")


def main() -> None:
    run_main_stage(run_all_stages, sys.argv[1:])


if __name__ == "__main__":
    main()
