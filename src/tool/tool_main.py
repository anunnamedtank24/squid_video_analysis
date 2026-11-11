#!/usr/bin/env python3
from __future__ import annotations

import time

print("[Info] 載入 numpy / opencv / av …（第一次執行或剛更新套件時需要編譯，可能要數十秒，請稍候）", flush=True)
_LOAD_START_FLOAT = time.time()

import hashlib
import json
import math
import re
import shutil
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from fractions import Fraction
from pathlib import Path

from tool_manifest import PART_STR_TUPLE, info, warn

try:
    import av
    import cv2
    import numpy as np
except ImportError as dep_import_error:
    av = cv2 = np = None
    DEP_IMPORT_ERROR_STR = str(dep_import_error)
else:
    DEP_IMPORT_ERROR_STR = ""
print(f"[Info] 套件載入完成（{time.time() - _LOAD_START_FLOAT:.1f} 秒）", flush=True)

XyType = tuple[float, float]
WhType = tuple[int, int]
XyrType = tuple[float, float, float]
XyrzType = tuple[float, float, float, float]

NAN_FLOAT = float("nan")
HOUR_NAME_RE = re.compile(r"^\d{10}$")
MP4_NAME_RE = re.compile(r"^(\d{2})(?!\d).*\.mp4$", re.IGNORECASE)
CONFIG_KEY_STR_SET = set(PART_STR_TUPLE)

BLOB_DEFAULT_DICT: dict = {
    "polarity": "dark",
    "margin": 0.10,
    "r_min": 1.0,
    "r_max": 14.0,
    "sigma_k": 1.4,
    "k_z": 2.5,
    "max_cand": 12,
    "z_cap": 200.0,
    "size_ratio_max": 3.0,
    "eye_gap": 1.2,
    "fit_rays": 24,
    "fit_rmax_mul": 2.2,
    "fit_smooth": 0.6,
}
BLOB_RULE_DICT_DICT: dict[str, dict] = {
    "polarity": {"type": "str", "choices": ["dark", "bright"]},
    "margin": {"type": "float", "min": 0, "max": 0.4, "max_open": True},
    "r_min": {"type": "float", "min": 0, "min_open": True},
    "r_max": {"type": "float", "min": 0, "min_open": True},
    "sigma_k": {"type": "float", "min": 1, "min_open": True},
    "k_z": {"type": "float", "min": 0, "min_open": True},
    "max_cand": {"type": "int", "min": 3, "max": 200},
    "z_cap": {"type": "float", "min": 0, "min_open": True},
    "size_ratio_max": {"type": "float", "min": 1},
    "eye_gap": {"type": "float", "min": 0},
    "fit_rays": {"type": "int", "min": 8, "max": 360},
    "fit_rmax_mul": {"type": "float", "min": 1, "min_open": True},
    "fit_smooth": {"type": "float", "min": 0, "min_open": True},
}


def get_now_str() -> str:
    return datetime.now().isoformat(timespec="seconds")


def is_finite_num(obj: object) -> bool:
    return isinstance(obj, (int, float)) and not isinstance(obj, bool) and math.isfinite(obj)


def is_xy_finite(xy_obj: object) -> bool:
    return isinstance(xy_obj, (list, tuple)) and len(xy_obj) == 2 and all(is_finite_num(num) for num in xy_obj)


def get_count_dict_from_strs(strs: list[str]) -> dict[str, int]:
    count_dict: dict[str, int] = {}
    for item_str in strs:
        count_dict[item_str] = count_dict.get(item_str, 0) + 1
    return count_dict


def get_json_obj_from_path(json_path: Path, what_str: str) -> object:
    if not json_path.is_file():
        raise FileNotFoundError(f"[Error] 找不到{what_str}：{json_path}")
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error_obj:
        raise ValueError(f"[Error] {what_str}不是合法的 JSON：{json_path}（{error_obj}）") from error_obj


def save_json_obj_to_path(json_obj: object, json_path: Path, indent_int: int = 1) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = json_path.with_suffix(json_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(json_obj, ensure_ascii=False, indent=indent_int), encoding="utf-8")
    tmp_path.replace(json_path)
    info(f"已存檔：{json_path}")


def get_sha256_str_from_path(file_path: Path) -> str:
    sha_obj = hashlib.sha256()
    with open(file_path, "rb") as file_obj:
        for chunk_bytes in iter(lambda: file_obj.read(1 << 20), b""):
            sha_obj.update(chunk_bytes)
    return sha_obj.hexdigest()


def check_deps_are_available() -> None:
    if DEP_IMPORT_ERROR_STR:
        raise ImportError(f"[Error] 缺少套件（{DEP_IMPORT_ERROR_STR}）。"
                          "請在專案 venv 內執行：pip install -r requirements.txt")


def check_config_dict(config_dict: object) -> None:
    if not isinstance(config_dict, dict):
        raise ValueError("[Error] config.json 最外層必須是 JSON 物件 {...}")
    unknown_strs = sorted(set(config_dict) - CONFIG_KEY_STR_SET)
    if unknown_strs:
        raise ValueError(f"[Error] config.json 有不認得的欄位 {unknown_strs}；允許的欄位：{sorted(CONFIG_KEY_STR_SET)}")
    for section_str in PART_STR_TUPLE:
        if section_str in config_dict and not isinstance(config_dict[section_str], dict):
            raise ValueError(f"[Error] config.json 的 {section_str} 必須是 JSON 物件 {{...}}")


