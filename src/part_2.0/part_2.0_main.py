#!/usr/bin/env python3
from __future__ import annotations

import functools
import math
import signal
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

sys.dont_write_bytecode = True

USAGE_STR = "part_2.0：兩個互動視窗，產生後面所有 part 需要的「人工輸入」：\n用法：python src/part_2.0/part_2.0_main.py MANIFEST_JSON START_MIN END_MIN"


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
    print_banner("part_2.0_main.py")

from tool_main import (WhType, XyType, XyrType, check_deps_are_available, cv2, get_blob_param_dict_from_config_dict, get_scale_msg_str_from_param_dict,
                       get_config_dict_from_path, get_files_dict_from_part_1_5, get_first_bgr_arr_from_mp4_path,
                       get_img_arr_from_gray_arr, get_inputs_dict_from_part_strs, get_json_obj_from_path,
                       get_meta_dict_from_part_dir, get_minute_strs_from_range, get_now_str, get_ordered_xys_from_xys,
                       get_param_dict_from_config_dict, get_part_dir_path, get_rectified_arr_from_arr,
                       get_rel_dict_from_xyrs, get_transform_from_xys, get_xyr_method_z_tuple_or_none_from_click, np,
                       run_prepare_part_dir_stage, save_json_obj_to_path)
from tool_manifest import (get_args_ns_from_argv_strs, info, run_main_stage, success)

try:
    import tkinter as tk
    from tkinter import messagebox, ttk

    from PIL import Image, ImageTk
except ImportError as tk_import_error:
    tk = messagebox = ttk = Image = ImageTk = None
    TK_IMPORT_ERROR_STR = str(tk_import_error)
else:
    TK_IMPORT_ERROR_STR = ""

PART_STR = "part_2.0"
HIT_RADIUS_INT = 12
MIN_AREA_RATIO_FLOAT = 0.001
IMG_CACHE_SIZE_INT = 24
SLIDE_DELAY_MS_INT = 150
POLL_MS_INT = 200
CORNER_NAME_STRS = ["top_left", "top_right", "bottom_right", "bottom_left"]
SEED_NAME_STRS = ["右眼", "左眼", "腹部"]
SLOT_COLOR_STRS = ["#ff3355", "#33aaff", "#33dd66", "#ffee55"]
DEFAULT_PARAM_DICT: dict = {
    "seed_search_px": 10.0,
}
RULE_DICT_DICT: dict[str, dict] = {
    "seed_search_px": {"type": "float", "min": 1, "max": 200},
}


def check_tk_is_available() -> None:
    if tk is None:
        raise ImportError(f"[Error] 無法載入 tkinter / Pillow.ImageTk（{TK_IMPORT_ERROR_STR}）。"
                          "macOS：brew install python-tk@3.12，並用該版本的 python 建 venv、pip install Pillow")


def get_pil_img_from_bgr_arr(bgr_arr: "np.ndarray") -> "Image.Image":
    return Image.fromarray(cv2.cvtColor(bgr_arr, cv2.COLOR_BGR2RGB))


def get_first_pil_img_from_minute_str(ts_to_path_dict: dict[str, Path], minute_str: str) -> "Image.Image":
    info(f"視窗一：載入 {minute_str} 的第一幀")
    return get_pil_img_from_bgr_arr(get_first_bgr_arr_from_mp4_path(ts_to_path_dict[minute_str]))


def get_rectified_pil_img_from_minute_str(ts_to_path_dict: dict[str, Path], minute_str: str, matrix_arr: "np.ndarray",
                                          out_wh: WhType) -> "Image.Image":
    info(f"視窗二：載入 {minute_str} 的第一幀並拉正")
    bgr_arr = get_first_bgr_arr_from_mp4_path(ts_to_path_dict[minute_str])
    return get_pil_img_from_bgr_arr(get_rectified_arr_from_arr(bgr_arr, matrix_arr, out_wh))


