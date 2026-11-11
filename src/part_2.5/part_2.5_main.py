#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

sys.dont_write_bytecode = True

USAGE_STR = "part_2.5：依 part_2.0 的四邊形，把每分鐘的 mp4 統一裁切並拉正（透視變換），輸出「一分鐘一個」拉正後的 mp4。\n用法：python src/part_2.5/part_2.5_main.py MANIFEST_JSON START_MIN END_MIN"


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
    print_banner("part_2.5_main.py")

from tool_main import (WhType, XyType, check_deps_are_available, check_input_sha_in_meta_dict,
                       get_config_dict_from_path, get_files_dict_from_part_1_5, get_inputs_dict_from_part_strs,
                       get_json_obj_from_path, get_meta_dict_from_part_dir, get_minute_strs_from_range, get_now_str,
                       get_param_dict_from_config_dict, get_part_dir_path, get_rectified_arr_from_arr,
                       get_transform_from_xys, np, run_encode_mp4_stage, run_prepare_part_dir_stage,
                       save_json_obj_to_path)
from tool_manifest import (get_args_ns_from_argv_strs, info, run_main_stage, success)

PART_STR = "part_2.5"
X264_CRF_STR = "10"
MPEG4_QSCALE_STR = "2"


def get_roi_dict_from_part_dir(manifest_dict: dict, start_min_str: str, end_min_str: str) -> dict:
    roi_dict = get_json_obj_from_path(get_part_dir_path(manifest_dict, start_min_str, end_min_str, "part_2.0") / "roi.json",
                                      "part_2.0 的 roi.json")
    try:
        is_ok_bool = (roi_dict["kind"] == "roi_quad" and len(roi_dict["points"]) == 4
                      and all(len(xy) == 2 for xy in roi_dict["points"]) and len(roi_dict["frame_size"]) == 2)
    except (KeyError, TypeError):
        is_ok_bool = False
    if not is_ok_bool:
        raise ValueError("[Error] part_2.0 的 roi.json 格式不對（需要 kind=roi_quad、frame_size、4 個 points）。請重新執行 part_2.0")
    return roi_dict


def check_roi_dict_matches_frame_wh(roi_dict: dict, frame_wh: WhType) -> None:
    if tuple(roi_dict["frame_size"]) != tuple(frame_wh):
        raise ValueError(f"[Error] roi.json 是在 {roi_dict['frame_size'][0]}×{roi_dict['frame_size'][1]} 的影格上選的，"
                         f"但 part_1.5 記錄的影格是 {frame_wh[0]}×{frame_wh[1]}。請重新執行 part_1.5 與 part_2.0")


def get_convert_func_from_matrix_arr(matrix_arr: "np.ndarray", out_wh: WhType,
                                     frame_wh: WhType) -> Callable[[int, float, "np.ndarray"], "np.ndarray"]:
    def get_converted_arr_from_bgr_arr(index_int: int, sec_float: float, bgr_arr: "np.ndarray") -> "np.ndarray":
        if (bgr_arr.shape[1], bgr_arr.shape[0]) != tuple(frame_wh):
            raise ValueError(f"[Error] 第 {index_int} 幀尺寸 {bgr_arr.shape[1]}×{bgr_arr.shape[0]}，與 part_1.5 記錄的 "
                             f"{frame_wh[0]}×{frame_wh[1]} 不同")
        return get_rectified_arr_from_arr(bgr_arr, matrix_arr, out_wh)
    return get_converted_arr_from_bgr_arr


def run_minute_stage(ts_str: str, in_mp4_path: Path, out_mp4_path: Path, matrix_arr: "np.ndarray", out_wh: WhType,
                     frame_wh: WhType) -> dict:
    return run_encode_mp4_stage(in_mp4_path, out_mp4_path, out_wh, get_convert_func_from_matrix_arr(matrix_arr, out_wh, frame_wh),
                                X264_CRF_STR, MPEG4_QSCALE_STR)


