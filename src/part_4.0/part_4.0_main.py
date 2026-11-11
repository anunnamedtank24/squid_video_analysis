#!/usr/bin/env python3
from __future__ import annotations

import math
import json
import os
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True

USAGE_STR = "part_4.0：依 part_3.0 的兩眼位置，在以雙眼為準的橢圓內找烏賊的腹部，每個有眼睛結果的幀輸出腹部圓心與半徑。一分鐘輸出一個 json。\n用法：python src/part_4.0/part_4.0_main.py MANIFEST_JSON START_MIN END_MIN"


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
    print_banner("part_4.0_main.py")

from tool_main import (BLOB_DEFAULT_DICT, BLOB_RULE_DICT_DICT, NAN_FLOAT, XyrType, XyrzType, XyType, check_blob_param_dict,
                       check_deps_are_available, check_input_sha_in_meta_dict, gen_index_sec_gray_from_mp4_path,
                       get_belly_xyr_from_rel_and_eyes, get_config_dict_from_path, get_count_dict_from_strs,
                       get_fit_xyr_method_tuple_from_img_arr, get_img_arr_from_gray_arr, get_inputs_dict_from_part_strs,
                       get_json_obj_from_path, get_meta_dict_from_part_dir, get_minute_strs_from_range, get_now_str,
                       get_param_dict_from_config_dict, get_part_dir_path, get_rel_dict_from_xyrs, get_scale_msg_str_from_param_dict,
                       get_seed_dict_from_part_dir, get_xyrz_list_from_img_arr, is_finite_num, run_prepare_part_dir_stage,
                       save_json_obj_to_path)
from tool_manifest import (get_args_ns_from_argv_strs, info, run_main_stage, success, warn)

PART_STR = "part_4.0"
REL_KEY_STR_TUPLE = ("u", "v", "belly_r_rel")
BODY_DEFAULT_DICT: dict = {
    "body_r_ratio": [0.3, 4.0],
    "body_zone_par": 0.4,
    "body_zone_perp": 0.8,
    "body_k_z": 2.0,
    "body_k_z_edge": 8.0,
    "body_trust_z": 15.0,
}
BODY_RULE_DICT_DICT: dict[str, dict] = {
    "body_r_ratio": {"type": "float_pair", "min": 0, "min_open": True},
    "body_zone_par": {"type": "float", "min": 0, "min_open": True},
    "body_zone_perp": {"type": "float", "min": 0, "min_open": True},
    "body_k_z": {"type": "float", "min": 0, "min_open": True},
    "body_k_z_edge": {"type": "float", "min": 0, "min_open": True},
    "body_trust_z": {"type": "float", "min": 0, "min_open": True},
}
DEFAULT_PARAM_DICT: dict = {**BLOB_DEFAULT_DICT, **BODY_DEFAULT_DICT}
RULE_DICT_DICT: dict[str, dict] = {**BLOB_RULE_DICT_DICT, **BODY_RULE_DICT_DICT}


def check_body_param_dict(param_dict: dict) -> None:
    if param_dict["body_k_z_edge"] < param_dict["body_k_z"]:
        raise ValueError(f"[Error] config.json 的 part_4.0.body_k_z_edge（{param_dict['body_k_z_edge']}）不可小於 body_k_z（{param_dict['body_k_z']}）")


def check_part_3_is_complete(meta_3_dict: dict) -> None:
    if meta_3_dict.get("status") != "complete":
        failed_dict = meta_3_dict.get("failed") or {}
        raise ValueError(f"[Error] part_3.0 還沒完整完成（status={meta_3_dict.get('status')!r}"
                         + (f"，失敗在 {failed_dict.get('minute')}{'' if failed_dict.get('frame') is None else ' 第 ' + str(failed_dict['frame']) + ' 幀'}：{str(failed_dict.get('error')).removeprefix('[Error] ')}" if failed_dict else "")
                         + "）。part_4.0 需要整個範圍的眼睛結果；請調整參數後重跑 part_3.0，可先用 part_3.5 的影片檢查")


