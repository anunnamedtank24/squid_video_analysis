#!/usr/bin/env python3
from __future__ import annotations

import bisect
import json
import os
import sys
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

sys.dont_write_bytecode = True

USAGE_STR = "part_3.5：把 part_3.0 的追蹤結果畫回拉正後的影片，讓人用眼睛檢查。每分鐘一個 mp4。\n用法：python src/part_3.5/part_3.5_main.py MANIFEST_JSON START_MIN END_MIN"


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
    print_banner("part_3.5_main.py")

from tool_main import (WhType, check_deps_are_available, check_input_sha_in_meta_dict, cv2, get_config_dict_from_path,
                       get_inputs_dict_from_part_strs, get_json_obj_from_path, get_meta_dict_from_part_dir,
                       get_minute_strs_from_range, get_now_str, get_param_dict_from_config_dict, get_part_dir_path,
                       is_finite_num, is_xy_finite, np, run_encode_mp4_stage, run_prepare_part_dir_stage,
                       save_json_obj_to_path)
from tool_manifest import (get_args_ns_from_argv_strs, info, run_main_stage, success, warn)

PART_STR = "part_3.5"
KEY_STR_TUPLE = ("right_eye", "left_eye", "body")
KEY_TO_BGR_DICT = {"right_eye": (0, 0, 255), "left_eye": (255, 150, 0), "body": (0, 210, 0)}
PREDICTED_BGR_TUPLE = (255, 0, 255)
SEARCH_BOX_BGR_TUPLE = (0, 255, 255)
ZONE_BGR_TUPLE = (0, 140, 255)
X264_CRF_STR = "18"
MPEG4_QSCALE_STR = "3"
MAX_OUT_SIDE_INT = 8192
SHIFT_INT = 4
LABEL_OUTLINE_OFFSET_TUPLE = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
DEFAULT_PARAM_DICT: dict = {
    "rmul": 1.2,
    "radd": 1.0,
    "scale": 4,
    "thickness_tracked": 2,
    "thickness_hold": 1,
    "thickness_zone": 1,
}
RULE_DICT_DICT: dict[str, dict] = {
    "rmul": {"type": "float", "min": 0, "min_open": True},
    "radd": {"type": "float", "min": 0},
    "scale": {"type": "int", "min": 1, "max": 32},
    "thickness_tracked": {"type": "int", "min": 1, "max": 10},
    "thickness_hold": {"type": "int", "min": 1, "max": 10},
    "thickness_zone": {"type": "int", "min": 1, "max": 10},
}


def check_out_wh_is_valid(rectified_wh: WhType, up_int: int) -> None:
    if max(rectified_wh) * up_int > MAX_OUT_SIDE_INT:
        raise ValueError(f"[Error] 放大 ×{up_int} 後影片會是 {rectified_wh[0] * up_int}×{rectified_wh[1] * up_int}，超過單邊 {MAX_OUT_SIDE_INT}；"
                         f"請調低 config.json 的 part_3.5.scale（part_2.5 的 mp4 是 {rectified_wh[0]}×{rectified_wh[1]}）")


def get_minute_strs_from_meta_dict(meta_3_dict: dict, minute_strs: list[str]) -> list[str]:
    status_str = meta_3_dict.get("status")
    failed_dict = meta_3_dict.get("failed") or {}
    failed_only_bool = bool(failed_dict.get("last_good")) and failed_dict.get("minute") in minute_strs \
        and failed_dict["minute"] not in meta_3_dict.get("minutes", {})
    done_strs = [ts_str for ts_str in minute_strs if ts_str in meta_3_dict.get("minutes", {})
                 or (failed_only_bool and ts_str == failed_dict["minute"])]
    if status_str != "complete":
        warn(f"part_3.0 的 status={status_str!r}（不是 complete）：只畫已有結果的 {len(done_strs)}/{len(minute_strs)} 個分鐘。"
             + (f"失敗在 {failed_dict.get('minute')}{'' if failed_dict.get('frame') is None else ' 第 ' + str(failed_dict['frame']) + ' 幀'}：{str(failed_dict.get('error')).removeprefix('[Error] ')}" if failed_dict else
                "（可能還在跑，或被強制結束）"))
    if not done_strs:
        raise ValueError(f"[Error] part_3.0 還沒有任何分鐘的結果可畫（status={status_str!r}）"
                         + (f"。失敗原因：{str(meta_3_dict['failed'].get('error')).removeprefix('[Error] ')}" if meta_3_dict.get("failed") else ""))
    return done_strs