def get_area_float_from_xys(xys: list[XyType]) -> float:
    twice_area_float = 0.0
    for index_int, (x1_float, y1_float) in enumerate(xys):
        x2_float, y2_float = xys[(index_int + 1) % len(xys)]
        twice_area_float += x1_float * y2_float - x2_float * y1_float
    return abs(twice_area_float) / 2


def is_area_valid(xys: list[XyType], wh: WhType) -> bool:
    return get_area_float_from_xys(get_ordered_xys_from_xys(xys)) >= wh[0] * wh[1] * MIN_AREA_RATIO_FLOAT


def get_roi_dict_from_xys(start_min_str: str, end_min_str: str, frame_wh: WhType, minute_str: str, xys: list[XyType],
                          out_wh: WhType) -> dict:
    return {"schema_version": 2, "kind": "roi_quad", "start_min": start_min_str, "end_min": end_min_str,
            "frame_size": list(frame_wh), "reference_minute": minute_str, "rectified_size": list(out_wh),
            "coordinate_system": "原始 mp4 影格像素，原點在左上角（像素 i 佔 [i, i+1)），x 向右、y 向下",
            "order": CORNER_NAME_STRS, "points": [[x, y] for x, y in xys], "saved_at": get_now_str()}


def run_save_roi_stage(part_dir_path: Path, start_min_str: str, end_min_str: str, frame_wh: WhType, minute_str: str,
                       xyr_list: list[XyrType | None]) -> str:
    xys = [(xyr[0], xyr[1]) for xyr in xyr_list if xyr is not None]
    if len(xys) != 4:
        raise ValueError("需要 4 個頂點才能儲存")
    if not is_area_valid(xys, frame_wh):
        raise ValueError("四個點圍成的面積幾乎為 0，請重新選取")
    ordered_xys = get_ordered_xys_from_xys(xys)
    _, out_wh = get_transform_from_xys(ordered_xys, frame_wh)
    save_json_obj_to_path(get_roi_dict_from_xys(start_min_str, end_min_str, frame_wh, minute_str, ordered_xys, out_wh),
                          part_dir_path / "roi.json", indent_int=2)
    return f"已儲存 roi.json（拉正後 {out_wh[0]}×{out_wh[1]}）"


def get_xyr_tuple_or_none_from_click(pil_img_obj: "Image.Image", click_xy: XyType, search_px_float: float,
                                     blob_param_dict: dict) -> tuple[XyrType, str, float] | None:
    img_arr = get_img_arr_from_gray_arr(np.array(pil_img_obj.convert("L")), blob_param_dict)
    found_tuple = get_xyr_method_z_tuple_or_none_from_click(img_arr, (click_xy[0] - 0.5, click_xy[1] - 0.5), search_px_float,
                                                            blob_param_dict)
    if found_tuple is None:
        return None
    (x_float, y_float, r_float), method_str, z_float = found_tuple
    return (x_float + 0.5, y_float + 0.5, r_float), method_str, z_float