def get_rel3_dict_from_rel_dict(rel_dict: dict) -> dict:
    return {key_str: rel_dict[key_str] for key_str in REL_KEY_STR_TUPLE}


def get_entry_dict_list_from_minute_str(part_3_dir_path: Path, minute_str: str) -> list[dict]:
    entry_dict_list = get_json_obj_from_path(part_3_dir_path / f"{minute_str}.json", f"part_3.0 的 {minute_str}.json")
    try:
        is_ok_bool = (isinstance(entry_dict_list, list) and len(entry_dict_list) > 0
                      and all(isinstance(entry_dict["time"], str) and isinstance(entry_dict["frame"], int)
                              and isinstance(entry_dict["kind"], str)
                              and all(len(entry_dict[key_str]) == 2 and all(is_finite_num(num) for num in entry_dict[key_str])
                                      for key_str in ("right_eye", "left_eye"))
                              and all(is_finite_num(entry_dict[key_str]) for key_str in ("right_eye_r", "left_eye_r"))
                              for entry_dict in entry_dict_list))
    except (KeyError, TypeError):
        is_ok_bool = False
    if not is_ok_bool:
        raise ValueError(f"[Error] part_3.0 的 {minute_str}.json 必須是非空的 list，且每筆都有字串 time / kind、整數 frame、"
                         "兩眼的座標與半徑")
    if len({entry_dict["time"] for entry_dict in entry_dict_list}) != len(entry_dict_list):
        raise ValueError(f"[Error] part_3.0 的 {minute_str}.json 有重複的 time")
    return sorted(entry_dict_list, key=lambda entry_dict: entry_dict["frame"])


def get_eye_xyrs_from_entry_dict(entry_dict: dict) -> tuple[XyrType, XyrType]:
    return (*entry_dict["right_eye"], entry_dict["right_eye_r"]), (*entry_dict["left_eye"], entry_dict["left_eye_r"])


