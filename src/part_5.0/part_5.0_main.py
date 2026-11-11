#!/usr/bin/env python3
from __future__ import annotations

import math
import json
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True

USAGE_STR = "part_5.0：以腹部圓心為中心、固定半徑，量測圓內的平均顏色（含灰階亮度與背景環對照）。每分鐘輸出一個 json（dict，key = 時間）。\n用法：python src/part_5.0/part_5.0_main.py MANIFEST_JSON START_MIN END_MIN"


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
    print_banner("part_5.0_main.py")

from tool_main import (NAN_FLOAT, WhType, XyType, check_deps_are_available, check_input_sha_in_meta_dict,
                       gen_index_sec_bgr_from_mp4_path, get_config_dict_from_path, get_count_dict_from_strs,
                       get_inputs_dict_from_part_strs, get_json_obj_from_path, get_meta_dict_from_part_dir,
                       cv2, get_minute_strs_from_range, get_now_str, get_param_dict_from_config_dict, get_part_dir_path,
                       is_xy_finite, np, run_prepare_part_dir_stage, save_json_obj_to_path)
from tool_manifest import (get_args_ns_from_argv_strs, info, run_main_stage, success)

PART_STR = "part_5.0"
DEFAULT_PARAM_DICT: dict = {
    "r": 3.0,
    "ring": [1.0, 3.0],
}
RULE_DICT_DICT: dict[str, dict] = {
    "r": {"type": "float", "min": 0, "min_open": True},
    "ring": {"type": "float_pair", "min": 0},
}


def check_r_float(r_float: float, rectified_wh: WhType) -> None:
    limit_float = min(rectified_wh) / 2
    if r_float > limit_float:
        raise ValueError(f"[Error] config.json 的 part_5.0.r={r_float} 太大：拉正後 {rectified_wh[0]}×{rectified_wh[1]}，半徑上限為 {limit_float}")


def get_entry_dict_list_from_minute_str(part_4_dir_path: Path, minute_str: str) -> list[dict]:
    entry_dict_list = get_json_obj_from_path(part_4_dir_path / f"{minute_str}.json", f"part_4.0 的 {minute_str}.json")
    if not (isinstance(entry_dict_list, list) and entry_dict_list
            and all(isinstance(entry_dict, dict) and isinstance(entry_dict.get("time"), str)
                    and isinstance(entry_dict.get("frame"), int) for entry_dict in entry_dict_list)):
        raise ValueError(f"[Error] part_4.0 的 {minute_str}.json 必須是非空的 list，且每筆都有字串 time 與整數 frame")
    if len({entry_dict["time"] for entry_dict in entry_dict_list}) != len(entry_dict_list):
        raise ValueError(f"[Error] part_4.0 的 {minute_str}.json 有重複的 time（無法當 dict 的 key）")
    return entry_dict_list


def get_nan_value_dict(r_float: float, status_str: str) -> dict:
    return {"mean": NAN_FLOAT, "std": NAN_FLOAT, "bg_mean": NAN_FLOAT, "contrast": NAN_FLOAT,
            "mean_b": NAN_FLOAT, "mean_g": NAN_FLOAT, "mean_r": NAN_FLOAT, "n_pixels": 0, "r": r_float, "status": status_str}


def get_window_tuple_from_xy(center_xy: XyType, radius_float: float, frame_wh: WhType) -> tuple[int, int, int, int]:
    return (max(0, math.floor(center_xy[0] - radius_float)), max(0, math.floor(center_xy[1] - radius_float)),
            min(frame_wh[0], math.floor(center_xy[0] + radius_float) + 1), min(frame_wh[1], math.floor(center_xy[1] + radius_float) + 1))