def get_seed_dict_from_slot_list(start_min_str: str, end_min_str: str, minute_str: str, rectified_wh: WhType,
                                 slot_tuple_list: list[tuple[XyrType, XyType, str] | None]) -> dict:
    if len(slot_tuple_list) != 3 or any(slot_tuple is None for slot_tuple in slot_tuple_list):
        raise ValueError("需要右眼、左眼、腹部三個點才能儲存")
    center_xyrs = [(xyr[0] - 0.5, xyr[1] - 0.5, xyr[2]) for xyr, _, _ in slot_tuple_list]
    for xyr in center_xyrs:
        if not all(math.isfinite(num) for num in xyr) or xyr[2] <= 0:
            raise ValueError("抓回的圓心或半徑不合理，請重新點選")
    right_xyr, left_xyr, belly_xyr = center_xyrs
    if math.dist(right_xyr[:2], left_xyr[:2]) < right_xyr[2] + left_xyr[2]:
        raise ValueError("兩眼重疊（右眼與左眼抓到同一個點？），請重新點選")
    for eye_xyr in (right_xyr, left_xyr):
        if math.dist(eye_xyr[:2], belly_xyr[:2]) < eye_xyr[2] + 0.5 * belly_xyr[2]:
            raise ValueError("腹部與眼睛重疊，請重新點選")
    return {"schema_version": 2, "kind": "seed", "start_min": start_min_str, "end_min": end_min_str,
            "minute": minute_str, "frame": 0, "sec": 0.0, "frame_size_rectified": list(rectified_wh),
            "coordinate_system": "拉正後影格像素，像素中心在整數（OpenCV / numpy 慣例）；半徑同單位",
            "clicks": {"right_eye": [slot_tuple_list[0][1][0] - 0.5, slot_tuple_list[0][1][1] - 0.5],
                       "left_eye": [slot_tuple_list[1][1][0] - 0.5, slot_tuple_list[1][1][1] - 0.5],
                       "belly": [slot_tuple_list[2][1][0] - 0.5, slot_tuple_list[2][1][1] - 0.5]},
            "right_eye": list(right_xyr), "left_eye": list(left_xyr), "belly": list(belly_xyr),
            "fit": {"right_eye": slot_tuple_list[0][2], "left_eye": slot_tuple_list[1][2], "belly": slot_tuple_list[2][2]},
            "rel": get_rel_dict_from_xyrs(right_xyr, left_xyr, belly_xyr), "saved_at": get_now_str()}


def run_save_seed_stage(part_dir_path: Path, start_min_str: str, end_min_str: str, minute_str: str, rectified_wh: WhType,
                        slot_tuple_list: list[tuple[XyrType, XyType, str] | None]) -> str:
    seed_dict = get_seed_dict_from_slot_list(start_min_str, end_min_str, minute_str, rectified_wh, slot_tuple_list)
    save_json_obj_to_path(seed_dict, part_dir_path / "seed.json", indent_int=2)
    rel_dict = seed_dict["rel"]
    return f"已儲存 seed.json（眼距 {rel_dict['eye_dist_px']:.1f}px，腹部相對位置 u={rel_dict['u']:.2f} v={rel_dict['v']:.2f}）"