def get_zone_tuple_from_eyes_and_center(right_xyr: XyrType, left_xyr: XyrType, center_xyr: XyrType,
                                        param_dict: dict) -> tuple[float, float, float, float, float]:
    eye_x_float, eye_y_float = left_xyr[0] - right_xyr[0], left_xyr[1] - right_xyr[1]
    dist_float = math.hypot(eye_x_float, eye_y_float)
    return (center_xyr[0], center_xyr[1], param_dict["body_zone_par"] * dist_float, param_dict["body_zone_perp"] * dist_float,
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
    zone_tuple = get_zone_tuple_from_eyes_and_center(right_xyr, left_xyr, center_xyr, param_dict)
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


def is_belly_trusted(belly_dict: dict, param_dict: dict) -> bool:
    return belly_dict["status"] == "detected" and belly_dict["score"] >= param_dict["body_trust_z"]


def get_rel_dict_from_belly_dict(right_xyr: XyrType, left_xyr: XyrType, belly_dict: dict, rel_dict: dict, param_dict: dict) -> dict:
    if is_belly_trusted(belly_dict, param_dict):
        return get_rel3_dict_from_rel_dict(get_rel_dict_from_xyrs(right_xyr, left_xyr, belly_dict["xyr"]))
    return rel_dict


def get_out_entry_dict_from_belly_dict(entry_dict: dict, belly_dict: dict, rel_dict: dict) -> dict:
    belly_xyr = belly_dict["xyr"]
    return {"time": entry_dict["time"], "minute": entry_dict["minute"], "frame": entry_dict["frame"], "sec": entry_dict["sec"],
            "kind": entry_dict["kind"],
            "body": [round(belly_xyr[0], 3), round(belly_xyr[1], 3)], "body_r": round(belly_xyr[2], 3),
            "body_status": belly_dict["status"],
            "body_score": round(belly_dict["score"], 3) if belly_dict["status"] == "detected" else NAN_FLOAT,
            "rel": {key_str: round(rel_dict[key_str], 4) for key_str in REL_KEY_STR_TUPLE},
            "body_zone": [round(num, 3) for num in belly_dict["zone"]], "fit": belly_dict["fit"]}


def get_index_to_gray_dict_from_mp4_path(mp4_path: Path, wanted_ints: list[int]) -> dict[int, "np.ndarray"]:
    wanted_set = set(wanted_ints)
    index_to_gray_dict: dict[int, "np.ndarray"] = {}
    for index_int, _, gray_arr in gen_index_sec_gray_from_mp4_path(mp4_path):
        if index_int in wanted_set:
            index_to_gray_dict[index_int] = gray_arr
        if index_int >= max(wanted_set):
            break
    missing_ints = sorted(wanted_set - set(index_to_gray_dict))
    if missing_ints:
        raise ValueError(f"[Error] {mp4_path} 解碼不出第 {missing_ints[:5]} 幀等 {len(missing_ints)} 幀（影片比 part_3.0 記錄的短？）")
    return index_to_gray_dict


def run_minute_stage(minute_str: str, mp4_path: Path, entry_dict_list: list[dict], order_str: str, rel_dict: dict,
                     ref_rel_dict: dict, param_dict: dict) -> tuple[list[dict], dict]:
    index_to_gray_dict = get_index_to_gray_dict_from_mp4_path(mp4_path, [entry_dict["frame"] for entry_dict in entry_dict_list])
    out_dict_list: list[dict] = []
    for entry_dict in (entry_dict_list if order_str == "forward" else entry_dict_list[::-1]):
        right_xyr, left_xyr = get_eye_xyrs_from_entry_dict(entry_dict)
        img_arr = get_img_arr_from_gray_arr(index_to_gray_dict[entry_dict["frame"]], param_dict)
        belly_dict = get_belly_dict_from_img_arr(img_arr, right_xyr, left_xyr, rel_dict, ref_rel_dict, param_dict)
        rel_dict = get_rel_dict_from_belly_dict(right_xyr, left_xyr, belly_dict, rel_dict, param_dict)
        out_dict_list.append(get_out_entry_dict_from_belly_dict(entry_dict, belly_dict, rel_dict))
    out_dict_list.sort(key=lambda out_dict: out_dict["frame"])
    return out_dict_list, rel_dict


def get_stat_dict_from_out_dict_list(out_dict_list: list[dict]) -> dict:
    return {"entries": len(out_dict_list),
            "by_body_status": get_count_dict_from_strs([out_dict["body_status"] for out_dict in out_dict_list])}


def get_meta_dict_from_stage_results(args_ns: object, manifest_dict: dict, param_dict: dict, seed_dict: dict,
                                     ts_to_stat_dict: dict[str, dict]) -> dict:
    return {"kind": PART_STR, "start_min": args_ns.start_min, "end_min": args_ns.end_min, "params": param_dict,
            "inputs": get_inputs_dict_from_part_strs(manifest_dict, args_ns.start_min, args_ns.end_min, ["part_2.5", "part_3.0", "part_2.0"]),
            "seed": {"minute": seed_dict["minute"], "frame": 0, "rel": get_rel3_dict_from_rel_dict(seed_dict["rel"])},
            "minutes": dict(sorted(ts_to_stat_dict.items())), "created_at": get_now_str()}


def run_all_stages(argv_strs: list[str]) -> None:
    check_deps_are_available()
    args_ns = get_args_ns_from_argv_strs("part_4.0", USAGE_STR, argv_strs)
    manifest_dict = args_ns.manifest_dict
    config_dict = get_config_dict_from_path(manifest_dict["config_path"])
    param_dict = get_param_dict_from_config_dict(config_dict, PART_STR, DEFAULT_PARAM_DICT, RULE_DICT_DICT)
    check_blob_param_dict(param_dict)
    check_body_param_dict(param_dict)
    info(get_scale_msg_str_from_param_dict(param_dict))

    meta_3_dict = get_meta_dict_from_part_dir(manifest_dict, args_ns.start_min, args_ns.end_min, "part_3.0")
    check_input_sha_in_meta_dict(meta_3_dict, "part_2.5", manifest_dict, args_ns.start_min, args_ns.end_min)
    check_input_sha_in_meta_dict(meta_3_dict, "part_2.0", manifest_dict, args_ns.start_min, args_ns.end_min)
    check_part_3_is_complete(meta_3_dict)
    minute_strs = get_minute_strs_from_range(args_ns.start_min, args_ns.end_min)
    in_dir_path = get_part_dir_path(manifest_dict, args_ns.start_min, args_ns.end_min, "part_2.5") / "mp4s"
    part_3_dir_path = get_part_dir_path(manifest_dict, args_ns.start_min, args_ns.end_min, "part_3.0")
    seed_dict = get_seed_dict_from_part_dir(manifest_dict, args_ns.start_min, args_ns.end_min, need_belly_bool=True)
    ref_rel_dict = get_rel3_dict_from_rel_dict(seed_dict["rel"])
    seed_index_int = minute_strs.index(seed_dict["minute"])
    info(f"種子：{seed_dict['minute']} 第 0 秒；腹部相對位置 u={ref_rel_dict['u']:.2f} v={ref_rel_dict['v']:.2f}、半徑比 {ref_rel_dict['belly_r_rel']:.2f}"
         "（橢圓的中心固定用它）。先往後處理，再往前")

    out_dir_path = get_part_dir_path(manifest_dict, args_ns.start_min, args_ns.end_min, PART_STR)
    run_prepare_part_dir_stage(out_dir_path)
    plan_tuple_list = ([(ts_str, "forward") for ts_str in minute_strs[seed_index_int:]]
                       + [(ts_str, "backward") for ts_str in reversed(minute_strs[:seed_index_int])])
    ts_to_stat_dict: dict[str, dict] = {}
    rel_dict = ref_rel_dict
    seed_first_rel_dict = ref_rel_dict
    for step_int, (ts_str, order_str) in enumerate(plan_tuple_list, start=1):
        if order_str == "backward" and ts_str == minute_strs[seed_index_int - 1]:
            rel_dict = seed_first_rel_dict
        start_float = time.time()
        entry_dict_list = get_entry_dict_list_from_minute_str(part_3_dir_path, ts_str)
        out_dict_list, rel_dict = run_minute_stage(ts_str, in_dir_path / f"{ts_str}.mp4", entry_dict_list, order_str, rel_dict,
                                                   ref_rel_dict, param_dict)
        save_json_obj_to_path(out_dict_list, out_dir_path / f"{ts_str}.json")
        ts_to_stat_dict[ts_str] = get_stat_dict_from_out_dict_list(out_dict_list)
        if ts_str == seed_dict["minute"]:
            seed_first_rel_dict = get_rel3_dict_from_rel_dict(out_dict_list[0]["rel"])
        info(f"({step_int}/{len(plan_tuple_list)}) {ts_str} {order_str}：{len(out_dict_list)} 筆，腹部 {ts_to_stat_dict[ts_str]['by_body_status']}"
             f"（{time.time() - start_float:.1f} 秒）")

    save_json_obj_to_path(get_meta_dict_from_stage_results(args_ns, manifest_dict, param_dict, seed_dict, ts_to_stat_dict),
                          out_dir_path / "meta.json")
    predicted_int = sum(stat_dict["by_body_status"].get("predicted", 0) for stat_dict in ts_to_stat_dict.values())
    if predicted_int:
        warn(f"共有 {predicted_int} 筆腹部找不到、改用相對位置推算（body_status=predicted，信心低）")
    success(f"part_4.0 完成：{len(minute_strs)} 個分鐘的 json。輸出：{out_dir_path}")


def main() -> None:
    run_main_stage(run_all_stages, sys.argv[1:])


if __name__ == "__main__":
    main()
