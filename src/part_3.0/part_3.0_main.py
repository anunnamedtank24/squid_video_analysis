#!/usr/bin/env python3
from __future__ import annotations

import math
import json
import os
import sys
import time
from itertools import combinations
from pathlib import Path

sys.dont_write_bytecode = True

USAGE_STR = "part_3.0：在拉正後的 mp4 上追蹤烏賊的「右眼、左眼」，每個點輸出圓心與半徑。一分鐘輸出一個 json。\n用法：python src/part_3.0/part_3.0_main.py MANIFEST_JSON START_MIN END_MIN"


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
    print_banner("part_3.0_main.py")

from tool_main import (BLOB_DEFAULT_DICT, BLOB_RULE_DICT_DICT, NAN_FLOAT, WhType, XyType, XyrType, XyrzType,
                       check_blob_param_dict, check_deps_are_available, check_input_sha_in_meta_dict, gen_index_sec_gray_from_mp4_path,
                       get_config_dict_from_path, get_count_dict_from_strs,
                       get_scale_msg_str_from_param_dict,
                       get_fit_xyr_method_tuple_from_img_arr, get_img_arr_from_gray_arr,
                       get_inputs_dict_from_part_strs, get_json_obj_from_path, get_meta_dict_from_part_dir,
                       get_minute_strs_from_range, get_now_str, get_param_dict_from_config_dict, get_part_dir_path, get_seed_dict_from_part_dir,
                       get_sec_floats_from_mp4_path, get_time_str_from_minute_str, get_xyrz_list_from_img_arr,
                       is_finite_num, np, run_prepare_part_dir_stage, save_json_obj_to_path)
from tool_manifest import (get_args_ns_from_argv_strs, info, run_main_stage, success, warn)

PART_STR = "part_3.0"
TRACK_DEFAULT_DICT: dict = {
    "sample_step_s": 10.0,
    "move_tol_px": 1.5,
    "sample_search_mul": 3.0,
    "frame_search_mul": 1.0,
    "spacing_tol": 0.5,
    "retry_frames": 9,
    "move_weight": 4.0,
    "eye_r_ratio": [0.3, 3.0],
    "eye_k_z": 7.0,
    "size_ratio_max": 3.0,
    "eye_gap": 1.2,
    "eye_z_ratio_min": 0.2,
}
TRACK_RULE_DICT_DICT: dict[str, dict] = {
    "sample_step_s": {"type": "float", "min": 0, "min_open": True},
    "move_tol_px": {"type": "float", "min": 0, "min_open": True},
    "sample_search_mul": {"type": "float", "min": 0, "min_open": True},
    "frame_search_mul": {"type": "float", "min": 0, "min_open": True},
    "spacing_tol": {"type": "float", "min": 0, "max": 5},
    "retry_frames": {"type": "int", "min": 0, "max": 100},
    "move_weight": {"type": "float", "min": 0},
    "eye_r_ratio": {"type": "float_pair", "min": 0, "min_open": True},
    "eye_k_z": {"type": "float", "min": 0, "min_open": True},
    "size_ratio_max": {"type": "float", "min": 1},
    "eye_gap": {"type": "float", "min": 0},
    "eye_z_ratio_min": {"type": "float", "min": 0, "max": 1},
}
DEFAULT_PARAM_DICT: dict = {**BLOB_DEFAULT_DICT, **TRACK_DEFAULT_DICT}
RULE_DICT_DICT: dict[str, dict] = {**BLOB_RULE_DICT_DICT, **TRACK_RULE_DICT_DICT}


class TrackError(ValueError):

    def __init__(self, msg_str: str, frame_int: int, last_good_dict: dict) -> None:
        super().__init__(msg_str)
        self.frame_int = frame_int
        self.last_good_dict = last_good_dict


def get_state_dict_from_xyrs(right_xyr: XyrType, left_xyr: XyrType, ref_dict: dict | None = None, z_float: float = 0.0) -> dict:
    d_float = math.dist(right_xyr[:2], left_xyr[:2])
    return {"right": tuple(right_xyr), "left": tuple(left_xyr), "d": d_float,
            "ref": {"d": d_float} if ref_dict is None else ref_dict, "z": z_float}