class PickerApp:

    def __init__(self, root_obj: "tk.Tk", title_str: str, minute_strs: list[str], get_img_func: Callable[[str], "Image.Image"],
                 name_strs: list[str], refine_func: Callable | None, save_func: Callable, clear_on_slide_bool: bool,
                 help_str: str):
        self.root_obj, self.title_str, self.minute_strs = root_obj, title_str, minute_strs
        self.get_img_func, self.name_strs, self.refine_func = get_img_func, name_strs, refine_func
        self.save_func, self.clear_on_slide_bool, self.help_str = save_func, clear_on_slide_bool, help_str
        self.slot_list: list[tuple[XyrType, XyType, str] | None] = [None] * len(name_strs)
        self.img = None
        self.cur_minute_str: str | None = None
        self.img_cache_dict: dict[str, "Image.Image"] = {}
        self.scale_float = self.fit_scale_float = 1.0
        self.offset_xy: XyType = (0.0, 0.0)
        self.pan_last_xy: XyType | None = None
        self.photo_obj = None
        self.after_id_str: str | None = None
        self.is_saved_bool = False
        self.init_widgets()
        self.init_bindings()
        self.root_obj.update_idletasks()
        self.update_image_by_index(0)

    def init_widgets(self) -> None:
        self.root_obj.title(self.title_str)
        self.root_obj.geometry("1200x800")
        self.canvas_obj = tk.Canvas(self.root_obj, bg="#202020", highlightthickness=0, cursor="crosshair")
        self.canvas_obj.pack(fill="both", expand=True)
        bar_obj = ttk.Frame(self.root_obj)
        bar_obj.pack(fill="x", padx=6, pady=4)
        self.slider_obj = tk.Scale(bar_obj, from_=0, to=max(0, len(self.minute_strs) - 1), orient="horizontal",
                                   showvalue=False, command=self.on_slide)
        self.slider_obj.pack(fill="x")
        row_obj = ttk.Frame(bar_obj)
        row_obj.pack(fill="x", pady=(2, 0))
        self.status_obj = ttk.Label(row_obj, text="")
        self.status_obj.pack(side="left")
        ttk.Button(row_obj, text="儲存 (S)", command=self.on_save).pack(side="right")
        ttk.Button(row_obj, text="清除 (C)", command=self.update_slots_by_clear).pack(side="right", padx=4)
        ttk.Button(row_obj, text="縮放至全圖 (F)", command=self.update_view_by_fit).pack(side="right")

    def init_bindings(self) -> None:
        canvas_obj, root_obj = self.canvas_obj, self.root_obj
        canvas_obj.bind("<Configure>", lambda event: self.draw_canvas())
        canvas_obj.bind("<Button-1>", self.on_left_click)
        for button_int in (2, 3):
            canvas_obj.bind(f"<ButtonPress-{button_int}>", self.on_pan_start)
            canvas_obj.bind(f"<B{button_int}-Motion>", self.on_pan_move)
        canvas_obj.bind("<MouseWheel>", self.on_wheel)
        canvas_obj.bind("<Button-4>", lambda event: self.update_view_by_zoom((event.x, event.y), 1.25))
        canvas_obj.bind("<Button-5>", lambda event: self.update_view_by_zoom((event.x, event.y), 0.8))
        root_obj.bind("<Left>", lambda event: self.update_slider_by_step(-1))
        root_obj.bind("<Right>", lambda event: self.update_slider_by_step(1))
        root_obj.bind("<f>", lambda event: self.update_view_by_fit())
        root_obj.bind("<c>", lambda event: self.update_slots_by_clear())
        root_obj.bind("<s>", lambda event: self.on_save())
        root_obj.bind("<Escape>", lambda event: self.root_obj.destroy())

    def update_image_by_index(self, index_int: int) -> None:
        minute_str = self.minute_strs[index_int]
        if minute_str == self.cur_minute_str:
            return
        if minute_str not in self.img_cache_dict:
            if len(self.img_cache_dict) >= IMG_CACHE_SIZE_INT:
                self.img_cache_dict.pop(next(iter(self.img_cache_dict)))
            self.img_cache_dict[minute_str] = self.get_img_func(minute_str)
        new_img_obj = self.img_cache_dict[minute_str]
        need_fit_bool = self.img is None or new_img_obj.size != self.img.size
        self.img, self.cur_minute_str = new_img_obj, minute_str
        if self.clear_on_slide_bool:
            self.slot_list = [None] * len(self.name_strs)
        if need_fit_bool:
            self.update_view_by_fit()
        else:
            self.draw_canvas()

    def on_slide(self, value_str: str) -> None:
        if self.after_id_str is not None:
            self.root_obj.after_cancel(self.after_id_str)
        self.update_status_by_msg(f"→ {self.minute_strs[int(float(value_str))]}")
        self.after_id_str = self.root_obj.after(SLIDE_DELAY_MS_INT, self.on_slide_idle)

    def on_slide_idle(self) -> None:
        self.after_id_str = None
        self.update_image_by_index(int(float(self.slider_obj.get())))

    def update_slider_by_step(self, delta_int: int) -> None:
        self.slider_obj.set(min(max(int(self.slider_obj.get()) + delta_int, 0), len(self.minute_strs) - 1))

    def to_screen_xy(self, image_xy: XyType) -> XyType:
        return (self.offset_xy[0] + image_xy[0] * self.scale_float, self.offset_xy[1] + image_xy[1] * self.scale_float)

    def to_image_xy(self, screen_xy: XyType) -> XyType:
        return ((screen_xy[0] - self.offset_xy[0]) / self.scale_float, (screen_xy[1] - self.offset_xy[1]) / self.scale_float)

    def update_view_by_fit(self) -> None:
        if self.img is None:
            return
        canvas_w_int = max(1, self.canvas_obj.winfo_width())
        canvas_h_int = max(1, self.canvas_obj.winfo_height())
        img_w_int, img_h_int = self.img.size
        self.fit_scale_float = self.scale_float = min(canvas_w_int / img_w_int, canvas_h_int / img_h_int)
        self.offset_xy = ((canvas_w_int - img_w_int * self.scale_float) / 2, (canvas_h_int - img_h_int * self.scale_float) / 2)
        self.draw_canvas()

    def update_view_by_zoom(self, mouse_xy: XyType, factor_float: float) -> None:
        new_scale_float = min(max(self.scale_float * factor_float, self.fit_scale_float * 0.5), self.fit_scale_float * 40)
        ratio_float = new_scale_float / self.scale_float
        self.offset_xy = (mouse_xy[0] - (mouse_xy[0] - self.offset_xy[0]) * ratio_float,
                          mouse_xy[1] - (mouse_xy[1] - self.offset_xy[1]) * ratio_float)
        self.scale_float = new_scale_float
        self.draw_canvas()

    def on_wheel(self, event_obj: "tk.Event") -> None:
        self.update_view_by_zoom((event_obj.x, event_obj.y), 1.25 if event_obj.delta > 0 else 0.8)

    def on_pan_start(self, event_obj: "tk.Event") -> None:
        self.pan_last_xy = (event_obj.x, event_obj.y)

    def on_pan_move(self, event_obj: "tk.Event") -> None:
        if self.pan_last_xy is None:
            return
        self.offset_xy = (self.offset_xy[0] + event_obj.x - self.pan_last_xy[0],
                          self.offset_xy[1] + event_obj.y - self.pan_last_xy[1])
        self.pan_last_xy = (event_obj.x, event_obj.y)
        self.draw_canvas()

    def draw_canvas(self, msg_str: str = "") -> None:
        if self.img is None:
            return
        self.canvas_obj.delete("all")
        self.draw_image_on_canvas()
        self.draw_points_on_canvas()
        self.update_status_by_msg(msg_str)

    def draw_image_on_canvas(self) -> None:
        canvas_w_int, canvas_h_int = self.canvas_obj.winfo_width(), self.canvas_obj.winfo_height()
        img_w_int, img_h_int = self.img.size
        left_float, top_float = self.to_image_xy((0, 0))
        right_float, bottom_float = self.to_image_xy((canvas_w_int, canvas_h_int))
        box_int_tuple = (max(0, math.floor(left_float)), max(0, math.floor(top_float)),
                         min(img_w_int, math.ceil(right_float)), min(img_h_int, math.ceil(bottom_float)))
        if box_int_tuple[2] <= box_int_tuple[0] or box_int_tuple[3] <= box_int_tuple[1]:
            return
        region_img_obj = self.img.crop(box_int_tuple)
        size_int_tuple = (max(1, round((box_int_tuple[2] - box_int_tuple[0]) * self.scale_float)),
                          max(1, round((box_int_tuple[3] - box_int_tuple[1]) * self.scale_float)))
        region_img_obj = region_img_obj.resize(size_int_tuple, Image.NEAREST if self.scale_float >= 3 else Image.BILINEAR)
        self.photo_obj = ImageTk.PhotoImage(region_img_obj)
        screen_x_float, screen_y_float = self.to_screen_xy((box_int_tuple[0], box_int_tuple[1]))
        self.canvas_obj.create_image(screen_x_float, screen_y_float, image=self.photo_obj, anchor="nw")

    def draw_points_on_canvas(self) -> None:
        filled_tuples = [(index_int, slot_tuple) for index_int, slot_tuple in enumerate(self.slot_list) if slot_tuple is not None]
        if len(self.slot_list) == 4 and len(filled_tuples) == 4:
            ordered_xys = get_ordered_xys_from_xys([slot_tuple[0][:2] for _, slot_tuple in filled_tuples])
            flat_nums = [num for xy in ordered_xys for num in self.to_screen_xy(xy)]
            self.canvas_obj.create_polygon(*flat_nums, outline="#00ff88", fill="", width=2)
        for index_int, slot_tuple in filled_tuples:
            color_str = SLOT_COLOR_STRS[index_int % len(SLOT_COLOR_STRS)]
            screen_x_float, screen_y_float = self.to_screen_xy(slot_tuple[0][:2])
            r_float = max(6.0, slot_tuple[0][2] * self.scale_float) if self.refine_func is not None else 6.0
            self.canvas_obj.create_oval(screen_x_float - r_float, screen_y_float - r_float, screen_x_float + r_float,
                                        screen_y_float + r_float, outline=color_str, width=2)
            self.canvas_obj.create_line(screen_x_float - 3, screen_y_float, screen_x_float + 3, screen_y_float, fill=color_str)
            self.canvas_obj.create_line(screen_x_float, screen_y_float - 3, screen_x_float, screen_y_float + 3, fill=color_str)
            self.canvas_obj.create_text(screen_x_float + r_float + 6, screen_y_float - r_float - 6, text=self.name_strs[index_int],
                                        fill="#ffee55", font=("TkDefaultFont", 12, "bold"))

    def update_status_by_msg(self, msg_str: str) -> None:
        zoom_float = self.scale_float / self.fit_scale_float if self.fit_scale_float else 1.0
        filled_int = sum(slot_tuple is not None for slot_tuple in self.slot_list)
        next_str = next((name_str for name_str, slot_tuple in zip(self.name_strs, self.slot_list) if slot_tuple is None), "（已全部點完，按 S 儲存）")
        text_str = f"{self.cur_minute_str or '-'}   已點 {filled_int}/{len(self.name_strs)}   下一個：{next_str}   縮放 ×{zoom_float:.1f}"
        self.status_obj.config(text=text_str + (f"   | {msg_str}" if msg_str else ""))

    def get_hit_index_from_screen_xy(self, screen_xy: XyType) -> int | None:
        for index_int, slot_tuple in enumerate(self.slot_list):
            if slot_tuple is None:
                continue
            point_x_float, point_y_float = self.to_screen_xy(slot_tuple[0][:2])
            if math.hypot(screen_xy[0] - point_x_float, screen_xy[1] - point_y_float) <= HIT_RADIUS_INT:
                return index_int
        return None

    def on_left_click(self, event_obj: "tk.Event") -> None:
        hit_index_int = self.get_hit_index_from_screen_xy((event_obj.x, event_obj.y))
        if hit_index_int is not None:
            self.slot_list[hit_index_int] = None
            self.draw_canvas(f"已取消「{self.name_strs[hit_index_int]}」")
            return
        image_x_float, image_y_float = self.to_image_xy((event_obj.x, event_obj.y))
        img_w_int, img_h_int = self.img.size
        if not (0 <= image_x_float < img_w_int and 0 <= image_y_float < img_h_int):
            self.update_status_by_msg("點擊在圖片外，已忽略")
            return
        if all(slot_tuple is not None for slot_tuple in self.slot_list):
            self.update_status_by_msg("已全部點完：先點既有的點取消，或按 C 清除，或按 S 儲存")
            return
        slot_index_int = self.slot_list.index(None)
        click_xy = (round(image_x_float, 1), round(image_y_float, 1))
        if self.refine_func is None:
            self.slot_list[slot_index_int] = ((click_xy[0], click_xy[1], 0.0), click_xy, "click")
            self.draw_canvas()
            return
        found_tuple = self.refine_func(self.img, click_xy)
        if found_tuple is None:
            self.update_status_by_msg(f"「{self.name_strs[slot_index_int]}」附近找不到明顯的點，請點得更靠近中心")
            return
        xyr, method_str, z_float = found_tuple
        self.slot_list[slot_index_int] = (xyr, click_xy, method_str)
        info(f"{self.cur_minute_str} {self.name_strs[slot_index_int]}：點擊 {click_xy} → 圓心 ({xyr[0]:.2f}, {xyr[1]:.2f}) "
             f"半徑 {xyr[2]:.2f}（{method_str}，z={z_float:.1f}）")
        self.draw_canvas(f"{self.name_strs[slot_index_int]}：半徑 {xyr[2]:.1f}（{method_str}）")

    def update_slots_by_clear(self) -> None:
        self.slot_list = [None] * len(self.name_strs)
        self.draw_canvas()

    def on_save(self) -> None:
        if any(slot_tuple is None for slot_tuple in self.slot_list):
            self.update_status_by_msg(f"還沒點完（{len(self.name_strs)} 個點）")
            return
        try:
            if self.refine_func is None:
                msg_str = self.save_func(self.cur_minute_str, self.img.size, [slot_tuple[0] for slot_tuple in self.slot_list])
            else:
                msg_str = self.save_func(self.cur_minute_str, self.img.size, list(self.slot_list))
        except ValueError as error_obj:
            messagebox.showwarning("無法儲存", str(error_obj))
            return
        except OSError as error_obj:
            messagebox.showerror("儲存失敗", str(error_obj))
            return
        self.is_saved_bool = True
        self.update_status_by_msg(msg_str + "  → 視窗即將自動關閉")
        self.root_obj.after(400, self.root_obj.destroy)


