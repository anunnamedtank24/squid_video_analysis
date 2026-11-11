# part_4.5 — 把眼睛與腹部畫回影片

把 [part_3.0](../part_3.0/README.md) 的眼睛與 [part_4.0](../part_4.0/README.md) 的腹部（含允許範圍橢圓）畫在拉正後的影片上，讓人用眼睛檢查。**每分鐘一個 mp4**（不會把各分鐘接起來）。

| 項目 | 內容 |
| --- | --- |
| 腳本 | `src/part_4.5/part_4.5_main.py` |
| 上游 | [part_2.5](../part_2.5/README.md)（拉正 mp4）、part_3.0（眼睛）、part_4.0（腹部） |
| 下游 | 無（給人看的）；part_5.0 不依賴它 |
| 與 part_3.5 的差別 | part_3.5 只畫眼睛，且 part_3.0 失敗 / 中斷也能畫到失敗那一幀；part_4.5 畫眼睛 + 腹部，**需要 part_3.0 與 part_4.0 都完整完成** |

## 用法

```bash
python src/part_4.5/part_4.5_main.py MANIFEST_JSON START_MIN END_MIN
# 例
python src/part_4.5/part_4.5_main.py manifest.json 202605211317 202605211359
```

## 輸入

| 輸入 | 說明 |
| --- | --- |
| `START_MIN` / `END_MIN` | 必須與前面的 part 相同 |
| `part_2.5/mp4s/{分鐘}.mp4`、`meta.json` | 拉正後的 mp4；尺寸與每分鐘幀數 |
| `part_3.0/{分鐘}.json` + `meta.json` | 眼睛；`status = complete`，記錄的 part_2.5 版本要是目前的（sha256） |
| `part_4.0/{分鐘}.json` + `meta.json` | 腹部；記錄的 part_3.0 版本要是目前的（sha256）。part_3.0 重跑過就要重跑 part_4.0 |
| `config.json` 的 `part_4.5` | 見下 |

## 輸出

`{output}/{START}_{END}/part_4.5/`

| 檔案 | 內容 |
| --- | --- |
| `mp4s/{YYYYMMDDHHMM}.mp4` | 畫了圓與橢圓的影片；放大 `scale` 倍；幀數與 part_2.5 相同 |
| `meta.json` | `params`（含顏色與半徑公式）、`rectified_size`、`out_size`、`minutes`（每分鐘的幀數 / 有結果的幀數 / 沿用上一筆的幀數）、`inputs`（part_2.5、part_3.0、part_4.0 的 meta sha256）、`created_at` |

## 怎麼畫

每個點以圓心畫**空心圓**，半徑 = `追蹤半徑 × rmul + radd`（拉正後像素），再乘上 `scale`。

### 顏色（BGR）

