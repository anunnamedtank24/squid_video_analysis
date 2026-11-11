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

USAGE_STR = "part_3.0：在拉正後的 mp4 上追蹤烏賊的「右眼、左眼、腹部」，每個點輸出圓心與半徑。一分鐘輸出一個 json。\n用法：python src/part_3.0/part_3.0_main.py MANIFEST_JSON START_MIN END_MIN"


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
                       get_belly_xyr_from_rel_and_eyes, get_config_dict_from_path, get_count_dict_from_strs,
                       get_scale_msg_str_from_param_dict,
                       get_fit_xyr_method_tuple_from_img_arr, get_img_arr_from_gray_arr,
                       get_inputs_dict_from_part_strs, get_json_obj_from_path, get_meta_dict_from_part_dir,
                       get_minute_strs_from_range, get_now_str, get_param_dict_from_config_dict, get_part_dir_path, get_rel_dict_from_xyrs,
                       get_sec_floats_from_mp4_path, get_time_str_from_minute_str, get_xyrz_list_from_img_arr,
                       is_finite_num, np, run_prepare_part_dir_stage, save_json_obj_to_path)
from tool_manifest import (get_args_ns_from_argv_strs, info, run_main_stage, success, warn)

PART_STR = "part_3.0"
REL_KEY_STR_TUPLE = ("u", "v", "belly_r_rel")
TRACK_DEFAULT_DICT: dict = {
    "sample_step_s": 10.0,
    "move_tol_px": 1.5,
    "sample_search_mul": 3.0,
    "frame_search_mul": 1.0,
    "spacing_tol": 0.5,
    "boundary_search_px": 6.0,
    "boundary_tol_px": 3.0,
    "move_weight": 4.0,
    "eye_r_ratio": [0.3, 3.0],
    "body_r_ratio": [0.3, 4.0],
    "body_zone_par": 0.4,
    "body_zone_perp": 0.8,
    "body_k_z": 2.0,
    "body_k_z_edge": 8.0,
    "body_trust_z": 15.0,
    "eye_k_z": 6.0,
    "eye_z_ratio_min": 0.2,
}
TRACK_RULE_DICT_DICT: dict[str, dict] = {
    "sample_step_s": {"type": "float", "min": 0, "min_open": True},
    "move_tol_px": {"type": "float", "min": 0, "min_open": True},
    "sample_search_mul": {"type": "float", "min": 0, "min_open": True},
    "frame_search_mul": {"type": "float", "min": 0, "min_open": True},
    "spacing_tol": {"type": "float", "min": 0, "max": 5},
    "boundary_search_px": {"type": "float", "min": 0, "min_open": True},
    "boundary_tol_px": {"type": "float", "min": 0, "min_open": True},
    "move_weight": {"type": "float", "min": 0},
    "eye_r_ratio": {"type": "float_pair", "min": 0, "min_open": True},
    "body_r_ratio": {"type": "float_pair", "min": 0, "min_open": True},
    "body_zone_par": {"type": "float", "min": 0, "min_open": True},
    "body_zone_perp": {"type": "float", "min": 0, "min_open": True},
    "body_k_z": {"type": "float", "min": 0, "min_open": True},
    "body_k_z_edge": {"type": "float", "min": 0, "min_open": True},
    "body_trust_z": {"type": "float", "min": 0, "min_open": True},
    "eye_k_z": {"type": "float", "min": 0, "min_open": True},
    "eye_z_ratio_min": {"type": "float", "min": 0, "max": 1},
}
DEFAULT_PARAM_DICT: dict = {**BLOB_DEFAULT_DICT, **TRACK_DEFAULT_DICT}
RULE_DICT_DICT: dict[str, dict] = {**BLOB_RULE_DICT_DICT, **TRACK_RULE_DICT_DICT}


class TrackError(ValueError):

    def __init__(self, msg_str: str, frame_int: int, last_good_dict: dict) -> None:
        super().__init__(msg_str)
        self.frame_int = frame_int
        self.last_good_dict = last_good_dict