def update_window_by_raise(root_obj: "tk.Tk") -> None:
    root_obj.update_idletasks()
    root_obj.lift()
    root_obj.attributes("-topmost", True)
    root_obj.after(300, lambda: root_obj.attributes("-topmost", False))
    root_obj.focus_force()


def on_poll_tick(root_obj: "tk.Tk", state_dict: dict) -> None:
    if state_dict["interrupted"]:
        root_obj.destroy()
        return
    root_obj.after(POLL_MS_INT, on_poll_tick, root_obj, state_dict)


def run_picker_window_stage(title_str: str, minute_strs: list[str], get_img_func: Callable[[str], "Image.Image"],
                            name_strs: list[str], refine_func: Callable | None, save_func: Callable,
                            clear_on_slide_bool: bool, help_str: str) -> None:
    check_tk_is_available()
    state_dict = {"interrupted": False}
    old_handler_obj = signal.signal(signal.SIGINT, lambda signum, frame: state_dict.update(interrupted=True))
    try:
        root_obj = tk.Tk()
        app_obj = PickerApp(root_obj, title_str, minute_strs, get_img_func, name_strs, refine_func, save_func,
                            clear_on_slide_bool, help_str)
        update_window_by_raise(root_obj)
        on_poll_tick(root_obj, state_dict)
        info(f"視窗已開啟：{title_str}（若沒看到，請檢查 Dock 或其他視窗後面）")
        info(help_str)
        root_obj.mainloop()
    finally:
        signal.signal(signal.SIGINT, old_handler_obj)
    if state_dict["interrupted"]:
        raise KeyboardInterrupt
    if not app_obj.is_saved_bool:
        raise ValueError(f"[Error] 「{title_str}」視窗已關閉，但沒有儲存。後面的步驟需要這份結果，結束")