def get_entry_dict_list_from_minute_str(part_3_dir_path: Path, minute_str: str, frame_count_int: int,
                                        complete_bool: bool, has_json_bool: bool) -> list[dict]:
    if not has_json_bool:
        return []
    entry_dict_list = get_json_obj_from_path(part_3_dir_path / f"{minute_str}.json", f"part_3.0 的 {minute_str}.json")
    if not (isinstance(entry_dict_list, list) and entry_dict_list
            and all(isinstance(entry_dict, dict) and isinstance(entry_dict.get("frame"), int) for entry_dict in entry_dict_list)):
        raise ValueError(f"[Error] part_3.0 的 {minute_str}.json 必須是非空的 list，且每筆都有整數 frame")
    frame_ints = [entry_dict["frame"] for entry_dict in entry_dict_list]
    if frame_ints != sorted(set(frame_ints)) or frame_ints[-1] >= frame_count_int or (complete_bool and frame_ints[0] != 0):
        raise ValueError(f"[Error] part_3.0 的 {minute_str}.json 的 frame 必須遞增不重複、小於影片幀數 {frame_count_int}"
                         + ("、且由 0 開始" if complete_bool else "（這分鐘是 part_3.0 失敗前的部分結果，不要求由 0 開始）"))
    return entry_dict_list


def get_entry_dict_or_none_and_mode_str_from_index(index_int: int, frame_to_entry_dict: dict[int, dict], frame_ints: list[int],
                                                   entry_dict_list: list[dict],
                                                   range_tuple: tuple[int, int]) -> tuple[dict | None, str, bool]:
    if not entry_dict_list or not range_tuple[0] <= index_int <= range_tuple[1]:
        return None, "no part_3.0 result", False
    if index_int in frame_to_entry_dict:
        entry_dict = frame_to_entry_dict[index_int]
        return entry_dict, f"tracked:{entry_dict['kind']}", False
    held_dict = entry_dict_list[max(0, bisect.bisect_left(frame_ints, index_int) - 1)]
    return held_dict, f"hold({held_dict['time'][11:]})", True


def get_circle_args_tuple_or_none(entry_dict: dict, key_str: str, up_int: int,
                                  param_dict: dict) -> tuple[tuple[int, int], int] | None:
    center_xy, r_float = entry_dict.get(key_str), entry_dict.get(key_str + "_r")
    if not (is_xy_finite(center_xy) and is_finite_num(r_float)):
        return None
    center_x_float, center_y_float = (center_xy[0] + 0.5) * up_int - 0.5, (center_xy[1] + 0.5) * up_int - 0.5
    radius_float = (r_float * param_dict["rmul"] + param_dict["radd"]) * up_int
    return (int(round(center_x_float * 16)), int(round(center_y_float * 16))), int(round(radius_float * 16))


def get_bgr_tuple_from_key_str(entry_dict: dict, key_str: str) -> tuple[int, int, int]:
    if key_str == "body" and entry_dict.get("body_status") == "predicted":
        return PREDICTED_BGR_TUPLE
    return KEY_TO_BGR_DICT[key_str]


def draw_entry_on_arr(bgr_arr: "np.ndarray", entry_dict: dict, up_int: int, thickness_int: int, param_dict: dict) -> None:
    for key_str in KEY_STR_TUPLE:
        circle_tuple = get_circle_args_tuple_or_none(entry_dict, key_str, up_int, param_dict)
        if circle_tuple is not None:
            cv2.circle(bgr_arr, circle_tuple[0], circle_tuple[1], get_bgr_tuple_from_key_str(entry_dict, key_str), thickness_int,
                       cv2.LINE_AA, SHIFT_INT)