def get_state_dict_from_entry_dict(entry_dict: dict, ref_dict: dict | None = None) -> dict:
    return get_state_dict_from_xyrs((*entry_dict["right_eye"], entry_dict["right_eye_r"]),
                                    (*entry_dict["left_eye"], entry_dict["left_eye_r"]), ref_dict, entry_dict.get("eye_z", 0.0))


def get_sample_index_ints_from_sec_floats(sec_floats: list[float], step_float: float) -> list[int]:
    index_set = {0, len(sec_floats) - 1}
    target_float = step_float
    while target_float <= sec_floats[-1]:
        index_set.add(min(range(len(sec_floats)), key=lambda index_int: abs(sec_floats[index_int] - target_float)))
        target_float += step_float
    return sorted(index_set)


def get_search_xyxy_from_state_dict(state_dict: dict, mul_float: float, img_wh: WhType) -> tuple[int, int, int, int]:
    mid_x_float = (state_dict["right"][0] + state_dict["left"][0]) / 2
    mid_y_float = (state_dict["right"][1] + state_dict["left"][1]) / 2
    half_float = (mul_float + 0.5) * state_dict["d"]
    return (max(0, int(math.floor(mid_x_float - half_float))), max(0, int(math.floor(mid_y_float - half_float))),
            min(img_wh[0], int(math.ceil(mid_x_float + half_float)) + 1), min(img_wh[1], int(math.ceil(mid_y_float + half_float)) + 1))


def is_eye_pair_valid(xyrz_1: XyrzType, xyrz_2: XyrzType, state_dict: dict, param_dict: dict) -> bool:
    if min(xyrz_1[3], xyrz_2[3]) < max(param_dict["eye_k_z"], param_dict["eye_z_ratio_min"] * state_dict["z"]):
        return False
    if max(xyrz_1[2], xyrz_2[2]) / min(xyrz_1[2], xyrz_2[2]) > param_dict["size_ratio_max"]:
        return False
    dist_float = math.dist(xyrz_1[:2], xyrz_2[:2])
    if dist_float < param_dict["eye_gap"] * (xyrz_1[2] + xyrz_2[2]):
        return False
    return abs(dist_float - state_dict["ref"]["d"]) <= param_dict["spacing_tol"] * state_dict["ref"]["d"]


def get_assigned_tuple_from_xyrzs(xyrz_1: XyrzType, xyrz_2: XyrzType, state_dict: dict) -> tuple[XyrzType, XyrzType, float]:
    same_float = math.dist(xyrz_1[:2], state_dict["right"][:2]) + math.dist(xyrz_2[:2], state_dict["left"][:2])
    swap_float = math.dist(xyrz_2[:2], state_dict["right"][:2]) + math.dist(xyrz_1[:2], state_dict["left"][:2])
    return (xyrz_1, xyrz_2, same_float / 2) if same_float <= swap_float else (xyrz_2, xyrz_1, swap_float / 2)


def get_pair_score_float(right_xyrz: XyrzType, left_xyrz: XyrzType, cost_float: float, state_dict: dict,
                         param_dict: dict) -> float:
    z_cap_float = param_dict["z_cap"]
    ratio_float = max(right_xyrz[2], left_xyrz[2]) / min(right_xyrz[2], left_xyrz[2])
    return ((min(right_xyrz[3], z_cap_float) + min(left_xyrz[3], z_cap_float)) / 2 - 2.0 * math.log(ratio_float)
            - param_dict["move_weight"] * cost_float / state_dict["d"])