def get_roi_dict_from_part_dir_path(part_dir_path: Path) -> dict:
    roi_dict = get_json_obj_from_path(part_dir_path / "roi.json", "roi.json")
    if not isinstance(roi_dict, dict) or len(roi_dict.get("points", [])) != 4:
        raise ValueError("[Error] roi.json 內容不對（需要 4 個點）")
    return roi_dict


def run_all_stages(argv_strs: list[str]) -> None:
    check_deps_are_available()
    args_ns = get_args_ns_from_argv_strs("part_2.0", USAGE_STR, argv_strs)
    manifest_dict = args_ns.manifest_dict
    config_dict = get_config_dict_from_path(manifest_dict["config_path"])
    param_dict = get_param_dict_from_config_dict(config_dict, PART_STR, DEFAULT_PARAM_DICT, RULE_DICT_DICT)
    blob_param_dict = get_blob_param_dict_from_config_dict(config_dict)
    info(get_scale_msg_str_from_param_dict(blob_param_dict))

    get_meta_dict_from_part_dir(manifest_dict, args_ns.start_min, args_ns.end_min, "part_1.5")
    ts_to_path_dict, frame_wh = get_files_dict_from_part_1_5(manifest_dict, args_ns.start_min, args_ns.end_min)
    minute_strs = get_minute_strs_from_range(args_ns.start_min, args_ns.end_min)
    info(f"影格尺寸 {frame_wh[0]}×{frame_wh[1]}，{len(minute_strs)} 個分鐘可選")
    part_dir_path = get_part_dir_path(manifest_dict, args_ns.start_min, args_ns.end_min, PART_STR)
    run_prepare_part_dir_stage(part_dir_path)

    roi_holder_dict: dict = {}

    def save_roi_func(minute_str: str, image_wh: WhType, xyr_list: list[XyrType | None]) -> str:
        msg_str = run_save_roi_stage(part_dir_path, args_ns.start_min, args_ns.end_min, frame_wh, minute_str, xyr_list)
        roi_holder_dict["minute"] = minute_str
        return msg_str

    run_picker_window_stage(
        f"視窗一：選取四邊形  {args_ns.start_min} ~ {args_ns.end_min}", minute_strs,
        functools.partial(get_first_pil_img_from_minute_str, ts_to_path_dict), ["1", "2", "3", "4"], None, save_roi_func,
        False, "左鍵依序點 4 個角 → 按 S 儲存 → 視窗自動關閉；滑桿只是換一張看得清楚的畫面。Ctrl-C 可中斷。")
    roi_dict = get_roi_dict_from_part_dir_path(part_dir_path)
    ordered_xys = [(xy[0], xy[1]) for xy in roi_dict["points"]]
    matrix_arr, out_wh = get_transform_from_xys(ordered_xys, frame_wh)
    info(f"四邊形已存，拉正後尺寸 {out_wh[0]}×{out_wh[1]}")

    seed_holder_dict: dict = {}

    def save_seed_func(minute_str: str, image_wh: WhType, slot_tuple_list: list) -> str:
        msg_str = run_save_seed_stage(part_dir_path, args_ns.start_min, args_ns.end_min, minute_str, out_wh, slot_tuple_list)
        seed_holder_dict["minute"] = minute_str
        return msg_str

    refine_func = functools.partial(get_xyr_tuple_or_none_from_click, search_px_float=param_dict["seed_search_px"],
                                    blob_param_dict=blob_param_dict)
    run_picker_window_stage(
        f"視窗二：點右眼、左眼、腹部（拉正後畫面，每分鐘的第 0 秒）  {args_ns.start_min} ~ {args_ns.end_min}", minute_strs,
        functools.partial(get_rectified_pil_img_from_minute_str, ts_to_path_dict, matrix_arr=matrix_arr, out_wh=out_wh),
        SEED_NAME_STRS, refine_func, save_seed_func, True,
        "滑桿挑一個三個點都看得清楚的分鐘 → 依序點 右眼、左眼、腹部（點大概即可，程式會抓回最深的中心）→ 按 S 儲存 → 自動關閉。Ctrl-C 可中斷。")

    meta_dict = {"kind": PART_STR, "start_min": args_ns.start_min, "end_min": args_ns.end_min, "params": param_dict,
                 "blob_params": blob_param_dict,
                 "inputs": get_inputs_dict_from_part_strs(manifest_dict, args_ns.start_min, args_ns.end_min, ["part_1.5"]),
                 "roi_reference_minute": roi_dict["reference_minute"], "seed_minute": seed_holder_dict["minute"],
                 "rectified_size": list(out_wh), "created_at": get_now_str()}
    save_json_obj_to_path(meta_dict, part_dir_path / "meta.json")
    success(f"part_2.0 完成：四邊形（{roi_dict['reference_minute']}）、種子點（{seed_holder_dict['minute']} 第 0 秒）。輸出：{part_dir_path}")


def main() -> None:
    run_main_stage(run_all_stages, sys.argv[1:])


if __name__ == "__main__":
    main()