def get_seed_dict_from_part_dir(manifest_dict: dict, start_min_str: str, end_min_str: str) -> dict:
    seed_dict = get_json_obj_from_path(get_part_dir_path(manifest_dict, start_min_str, end_min_str, "part_2.0") / "seed.json",
                                       "part_2.0 的 seed.json")
    try:
        is_ok_bool = (seed_dict["kind"] == "seed" and start_min_str <= seed_dict["minute"] <= end_min_str
                      and all(len(seed_dict[key_str]) == 3 and all(is_finite_num(num) for num in seed_dict[key_str])
                              for key_str in ("right_eye", "left_eye", "belly"))
                      and all(is_finite_num(seed_dict["rel"][key_str]) for key_str in ("u", "v", "belly_r_rel")))
    except (KeyError, TypeError):
        is_ok_bool = False
    if not is_ok_bool:
        raise ValueError(f"[Error] part_2.0 的 seed.json 格式不對，或種子分鐘不在 {start_min_str} ~ {end_min_str} 內。請重新執行 part_2.0")
    return seed_dict


def get_rel3_dict_from_rel_dict(rel_dict: dict) -> dict:
    return {key_str: rel_dict[key_str] for key_str in REL_KEY_STR_TUPLE}


def get_state_dict_from_xyrs(right_xyr: XyrType, left_xyr: XyrType, rel_dict: dict, ref_dict: dict | None = None,
                             z_float: float = 0.0) -> dict:
    d_float = math.dist(right_xyr[:2], left_xyr[:2])
    rel3_dict = get_rel3_dict_from_rel_dict(rel_dict)
    return {"right": tuple(right_xyr), "left": tuple(left_xyr), "d": d_float,
            "ref": {"d": d_float, "rel": rel3_dict} if ref_dict is None else ref_dict, "z": z_float, "rel": rel3_dict}


def get_state_dict_from_entry_dict(entry_dict: dict, ref_dict: dict | None = None) -> dict:
    return get_state_dict_from_xyrs((*entry_dict["right_eye"], entry_dict["right_eye_r"]),
                                    (*entry_dict["left_eye"], entry_dict["left_eye_r"]), entry_dict["rel"], ref_dict,
                                    entry_dict.get("eye_z", 0.0))


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
                                      param_dict: dict, gate_px_float: float | None = None) -> dict | None:
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
        if gate_px_float is not None and (math.dist(right_xyrz[:2], state_dict["right"][:2]) > gate_px_float
                                          or math.dist(left_xyrz[:2], state_dict["left"][:2]) > gate_px_float):
            continue
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


def check_body_param_dict(param_dict: dict) -> None:
    if param_dict["body_k_z_edge"] < param_dict["body_k_z"]:
        raise ValueError(f"[Error] config.json 的 part_3.0.body_k_z_edge（{param_dict['body_k_z_edge']}）不可小於 body_k_z（{param_dict['body_k_z']}）")


def get_zone_tuple_from_eyes_and_pred(right_xyr: XyrType, left_xyr: XyrType, pred_xyr: XyrType, param_dict: dict) -> tuple[float, float, float, float, float]:
    eye_x_float, eye_y_float = left_xyr[0] - right_xyr[0], left_xyr[1] - right_xyr[1]
    dist_float = math.hypot(eye_x_float, eye_y_float)
    return (pred_xyr[0], pred_xyr[1], param_dict["body_zone_par"] * dist_float, param_dict["body_zone_perp"] * dist_float,
            math.degrees(math.atan2(eye_y_float, eye_x_float)))


def get_rho_float_from_xy_and_zone(xy: XyType, zone_tuple: tuple[float, float, float, float, float]) -> float:
    angle_float = math.radians(zone_tuple[4])
    dx_float, dy_float = xy[0] - zone_tuple[0], xy[1] - zone_tuple[1]
    par_float = dx_float * math.cos(angle_float) + dy_float * math.sin(angle_float)
    perp_float = -dx_float * math.sin(angle_float) + dy_float * math.cos(angle_float)
    return math.hypot(par_float / zone_tuple[2], perp_float / zone_tuple[3])


def get_thr_float_from_rho(rho_float: float, param_dict: dict) -> float:
    return param_dict["body_k_z"] + (param_dict["body_k_z_edge"] - param_dict["body_k_z"]) * rho_float