def get_eye_dict_or_none_from_img_arr(img_arr: "np.ndarray", state_dict: dict, mul_float: float,
                                      param_dict: dict) -> dict | None:
    region_tuple = get_search_xyxy_from_state_dict(state_dict, mul_float, (img_arr.shape[1], img_arr.shape[0]))
    ref_r_float = (state_dict["right"][2] + state_dict["left"][2]) / 2
    low_float, high_float = param_dict["eye_r_ratio"][0] * ref_r_float, param_dict["eye_r_ratio"][1] * ref_r_float
    xyrz_list = [xyrz for xyrz in get_xyrz_list_from_img_arr(img_arr, region_tuple, param_dict, param_dict["k_z"])
                 if low_float <= xyrz[2] <= high_float]
    best_tuple = None
    for xyrz_1, xyrz_2 in combinations(xyrz_list, 2):
        if not is_eye_pair_valid(xyrz_1, xyrz_2, state_dict, param_dict):
            continue
        right_xyrz, left_xyrz, cost_float = get_assigned_tuple_from_xyrzs(xyrz_1, xyrz_2, state_dict)
        score_float = get_pair_score_float(right_xyrz, left_xyrz, cost_float, state_dict, param_dict)
        if best_tuple is None or score_float > best_tuple[0]:
            best_tuple = (score_float, right_xyrz, left_xyrz)
    if best_tuple is None:
        return None
    score_float, right_xyrz, left_xyrz = best_tuple
    gap_float = math.dist(right_xyrz[:2], left_xyrz[:2])
    right_xyr, right_method_str = get_fit_xyr_method_tuple_from_img_arr(
        img_arr, right_xyrz[:3], min(param_dict["fit_rmax_mul"] * right_xyrz[2], 0.85 * gap_float), param_dict)
    left_xyr, left_method_str = get_fit_xyr_method_tuple_from_img_arr(
        img_arr, left_xyrz[:3], min(param_dict["fit_rmax_mul"] * left_xyrz[2], 0.85 * gap_float), param_dict)
    return {"right": right_xyr, "left": left_xyr, "score": score_float, "z": min(right_xyrz[3], left_xyrz[3]),
            "fit": {"right_eye": right_method_str, "left_eye": left_method_str}}


def get_detect_dict_or_none_from_gray_arr(gray_arr: "np.ndarray", state_dict: dict, mul_float: float,
                                          param_dict: dict) -> dict | None:
    img_arr = get_img_arr_from_gray_arr(gray_arr, param_dict)
    return get_eye_dict_or_none_from_img_arr(img_arr, state_dict, mul_float, param_dict)


def get_frame_count_int_from_ctx_dict(ctx_dict: dict, pos_int: int) -> int:
    return ctx_dict["frame_count_ints"][pos_int]


def get_sec_floats_from_ctx_dict(ctx_dict: dict, pos_int: int) -> list[float]:
    if pos_int not in ctx_dict["sec_dict"]:
        ctx_dict["sec_dict"][pos_int] = get_sec_floats_from_mp4_path(ctx_dict["in_dir_path"] / f"{ctx_dict['minute_strs'][pos_int]}.mp4")
    return ctx_dict["sec_dict"][pos_int]


def get_pos_index_tuple_or_none(frame_count_ints: list[int], pos_int: int, index_int: int, delta_int: int) -> tuple[int, int] | None:
    step_int = 1 if delta_int > 0 else -1
    for _ in range(abs(delta_int)):
        index_int += step_int
        if index_int >= frame_count_ints[pos_int]:
            pos_int, index_int = pos_int + 1, 0
            if pos_int >= len(frame_count_ints):
                return None
        elif index_int < 0:
            pos_int -= 1
            if pos_int < 0:
                return None
            index_int = frame_count_ints[pos_int] - 1
    return pos_int, index_int


def get_candidate_tuple_list(ctx_dict: dict, pos_int: int, index_int: int, dir_int: int,
                             limit_index_int: int | None = None) -> list[tuple[int, int]]:
    candidate_list = [(pos_int, index_int)]
    for k_int in range(1, ctx_dict["param_dict"]["retry_frames"] + 1):
        key_tuple = get_pos_index_tuple_or_none(ctx_dict["frame_count_ints"], pos_int, index_int, dir_int * k_int)
        if key_tuple is None or (limit_index_int is not None and key_tuple[0] == pos_int
                                 and (key_tuple[1] - limit_index_int) * dir_int >= 0):
            break
        candidate_list.append(key_tuple)
    return candidate_list


