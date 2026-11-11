#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True

USAGE_STR = "part_5.5：把 part_5.0 的腹部亮度畫成「時間 — 亮暗度」折線圖（PNG）。\n用法：python src/part_5.5/part_5.5_main.py MANIFEST_JSON START_MIN END_MIN"


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
    print_banner("part_5.5_main.py")

from tool_main import (check_deps_are_available, get_config_dict_from_path, get_inputs_dict_from_part_strs, get_json_obj_from_path,
                       get_meta_dict_from_part_dir, get_minute_strs_from_range, get_now_str, get_param_dict_from_config_dict,
                       get_part_dir_path, np, run_prepare_part_dir_stage, save_json_obj_to_path)
from tool_manifest import (get_args_ns_from_argv_strs, info, run_main_stage, success, warn)

PART_STR = "part_5.5"
PNG_NAME_STR = "brightness.png"
TIME_FORMAT_STR = "%Y-%m-%dT%H:%M:%S.%f"
INK_HEX_STR, MUTED_HEX_STR, GRID_HEX_STR, SURFACE_HEX_STR = "#1f2933", "#6b7785", "#e3e7ec", "#ffffff"
GRAY_LINE_HEX_STR, BG_LINE_HEX_STR, PREDICTED_HEX_STR = "#2f4b7c", "#9aa5b1", "#d1495b"
CHANNEL_HEX_DICT = {"mean_r": "#d1495b", "mean_g": "#2e8b57", "mean_b": "#3b6fb6"}
CHANNEL_LABEL_DICT = {"mean_r": "R", "mean_g": "G", "mean_b": "B"}
DEFAULT_PARAM_DICT: dict = {
    "width_in": 16.0,
    "height_in": 8.0,
    "dpi": 150,
    "line_width": 0.8,
    "show_channels": True,
    "show_bg": False,
    "mark_predicted": True,
}
RULE_DICT_DICT: dict[str, dict] = {
    "width_in": {"type": "float", "min": 2, "max": 60},
    "height_in": {"type": "float", "min": 2, "max": 40},
    "dpi": {"type": "int", "min": 50, "max": 400},
    "line_width": {"type": "float", "min": 0.1, "max": 5},
    "show_channels": {"type": "bool"},
    "show_bg": {"type": "bool"},
    "mark_predicted": {"type": "bool"},
}


def get_plt_module():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error_obj:
        raise ImportError(f"[Error] 缺少 matplotlib（{error_obj}）。請在專案 venv 內執行：pip install -r requirements.txt") from error_obj
    return plt


def get_value_dict_from_json_obj(json_obj: object, minute_str: str) -> dict[str, dict]:
    if not (isinstance(json_obj, dict) and json_obj and all(isinstance(value_dict, dict) for value_dict in json_obj.values())):
        raise ValueError(f"[Error] part_5.0 的 {minute_str}.json 必須是非空的 dict（key = 時間，value = dict）")
    for time_str, value_dict in json_obj.items():
        is_ok_bool = (all(key_str in value_dict for key_str in ("mean", "mean_b", "mean_g", "mean_r", "bg_mean", "status", "body_status"))
                      and all(isinstance(value_dict[key_str], (int, float)) and not isinstance(value_dict[key_str], bool)
                              for key_str in ("mean", "mean_b", "mean_g", "mean_r", "bg_mean")))
        try:
            datetime.strptime(time_str, TIME_FORMAT_STR)
        except ValueError:
            is_ok_bool = False
        if not is_ok_bool:
            raise ValueError(f"[Error] part_5.0 的 {minute_str}.json 的 {time_str!r} 格式不對：key 必須是 YYYY-MM-DDTHH:MM:SS.mmm，"
                             "value 必須有數字的 mean / mean_b / mean_g / mean_r / bg_mean 與 status / body_status")
    return json_obj


def get_series_dict_from_value_dicts(time_to_value_dict: dict[str, dict]) -> dict:
    time_strs = sorted(time_to_value_dict)
    return {"time": [datetime.strptime(time_str, TIME_FORMAT_STR) for time_str in time_strs],
            **{key_str: np.array([time_to_value_dict[time_str][key_str] for time_str in time_strs], dtype=np.float64)
               for key_str in ("mean", "mean_b", "mean_g", "mean_r", "bg_mean")},
            "predicted": np.array([time_to_value_dict[time_str]["body_status"] == "predicted" for time_str in time_strs]),
            "ok": np.array([time_to_value_dict[time_str]["status"] == "ok" for time_str in time_strs])}