def get_belly_dict_from_img_arr(img_arr: "np.ndarray", right_xyr: XyrType, left_xyr: XyrType, rel_dict: dict,
                                ref_rel_dict: dict, param_dict: dict) -> dict:
    pred_xyr = get_belly_xyr_from_rel_and_eyes(rel_dict, right_xyr[:2], left_xyr[:2])
    center_xyr = get_belly_xyr_from_rel_and_eyes(ref_rel_dict, right_xyr[:2], left_xyr[:2])
    zone_tuple = get_zone_tuple_from_eyes_and_pred(right_xyr, left_xyr, center_xyr, param_dict)
    half_float = max(zone_tuple[2], zone_tuple[3])
    region_tuple = (int(math.floor(center_xyr[0] - half_float)), int(math.floor(center_xyr[1] - half_float)),
                   int(math.ceil(center_xyr[0] + half_float)) + 1, int(math.ceil(center_xyr[1] + half_float)) + 1)
    xyrz_list = get_xyrz_list_from_img_arr(img_arr, region_tuple, param_dict, param_dict["body_k_z"])
    low_float, high_float = param_dict["body_r_ratio"][0] * pred_xyr[2], param_dict["body_r_ratio"][1] * pred_xyr[2]
    rank_xyrz_list: list[tuple[float, XyrzType]] = []
    for xyrz in xyrz_list:
        rho_float = get_rho_float_from_xy_and_zone(xyrz[:2], zone_tuple)
        thr_float = get_thr_float_from_rho(rho_float, param_dict)
        if rho_float > 1 or xyrz[3] <= thr_float or not low_float <= xyrz[2] <= high_float:
            continue
        if any(math.dist(xyrz[:2], eye_xyr[:2]) < eye_xyr[2] + 0.5 * xyrz[2] for eye_xyr in (right_xyr, left_xyr)):
            continue
        rank_xyrz_list.append((min(xyrz[3], param_dict["z_cap"]) / thr_float, xyrz))
    if rank_xyrz_list:
        best_xyrz = max(rank_xyrz_list, key=lambda rank_xyrz: rank_xyrz[0])[1]
        near_float = min(math.dist(best_xyrz[:2], eye_xyr[:2]) for eye_xyr in (right_xyr, left_xyr))
        fit_xyr, method_str = get_fit_xyr_method_tuple_from_img_arr(
            img_arr, best_xyrz[:3], min(param_dict["fit_rmax_mul"] * best_xyrz[2], 0.85 * near_float), param_dict)
        if low_float <= fit_xyr[2] <= high_float:
            return {"xyr": fit_xyr, "status": "detected", "score": best_xyrz[3], "fit": method_str, "zone": zone_tuple}
    return {"xyr": pred_xyr, "status": "predicted", "score": NAN_FLOAT, "fit": None, "zone": zone_tuple}


def get_rel_dict_from_belly_dict(right_xyr: XyrType, left_xyr: XyrType, belly_dict: dict, state_dict: dict, param_dict: dict) -> dict:
    if is_belly_trusted(belly_dict, param_dict):
        return get_rel3_dict_from_rel_dict(get_rel_dict_from_xyrs(right_xyr, left_xyr, belly_dict["xyr"]))
    return state_dict["rel"]


def is_belly_trusted(belly_dict: dict, param_dict: dict) -> bool:
    return belly_dict["status"] == "detected" and belly_dict["score"] >= param_dict["body_trust_z"]


def get_detect_dict_or_none_from_gray_arr(gray_arr: "np.ndarray", state_dict: dict, mul_float: float,
                                          param_dict: dict, gate_px_float: float | None = None) -> dict | None:
    img_arr = get_img_arr_from_gray_arr(gray_arr, param_dict)
    eye_dict = get_eye_dict_or_none_from_img_arr(img_arr, state_dict, mul_float, param_dict, gate_px_float)
    if eye_dict is None:
        return None
    belly_dict = get_belly_dict_from_img_arr(img_arr, eye_dict["right"], eye_dict["left"], state_dict["rel"],
                                         state_dict["ref"]["rel"], param_dict)
    return {**eye_dict, "belly": belly_dict,
            "rel": get_rel_dict_from_belly_dict(eye_dict["right"], eye_dict["left"], belly_dict, state_dict, param_dict)}