def update_gray_dict_from_key_tuples(ctx_dict: dict, gray_dict: dict, key_tuples: list[tuple[int, int]]) -> None:
    need_dict: dict[int, set[int]] = {}
    for pos_int, index_int in key_tuples:
        if (pos_int, index_int) not in gray_dict:
            need_dict.setdefault(pos_int, set()).add(index_int)
    for pos_int, index_set in need_dict.items():
        mp4_path = ctx_dict["in_dir_path"] / f"{ctx_dict['minute_strs'][pos_int]}.mp4"
        got_set: set[int] = set()
        for index_int, _, gray_arr in gen_index_sec_gray_from_mp4_path(mp4_path):
            if index_int in index_set:
                gray_dict[(pos_int, index_int)] = gray_arr
                got_set.add(index_int)
            if index_int >= max(index_set):
                break
        if got_set != index_set:
            raise ValueError(f"[Error] {mp4_path} 解碼不出第 {sorted(index_set - got_set)[:5]} 幀等 {len(index_set - got_set)} 幀（影片比封包記錄的短？）")


def get_found_tuple_or_none_and_candidate_list(ctx_dict: dict, gray_dict: dict, pos_int: int, index_int: int, dir_int: int,
                                               state_dict: dict, mul_float: float,
                                               limit_index_int: int | None = None) -> tuple[tuple | None, list[tuple[int, int]]]:
    candidate_list = get_candidate_tuple_list(ctx_dict, pos_int, index_int, dir_int, limit_index_int)
    for k_int, key_tuple in enumerate(candidate_list):
        if key_tuple not in gray_dict:
            update_gray_dict_from_key_tuples(ctx_dict, gray_dict, candidate_list)
        detect_dict = get_detect_dict_or_none_from_gray_arr(gray_dict[key_tuple], state_dict, mul_float, ctx_dict["param_dict"])
        if detect_dict is not None:
            return (k_int, key_tuple[0], key_tuple[1], detect_dict), candidate_list
    return None, candidate_list


def get_entry_dict_from_detect_dict(ctx_dict: dict, pos_int: int, index_int: int, kind_str: str, k_int: int,
                                    detect_dict: dict) -> dict:
    minute_str = ctx_dict["minute_strs"][pos_int]
    sec_float = get_sec_floats_from_ctx_dict(ctx_dict, pos_int)[index_int]
    right_xyr, left_xyr = detect_dict["right"], detect_dict["left"]
    return {"time": get_time_str_from_minute_str(minute_str, sec_float), "minute": minute_str, "frame": index_int,
            "sec": round(sec_float, 3), "kind": kind_str, "retry_k": k_int,
            "right_eye": [round(right_xyr[0], 3), round(right_xyr[1], 3)], "right_eye_r": round(right_xyr[2], 3),
            "left_eye": [round(left_xyr[0], 3), round(left_xyr[1], 3)], "left_eye_r": round(left_xyr[2], 3),
            "eye_score": round(detect_dict["score"], 3), "eye_z": round(detect_dict["z"], 3), "fit": detect_dict["fit"]}


def get_dist_float_from_entry_dicts(entry_dict_a: dict, entry_dict_b: dict) -> float:
    return max(math.dist(entry_dict_a["right_eye"], entry_dict_b["right_eye"]),
               math.dist(entry_dict_a["left_eye"], entry_dict_b["left_eye"]))


def get_last_good_dict_from_state_dict(state_dict: dict, mul_float: float) -> dict:
    right_xyr, left_xyr = state_dict["right"], state_dict["left"]
    mid_x_float, mid_y_float = (right_xyr[0] + left_xyr[0]) / 2, (right_xyr[1] + left_xyr[1]) / 2
    half_float = (mul_float + 0.5) * state_dict["d"]
    return {"right_eye": [round(right_xyr[0], 3), round(right_xyr[1], 3)], "right_eye_r": round(right_xyr[2], 3),
            "left_eye": [round(left_xyr[0], 3), round(left_xyr[1], 3)], "left_eye_r": round(left_xyr[2], 3),
            "search_box": [round(mid_x_float - half_float, 1), round(mid_y_float - half_float, 1),
                           round(mid_x_float + half_float, 1), round(mid_y_float + half_float, 1)]}