def draw_zone_on_arr(bgr_arr: "np.ndarray", zone_floats: list[float], up_int: int, thickness_int: int) -> None:
    center_x_float, center_y_float = (zone_floats[0] + 0.5) * up_int - 0.5, (zone_floats[1] + 0.5) * up_int - 0.5
    center_tuple = (int(round(center_x_float * 16)), int(round(center_y_float * 16)))
    axes_tuple = (int(round(zone_floats[2] * up_int * 16)), int(round(zone_floats[3] * up_int * 16)))
    cv2.ellipse(bgr_arr, center_tuple, axes_tuple, zone_floats[4], 0, 360, ZONE_BGR_TUPLE, thickness_int, cv2.LINE_AA, SHIFT_INT)


def draw_search_box_on_arr(bgr_arr: "np.ndarray", box_floats: list[float], up_int: int, thickness_int: int) -> None:
    x0_int, y0_int, x1_int, y1_int = (int(round((value_float + 0.5) * up_int - 0.5)) for value_float in box_floats)
    cv2.rectangle(bgr_arr, (x0_int, y0_int), (x1_int, y1_int), SEARCH_BOX_BGR_TUPLE, thickness_int, cv2.LINE_AA)


def draw_gate_on_arr(bgr_arr: "np.ndarray", last_good_dict: dict, up_int: int, thickness_int: int) -> None:
    gate_px_float = last_good_dict["gate_px"]
    for key_str in ("right_eye", "left_eye"):
        center_xy = last_good_dict.get(key_str)
        if not is_xy_finite(center_xy):
            continue
        center_x_float, center_y_float = (center_xy[0] + 0.5) * up_int - 0.5, (center_xy[1] + 0.5) * up_int - 0.5
        center_tuple = (int(round(center_x_float * 16)), int(round(center_y_float * 16)))
        cv2.circle(bgr_arr, center_tuple, int(round(gate_px_float * up_int * 16)), SEARCH_BOX_BGR_TUPLE, thickness_int,
                   cv2.LINE_AA, SHIFT_INT)


def draw_label_on_arr(bgr_arr: "np.ndarray", text_str: str, up_int: int) -> None:
    font_scale_float = max(0.5, 0.15 * up_int)
    thick_int = 1 if font_scale_float < 1.0 else 2
    org_tuple = (4, int(14 + 6 * font_scale_float))
    for dx_int, dy_int in LABEL_OUTLINE_OFFSET_TUPLE:
        cv2.putText(bgr_arr, text_str, (org_tuple[0] + dx_int, org_tuple[1] + dy_int), cv2.FONT_HERSHEY_SIMPLEX, font_scale_float,
                    (0, 0, 0), thick_int, cv2.LINE_AA)
    cv2.putText(bgr_arr, text_str, org_tuple, cv2.FONT_HERSHEY_SIMPLEX, font_scale_float, (255, 255, 255), thick_int, cv2.LINE_AA)


def get_clock_str_from_minute_str(minute_str: str, sec_float: float) -> str:
    time_dt = datetime.strptime(minute_str, "%Y%m%d%H%M") + timedelta(milliseconds=int(round(sec_float * 1000)))
    return time_dt.strftime("%H:%M:%S.") + f"{time_dt.microsecond // 1000:03d}"


def get_range_tuple_from_entry_dict_list(entry_dict_list: list[dict], failed_frame_int: int | None,
                                         frame_count_int: int, complete_bool: bool) -> tuple[int, int]:
    if complete_bool:
        return 0, frame_count_int - 1
    frame_ints = [entry_dict["frame"] for entry_dict in entry_dict_list] + ([] if failed_frame_int is None else [failed_frame_int])
    return min(frame_ints), max(frame_ints)