def get_entry_dict_from_detect_dict(minute_str: str, index_int: int, sec_float: float, kind_str: str,
                                    detect_dict: dict) -> dict:
    right_xyr, left_xyr, belly_dict = detect_dict["right"], detect_dict["left"], detect_dict["belly"]
    belly_xyr = belly_dict["xyr"]
    return {"time": get_time_str_from_minute_str(minute_str, sec_float), "minute": minute_str, "frame": index_int,
            "sec": round(sec_float, 3), "kind": kind_str,
            "right_eye": [round(right_xyr[0], 3), round(right_xyr[1], 3)], "right_eye_r": round(right_xyr[2], 3),
            "left_eye": [round(left_xyr[0], 3), round(left_xyr[1], 3)], "left_eye_r": round(left_xyr[2], 3),
            "body": [round(belly_xyr[0], 3), round(belly_xyr[1], 3)], "body_r": round(belly_xyr[2], 3),
            "body_status": belly_dict["status"], "eye_score": round(detect_dict["score"], 3), "eye_z": round(detect_dict["z"], 3),
            "body_score": round(belly_dict["score"], 3) if belly_dict["status"] == "detected" else NAN_FLOAT,
            "rel": {key_str: round(detect_dict["rel"][key_str], 4) for key_str in REL_KEY_STR_TUPLE},
            "body_zone": [round(num, 3) for num in belly_dict["zone"]],
            "fit": {**detect_dict["fit"], "body": belly_dict["fit"]}}


def get_dist_float_from_entry_dicts(entry_dict_a: dict, entry_dict_b: dict) -> float:
    return max(math.dist(entry_dict_a["right_eye"], entry_dict_b["right_eye"]),
               math.dist(entry_dict_a["left_eye"], entry_dict_b["left_eye"]))


def get_last_good_dict_from_state_dict(state_dict: dict, mul_float: float | None, gate_px_float: float | None = None) -> dict:
    right_xyr, left_xyr = state_dict["right"], state_dict["left"]
    last_good_dict: dict = {"right_eye": [round(right_xyr[0], 3), round(right_xyr[1], 3)], "right_eye_r": round(right_xyr[2], 3),
                            "left_eye": [round(left_xyr[0], 3), round(left_xyr[1], 3)], "left_eye_r": round(left_xyr[2], 3),
                            "search_box": None, "gate_px": gate_px_float}
    if mul_float is not None:
        mid_x_float, mid_y_float = (right_xyr[0] + left_xyr[0]) / 2, (right_xyr[1] + left_xyr[1]) / 2
        half_float = (mul_float + 0.5) * state_dict["d"]
        last_good_dict["search_box"] = [round(mid_x_float - half_float, 1), round(mid_y_float - half_float, 1),
                                        round(mid_x_float + half_float, 1), round(mid_y_float + half_float, 1)]
    return last_good_dict


def check_boundary_dist(dist_float: float, label_str: str, boundary_tol_px_float: float, entry_dict: dict,
                        boundary_entry_dict: dict) -> None:
    if dist_float > boundary_tol_px_float:
        raise TrackError(f"[Error] {entry_dict['time']}（第 {entry_dict['frame']} 幀）找到的眼睛位置與{label_str}相差 {dist_float:.2f}px，"
                         f"超過 config.json 的 part_3.0.boundary_tol_px={boundary_tol_px_float}。兩分鐘交界的畫面應該幾乎相同——"
                         "可能中間漏掉一段時間、拉正的四邊形不同、或追錯了目標",
                         entry_dict["frame"], get_last_good_dict_from_state_dict(get_state_dict_from_entry_dict(boundary_entry_dict), None))