def get_inner_ring_mask_arr_tuple(window_tuple: tuple[int, int, int, int], center_xy: XyType, r_float: float,
                                  ring_floats: list[float]) -> tuple["np.ndarray", "np.ndarray"]:
    x0_int, y0_int, x1_int, y1_int = window_tuple
    grid_y_arr, grid_x_arr = np.mgrid[y0_int:y1_int, x0_int:x1_int]
    dist_arr = np.hypot(grid_x_arr - center_xy[0], grid_y_arr - center_xy[1])
    return dist_arr <= r_float, (dist_arr > r_float + ring_floats[0]) & (dist_arr <= r_float + ring_floats[1])


def get_value_dict_from_bgr_arr(bgr_arr: "np.ndarray", body_xy: XyType, param_dict: dict) -> dict:
    gray_arr = cv2.cvtColor(bgr_arr, cv2.COLOR_BGR2GRAY)
    frame_wh = (gray_arr.shape[1], gray_arr.shape[0])
    window_tuple = get_window_tuple_from_xy(body_xy, param_dict["r"] + param_dict["ring"][1], frame_wh)
    if window_tuple[2] <= window_tuple[0] or window_tuple[3] <= window_tuple[1]:
        return get_nan_value_dict(param_dict["r"], "no_pixels")
    inner_arr, ring_arr = get_inner_ring_mask_arr_tuple(window_tuple, body_xy, param_dict["r"], param_dict["ring"])
    sub_arr = gray_arr[window_tuple[1]:window_tuple[3], window_tuple[0]:window_tuple[2]]
    n_pixels_int = int(inner_arr.sum())
    if n_pixels_int == 0:
        return get_nan_value_dict(param_dict["r"], "no_pixels")
    value_arr = sub_arr[inner_arr].astype(np.float64)
    mean_bgr_arr = bgr_arr[window_tuple[1]:window_tuple[3], window_tuple[0]:window_tuple[2]][inner_arr].astype(np.float64).mean(axis=0)
    mean_float = float(value_arr.mean())
    bg_float = float(sub_arr[ring_arr].mean()) if ring_arr.any() else NAN_FLOAT
    return {"mean": round(mean_float, 3), "std": round(float(value_arr.std()), 3),
            "bg_mean": round(bg_float, 3) if not math.isnan(bg_float) else NAN_FLOAT,
            "contrast": round(bg_float - mean_float, 3) if not math.isnan(bg_float) else NAN_FLOAT,
            "mean_b": round(float(mean_bgr_arr[0]), 3), "mean_g": round(float(mean_bgr_arr[1]), 3), "mean_r": round(float(mean_bgr_arr[2]), 3),
            "n_pixels": n_pixels_int, "r": param_dict["r"], "status": "ok"}


def run_minute_stage(minute_str: str, mp4_path: Path, entry_dict_list: list[dict], param_dict: dict) -> dict[str, dict]:
    frame_to_entry_dict = {entry_dict["frame"]: entry_dict for entry_dict in entry_dict_list}
    time_to_value_dict: dict[str, dict] = {}
    for index_int, _, bgr_arr in gen_index_sec_bgr_from_mp4_path(mp4_path):
        if index_int not in frame_to_entry_dict:
            continue
        entry_dict = frame_to_entry_dict[index_int]
        if not is_xy_finite(entry_dict.get("body")):
            raise ValueError(f"[Error] part_4.0 的 {minute_str}.json 第 {index_int} 幀的 body 不是有限的座標：{entry_dict.get('body')}")
        time_to_value_dict[entry_dict["time"]] = {
            **get_value_dict_from_bgr_arr(bgr_arr, tuple(entry_dict["body"]), param_dict),
            "body_status": entry_dict.get("body_status"), "frame": index_int, "body": entry_dict["body"]}
        if len(time_to_value_dict) == len(frame_to_entry_dict):
            break
    if len(time_to_value_dict) != len(frame_to_entry_dict):
        raise ValueError(f"[Error] {mp4_path} 解碼不出 part_4.0 的 {minute_str}.json 需要的所有幀（缺 {len(frame_to_entry_dict) - len(time_to_value_dict)} 幀）")
    return {entry_dict["time"]: time_to_value_dict[entry_dict["time"]] for entry_dict in entry_dict_list}