def get_all_time_to_value_dict(part_5_dir_path: Path, minute_strs: list[str]) -> dict[str, dict]:
    all_dict: dict[str, dict] = {}
    for minute_str in minute_strs:
        minute_dict = get_value_dict_from_json_obj(get_json_obj_from_path(part_5_dir_path / f"{minute_str}.json",
                                                                          f"part_5.0 的 {minute_str}.json"), minute_str)
        duplicate_strs = sorted(set(minute_dict) & set(all_dict))
        if duplicate_strs:
            raise ValueError(f"[Error] part_5.0 的 {minute_str}.json 有與其他分鐘重複的時間 {duplicate_strs[:3]}")
        all_dict.update(minute_dict)
    return all_dict


def init_axis(ax_obj, ylabel_str: str) -> None:
    ax_obj.set_facecolor(SURFACE_HEX_STR)
    ax_obj.grid(True, color=GRID_HEX_STR, linewidth=0.6)
    ax_obj.set_axisbelow(True)
    for side_str in ("top", "right"):
        ax_obj.spines[side_str].set_visible(False)
    for side_str in ("left", "bottom"):
        ax_obj.spines[side_str].set_color(MUTED_HEX_STR)
    ax_obj.tick_params(colors=MUTED_HEX_STR, labelsize=9)
    ax_obj.set_ylabel(ylabel_str, color=INK_HEX_STR, fontsize=10)


def draw_gray_panel(ax_obj, series_dict: dict, param_dict: dict) -> None:
    init_axis(ax_obj, "Mean gray inside circle (0-255)")
    ax_obj.plot(series_dict["time"], series_dict["mean"], color=GRAY_LINE_HEX_STR, linewidth=param_dict["line_width"], label="Belly mean gray")
    if param_dict["show_bg"]:
        ax_obj.plot(series_dict["time"], series_dict["bg_mean"], color=BG_LINE_HEX_STR, linewidth=param_dict["line_width"],
                    linestyle="--", label="Background ring mean gray")
    if param_dict["mark_predicted"] and series_dict["predicted"].any():
        mask_arr = series_dict["predicted"]
        ax_obj.scatter([time_dt for time_dt, flag_bool in zip(series_dict["time"], mask_arr) if flag_bool], series_dict["mean"][mask_arr],
                       s=14, marker="x", color=PREDICTED_HEX_STR, linewidths=0.9, label="Belly position predicted (low confidence)", zorder=3)
    legend_obj = ax_obj.legend(loc="upper right", fontsize=9, frameon=False)
    for text_obj in legend_obj.get_texts():
        text_obj.set_color(INK_HEX_STR)


def draw_channel_panel(ax_obj, series_dict: dict, param_dict: dict) -> None:
    init_axis(ax_obj, "Mean per channel (0-255)")
    for key_str, hex_str in CHANNEL_HEX_DICT.items():
        ax_obj.plot(series_dict["time"], series_dict[key_str], color=hex_str, linewidth=param_dict["line_width"], label=CHANNEL_LABEL_DICT[key_str])
    legend_obj = ax_obj.legend(loc="upper right", fontsize=9, frameon=False, ncol=3)
    for text_obj in legend_obj.get_texts():
        text_obj.set_color(INK_HEX_STR)


def get_title_str(args_ns: object, meta_5_dict: dict, series_dict: dict) -> str:
    return (f"Belly brightness over time   {series_dict['time'][0]:%Y-%m-%d %H:%M} to {series_dict['time'][-1]:%Y-%m-%d %H:%M}   "
            f"(fixed radius r = {meta_5_dict['params']['r']} px, {len(series_dict['time'])} points)")


def save_figure_to_path(series_dict: dict, title_str: str, param_dict: dict, png_path: Path) -> None:
    plt = get_plt_module()
    import matplotlib.dates as mdates
    panel_int = 2 if param_dict["show_channels"] else 1
    fig_obj, ax_objs = plt.subplots(panel_int, 1, figsize=(param_dict["width_in"], param_dict["height_in"]), sharex=True, squeeze=False,
                                    facecolor=SURFACE_HEX_STR)
    draw_gray_panel(ax_objs[0][0], series_dict, param_dict)
    if param_dict["show_channels"]:
        draw_channel_panel(ax_objs[1][0], series_dict, param_dict)
    locator_obj = mdates.AutoDateLocator(minticks=4, maxticks=14)
    ax_objs[-1][0].xaxis.set_major_locator(locator_obj)
    ax_objs[-1][0].xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator_obj))
    ax_objs[-1][0].set_xlabel("Time", color=INK_HEX_STR, fontsize=10)
    fig_obj.suptitle(title_str, color=INK_HEX_STR, fontsize=12, x=0.01, ha="left")
    fig_obj.tight_layout(rect=(0, 0, 1, 0.97))
    fig_obj.savefig(png_path, dpi=param_dict["dpi"], facecolor=SURFACE_HEX_STR)
    plt.close(fig_obj)