def get_not_found_msg_str(ctx_dict: dict, pos_int: int, index_int: int, state_dict: dict, mul_float: float,
                          candidate_list: list[tuple[int, int]]) -> str:
    minute_str = ctx_dict["minute_strs"][pos_int]
    sec_float = get_sec_floats_from_ctx_dict(ctx_dict, pos_int)[index_int]
    mid_x_float = (state_dict["right"][0] + state_dict["left"][0]) / 2
    mid_y_float = (state_dict["right"][1] + state_dict["left"][1]) / 2
    half_float = (mul_float + 0.5) * state_dict["d"]
    cross_bool = any(key_tuple[0] != pos_int for key_tuple in candidate_list)
    retry_str = ("" if len(candidate_list) <= 1 else
                 f"，往後再找 {len(candidate_list) - 1} 幀（{'含跨到另一個檔案' if cross_bool else '都在同一個檔案內'}）也都找不到")
    return (f"[Error] {get_time_str_from_minute_str(minute_str, sec_float)}（{minute_str} 第 {index_int} 幀）在上一個位置"
            f"（兩眼中點 ({mid_x_float:.1f}, {mid_y_float:.1f})）的 ±{half_float:.1f}px 範圍內找不到兩眼{retry_str}。"
            "可能動得太快、眼睛消失，或參數太嚴格；可調整 config.json 的 part_3.0"
            "（retry_frames / sample_search_mul / frame_search_mul / eye_k_z / k_z / spacing_tol / eye_r_ratio / r_min / r_max）")


def run_sample_stage(ctx_dict: dict, pos_int: int, order_str: str, state_dict: dict, seed_bool: bool,
                     entry_dict_list: list[dict]) -> dict | None:
    param_dict = ctx_dict["param_dict"]
    sec_floats = get_sec_floats_from_ctx_dict(ctx_dict, pos_int)
    index_ints = get_sample_index_ints_from_sec_floats(sec_floats, param_dict["sample_step_s"])
    dir_int = 1 if order_str == "forward" else -1
    plan_ints = index_ints if dir_int == 1 else index_ints[::-1]
    gray_dict: dict = {}
    update_gray_dict_from_key_tuples(ctx_dict, gray_dict, [key_tuple for index_int in plan_ints
                                                           for key_tuple in get_candidate_tuple_list(ctx_dict, pos_int, index_int, dir_int)
                                                           if key_tuple[0] == pos_int])
    last_index_int = entry_dict_list[-1]["frame"] if entry_dict_list else None
    for index_int in plan_ints:
        if last_index_int is not None and (index_int - last_index_int) * dir_int <= 0:
            continue
        first_bool = last_index_int is None
        mul_float = param_dict["frame_search_mul" if first_bool else "sample_search_mul"]
        found_tuple, candidate_list = get_found_tuple_or_none_and_candidate_list(ctx_dict, gray_dict, pos_int, index_int, dir_int,
                                                                                  state_dict, mul_float)
        if found_tuple is None:
            raise TrackError(get_not_found_msg_str(ctx_dict, pos_int, index_int, state_dict, mul_float, candidate_list), index_int,
                             get_last_good_dict_from_state_dict(state_dict, mul_float))
        k_int, found_pos_int, found_index_int, detect_dict = found_tuple
        kind_str = "retry" if k_int else ("seed" if seed_bool and first_bool else "sample")
        entry_dict = get_entry_dict_from_detect_dict(ctx_dict, found_pos_int, found_index_int, kind_str, k_int, detect_dict)
        if found_pos_int != pos_int:
            return entry_dict
        entry_dict_list.append(entry_dict)
        state_dict = get_state_dict_from_entry_dict(entry_dict, state_dict["ref"])
        last_index_int = found_index_int
    return None


def get_segment_tuple_list_from_entry_dict_list(entry_dict_list: list[dict], move_tol_px_float: float) -> list[tuple[dict, dict]]:
    return [(entry_dict_a, entry_dict_b) for entry_dict_a, entry_dict_b in zip(entry_dict_list[:-1], entry_dict_list[1:])
            if get_dist_float_from_entry_dicts(entry_dict_a, entry_dict_b) > move_tol_px_float and abs(entry_dict_b["frame"] - entry_dict_a["frame"]) > 1]