def get_not_found_msg_str(minute_str: str, index_int: int, sec_float: float, state_dict: dict, mul_float: float,
                          gate_px_float: float | None = None) -> str:
    mid_x_float = (state_dict["right"][0] + state_dict["left"][0]) / 2
    mid_y_float = (state_dict["right"][1] + state_dict["left"][1]) / 2
    half_float = (mul_float + 0.5) * state_dict["d"]
    where_str = (f"上一個位置（兩眼中點 ({mid_x_float:.1f}, {mid_y_float:.1f})）的 ±{half_float:.1f}px 範圍內"
                 if gate_px_float is None else
                 f"上一個位置（兩眼中點 ({mid_x_float:.1f}, {mid_y_float:.1f})）的 ±{half_float:.1f}px 範圍內、且每隻眼都在上一個位置的 {gate_px_float:g}px 內")
    param_str = ("sample_search_mul / frame_search_mul / eye_k_z / k_z / spacing_tol / eye_r_ratio / r_min / r_max"
                 if gate_px_float is None else
                 "boundary_search_px / frame_search_mul / eye_k_z / k_z / spacing_tol / eye_r_ratio / r_min / r_max")
    return (f"[Error] {get_time_str_from_minute_str(minute_str, sec_float)}（{minute_str} 第 {index_int} 幀）在{where_str}找不到兩眼。"
            f"可能動得太快、眼睛消失，或參數太嚴格；可調整 config.json 的 part_3.0（{param_str}）")


def run_sample_stage(minute_str: str, mp4_path: Path, index_ints: list[int], sec_floats: list[float], order_str: str,
                     state_dict: dict, boundary_entry_dict: dict, boundary_label_str: str, seed_bool: bool,
                     param_dict: dict, entry_dict_list: list[dict]) -> None:
    index_to_gray_dict: dict[int, "np.ndarray"] = {}
    wanted_set = set(index_ints)
    for index_int, _, gray_arr in gen_index_sec_gray_from_mp4_path(mp4_path):
        if index_int in wanted_set:
            index_to_gray_dict[index_int] = gray_arr
        if index_int >= max(index_ints):
            break
    missing_ints = sorted(wanted_set - set(index_to_gray_dict))
    if missing_ints:
        raise ValueError(f"[Error] {mp4_path} 解碼不出第 {missing_ints} 幀（影片比封包記錄的短？）")
    for step_int, index_int in enumerate(index_ints if order_str == "forward" else index_ints[::-1]):
        first_bool = step_int == 0
        mul_float = param_dict["frame_search_mul" if first_bool else "sample_search_mul"]
        gate_px_float = param_dict["boundary_search_px"] if first_bool else None
        detect_dict = get_detect_dict_or_none_from_gray_arr(index_to_gray_dict[index_int], state_dict, mul_float, param_dict,
                                                            gate_px_float)
        if detect_dict is None:
            raise TrackError(get_not_found_msg_str(minute_str, index_int, sec_floats[index_int], state_dict, mul_float, gate_px_float),
                             index_int, get_last_good_dict_from_state_dict(state_dict, mul_float, gate_px_float))
        kind_str = "seed" if (seed_bool and step_int == 0) else "sample"
        entry_dict = get_entry_dict_from_detect_dict(minute_str, index_int, sec_floats[index_int], kind_str, detect_dict)
        entry_dict_list.append(entry_dict)
        if step_int == 0:
            check_boundary_dist(get_dist_float_from_entry_dicts(entry_dict, boundary_entry_dict), boundary_label_str,
                                param_dict["boundary_tol_px"], entry_dict, boundary_entry_dict)
        state_dict = get_state_dict_from_entry_dict(entry_dict, state_dict["ref"])


def get_segment_tuple_list_from_entry_dict_list(entry_dict_list: list[dict], move_tol_px_float: float) -> list[tuple[dict, dict]]:
    return [(entry_dict_a, entry_dict_b) for entry_dict_a, entry_dict_b in zip(entry_dict_list[:-1], entry_dict_list[1:])
            if get_dist_float_from_entry_dicts(entry_dict_a, entry_dict_b) > move_tol_px_float and abs(entry_dict_b["frame"] - entry_dict_a["frame"]) > 1]