def get_convert_func_from_entry_dict_list(minute_str: str, entry_dict_list: list[dict], out_wh: WhType, up_int: int,
                                          param_dict: dict, range_tuple: tuple[int, int],
                                          failed_dict: dict | None) -> Callable[[int, float, "np.ndarray"], "np.ndarray"]:
    frame_to_entry_dict = {entry_dict["frame"]: entry_dict for entry_dict in entry_dict_list}
    frame_ints = [entry_dict["frame"] for entry_dict in entry_dict_list]
    failed_frame_int = None if failed_dict is None else failed_dict.get("frame")

    def get_drawn_arr_from_bgr_arr(index_int: int, sec_float: float, bgr_arr: "np.ndarray") -> "np.ndarray":
        up_arr = bgr_arr
        if up_int > 1:
            up_arr = cv2.resize(bgr_arr, (bgr_arr.shape[1] * up_int, bgr_arr.shape[0] * up_int), interpolation=cv2.INTER_NEAREST)
        up_arr = np.ascontiguousarray(up_arr[:out_wh[1], :out_wh[0]])
        entry_dict, mode_str, held_bool = get_entry_dict_or_none_and_mode_str_from_index(
            index_int, frame_to_entry_dict, frame_ints, entry_dict_list, range_tuple)
        extra_str = ""
        if failed_frame_int is not None and index_int == failed_frame_int:
            last_good_dict = failed_dict["last_good"]
            if index_int not in frame_to_entry_dict and last_good_dict is not None:
                entry_dict, held_bool = {**last_good_dict, "body_status": "none"}, True
                if last_good_dict.get("gate_px"):
                    draw_gate_on_arr(up_arr, last_good_dict, up_int, param_dict["thickness_tracked"])
                    extra_str = "  FAILED: eyes not found (colored circle = last good, yellow circle = allowed move range)"
                else:
                    if last_good_dict.get("search_box"):
                        draw_search_box_on_arr(up_arr, last_good_dict["search_box"], up_int, param_dict["thickness_tracked"])
                    extra_str = "  FAILED: eyes not found (circle = last good, yellow box = search area)"
            else:
                extra_str = "  FAILED: found here but does not match the previous frame (boundary check)"
            mode_str = "failed"
        if entry_dict is not None and entry_dict.get("body_zone"):
            draw_zone_on_arr(up_arr, entry_dict["body_zone"], up_int, param_dict["thickness_zone"])
        if entry_dict is not None:
            draw_entry_on_arr(up_arr, entry_dict, up_int, param_dict["thickness_hold" if held_bool else "thickness_tracked"], param_dict)
        predicted_str = "  belly predicted" if entry_dict is not None and entry_dict.get("body_status") == "predicted" else ""
        draw_label_on_arr(up_arr, f"{get_clock_str_from_minute_str(minute_str, sec_float)}  {mode_str}{predicted_str}{extra_str}", up_int)
        return up_arr
    return get_drawn_arr_from_bgr_arr


def run_minute_stage(minute_str: str, in_mp4_path: Path, out_mp4_path: Path, entry_dict_list: list[dict], out_wh: WhType,
                     up_int: int, param_dict: dict, range_tuple: tuple[int, int], failed_dict: dict | None) -> dict:
    stat_dict = run_encode_mp4_stage(in_mp4_path, out_mp4_path, out_wh,
                                     get_convert_func_from_entry_dict_list(minute_str, entry_dict_list, out_wh, up_int, param_dict,
                                                                           range_tuple, failed_dict),
                                     X264_CRF_STR, MPEG4_QSCALE_STR)
    return {**stat_dict, "frames_with_part_3_entry": len(entry_dict_list),
            "frames_hold": range_tuple[1] - range_tuple[0] + 1 - len(entry_dict_list)}