def get_meta_dict_from_stage_results(args_ns: object, manifest_dict: dict, roi_dict: dict, matrix_arr: "np.ndarray",
                                     out_wh: WhType, ts_to_stat_dict: dict[str, dict]) -> dict:
    return {"kind": PART_STR, "start_min": args_ns.start_min, "end_min": args_ns.end_min, "params": {},
            "inputs": get_inputs_dict_from_part_strs(manifest_dict, args_ns.start_min, args_ns.end_min, ["part_1.5", "part_2.0"]),
            "roi_reference_minute": roi_dict["reference_minute"], "frame_size": roi_dict["frame_size"],
            "rectified_size": list(out_wh), "homography": matrix_arr.tolist(), "minutes": ts_to_stat_dict,
            "created_at": get_now_str()}


def run_all_stages(argv_strs: list[str]) -> None:
    check_deps_are_available()
    args_ns = get_args_ns_from_argv_strs("part_2.5", USAGE_STR, argv_strs)
    manifest_dict = args_ns.manifest_dict
    config_dict = get_config_dict_from_path(manifest_dict["config_path"])
    get_param_dict_from_config_dict(config_dict, PART_STR, {}, {})

    get_meta_dict_from_part_dir(manifest_dict, args_ns.start_min, args_ns.end_min, "part_1.5")
    meta_2_dict = get_meta_dict_from_part_dir(manifest_dict, args_ns.start_min, args_ns.end_min, "part_2.0")
    check_input_sha_in_meta_dict(meta_2_dict, "part_1.5", manifest_dict, args_ns.start_min, args_ns.end_min)
    ts_to_path_dict, frame_wh = get_files_dict_from_part_1_5(manifest_dict, args_ns.start_min, args_ns.end_min)
    roi_dict = get_roi_dict_from_part_dir(manifest_dict, args_ns.start_min, args_ns.end_min)
    check_roi_dict_matches_frame_wh(roi_dict, frame_wh)
    ordered_xys: list[XyType] = [(xy[0], xy[1]) for xy in roi_dict["points"]]
    matrix_arr, out_wh = get_transform_from_xys(ordered_xys, frame_wh)
    info(f"四邊形 {[[round(x, 1), round(y, 1)] for x, y in ordered_xys]} → 拉正後 {out_wh[0]}×{out_wh[1]}")

    minute_strs = get_minute_strs_from_range(args_ns.start_min, args_ns.end_min)
    part_dir_path = get_part_dir_path(manifest_dict, args_ns.start_min, args_ns.end_min, PART_STR)
    run_prepare_part_dir_stage(part_dir_path)
    (part_dir_path / "mp4s").mkdir()
    files_obj = get_json_obj_from_path(get_part_dir_path(manifest_dict, args_ns.start_min, args_ns.end_min, "part_1.5") / "files.json",
                                       "part_1.5 的 files.json")
    ts_to_stat_dict: dict[str, dict] = {}
    for index_int, ts_str in enumerate(minute_strs, start=1):
        stat_dict = run_minute_stage(ts_str, ts_to_path_dict[ts_str], part_dir_path / "mp4s" / f"{ts_str}.mp4", matrix_arr,
                                     out_wh, frame_wh)
        if stat_dict["frames"] != files_obj["minutes"][ts_str]["frames"]:
            raise ValueError(f"[Error] {ts_str} 拉正後 {stat_dict['frames']} 幀，與 part_1.5 記錄的 "
                             f"{files_obj['minutes'][ts_str]['frames']} 幀不同（解碼不完整？）")
        ts_to_stat_dict[ts_str] = stat_dict
        info(f"({index_int}/{len(minute_strs)}) {ts_str}  {stat_dict['frames']} 幀  {stat_dict['duration_s']} 秒  {stat_dict['codec']}  → mp4s/{ts_str}.mp4")

    save_json_obj_to_path(get_meta_dict_from_stage_results(args_ns, manifest_dict, roi_dict, matrix_arr, out_wh, ts_to_stat_dict),
                          part_dir_path / "meta.json")
    success(f"part_2.5 完成：{len(minute_strs)} 個拉正後的 mp4。輸出：{part_dir_path}/mp4s/")


def main() -> None:
    run_main_stage(run_all_stages, sys.argv[1:])


if __name__ == "__main__":
    main()