def run_subdivide_stage(minute_str: str, mp4_path: Path, sec_floats: list[float], segment_tuple_list: list[tuple[dict, dict]],
                        ref_dict: dict, param_dict: dict, entry_dict_list: list[dict]) -> None:
    wanted_set: set[int] = set()
    for entry_dict_a, entry_dict_b in segment_tuple_list:
        low_int, high_int = sorted((entry_dict_a["frame"], entry_dict_b["frame"]))
        wanted_set.update(range(low_int + 1, high_int))
    index_to_gray_dict: dict[int, "np.ndarray"] = {}
    for index_int, _, gray_arr in gen_index_sec_gray_from_mp4_path(mp4_path):
        if index_int in wanted_set:
            index_to_gray_dict[index_int] = gray_arr
        if index_int >= max(wanted_set):
            break
    for entry_dict_a, entry_dict_b in segment_tuple_list:
        step_int = 1 if entry_dict_b["frame"] > entry_dict_a["frame"] else -1
        state_dict = get_state_dict_from_entry_dict(entry_dict_a, ref_dict)
        for index_int in range(entry_dict_a["frame"] + step_int, entry_dict_b["frame"], step_int):
            detect_dict = get_detect_dict_or_none_from_gray_arr(index_to_gray_dict[index_int], state_dict,
                                                                param_dict["frame_search_mul"], param_dict)
            if detect_dict is None:
                raise TrackError(get_not_found_msg_str(minute_str, index_int, sec_floats[index_int], state_dict,
                                                       param_dict["frame_search_mul"]), index_int,
                                 get_last_good_dict_from_state_dict(state_dict, param_dict["frame_search_mul"]))
            entry_dict = get_entry_dict_from_detect_dict(minute_str, index_int, sec_floats[index_int], "frame", detect_dict)
            entry_dict_list.append(entry_dict)
            state_dict = get_state_dict_from_entry_dict(entry_dict, ref_dict)


def run_minute_stage(minute_str: str, mp4_path: Path, order_str: str, state_dict: dict, boundary_entry_dict: dict,
                     boundary_label_str: str, seed_bool: bool, param_dict: dict,
                     entry_dict_list: list[dict]) -> None:
    sec_floats = get_sec_floats_from_mp4_path(mp4_path)
    index_ints = get_sample_index_ints_from_sec_floats(sec_floats, param_dict["sample_step_s"])
    run_sample_stage(minute_str, mp4_path, index_ints, sec_floats, order_str, state_dict, boundary_entry_dict,
                     boundary_label_str, seed_bool, param_dict, entry_dict_list)
    segment_tuple_list = get_segment_tuple_list_from_entry_dict_list(list(entry_dict_list), param_dict["move_tol_px"])
    if segment_tuple_list:
        info(f"{minute_str}：{len(segment_tuple_list)} 段有動（位移 > {param_dict['move_tol_px']}px），細分到逐幀")
        run_subdivide_stage(minute_str, mp4_path, sec_floats, segment_tuple_list, state_dict["ref"], param_dict, entry_dict_list)
    entry_dict_list.sort(key=lambda entry_dict: entry_dict["frame"])
    if len({entry_dict["time"] for entry_dict in entry_dict_list}) != len(entry_dict_list):
        raise ValueError(f"[Error] {minute_str} 有不同的幀得到相同的時間字串（時間不重複是 part_4.0 的前提）")