def get_meta_dict_from_stage_results(args_ns: object, manifest_dict: dict, param_dict: dict,
                                     ts_to_stat_dict: dict[str, dict]) -> dict:
    return {"kind": PART_STR, "start_min": args_ns.start_min, "end_min": args_ns.end_min,
            "params": {**param_dict, "unit": "拉正後影格像素；顏色與亮度 = 0~255（mean = 灰階；mean_b / mean_g / mean_r = 圓內各通道平均）"},
            "inputs": get_inputs_dict_from_part_strs(manifest_dict, args_ns.start_min, args_ns.end_min, ["part_2.5", "part_4.0"]),
            "minutes": ts_to_stat_dict, "created_at": get_now_str()}


def run_all_stages(argv_strs: list[str]) -> None:
    check_deps_are_available()
    args_ns = get_args_ns_from_argv_strs("part_5.0", USAGE_STR, argv_strs)
    manifest_dict = args_ns.manifest_dict
    config_dict = get_config_dict_from_path(manifest_dict["config_path"])
    param_dict = get_param_dict_from_config_dict(config_dict, PART_STR, DEFAULT_PARAM_DICT, RULE_DICT_DICT)

    meta_2_5_dict = get_meta_dict_from_part_dir(manifest_dict, args_ns.start_min, args_ns.end_min, "part_2.5")
    meta_4_dict = get_meta_dict_from_part_dir(manifest_dict, args_ns.start_min, args_ns.end_min, "part_4.0")
    check_input_sha_in_meta_dict(meta_4_dict, "part_2.5", manifest_dict, args_ns.start_min, args_ns.end_min)
    check_input_sha_in_meta_dict(meta_4_dict, "part_3.0", manifest_dict, args_ns.start_min, args_ns.end_min)
    check_r_float(param_dict["r"], (meta_2_5_dict["rectified_size"][0], meta_2_5_dict["rectified_size"][1]))

    minute_strs = get_minute_strs_from_range(args_ns.start_min, args_ns.end_min)
    in_dir_path = get_part_dir_path(manifest_dict, args_ns.start_min, args_ns.end_min, "part_2.5") / "mp4s"
    part_4_dir_path = get_part_dir_path(manifest_dict, args_ns.start_min, args_ns.end_min, "part_4.0")
    out_dir_path = get_part_dir_path(manifest_dict, args_ns.start_min, args_ns.end_min, PART_STR)
    run_prepare_part_dir_stage(out_dir_path)
    ts_to_stat_dict: dict[str, dict] = {}
    for index_int, ts_str in enumerate(minute_strs, start=1):
        entry_dict_list = get_entry_dict_list_from_minute_str(part_4_dir_path, ts_str)
        time_to_value_dict = run_minute_stage(ts_str, in_dir_path / f"{ts_str}.mp4", entry_dict_list, param_dict)
        save_json_obj_to_path(time_to_value_dict, out_dir_path / f"{ts_str}.json")
        ts_to_stat_dict[ts_str] = {"entries": len(time_to_value_dict),
                                   "by_status": get_count_dict_from_strs([value_dict["status"] for value_dict in time_to_value_dict.values()]),
                                   "by_body_status": get_count_dict_from_strs([str(value_dict["body_status"]) for value_dict in time_to_value_dict.values()])}
        info(f"({index_int}/{len(minute_strs)}) {ts_str}  {len(time_to_value_dict)} 筆  {ts_to_stat_dict[ts_str]['by_status']}")

    save_json_obj_to_path(get_meta_dict_from_stage_results(args_ns, manifest_dict, param_dict, ts_to_stat_dict), out_dir_path / "meta.json")
    success(f"part_5.0 完成：{len(minute_strs)} 個分鐘的 json。輸出：{out_dir_path}")


def main() -> None:
    run_main_stage(run_all_stages, sys.argv[1:])


if __name__ == "__main__":
    main()