def get_config_dict_from_path(config_path: Path) -> dict:
    config_dict = get_json_obj_from_path(config_path, "設定檔 config.json")
    check_config_dict(config_dict)
    info(f"已讀取設定：{config_path}")
    return config_dict


def check_assets_dir_path(assets_dir_path: Path) -> None:
    if not assets_dir_path.is_dir():
        raise FileNotFoundError(f"[Error] assets 資料夾不存在：{assets_dir_path}（manifest 的 assets）")


def check_num_in_range_by_rule_dict(label_str: str, num: float, rule_dict: dict) -> None:
    low_num, high_num = rule_dict.get("min"), rule_dict.get("max")
    too_low_bool = low_num is not None and (num <= low_num if rule_dict.get("min_open") else num < low_num)
    too_high_bool = high_num is not None and (num >= high_num if rule_dict.get("max_open") else num > high_num)
    if too_low_bool or too_high_bool:
        low_str = "-∞" if low_num is None else f"{'(' if rule_dict.get('min_open') else '['}{low_num}"
        high_str = "∞)" if high_num is None else f"{high_num}{')' if rule_dict.get('max_open') else ']'}"
        raise ValueError(f"[Error] {label_str} 必須在 {low_str}, {high_str} 之間，收到 {num}")


def check_value_by_rule_dict(label_str: str, value_obj: object, rule_dict: dict) -> None:
    type_str = rule_dict["type"]
    if value_obj is None:
        if rule_dict.get("nullable"):
            return
        raise ValueError(f"[Error] {label_str} 不可為 null")
    if type_str == "bool":
        if not isinstance(value_obj, bool):
            raise ValueError(f"[Error] {label_str} 必須是 true / false，收到 {value_obj!r}")
    elif type_str == "int":
        if not isinstance(value_obj, int) or isinstance(value_obj, bool):
            raise ValueError(f"[Error] {label_str} 必須是整數，收到 {value_obj!r}")
        check_num_in_range_by_rule_dict(label_str, value_obj, rule_dict)
    elif type_str == "float":
        if not is_finite_num(value_obj):
            raise ValueError(f"[Error] {label_str} 必須是有限的數字，收到 {value_obj!r}")
        check_num_in_range_by_rule_dict(label_str, value_obj, rule_dict)
    elif type_str == "str":
        if value_obj not in rule_dict["choices"]:
            raise ValueError(f"[Error] {label_str} 必須是 {rule_dict['choices']} 其中之一，收到 {value_obj!r}")
    elif type_str == "float_pair":
        if not (isinstance(value_obj, list) and len(value_obj) == 2 and all(is_finite_num(num) for num in value_obj)
                and value_obj[0] < value_obj[1]):
            raise ValueError(f"[Error] {label_str} 必須是 [小, 大] 兩個有限數字且小 < 大，收到 {value_obj!r}")
        for num in value_obj:
            check_num_in_range_by_rule_dict(label_str, num, rule_dict)
    else:
        raise ValueError(f"[Error] 規則表裡有不認得的型態 {type_str!r}（{label_str}）")


def get_param_dict_from_config_dict(config_dict: dict, section_str: str, default_dict: dict,
                                    rule_dict_dict: dict[str, dict]) -> dict:
    section_dict = config_dict.get(section_str, {})
    unknown_strs = sorted(set(section_dict) - set(default_dict))
    if unknown_strs:
        raise ValueError(f"[Error] config.json 的 {section_str} 有不認得的參數 {unknown_strs}；"
                         f"允許的參數：{sorted(default_dict)}")
    param_dict = {**default_dict, **section_dict}
    for key_str, value_obj in param_dict.items():
        check_value_by_rule_dict(f"config.json 的 {section_str}.{key_str}", value_obj, rule_dict_dict[key_str])
    info(f"參數 {section_str}：{json.dumps(param_dict, ensure_ascii=False)}")
    return param_dict


def get_blob_param_dict_from_config_dict(config_dict: dict) -> dict:
    section_dict = config_dict.get("part_3.0", {})
    blob_section_dict = {key_str: value_obj for key_str, value_obj in section_dict.items() if key_str in BLOB_DEFAULT_DICT}
    blob_param_dict = get_param_dict_from_config_dict({"part_3.0": blob_section_dict}, "part_3.0", BLOB_DEFAULT_DICT, BLOB_RULE_DICT_DICT)
    check_blob_param_dict(blob_param_dict)
    return blob_param_dict


def get_minute_strs_from_range(start_min_str: str, end_min_str: str) -> list[str]:
    current_dt = datetime.strptime(start_min_str, "%Y%m%d%H%M")
    last_dt = datetime.strptime(end_min_str, "%Y%m%d%H%M")
    minute_strs: list[str] = []
    while current_dt <= last_dt:
        minute_strs.append(current_dt.strftime("%Y%m%d%H%M"))
        current_dt += timedelta(minutes=1)
    return minute_strs