def run_subdivide_stage(ctx_dict: dict, pos_int: int, segment_tuple_list: list[tuple[dict, dict]], ref_dict: dict,
                        entry_dict_list: list[dict]) -> None:
    param_dict = ctx_dict["param_dict"]
    wanted_set: set[int] = set()
    for entry_dict_a, entry_dict_b in segment_tuple_list:
        low_int, high_int = sorted((entry_dict_a["frame"], entry_dict_b["frame"]))
        wanted_set.update(range(low_int + 1, high_int))
    gray_dict: dict = {}
    update_gray_dict_from_key_tuples(ctx_dict, gray_dict, [(pos_int, index_int) for index_int in sorted(wanted_set)])
    for entry_dict_a, entry_dict_b in segment_tuple_list:
        dir_int = 1 if entry_dict_b["frame"] > entry_dict_a["frame"] else -1
        state_dict = get_state_dict_from_entry_dict(entry_dict_a, ref_dict)
        index_int = entry_dict_a["frame"] + dir_int
        while (entry_dict_b["frame"] - index_int) * dir_int > 0:
            found_tuple, candidate_list = get_found_tuple_or_none_and_candidate_list(
                ctx_dict, gray_dict, pos_int, index_int, dir_int, state_dict, param_dict["frame_search_mul"], entry_dict_b["frame"])
            if found_tuple is None:
                if (entry_dict_b["frame"] - index_int) * dir_int <= param_dict["retry_frames"]:
                    break
                raise TrackError(get_not_found_msg_str(ctx_dict, pos_int, index_int, state_dict, param_dict["frame_search_mul"],
                                                       candidate_list), index_int,
                                 get_last_good_dict_from_state_dict(state_dict, param_dict["frame_search_mul"]))
            k_int, _, found_index_int, detect_dict = found_tuple
            entry_dict = get_entry_dict_from_detect_dict(ctx_dict, pos_int, found_index_int, "retry" if k_int else "frame", k_int,
                                                         detect_dict)
            entry_dict_list.append(entry_dict)
            state_dict = get_state_dict_from_entry_dict(entry_dict, ref_dict)
            index_int = found_index_int + dir_int


def run_minute_stage(ctx_dict: dict, pos_int: int, order_str: str, state_dict: dict, seed_bool: bool,
                     entry_dict_list: list[dict]) -> dict | None:
    minute_str = ctx_dict["minute_strs"][pos_int]
    ctx_dict["sec_dict"] = {}
    carry_entry_dict = run_sample_stage(ctx_dict, pos_int, order_str, state_dict, seed_bool, entry_dict_list)
    segment_tuple_list = get_segment_tuple_list_from_entry_dict_list(list(entry_dict_list), ctx_dict["param_dict"]["move_tol_px"])
    if segment_tuple_list:
        info(f"{minute_str}：{len(segment_tuple_list)} 段有動（位移 > {ctx_dict['param_dict']['move_tol_px']}px），細分到逐幀")
        run_subdivide_stage(ctx_dict, pos_int, segment_tuple_list, state_dict["ref"], entry_dict_list)
    entry_dict_list.sort(key=lambda entry_dict: entry_dict["frame"])
    if len({entry_dict["time"] for entry_dict in entry_dict_list}) != len(entry_dict_list):
        raise ValueError(f"[Error] {minute_str} 有不同的幀得到相同的時間字串（時間不重複是 part_4.0、part_5.0 的前提）")
    return carry_entry_dict


def get_stat_dict_from_entry_dict_list(entry_dict_list: list[dict], complete_bool: bool) -> dict:
    return {"complete": complete_bool, "entries": len(entry_dict_list),
            "by_kind": get_count_dict_from_strs([entry_dict["kind"] for entry_dict in entry_dict_list])}


def get_failed_dict_from_error(error_obj: BaseException, ts_str: str, order_str: str) -> dict:
    failed_dict: dict = {"minute": ts_str, "order": order_str, "type": type(error_obj).__name__, "frame": None, "last_good": None}
    if isinstance(error_obj, KeyboardInterrupt):
        failed_dict["error"] = "使用者中斷（Ctrl-C）"
        return failed_dict
    failed_dict["error"] = str(error_obj)
    if isinstance(error_obj, TrackError):
        failed_dict["frame"], failed_dict["last_good"] = error_obj.frame_int, error_obj.last_good_dict
    return failed_dict