| 對象 | 顏色 | 說明 |
| --- | --- | --- |
| 右眼 | 🔴 紅 | |
| 左眼 | 🔵 藍 | |
| 腹部 `detected` | 🟢 綠 | 偵測到的 |
| 腹部 `predicted` | 🟣 洋紅 | 沒找到、用兩眼 + 相對位置推算（信心低） |
| 腹部允許範圍（橢圓） | 🟠 橘 | 以兩眼為基準的橢圓（平行兩眼連線的半軸短、垂直的半軸長），每一幀都畫；來自 part_4.0 的 `body_zone`（見 [part_4.0](../part_4.0/README.md#允許範圍以雙眼為準的橢圓)） |

### 每一幀怎麼決定畫什麼

part_3.0 與 part_4.0 的 entry 是一對一的（相同的 `frame`），畫的時候合併成一筆：

| 該幀的狀況 | 畫什麼 | 線寬 | 左上角標字 |
| --- | --- | --- | --- |
| 有 entry（`kind = seed / sample / frame / retry`） | 那一筆 | `thickness_tracked` | `時間  tracked:kind` |
| 沒有 entry（眼睛沒動、沒有逐幀處理、或 part_3.0 往後再找時跳過的幀） | **沿用時間上最近的前一筆**（這一分鐘第一筆之前的幀沿用第一筆） | `thickness_hold` | `時間  hold(上一筆的時間)` |
| 腹部是 `predicted` | 洋紅圓 | — | 另外加 `belly predicted` |
| 有 `body_zone` | 另外畫橘色橢圓 | `thickness_zone` | — |

> [!TIP]
> 沿用上一筆的幀若烏賊其實動了，就會看到圓沒有跟上——這正是用來檢查「有沒有漏看」的方式。

## config.json 的 `part_4.5`

沒寫的用預設值；寫了不認得的名稱就報錯。

| 參數 | 預設 | 範圍 | 意義 |
| --- | --- | --- | --- |
| `rmul` | `1.2` | `> 0` | 畫的半徑 = 追蹤半徑 × `rmul` + `radd` |
| `radd` | `1.0` | `≥ 0` | 同上（拉正後像素） |
| `scale` | `4` | `1 ~ 32`（整數） | 輸出相對拉正影片放大的倍率。放大才看得清楚小圓；越大越慢、檔案越大；放大後單邊上限 8192 |
| `thickness_tracked` | `2` | `1 ~ 10`（整數） | 有 entry 的幀的線寬（放大後像素） |
| `thickness_hold` | `1` | `1 ~ 10`（整數） | 沿用上一筆的幀的線寬 |
| `thickness_zone` | `1` | `1 ~ 10`（整數） | 腹部允許範圍橢圓的線寬 |

## 執行順序

```mermaid
flowchart TD
    A[config → 參數] --> B[上游檢查<br/>part_3.0 complete<br/>part_2.5 / part_3.0 版本一致]
    B --> C[放大後尺寸檢查<br/>單邊 ≤ 8192]
    C --> D[建立輸出資料夾<br/>一律覆蓋]
    D --> E["逐分鐘：讀 part_3.0 與 part_4.0 的 json 並合併<br/>→ 逐幀放大、畫圓與橢圓、標字、編碼"]
    E --> F[meta.json]
```

> [!WARNING]
> 任何一分鐘畫失敗（解碼 / 編碼 / json 格式不對、兩個 part 的 frame 對不上）→ 立刻報錯結束。

## 函數表

共用函數（`run_encode_mp4_stage` 等）見 [tool/README.md](../tool/README.md)。

| 函數 | 輸入 → 輸出 | 呼叫時機 |
| --- | --- | --- |
| `check_out_wh_is_valid` | `rectified_wh, up_int` → `None` | 一次；放大後尺寸不得超過 8192（在建立輸出資料夾前檢查） |
| `check_part_3_is_complete` | `meta_3_dict` → `None` | 一次；part_3.0 必須 `complete` |
| `get_entry_dict_list_from_minute_str` | `part_dir_path, part_str, minute_str, frame_count_int` → `list[dict]` | 每分鐘每個 part 一次；讀 json 並檢查（幀序遞增不重複、在影片範圍內；不要求由 0 開始，因為 part_3.0 往後再找可能跨檔案） |
| `get_merged_entry_dict_list` | `eye_dict_list, body_dict_list, minute_str` → `list[dict]` | 每分鐘一次；把眼睛與腹部依 `frame` 合併；兩邊 frame 不一致就報錯 |
| `get_entry_dict_and_mode_str_from_index` | `index_int, frame_to_entry_dict, frame_ints, entry_dict_list` → `(entry, 模式字串, 是否沿用)` | 每幀；有該幀的結果就用，否則沿用前一筆 |
| `get_circle_args_tuple_or_none` | `entry_dict, key_str, up_int, param_dict` → `(圓心, 半徑) \| None` | 每幀每個點；`cv2.circle` 用 shift = 4 的定點數 |
| `get_bgr_tuple_from_key_str` | `entry_dict, key_str` → `BGR` | 每幀每個點；腹部 `predicted` 用不同顏色 |
| `draw_entry_on_arr` | `bgr_arr, entry_dict, up_int, thickness_int, param_dict` → `None` | 每幀；畫三個圓 |
| `draw_zone_on_arr` | `bgr_arr, zone_floats, up_int, thickness_int` → `None` | 每幀；橘色橢圓，`zone_floats = [cx, cy, a_par, a_perp, angle_deg]` |
| `draw_label_on_arr` | `bgr_arr, text_str, up_int` → `None` | 每幀；左上角標字 |
| `get_clock_str_from_minute_str` | `minute_str, sec_float` → `str` | 每幀；`HH:MM:SS.mmm` |
| `get_convert_func_from_entry_dict_list` | `minute_str, entry_dict_list, out_wh, up_int, param_dict` → `func` | 每分鐘一次；回傳區域函數 `get_drawn_arr_from_bgr_arr(幀序號, 秒, bgr_arr)` → 畫好的放大影格（每幀呼叫） |
| `run_minute_stage` | `minute_str, in_mp4_path, out_mp4_path, entry_dict_list, out_wh, up_int, param_dict` → `dict` | 每分鐘一次；編碼一分鐘並回傳統計 |
| `run_all_stages` | `argv_strs` → `None` | `main()` 呼叫；整個流程 |
| `main` | — → `None` | 進入點 |

> [!NOTE]
> 檔案開頭的 `get_tool_dir_str_from_argv_strs` 與 `sys.path.insert` 是固定樣板：先用標準函式庫讀 manifest.json（第一個引數）找到 tool 資料夾，再載入 `tool_main` / `tool_manifest`。
