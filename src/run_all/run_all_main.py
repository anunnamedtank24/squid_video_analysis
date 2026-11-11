#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

USAGE_STR = ("run_all：依序跑 part_1.5 → part_4.0\n用法：python src/run_all/run_all_main.py MANIFEST_JSON START_MIN END_MIN [--start PART] [--end PART]\n"
             "例：只跑 part_2.5 到 part_3.5 → --start 2.5 --end 3.5")


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
    print_banner("run_all_main.py")

from tool_manifest import PART_STR_TUPLE, get_args_ns_from_argv_strs, info, run_main_stage, success, warn

PART_LABEL_DICT = {"part_1.5": "檢查時間範圍與 mp4（長度、解析度、每分鐘一個）", "part_2.0": "視窗一：選四邊形；視窗二：點右眼、左眼、腹部",
                   "part_2.5": "拉正 mp4", "part_3.0": "追蹤右眼、左眼、腹部", "part_3.5": "把圓畫回影片", "part_4.0": "腹部附近的亮度"}
INTERRUPT_CODE_INT = 130


def get_part_str_from_input_str(input_str: str) -> str:
    name_str = input_str.strip()
    part_str = name_str if name_str.startswith("part_") else f"part_{name_str}"
    if part_str not in PART_STR_TUPLE:
        raise ValueError(f"[Error] 不認得的 part「{input_str}」。可用：{', '.join(part_str.removeprefix('part_') for part_str in PART_STR_TUPLE)}")
    return part_str


def get_selected_part_strs_from_args_ns(args_ns: object) -> tuple[str, ...]:
    start_str = PART_STR_TUPLE[0] if args_ns.start is None else get_part_str_from_input_str(args_ns.start)
    end_str = PART_STR_TUPLE[-1] if args_ns.end is None else get_part_str_from_input_str(args_ns.end)
    start_int, end_int = PART_STR_TUPLE.index(start_str), PART_STR_TUPLE.index(end_str)
    if start_int > end_int:
        raise ValueError(f"[Error] --start {start_str} 在 --end {end_str} 之後。順序是：{' → '.join(PART_STR_TUPLE)}")
    return PART_STR_TUPLE[start_int:end_int + 1]


def get_script_path_dict_from_manifest_dict(manifest_dict: dict) -> dict[str, Path]:
    return {part_str: manifest_dict["part_dir_path_dict"][part_str] / f"{part_str}_main.py" for part_str in PART_STR_TUPLE}


def check_run_ready(manifest_dict: dict, script_path_dict: dict[str, Path]) -> None:
    python_path = manifest_dict["python_path"]
    if not (python_path.is_file() and os.access(python_path, os.X_OK)):
        raise FileNotFoundError(f"[Error] manifest 的 python 不存在或不可執行：{python_path}。請建立 venv，或改 manifest 的 python")
    missing_strs = [f"{part_str}：{script_path}" for part_str, script_path in script_path_dict.items() if not script_path.is_file()]
    if missing_strs:
        raise FileNotFoundError("[Error] 找不到下列 part 的腳本（請檢查 manifest 的 parts）：\n  " + "\n  ".join(missing_strs))


def get_cmd_strs_from_part_str(part_str: str, manifest_dict: dict, script_path_dict: dict[str, Path], args_ns: object) -> list[str]:
    return [str(manifest_dict["python_path"]), str(script_path_dict[part_str]), str(manifest_dict["manifest_path"]),
            args_ns.start_min, args_ns.end_min]


def get_exit_code_int_from_cmd_strs(cmd_strs: list[str]) -> int:
    proc_obj = subprocess.Popen(cmd_strs)
    try:
        return proc_obj.wait()
    except KeyboardInterrupt:
        try:
            proc_obj.wait()
        except KeyboardInterrupt:
            proc_obj.kill()
            proc_obj.wait()
        return INTERRUPT_CODE_INT


def run_part_stage(part_str: str, cmd_strs: list[str], selected_part_strs: tuple[str, ...]) -> int:
    print(flush=True)
    info(f"({selected_part_strs.index(part_str) + 1}/{len(selected_part_strs)}) 開始 {part_str}：{PART_LABEL_DICT[part_str]}")
    return get_exit_code_int_from_cmd_strs(cmd_strs)


def run_all_stages(argv_strs: list[str]) -> None:
    args_ns = get_args_ns_from_argv_strs("run_all", USAGE_STR, argv_strs, part_range_bool=True)
    selected_part_strs = get_selected_part_strs_from_args_ns(args_ns)
    info(f"要跑的 part：{' → '.join(selected_part_strs)}" + ("" if len(selected_part_strs) == len(PART_STR_TUPLE) else "（其餘 part 視為已完成，由各 part 自己檢查上游結果）"))
    manifest_dict = args_ns.manifest_dict
    script_path_dict = get_script_path_dict_from_manifest_dict(manifest_dict)
    check_run_ready(manifest_dict, script_path_dict)
    for part_str in selected_part_strs:
        code_int = run_part_stage(part_str, get_cmd_strs_from_part_str(part_str, manifest_dict, script_path_dict, args_ns), selected_part_strs)
        if code_int == 0:
            continue
        print(f"\n[Error] {part_str} 失敗（exit code {code_int}），整個流程停止", file=sys.stderr, flush=True)
        if part_str == "part_3.0" and "part_3.5" in selected_part_strs and code_int != INTERRUPT_CODE_INT:
            info("先用 part_3.0 已有的結果跑 part_3.5（只畫到失敗那一幀，黃圈 = 邊界幀每隻眼允許出現的範圍，黃框 = 一般幀的搜尋範圍），方便你調參數")
            part_3_5_code_int = run_part_stage("part_3.5", get_cmd_strs_from_part_str("part_3.5", manifest_dict, script_path_dict, args_ns), selected_part_strs)
            if part_3_5_code_int != 0:
                warn(f"part_3.5 也失敗了（exit code {part_3_5_code_int}，見上）")
        sys.exit(code_int)
    success(f"全部完成。輸出在 {manifest_dict['output_dir_path'] / (args_ns.start_min + '_' + args_ns.end_min)}")


def main() -> None:
    run_main_stage(run_all_stages, sys.argv[1:])


if __name__ == "__main__":
    main()