def get_meta_dict_from_stage_results(args_ns: object, manifest_dict: dict, param_dict: dict, seed_dict: dict,
                                     ts_to_stat_dict: dict[str, dict], minute_strs: list[str], status_str: str,
                                     failed_dict: dict | None) -> dict:
    return {"kind": PART_STR, "start_min": args_ns.start_min, "end_min": args_ns.end_min, "status": status_str,
            "params": param_dict,
            "inputs": get_inputs_dict_from_part_strs(manifest_dict, args_ns.start_min, args_ns.end_min, ["part_2.5", "part_2.0"]),
            "seed": {"minute": seed_dict["minute"], "frame": 0},
            "minutes": dict(sorted(ts_to_stat_dict.items())),
            "pending": [ts_str for ts_str in minute_strs if ts_str not in ts_to_stat_dict], "failed": failed_dict,
            "updated_at": get_now_str()}


def run_save_progress_stage(out_dir_path: Path, args_ns: object, manifest_dict: dict, param_dict: dict, seed_dict: dict,
                            ts_to_stat_dict: dict[str, dict], minute_strs: list[str], status_str: str,
                            failed_dict: dict | None) -> None:
    save_json_obj_to_path(get_meta_dict_from_stage_results(args_ns, manifest_dict, param_dict, seed_dict, ts_to_stat_dict,
                                                           minute_strs, status_str, failed_dict), out_dir_path / "meta.json")


def run_save_failure_stage(error_obj: BaseException, ts_str: str, order_str: str, entry_dict_list: list[dict], out_dir_path: Path,
                           args_ns: object, manifest_dict: dict, param_dict: dict, seed_dict: dict,
                           ts_to_stat_dict: dict[str, dict], minute_strs: list[str]) -> None:
    try:
        if entry_dict_list and ts_str not in ts_to_stat_dict:
            entry_dict_list.sort(key=lambda entry_dict: entry_dict["frame"])
            save_json_obj_to_path(entry_dict_list, out_dir_path / f"{ts_str}.json")
            ts_to_stat_dict[ts_str] = get_stat_dict_from_entry_dict_list(entry_dict_list, False)
        run_save_progress_stage(out_dir_path, args_ns, manifest_dict, param_dict, seed_dict, ts_to_stat_dict, minute_strs,
                                "interrupted" if isinstance(error_obj, KeyboardInterrupt) else "failed",
                                get_failed_dict_from_error(error_obj, ts_str, order_str))
        warn(f"part_3.0 沒做完，但已存下 {len(ts_to_stat_dict)} 個分鐘的結果（含失敗那分鐘失敗前的部分）。"
             f"仍可執行 python src/part_3.5/part_3.5_main.py {args_ns.manifest} {args_ns.start_min} {args_ns.end_min} 把它們畫出來檢查、調整參數")
    except Exception as save_error_obj:
        warn(f"寫入失敗資訊時又出錯（{type(save_error_obj).__name__}: {save_error_obj}）；原本的錯誤見下")