def get_stat_dict_from_series_dict(series_dict: dict) -> dict:
    ok_arr = series_dict["ok"] & np.isfinite(series_dict["mean"])
    mean_arr = series_dict["mean"][ok_arr]
    return {"points": len(series_dict["time"]), "points_ok": int(ok_arr.sum()), "points_predicted": int(series_dict["predicted"].sum()),
            "first_time": series_dict["time"][0].strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3],
            "last_time": series_dict["time"][-1].strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3],
            "mean_gray": {"min": round(float(mean_arr.min()), 3), "max": round(float(mean_arr.max()), 3),
                          "average": round(float(mean_arr.mean()), 3)} if mean_arr.size else None}


def run_all_stages(argv_strs: list[str]) -> None:
    check_deps_are_available()
    args_ns = get_args_ns_from_argv_strs("part_5.5", USAGE_STR, argv_strs)
    manifest_dict = args_ns.manifest_dict
    config_dict = get_config_dict_from_path(manifest_dict["config_path"])
    param_dict = get_param_dict_from_config_dict(config_dict, PART_STR, DEFAULT_PARAM_DICT, RULE_DICT_DICT)
    get_plt_module()

    meta_5_dict = get_meta_dict_from_part_dir(manifest_dict, args_ns.start_min, args_ns.end_min, "part_5.0")
    minute_strs = get_minute_strs_from_range(args_ns.start_min, args_ns.end_min)
    part_5_dir_path = get_part_dir_path(manifest_dict, args_ns.start_min, args_ns.end_min, "part_5.0")
    missing_strs = [ts_str for ts_str in minute_strs if not (part_5_dir_path / f"{ts_str}.json").is_file()]
    if missing_strs:
        raise FileNotFoundError(f"[Error] part_5.0 缺少 {len(missing_strs)} 個分鐘的 json：{missing_strs[:5]}。請重新執行 part_5.0")
    time_to_value_dict = get_all_time_to_value_dict(part_5_dir_path, minute_strs)
    series_dict = get_series_dict_from_value_dicts(time_to_value_dict)
    stat_dict = get_stat_dict_from_series_dict(series_dict)
    info(f"讀到 {stat_dict['points']} 個點（{stat_dict['first_time']} ~ {stat_dict['last_time']}），其中腹部 predicted {stat_dict['points_predicted']} 個、"
         f"無法量測（圓在影格外）{stat_dict['points'] - stat_dict['points_ok']} 個")
    if stat_dict["points_ok"] == 0:
        raise ValueError("[Error] part_5.0 沒有任何可用的量測點（status 全部不是 ok），無法畫圖")
    if stat_dict["points_predicted"]:
        warn(f"有 {stat_dict['points_predicted']} 個點的腹部位置是推算的（predicted），圖上用紅色 × 標出；解讀亮度時請留意")

    out_dir_path = get_part_dir_path(manifest_dict, args_ns.start_min, args_ns.end_min, PART_STR)
    run_prepare_part_dir_stage(out_dir_path)
    save_figure_to_path(series_dict, get_title_str(args_ns, meta_5_dict, series_dict), param_dict, out_dir_path / PNG_NAME_STR)
    info(f"已存檔：{out_dir_path / PNG_NAME_STR}")
    save_json_obj_to_path({"kind": PART_STR, "start_min": args_ns.start_min, "end_min": args_ns.end_min, "params": param_dict,
                           "inputs": get_inputs_dict_from_part_strs(manifest_dict, args_ns.start_min, args_ns.end_min, ["part_5.0"]),
                           "png": PNG_NAME_STR, "stat": stat_dict, "created_at": get_now_str()}, out_dir_path / "meta.json")
    success(f"part_5.5 完成：{PNG_NAME_STR}。輸出：{out_dir_path}")


def main() -> None:
    run_main_stage(run_all_stages, sys.argv[1:])


if __name__ == "__main__":
    main()