def run_all_stages(argv_strs: list[str]) -> None:
    check_deps_are_available()
    args_ns = get_args_ns_from_argv_strs("part_3.5", USAGE_STR, argv_strs)
    manifest_dict = args_ns.manifest_dict
    config_dict = get_config_dict_from_path(manifest_dict["config_path"])
    param_dict = get_param_dict_from_config_dict(config_dict, PART_STR, DEFAULT_PARAM_DICT, RULE_DICT_DICT)

    meta_2_5_dict = get_meta_dict_from_part_dir(manifest_dict, args_ns.start_min, args_ns.end_min, "part_2.5")
    meta_3_dict = get_meta_dict_from_part_dir(manifest_dict, args_ns.start_min, args_ns.end_min, "part_3.0")
    check_input_sha_in_meta_dict(meta_3_dict, "part_2.5", manifest_dict, args_ns.start_min, args_ns.end_min)
    rectified_wh = (meta_2_5_dict["rectified_size"][0], meta_2_5_dict["rectified_size"][1])
    up_int = param_dict["scale"]
    check_out_wh_is_valid(rectified_wh, up_int)
    out_wh = (rectified_wh[0] * up_int) // 2 * 2, (rectified_wh[1] * up_int) // 2 * 2
    info(f"拉正後 {rectified_wh[0]}×{rectified_wh[1]} → 輸出 {out_wh[0]}×{out_wh[1]}（×{up_int}）；圓半徑 = r×{param_dict['rmul']} + {param_dict['radd']}")

    minute_strs = get_minute_strs_from_range(args_ns.start_min, args_ns.end_min)
    draw_minute_strs = get_minute_strs_from_meta_dict(meta_3_dict, minute_strs)
    failed_dict = meta_3_dict.get("failed")
    in_dir_path = get_part_dir_path(manifest_dict, args_ns.start_min, args_ns.end_min, "part_2.5") / "mp4s"
    part_3_dir_path = get_part_dir_path(manifest_dict, args_ns.start_min, args_ns.end_min, "part_3.0")
    out_dir_path = get_part_dir_path(manifest_dict, args_ns.start_min, args_ns.end_min, PART_STR)
    run_prepare_part_dir_stage(out_dir_path)
    (out_dir_path / "mp4s").mkdir()
    ts_to_stat_dict: dict[str, dict] = {}
    for index_int, ts_str in enumerate(draw_minute_strs, start=1):
        frame_count_int = meta_2_5_dict["minutes"][ts_str]["frames"]
        has_json_bool = ts_str in meta_3_dict["minutes"]
        complete_bool = has_json_bool and bool(meta_3_dict["minutes"][ts_str].get("complete"))
        minute_failed_dict = failed_dict if (failed_dict and failed_dict.get("minute") == ts_str) else None
        entry_dict_list = get_entry_dict_list_from_minute_str(part_3_dir_path, ts_str, frame_count_int, complete_bool, has_json_bool)
        range_tuple = get_range_tuple_from_entry_dict_list(entry_dict_list, None if minute_failed_dict is None else minute_failed_dict.get("frame"),
                                                           frame_count_int, complete_bool)
        stat_dict = run_minute_stage(ts_str, in_dir_path / f"{ts_str}.mp4", out_dir_path / "mp4s" / f"{ts_str}.mp4", entry_dict_list,
                                     out_wh, up_int, param_dict, range_tuple, minute_failed_dict)
        ts_to_stat_dict[ts_str] = {**stat_dict, "part_3_complete": complete_bool, "drawn_frame_range": list(range_tuple)}
        info(f"({index_int}/{len(draw_minute_strs)}) {ts_str}  {stat_dict['frames']} 幀（有 part_3.0 結果 {stat_dict['frames_with_part_3_entry']}、"
             f"沿用 {stat_dict['frames_hold']}）"
             + ("" if complete_bool else f"【part_3.0 失敗前的部分結果，只畫第 {range_tuple[0]}~{range_tuple[1]} 幀】")
             + f"→ mp4s/{ts_str}.mp4")

    save_json_obj_to_path({"kind": PART_STR, "start_min": args_ns.start_min, "end_min": args_ns.end_min,
                           "params": {**param_dict, "colors_bgr": {**KEY_TO_BGR_DICT, "body_predicted": PREDICTED_BGR_TUPLE,
                                                                   "search_box": SEARCH_BOX_BGR_TUPLE, "body_zone": ZONE_BGR_TUPLE},
                                      "radius_formula": "畫的半徑 = 追蹤半徑 × rmul + radd（拉正後像素）"},
                           "inputs": get_inputs_dict_from_part_strs(manifest_dict, args_ns.start_min, args_ns.end_min,
                                                                    ["part_2.5", "part_3.0"]),
                           "part_3_status": meta_3_dict.get("status"), "part_3_failed": failed_dict,
                           "skipped_minutes": [ts_str for ts_str in minute_strs if ts_str not in ts_to_stat_dict],
                           "rectified_size": list(rectified_wh), "out_size": list(out_wh), "minutes": ts_to_stat_dict,
                           "created_at": get_now_str()}, out_dir_path / "meta.json")
    success(f"part_3.5 完成：{len(draw_minute_strs)}/{len(minute_strs)} 個影片（part_3.0 status={meta_3_dict.get('status')}）。輸出：{out_dir_path}/mp4s/")


def main() -> None:
    run_main_stage(run_all_stages, sys.argv[1:])


if __name__ == "__main__":
    main()