def run_all_stages(argv_strs: list[str]) -> None:
    check_deps_are_available()
    args_ns = get_args_ns_from_argv_strs("part_3.0", USAGE_STR, argv_strs)
    manifest_dict = args_ns.manifest_dict
    config_dict = get_config_dict_from_path(manifest_dict["config_path"])
    param_dict = get_param_dict_from_config_dict(config_dict, PART_STR, DEFAULT_PARAM_DICT, RULE_DICT_DICT)
    check_blob_param_dict(param_dict)
    info(get_scale_msg_str_from_param_dict(param_dict))

    get_meta_dict_from_part_dir(manifest_dict, args_ns.start_min, args_ns.end_min, "part_2.0")
    meta_2_5_dict = get_meta_dict_from_part_dir(manifest_dict, args_ns.start_min, args_ns.end_min, "part_2.5")
    check_input_sha_in_meta_dict(meta_2_5_dict, "part_2.0", manifest_dict, args_ns.start_min, args_ns.end_min)
    minute_strs = get_minute_strs_from_range(args_ns.start_min, args_ns.end_min)
    in_dir_path = get_part_dir_path(manifest_dict, args_ns.start_min, args_ns.end_min, "part_2.5") / "mp4s"
    missing_strs = [ts_str for ts_str in minute_strs if not (in_dir_path / f"{ts_str}.mp4").is_file()]
    if missing_strs:
        raise FileNotFoundError(f"[Error] part_2.5 缺少 {len(missing_strs)} 個拉正後的 mp4：{missing_strs[:5]}。請重新執行 part_2.5")
    seed_dict = get_seed_dict_from_part_dir(manifest_dict, args_ns.start_min, args_ns.end_min)
    seed_index_int = minute_strs.index(seed_dict["minute"])
    info(f"種子：{seed_dict['minute']} 第 0 秒；眼距 {math.dist(seed_dict['right_eye'][:2], seed_dict['left_eye'][:2]):.1f}px。"
         f"先往後追蹤 {len(minute_strs) - seed_index_int} 分鐘，再往前 {seed_index_int} 分鐘")

    out_dir_path = get_part_dir_path(manifest_dict, args_ns.start_min, args_ns.end_min, PART_STR)
    run_prepare_part_dir_stage(out_dir_path)
    ts_to_stat_dict: dict[str, dict] = {}
    seed_xyr_tuple = (tuple(seed_dict["right_eye"]), tuple(seed_dict["left_eye"]))
    plan_tuple_list = ([(ts_str, "forward") for ts_str in minute_strs[seed_index_int:]]
                       + [(ts_str, "backward") for ts_str in reversed(minute_strs[:seed_index_int])])
    ctx_dict: dict = {"minute_strs": minute_strs, "in_dir_path": in_dir_path, "param_dict": param_dict, "sec_dict": {},
                      "frame_count_ints": [meta_2_5_dict["minutes"][ts_str]["frames"] for ts_str in minute_strs]}
    state_dict = get_state_dict_from_xyrs(*seed_xyr_tuple)
    carry_entry_dict: dict | None = None
    seed_first_entry_dict: dict | None = None
    run_save_progress_stage(out_dir_path, args_ns, manifest_dict, param_dict, seed_dict, ts_to_stat_dict, minute_strs, "running", None)
    ts_str, order_str = plan_tuple_list[0]
    entry_dict_list: list[dict] = []
    try:
        for step_int, (ts_str, order_str) in enumerate(plan_tuple_list, start=1):
            entry_dict_list = [] if carry_entry_dict is None else [carry_entry_dict]
            if order_str == "backward" and ts_str == minute_strs[seed_index_int - 1]:
                state_dict = get_state_dict_from_entry_dict(seed_first_entry_dict, state_dict["ref"])
            start_float = time.time()
            carry_entry_dict = run_minute_stage(ctx_dict, minute_strs.index(ts_str), order_str, state_dict, ts_str == seed_dict["minute"],
                                                entry_dict_list)
            save_json_obj_to_path(entry_dict_list, out_dir_path / f"{ts_str}.json")
            ts_to_stat_dict[ts_str] = get_stat_dict_from_entry_dict_list(entry_dict_list, True)
            stat_dict = ts_to_stat_dict[ts_str]
            info(f"({step_int}/{len(plan_tuple_list)}) {ts_str} {order_str}：{stat_dict['entries']} 筆 {stat_dict['by_kind']}，"
                 f"（{time.time() - start_float:.1f} 秒）"
                 + ("" if carry_entry_dict is None else f"；檔案邊界附近找不到，往後找到了另一個檔案的 {carry_entry_dict['time']}（第 {carry_entry_dict['frame']} 幀）"))
            if ts_str == seed_dict["minute"]:
                seed_first_entry_dict = entry_dict_list[0]
            next_entry_dict = carry_entry_dict or (entry_dict_list[-1] if order_str == "forward" else entry_dict_list[0])
            state_dict = get_state_dict_from_entry_dict(next_entry_dict, state_dict["ref"])
            run_save_progress_stage(out_dir_path, args_ns, manifest_dict, param_dict, seed_dict, ts_to_stat_dict, minute_strs,
                                    "running", None)
    except BaseException as error_obj:
        run_save_failure_stage(error_obj, ts_str, order_str, entry_dict_list, out_dir_path, args_ns, manifest_dict, param_dict,
                               seed_dict, ts_to_stat_dict, minute_strs)
        raise

    run_save_progress_stage(out_dir_path, args_ns, manifest_dict, param_dict, seed_dict, ts_to_stat_dict, minute_strs, "complete", None)
    success(f"part_3.0 完成：{len(minute_strs)} 個分鐘的 json。輸出：{out_dir_path}")


def main() -> None:
    run_main_stage(run_all_stages, sys.argv[1:])


if __name__ == "__main__":
    main()