def get_stat_dict_from_entry_dict_list(entry_dict_list: list[dict], complete_bool: bool) -> dict:
    return {"complete": complete_bool, "entries": len(entry_dict_list),
            "by_kind": get_count_dict_from_strs([entry_dict["kind"] for entry_dict in entry_dict_list]),
            "by_body_status": get_count_dict_from_strs([entry_dict["body_status"] for entry_dict in entry_dict_list])}


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
            "seed": {"minute": seed_dict["minute"], "frame": 0, "rel": seed_dict["rel"]},
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
    check_body_param_dict(param_dict)
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
    rel_dict = seed_dict["rel"]
    seed_index_int = minute_strs.index(seed_dict["minute"])
    info(f"種子：{seed_dict['minute']} 第 0 秒；眼距 {rel_dict['eye_dist_px']:.1f}px；腹部相對位置 u={rel_dict['u']:.2f} "
         f"v={rel_dict['v']:.2f}、半徑比 {rel_dict['belly_r_rel']:.2f}。先往後追蹤 {len(minute_strs) - seed_index_int} 分鐘，再往前 {seed_index_int} 分鐘")

    out_dir_path = get_part_dir_path(manifest_dict, args_ns.start_min, args_ns.end_min, PART_STR)
    run_prepare_part_dir_stage(out_dir_path)
    ts_to_stat_dict: dict[str, dict] = {}
    seed_xyr_tuple = (tuple(seed_dict["right_eye"]), tuple(seed_dict["left_eye"]))
    plan_tuple_list = ([(ts_str, "forward") for ts_str in minute_strs[seed_index_int:]]
                       + [(ts_str, "backward") for ts_str in reversed(minute_strs[:seed_index_int])])
    state_dict = get_state_dict_from_xyrs(*seed_xyr_tuple, rel_dict)
    boundary_entry_dict = {"time": seed_dict["minute"], "frame": 0,
                           "right_eye": seed_dict["right_eye"][:2], "right_eye_r": seed_dict["right_eye"][2],
                           "left_eye": seed_dict["left_eye"][:2], "left_eye_r": seed_dict["left_eye"][2]}
    boundary_label_str = "你在 part_2.0 點的種子位置"
    seed_first_entry_dict: dict | None = None
    run_save_progress_stage(out_dir_path, args_ns, manifest_dict, param_dict, seed_dict, ts_to_stat_dict, minute_strs, "running", None)
    ts_str, order_str = plan_tuple_list[0]
    entry_dict_list: list[dict] = []
    try:
        for step_int, (ts_str, order_str) in enumerate(plan_tuple_list, start=1):
            entry_dict_list = []
            if order_str == "backward" and ts_str == minute_strs[seed_index_int - 1]:
                state_dict = get_state_dict_from_entry_dict(seed_first_entry_dict, state_dict["ref"])
                boundary_entry_dict, boundary_label_str = seed_first_entry_dict, f"{minute_strs[seed_index_int]} 的第一幀"
            start_float = time.time()
            run_minute_stage(ts_str, in_dir_path / f"{ts_str}.mp4", order_str, state_dict, boundary_entry_dict,
                             boundary_label_str, ts_str == seed_dict["minute"], param_dict, entry_dict_list)
            save_json_obj_to_path(entry_dict_list, out_dir_path / f"{ts_str}.json")
            ts_to_stat_dict[ts_str] = get_stat_dict_from_entry_dict_list(entry_dict_list, True)
            stat_dict = ts_to_stat_dict[ts_str]
            info(f"({step_int}/{len(plan_tuple_list)}) {ts_str} {order_str}：{stat_dict['entries']} 筆 {stat_dict['by_kind']}，"
                 f"腹部 {stat_dict['by_body_status']}（{time.time() - start_float:.1f} 秒）")
            if ts_str == seed_dict["minute"]:
                seed_first_entry_dict = entry_dict_list[0]
            next_entry_dict = entry_dict_list[-1] if order_str == "forward" else entry_dict_list[0]
            state_dict = get_state_dict_from_entry_dict(next_entry_dict, state_dict["ref"])
            boundary_entry_dict, boundary_label_str = next_entry_dict, f"{ts_str} 的{'最後' if order_str == 'forward' else '第一'}幀"
            run_save_progress_stage(out_dir_path, args_ns, manifest_dict, param_dict, seed_dict, ts_to_stat_dict, minute_strs,
                                    "running", None)
    except BaseException as error_obj:
        run_save_failure_stage(error_obj, ts_str, order_str, entry_dict_list, out_dir_path, args_ns, manifest_dict, param_dict,
                               seed_dict, ts_to_stat_dict, minute_strs)
        raise

    run_save_progress_stage(out_dir_path, args_ns, manifest_dict, param_dict, seed_dict, ts_to_stat_dict, minute_strs, "complete", None)
    belly_int = sum(stat_dict["by_body_status"].get("predicted", 0) for stat_dict in ts_to_stat_dict.values())
    if belly_int:
        warn(f"共有 {belly_int} 筆腹部找不到、改用相對位置推算（body_status=predicted，信心低）")
    success(f"part_3.0 完成：{len(minute_strs)} 個分鐘的 json。輸出：{out_dir_path}")


def main() -> None:
    run_main_stage(run_all_stages, sys.argv[1:])


if __name__ == "__main__":
    main()