def get_time_str_from_minute_str(minute_str: str, sec_float: float = 0.0) -> str:
    time_dt = datetime.strptime(minute_str, "%Y%m%d%H%M") + timedelta(milliseconds=int(round(sec_float * 1000)))
    return time_dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{time_dt.microsecond // 1000:03d}"


def is_hour_name(name_str: str) -> bool:
    if not HOUR_NAME_RE.fullmatch(name_str):
        return False
    try:
        datetime.strptime(name_str, "%Y%m%d%H")
    except ValueError:
        return False
    return True


def get_minute_str_from_file_name(name_str: str) -> str | None:
    match_obj = MP4_NAME_RE.match(name_str)
    if match_obj is None or int(match_obj.group(1)) > 59:
        return None
    return match_obj.group(1)


def is_hour_dir_path(dir_path: Path) -> bool:
    return (dir_path.is_dir() and is_hour_name(dir_path.name)
            and any(child_path.is_file() and get_minute_str_from_file_name(child_path.name) is not None
                    for child_path in dir_path.iterdir()))


def gen_hour_dir_path_from_assets_dir_path(assets_dir_path: Path) -> Iterator[Path]:
    for level1_path in sorted(assets_dir_path.iterdir()):
        if not level1_path.is_dir():
            continue
        for cand_path in [level1_path, *sorted(level1_path.iterdir())]:
            if is_hour_dir_path(cand_path):
                yield cand_path


def get_ts_to_mp4_paths_dict_from_assets_dir_path(assets_dir_path: Path) -> dict[str, list[Path]]:
    ts_to_mp4_paths_dict: dict[str, list[Path]] = {}
    for hour_dir_path in gen_hour_dir_path_from_assets_dir_path(assets_dir_path):
        for file_path in sorted(hour_dir_path.iterdir()):
            minute_str = get_minute_str_from_file_name(file_path.name)
            if minute_str is not None and file_path.is_file():
                ts_to_mp4_paths_dict.setdefault(hour_dir_path.name + minute_str, []).append(file_path)
    return ts_to_mp4_paths_dict


def get_range_dir_path(manifest_dict: dict, start_min_str: str, end_min_str: str) -> Path:
    return manifest_dict["output_dir_path"] / f"{start_min_str}_{end_min_str}"


def get_part_dir_path(manifest_dict: dict, start_min_str: str, end_min_str: str, part_str: str) -> Path:
    return get_range_dir_path(manifest_dict, start_min_str, end_min_str) / part_str


def run_prepare_part_dir_stage(part_dir_path: Path) -> None:
    if part_dir_path.exists():
        info(f"覆蓋既有輸出：{part_dir_path}")
        shutil.rmtree(part_dir_path)
    part_dir_path.mkdir(parents=True)
    info(f"輸出資料夾：{part_dir_path}")


def get_yes_bool_from_prompt(prompt_str: str) -> bool:
    print(prompt_str, end="", flush=True)
    try:
        answer_str = input().strip().lower()
    except EOFError:
        print("", flush=True)
        return False
    return answer_str in ("y", "yes")


def run_overwrite_prompt_stage(range_dir_path: Path) -> None:
    if not range_dir_path.exists():
        return
    warn(f"{range_dir_path} 已經存在（裡面可能有之前的結果）")
    if not get_yes_bool_from_prompt(f"[Ask] would you like to overwrite {range_dir_path} ? 會刪除整個資料夾後重做 [y/N] "):
        raise FileExistsError(f"[Error] 使用者選擇不覆蓋 {range_dir_path}，結束")
    shutil.rmtree(range_dir_path)
    info(f"已刪除 {range_dir_path}")


def get_meta_dict_from_part_dir(manifest_dict: dict, start_min_str: str, end_min_str: str, part_str: str) -> dict:
    part_dir_path = get_part_dir_path(manifest_dict, start_min_str, end_min_str, part_str)
    if not part_dir_path.is_dir():
        raise FileNotFoundError(f"[Error] 找不到 {part_str} 的輸出資料夾：{part_dir_path}。請先執行 {part_str}")
    meta_dict = get_json_obj_from_path(part_dir_path / "meta.json", f"{part_str} 的 meta.json（沒有 = 上次沒做完）")
    if not isinstance(meta_dict, dict):
        raise ValueError(f"[Error] {part_dir_path}/meta.json 最外層必須是 JSON 物件")
    if meta_dict.get("kind") != part_str:
        raise ValueError(f"[Error] {part_dir_path}/meta.json 的 kind={meta_dict.get('kind')!r}，預期 {part_str!r}")
    if meta_dict.get("start_min") != start_min_str or meta_dict.get("end_min") != end_min_str:
        raise ValueError(f"[Error] {part_dir_path}/meta.json 的範圍 {meta_dict.get('start_min')} ~ "
                         f"{meta_dict.get('end_min')} 與這次的 {start_min_str} ~ {end_min_str} 不符")
    info(f"上游 {part_str} 檢查通過（完成時間 {meta_dict.get('created_at') or meta_dict.get('updated_at')}）")
    return meta_dict


def get_inputs_dict_from_part_strs(manifest_dict: dict, start_min_str: str, end_min_str: str,
                                   part_strs: list[str]) -> dict[str, str]:
    return {f"{part_str}_meta_sha256": get_sha256_str_from_path(
        get_part_dir_path(manifest_dict, start_min_str, end_min_str, part_str) / "meta.json")
        for part_str in part_strs}


def check_input_sha_in_meta_dict(meta_dict: dict, part_str: str, manifest_dict: dict, start_min_str: str,
                                 end_min_str: str) -> None:
    key_str = f"{part_str}_meta_sha256"
    now_str = get_sha256_str_from_path(get_part_dir_path(manifest_dict, start_min_str, end_min_str, part_str) / "meta.json")
    if meta_dict.get("inputs", {}).get(key_str) != now_str:
        raise ValueError(f"[Error] {meta_dict.get('kind')} 不是由目前的 {part_str} 算出來的（{part_str} 之後被重做過）。"
                         f"請從 {meta_dict.get('kind')} 起依序重做")


def get_files_dict_from_part_1_5(manifest_dict: dict, start_min_str: str,
                                end_min_str: str) -> tuple[dict[str, Path], WhType]:
    files_obj = get_json_obj_from_path(
        get_part_dir_path(manifest_dict, start_min_str, end_min_str, "part_1.5") / "files.json", "part_1.5 的 files.json")
    try:
        assets_dir_path = manifest_dict["assets_dir_path"]
        frame_wh = (int(files_obj["frame_size"][0]), int(files_obj["frame_size"][1]))
        ts_to_path_dict = {ts_str: assets_dir_path / minute_dict["path"] for ts_str, minute_dict in files_obj["minutes"].items()}
    except (KeyError, TypeError, ValueError, IndexError) as error_obj:
        raise ValueError(f"[Error] part_1.5 的 files.json 格式不對（{error_obj!r}）。請重新執行 part_1.5") from error_obj
    for ts_str in get_minute_strs_from_range(start_min_str, end_min_str):
        if ts_str not in ts_to_path_dict:
            raise ValueError(f"[Error] part_1.5 的 files.json 缺少 {ts_str}。請重新執行 part_1.5")
        if not ts_to_path_dict[ts_str].is_file():
            raise FileNotFoundError(f"[Error] {ts_str} 的 mp4 已不存在：{ts_to_path_dict[ts_str]}")
    return ts_to_path_dict, frame_wh


def get_fps_frac_from_stream(stream_obj: "av.video.stream.VideoStream") -> Fraction:
    return Fraction(stream_obj.average_rate or stream_obj.guessed_rate or 25)


def get_probe_dict_from_mp4_path(mp4_path: Path) -> dict:
    try:
        with av.open(str(mp4_path)) as container_obj:
            if not container_obj.streams.video:
                raise ValueError("檔案內沒有影像串流")
            stream_obj = container_obj.streams.video[0]
            fps_float = float(get_fps_frac_from_stream(stream_obj))
            wh = (stream_obj.codec_context.width, stream_obj.codec_context.height)
            pts_ints = sorted(packet_obj.pts for packet_obj in container_obj.demux(stream_obj)
                              if packet_obj.pts is not None and packet_obj.size > 0)
            time_base_frac = stream_obj.time_base
    except (av.error.FFmpegError, ValueError) as error_obj:
        raise ValueError(f"[Error] mp4 損壞或無法讀取：{mp4_path}（{error_obj}）") from error_obj
    if not pts_ints or fps_float <= 0 or wh[0] <= 0 or wh[1] <= 0:
        raise ValueError(f"[Error] mp4 沒有可用的影格或參數不合理：{mp4_path}（幀數 {len(pts_ints)}，fps {fps_float}，尺寸 {wh}）")
    sec_floats = [float((pts_int - pts_ints[0]) * time_base_frac) for pts_int in pts_ints]
    return {"width": wh[0], "height": wh[1], "fps": round(fps_float, 4), "frames": len(pts_ints),
            "duration_s": round(sec_floats[-1] + 1 / fps_float, 3), "sec_floats": sec_floats}


def get_sec_floats_from_mp4_path(mp4_path: Path) -> list[float]:
    return get_probe_dict_from_mp4_path(mp4_path)["sec_floats"]


def get_first_bgr_arr_from_mp4_path(mp4_path: Path) -> "np.ndarray":
    try:
        with av.open(str(mp4_path)) as container_obj:
            for frame_obj in container_obj.decode(video=0):
                return frame_obj.to_ndarray(format="bgr24")
    except (av.error.FFmpegError, IndexError) as error_obj:
        raise ValueError(f"[Error] mp4 第一幀無法解碼：{mp4_path}（{error_obj}）") from error_obj
    raise ValueError(f"[Error] mp4 沒有任何可解碼的影格：{mp4_path}")


def gen_index_sec_gray_from_mp4_path(mp4_path: Path) -> Iterator[tuple[int, float, "np.ndarray"]]:
    with av.open(str(mp4_path)) as container_obj:
        stream_obj = container_obj.streams.video[0]
        stream_obj.thread_type = "AUTO"
        fps_frac = get_fps_frac_from_stream(stream_obj)
        first_sec_float = None
        for index_int, frame_obj in enumerate(container_obj.decode(stream_obj)):
            sec_float = float(frame_obj.time) if frame_obj.time is not None else index_int / float(fps_frac)
            first_sec_float = sec_float if first_sec_float is None else first_sec_float
            yield index_int, sec_float - first_sec_float, frame_obj.to_ndarray(format="gray")


def get_stream_and_codec_str_from_container(out_container_obj: "av.container.OutputContainer", fps_frac: Fraction,
                                            out_wh: WhType, crf_str: str,
                                            qscale_str: str) -> tuple[object, str]:
    last_error_obj: Exception | None = None
    for codec_str, option_dict in (("libx264", {"crf": crf_str, "preset": "veryfast"}),
                                   ("mpeg4", {"qscale": qscale_str})):
        try:
            out_stream_obj = out_container_obj.add_stream(codec_str, rate=fps_frac)
            out_stream_obj.width, out_stream_obj.height = out_wh
            out_stream_obj.pix_fmt = "yuv420p"
            out_stream_obj.options = option_dict
            out_stream_obj.codec_context.time_base = Fraction(1, 1000)
            return out_stream_obj, codec_str
        except Exception as error_obj:
            last_error_obj = error_obj
    raise ValueError(f"[Error] 找不到可用的 mp4 編碼器：{last_error_obj}")


def get_out_frame_obj_from_bgr_arr(bgr_arr: "np.ndarray", sec_float: float) -> "av.VideoFrame":
    out_frame_obj = av.VideoFrame.from_ndarray(bgr_arr, format="bgr24").reformat(format="yuv420p")
    out_frame_obj.pts, out_frame_obj.time_base = int(round(sec_float * 1000)), Fraction(1, 1000)
    return out_frame_obj


def run_encode_mp4_stage(in_path: Path, out_path: Path, out_wh: WhType,
                         convert_func: Callable[[int, float, "np.ndarray"], "np.ndarray"], crf_str: str,
                         qscale_str: str) -> dict:
    tmp_path = out_path.with_suffix(".tmp.mp4")
    tmp_path.unlink(missing_ok=True)
    try:
        with av.open(str(in_path)) as in_container_obj:
            in_stream_obj = in_container_obj.streams.video[0]
            in_stream_obj.thread_type = "AUTO"
            fps_frac = get_fps_frac_from_stream(in_stream_obj)
            with av.open(str(tmp_path), "w") as out_container_obj:
                out_stream_obj, codec_str = get_stream_and_codec_str_from_container(
                    out_container_obj, fps_frac, out_wh, crf_str, qscale_str)
                frame_count_int, first_sec_float, last_sec_float = 0, None, 0.0
                for index_int, frame_obj in enumerate(in_container_obj.decode(in_stream_obj)):
                    raw_sec_float = float(frame_obj.time) if frame_obj.time is not None else index_int / float(fps_frac)
                    first_sec_float = raw_sec_float if first_sec_float is None else first_sec_float
                    last_sec_float = raw_sec_float - first_sec_float
                    out_bgr_arr = convert_func(index_int, last_sec_float, frame_obj.to_ndarray(format="bgr24"))
                    if (out_bgr_arr.shape[1], out_bgr_arr.shape[0]) != tuple(out_wh):
                        raise ValueError(f"[Error] 輸出影格尺寸 {out_bgr_arr.shape[1]}×{out_bgr_arr.shape[0]} 不是預期的 "
                                         f"{out_wh[0]}×{out_wh[1]}")
                    for packet_obj in out_stream_obj.encode(get_out_frame_obj_from_bgr_arr(out_bgr_arr, last_sec_float)):
                        out_container_obj.mux(packet_obj)
                    frame_count_int += 1
                for packet_obj in out_stream_obj.encode():
                    out_container_obj.mux(packet_obj)
        if frame_count_int == 0:
            raise ValueError(f"[Error] 沒有解出任何影格：{in_path}")
        tmp_path.replace(out_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return {"frames": frame_count_int, "duration_s": round(last_sec_float, 3), "fps": float(fps_frac), "codec": codec_str}


def get_ordered_xys_from_xys(xys: list[XyType]) -> list[XyType]:
    if len(xys) != 4:
        raise ValueError("[Error] 需要剛好 4 個點")
    center_x_float = sum(xy[0] for xy in xys) / 4
    center_y_float = sum(xy[1] for xy in xys) / 4
    sorted_xys = sorted(xys, key=lambda xy: math.atan2(xy[1] - center_y_float, xy[0] - center_x_float))
    start_index_int = min(range(4), key=lambda index_int: sorted_xys[index_int][0] + sorted_xys[index_int][1])
    return [sorted_xys[(start_index_int + offset_int) % 4] for offset_int in range(4)]


def get_out_wh_from_xys(xys: list[XyType]) -> WhType:
    top_left_xy, top_right_xy, bottom_right_xy, bottom_left_xy = xys
    width_float = (math.dist(top_left_xy, top_right_xy) + math.dist(bottom_left_xy, bottom_right_xy)) / 2
    height_float = (math.dist(top_left_xy, bottom_left_xy) + math.dist(top_right_xy, bottom_right_xy)) / 2
    return int(round(width_float / 2)) * 2, int(round(height_float / 2)) * 2


def get_transform_from_xys(xys: list[XyType], frame_wh: WhType) -> tuple["np.ndarray", WhType]:
    for x_float, y_float in xys:
        if not (0 <= x_float <= frame_wh[0] and 0 <= y_float <= frame_wh[1]):
            raise ValueError(f"[Error] 四邊形頂點 ({x_float}, {y_float}) 超出影格範圍 {frame_wh[0]}×{frame_wh[1]}")
    src_xys = [(x_float - 0.5, y_float - 0.5) for x_float, y_float in xys]
    out_wh = get_out_wh_from_xys(src_xys)
    if min(out_wh) < 8:
        raise ValueError(f"[Error] 四邊形拉正後尺寸只有 {out_wh[0]}×{out_wh[1]}（小於 8）。請在 part_2.0 重新選取較大的區域")
    dst_xys = [(0, 0), (out_wh[0] - 1, 0), (out_wh[0] - 1, out_wh[1] - 1), (0, out_wh[1] - 1)]
    matrix_arr = cv2.getPerspectiveTransform(np.array(src_xys, np.float32), np.array(dst_xys, np.float32))
    return matrix_arr, out_wh


def get_rectified_arr_from_arr(img_arr: "np.ndarray", matrix_arr: "np.ndarray", out_wh: WhType) -> "np.ndarray":
    return cv2.warpPerspective(img_arr, matrix_arr, out_wh, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def get_img_arr_from_gray_arr(gray_arr: "np.ndarray", param_dict: dict) -> "np.ndarray":
    img_arr = gray_arr.astype(np.float32)
    return 255.0 - img_arr if param_dict["polarity"] == "bright" else img_arr


def get_valid_mask_arr_from_wh(wh: WhType, margin_float: float) -> "np.ndarray":
    width_int, height_int = wh
    margin_int = int(round(margin_float * min(height_int, width_int)))
    mask_arr = np.zeros((height_int, width_int), bool)
    mask_arr[margin_int:height_int - margin_int, margin_int:width_int - margin_int] = True
    return mask_arr


def check_blob_param_dict(param_dict: dict) -> None:
    if param_dict["r_max"] <= param_dict["r_min"]:
        raise ValueError(f"[Error] config.json 的 r_max（{param_dict['r_max']}）必須大於 r_min（{param_dict['r_min']}）")


def get_layer_count_int_from_param_dict(param_dict: dict) -> int:
    return max(3, math.ceil(math.log(param_dict["r_max"] / param_dict["r_min"]) / math.log(param_dict["sigma_k"])) + 1)


def get_sigma_floats_from_param_dict(param_dict: dict) -> list[float]:
    layer_count_int = get_layer_count_int_from_param_dict(param_dict)
    sigma_lo_float, sigma_hi_float = param_dict["r_min"] / math.sqrt(2), param_dict["r_max"] / math.sqrt(2)
    ratio_float = (sigma_hi_float / sigma_lo_float) ** (1 / (layer_count_int - 1))
    return [sigma_lo_float / math.sqrt(ratio_float) * ratio_float ** index_int for index_int in range(layer_count_int + 1)]


def get_layer_radius_floats_from_param_dict(param_dict: dict) -> list[float]:
    sigma_floats = get_sigma_floats_from_param_dict(param_dict)
    return [math.sqrt(2) * math.sqrt(sigma_floats[index_int] * sigma_floats[index_int + 1]) for index_int in range(len(sigma_floats) - 1)]


def get_scale_msg_str_from_param_dict(param_dict: dict) -> str:
    sigma_floats = get_sigma_floats_from_param_dict(param_dict)
    radius_floats = get_layer_radius_floats_from_param_dict(param_dict)
    return (f"找點的卷積（DoG）共 {len(radius_floats)} 層（用 {len(sigma_floats)} 個高斯模糊 σ = {sigma_floats[0]:.2f} ~ {sigma_floats[-1]:.2f} 相鄰相減），"
            f"各層偵測的圓半徑 ≈ √2·σ = {radius_floats[0]:.1f} ~ {radius_floats[-1]:.1f} px"
            f"（config 的 r_min / r_max / sigma_k；相鄰層半徑比 ≤ {param_dict['sigma_k']}）")


def get_blur_arr_list_from_img_arr(img_arr: "np.ndarray", mask_arr: "np.ndarray",
                                   sigma_floats: list[float]) -> list["np.ndarray"]:
    mask_f_arr = mask_arr.astype(np.float32)
    masked_arr = img_arr * mask_f_arr
    return [cv2.GaussianBlur(masked_arr, (0, 0), sigma_float)
            / np.maximum(cv2.GaussianBlur(mask_f_arr, (0, 0), sigma_float), 1e-3) for sigma_float in sigma_floats]


def get_z_arr_list_from_blur_arr_list(blur_arr_list: list["np.ndarray"], noise_mask_arr: "np.ndarray") -> list["np.ndarray"]:
    z_arr_list: list["np.ndarray"] = []
    for index_int in range(len(blur_arr_list) - 1):
        resp_arr = blur_arr_list[index_int + 1] - blur_arr_list[index_int]
        value_arr = resp_arr[noise_mask_arr]
        median_float = float(np.median(value_arr))
        noise_float = max(1.4826 * float(np.median(np.abs(value_arr - median_float))), 0.25)
        z_arr_list.append((resp_arr - median_float) / noise_float)
    return z_arr_list


def get_cand_tuple_list_from_z_arr_list(z_arr_list: list["np.ndarray"], region_mask_arr: "np.ndarray",
                                        sigma_floats: list[float], k_z_float: float) -> list[tuple]:
    kernel_arr = np.ones((3, 3), np.uint8)
    dilated_arr_list = [cv2.dilate(z_arr, kernel_arr) for z_arr in z_arr_list]
    cand_tuple_list: list[tuple] = []
    for index_int, z_arr in enumerate(z_arr_list):
        neighbor_arr = dilated_arr_list[index_int]
        if index_int > 0:
            neighbor_arr = np.maximum(neighbor_arr, dilated_arr_list[index_int - 1])
        if index_int < len(z_arr_list) - 1:
            neighbor_arr = np.maximum(neighbor_arr, dilated_arr_list[index_int + 1])
        ys_arr, xs_arr = np.nonzero((z_arr >= neighbor_arr) & (z_arr > k_z_float) & region_mask_arr)
        sigma_c_float = math.sqrt(sigma_floats[index_int] * sigma_floats[index_int + 1])
        for x_int, y_int in zip(xs_arr, ys_arr):
            cand_tuple_list.append((int(x_int), int(y_int), float(z_arr[y_int, x_int]), z_arr, sigma_c_float))
    cand_tuple_list.sort(key=lambda cand_tuple: -cand_tuple[2])
    return cand_tuple_list


def get_refined_xy_from_z_arr(z_arr: "np.ndarray", x_int: int, y_int: int) -> XyType:
    height_int, width_int = z_arr.shape
    x0_int, x1_int = max(0, x_int - 1), min(width_int, x_int + 2)
    y0_int, y1_int = max(0, y_int - 1), min(height_int, y_int + 2)
    patch_arr = np.clip(z_arr[y0_int:y1_int, x0_int:x1_int], 0, None)
    sum_float = float(patch_arr.sum())
    if sum_float <= 0:
        return float(x_int), float(y_int)
    grid_y_arr, grid_x_arr = np.mgrid[y0_int:y1_int, x0_int:x1_int]
    return float((patch_arr * grid_x_arr).sum() / sum_float), float((patch_arr * grid_y_arr).sum() / sum_float)


def get_xyrz_list_from_img_arr(img_arr: "np.ndarray", region_tuple: tuple[int, int, int, int] | None,
                               param_dict: dict, k_z_float: float) -> list[XyrzType]:
    height_int, width_int = img_arr.shape
    x0_int, y0_int, x1_int, y1_int = (0, 0, width_int, height_int) if region_tuple is None else region_tuple
    x0_int, y0_int, x1_int, y1_int = max(0, x0_int), max(0, y0_int), min(width_int, x1_int), min(height_int, y1_int)
    if x1_int - x0_int < 5 or y1_int - y0_int < 5:
        return []
    sigma_floats = get_sigma_floats_from_param_dict(param_dict)
    pad_int = int(math.ceil(3 * sigma_floats[-1]))
    cx0_int, cy0_int = max(0, x0_int - pad_int), max(0, y0_int - pad_int)
    cx1_int, cy1_int = min(width_int, x1_int + pad_int), min(height_int, y1_int + pad_int)
    crop_arr = img_arr[cy0_int:cy1_int, cx0_int:cx1_int]
    valid_arr = get_valid_mask_arr_from_wh((width_int, height_int), param_dict["margin"])[cy0_int:cy1_int, cx0_int:cx1_int]
    region_arr = np.zeros(crop_arr.shape, bool)
    region_arr[y0_int - cy0_int:y1_int - cy0_int, x0_int - cx0_int:x1_int - cx0_int] = True
    region_arr &= valid_arr
    if region_arr.sum() < 25:
        return []
    blur_arr_list = get_blur_arr_list_from_img_arr(crop_arr, valid_arr, sigma_floats)
    z_arr_list = get_z_arr_list_from_blur_arr_list(blur_arr_list, valid_arr)
    cand_tuple_list = get_cand_tuple_list_from_z_arr_list(z_arr_list, region_arr, sigma_floats, k_z_float)
    xyrz_list: list[XyrzType] = []
    for x_int, y_int, z_float, z_arr, sigma_c_float in cand_tuple_list[:param_dict["max_cand"]]:
        fit_x_float, fit_y_float = get_refined_xy_from_z_arr(z_arr, x_int, y_int)
        xyrz_list.append((fit_x_float + cx0_int, fit_y_float + cy0_int, math.sqrt(2) * sigma_c_float, z_float))
    return xyrz_list


def get_ray_sample_tuple_from_xy(sm_arr: "np.ndarray", xy: XyType, rs_arr: "np.ndarray", ray_count_int: int,
                                 step_float: float) -> tuple["np.ndarray", "np.ndarray"]:
    th_arr = np.linspace(0, 2 * np.pi, ray_count_int, endpoint=False).astype(np.float32)
    map_x_arr = (xy[0] + np.outer(np.cos(th_arr), rs_arr)).astype(np.float32)
    map_y_arr = (xy[1] + np.outer(np.sin(th_arr), rs_arr)).astype(np.float32)
    prof_arr = cv2.remap(sm_arr, map_x_arr, map_y_arr, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return th_arr, np.gradient(prof_arr, step_float, axis=1)


def get_circle_xyr_or_none_from_edge_points(px_arr: "np.ndarray", py_arr: "np.ndarray") -> XyrType | None:
    sol_arr, *_ = np.linalg.lstsq(np.column_stack([px_arr, py_arr, np.ones_like(px_arr)]),
                                  -(px_arr ** 2 + py_arr ** 2), rcond=None)
    center_x_float, center_y_float = -sol_arr[0] / 2, -sol_arr[1] / 2
    r2_float = center_x_float ** 2 + center_y_float ** 2 - sol_arr[2]
    return (float(center_x_float), float(center_y_float), math.sqrt(r2_float)) if r2_float > 0 else None


def get_fit_xyr_method_tuple_from_sm_arr(sm_arr: "np.ndarray", xyr: XyrType, rmax_float: float,
                                         param_dict: dict) -> tuple[XyrType, str]:
    x_float, y_float, r0_float = xyr
    step_float = 0.2
    r_lo_float = max(0.35 * r0_float, 0.4)
    rs_arr = np.arange(r_lo_float, max(rmax_float, r_lo_float + 4 * step_float), step_float, dtype=np.float32)
    if len(rs_arr) < 5:
        return xyr, "scale"
    ray_count_int = param_dict["fit_rays"]
    th_arr, grad_arr = get_ray_sample_tuple_from_xy(sm_arr, (x_float, y_float), rs_arr, ray_count_int, step_float)
    index_arr = grad_arr.argmax(axis=1)
    strength_arr = grad_arr[np.arange(ray_count_int), index_arr]
    if strength_arr.max() <= 0:
        return xyr, "scale"
    keep_arr = (strength_arr >= 0.5 * strength_arr.max()) & (index_arr > 0) & (index_arr < len(rs_arr) - 1)
    if keep_arr.sum() < 6:
        return xyr, "scale"
    rr_arr, tt_arr = rs_arr[index_arr][keep_arr].astype(np.float64), th_arr[keep_arr].astype(np.float64)
    px_arr, py_arr = x_float + rr_arr * np.cos(tt_arr), y_float + rr_arr * np.sin(tt_arr)
    circle_xyr = get_circle_xyr_or_none_from_edge_points(px_arr, py_arr)
    if circle_xyr is not None:
        is_ok_bool = (0.5 * r0_float <= circle_xyr[2] <= 2.2 * r0_float
                      and math.hypot(circle_xyr[0] - x_float, circle_xyr[1] - y_float) <= r0_float)
        if is_ok_bool:
            return circle_xyr, "edge"
    return (x_float, y_float, float(np.median(rr_arr))), "ray"


def get_fit_xyr_method_tuple_from_img_arr(img_arr: "np.ndarray", xyr: XyrType, rmax_float: float,
                                          param_dict: dict) -> tuple[XyrType, str]:
    pad_int = int(math.ceil(rmax_float + 4 * param_dict["fit_smooth"] + 3))
    x0_int, y0_int = max(0, int(xyr[0]) - pad_int), max(0, int(xyr[1]) - pad_int)
    x1_int, y1_int = min(img_arr.shape[1], int(xyr[0]) + pad_int + 1), min(img_arr.shape[0], int(xyr[1]) + pad_int + 1)
    sm_arr = cv2.GaussianBlur(img_arr[y0_int:y1_int, x0_int:x1_int], (0, 0), param_dict["fit_smooth"])
    fit_xyr, method_str = get_fit_xyr_method_tuple_from_sm_arr(sm_arr, (xyr[0] - x0_int, xyr[1] - y0_int, xyr[2]),
                                                               rmax_float, param_dict)
    return (fit_xyr[0] + x0_int, fit_xyr[1] + y0_int, fit_xyr[2]), method_str


def get_xyr_method_z_tuple_or_none_from_click(img_arr: "np.ndarray", click_xy: XyType, search_px_float: float,
                                              param_dict: dict) -> tuple[XyrType, str, float] | None:
    region_tuple = (int(click_xy[0] - search_px_float), int(click_xy[1] - search_px_float),
                   int(click_xy[0] + search_px_float) + 1, int(click_xy[1] + search_px_float) + 1)
    xyrz_list = get_xyrz_list_from_img_arr(img_arr, region_tuple, param_dict, param_dict["k_z"])
    xyrz_list = [xyrz for xyrz in xyrz_list if math.dist(xyrz[:2], click_xy) <= search_px_float]
    if not xyrz_list:
        return None
    best_xyrz = max(xyrz_list, key=lambda xyrz: min(xyrz[3], param_dict["z_cap"]) - 2.0 * math.dist(xyrz[:2], click_xy) / search_px_float)
    fit_xyr, method_str = get_fit_xyr_method_tuple_from_img_arr(img_arr, best_xyrz[:3],
                                                                param_dict["fit_rmax_mul"] * best_xyrz[2], param_dict)
    return fit_xyr, method_str, best_xyrz[3]


def get_rel_dict_from_xyrs(right_xyr: XyrType, left_xyr: XyrType, belly_xyr: XyrType) -> dict:
    mid_xy = ((right_xyr[0] + left_xyr[0]) / 2, (right_xyr[1] + left_xyr[1]) / 2)
    eye_x_float, eye_y_float = left_xyr[0] - right_xyr[0], left_xyr[1] - right_xyr[1]
    dist_float = math.hypot(eye_x_float, eye_y_float)
    if dist_float <= 0:
        raise ValueError("[Error] 兩眼位置重疊，無法計算相對位置")
    e_hat_xy, n_hat_xy = (eye_x_float / dist_float, eye_y_float / dist_float), (-eye_y_float / dist_float, eye_x_float / dist_float)
    rel_x_float, rel_y_float = belly_xyr[0] - mid_xy[0], belly_xyr[1] - mid_xy[1]
    return {"u": (rel_x_float * e_hat_xy[0] + rel_y_float * e_hat_xy[1]) / dist_float,
            "v": (rel_x_float * n_hat_xy[0] + rel_y_float * n_hat_xy[1]) / dist_float,
            "belly_r_rel": belly_xyr[2] / dist_float,
            "right_eye_r_rel": right_xyr[2] / dist_float, "left_eye_r_rel": left_xyr[2] / dist_float,
            "eye_dist_px": dist_float,
            "definition": "m=兩眼中點；e_hat=(左眼-右眼)/d；n_hat=(-e_y,e_x)；u=(b-m)·e_hat/d；v=(b-m)·n_hat/d；半徑比=r/d；d=眼距"}


def get_belly_xyr_from_rel_and_eyes(rel_dict: dict, right_xy: XyType, left_xy: XyType) -> XyrType:
    eye_x_float, eye_y_float = left_xy[0] - right_xy[0], left_xy[1] - right_xy[1]
    dist_float = math.hypot(eye_x_float, eye_y_float)
    e_hat_xy, n_hat_xy = (eye_x_float / dist_float, eye_y_float / dist_float), (-eye_y_float / dist_float, eye_x_float / dist_float)
    mid_xy = ((right_xy[0] + left_xy[0]) / 2, (right_xy[1] + left_xy[1]) / 2)
    return (mid_xy[0] + dist_float * (rel_dict["u"] * e_hat_xy[0] + rel_dict["v"] * n_hat_xy[0]),
            mid_xy[1] + dist_float * (rel_dict["u"] * e_hat_xy[1] + rel_dict["v"] * n_hat_xy[1]),
            rel_dict["belly_r_rel"] * dist_float)


