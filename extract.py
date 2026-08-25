"""
PDF 報表擷取核心邏輯（與 UI 框架無關，Streamlit / Gradio 皆可共用）

邏輯：
1) 依 Y 座標分行
2) 表頭 = 第一個「第一格是純數字序號」列的前一行
3) 欄界不用表頭文字位置，改用資料列文字座標的「最大間距」決定
   （避免寬欄位表頭置中/偏移造成誤判，例如 行庫名稱、載具號碼 這種寬欄位）
4) 序號欄空白的行視為上一筆記錄換行延續，自動併回
5) 若某頁完全沒有文字層，且呼叫端允許，才用 Tesseract OCR 補文字
   （輔助手段：只有真的拿到掃描成圖片的 PDF 才會觸發，一般報表不會用到）
"""

import re

LINE_TOLERANCE = 3
SERIAL_PATTERN = re.compile(r"^\d+$")
OCR_LANG = "chi_tra+eng"
OCR_MIN_CONF = 30  # 信心值低於此門檻的 OCR 文字直接丟棄，避免雜訊干擾欄位偵測


def group_lines(words):
    """把 word 依 Y 座標分行，每行內依 X 座標排序"""
    lines = []
    cur = None
    for w in sorted(words, key=lambda w: w["top"]):
        if cur is None or abs(w["top"] - cur["top"]) > LINE_TOLERANCE:
            cur = {"top": w["top"], "words": []}
            lines.append(cur)
        cur["words"].append(w)
    for l in lines:
        l["words"].sort(key=lambda w: w["x0"])
    return lines


def find_header_index(lines):
    """表頭 = 第一個「序號列」的前一行"""
    for i, l in enumerate(lines):
        if i == 0:
            continue
        first_txt = l["words"][0]["text"]
        if SERIAL_PATTERN.match(first_txt):
            return i - 1
    return None


def words_from_ocr(page):
    """OCR 輔助：用 pdfplumber 內建 to_image() 轉成圖片後跑 Tesseract，
    回傳跟 extract_words() 相容的格式（text / x0 / x1 / top）。
    只在頁面完全沒有文字層時才會被呼叫。"""
    import pytesseract

    im = page.to_image(resolution=300)
    pil_img = im.original
    scale = pil_img.width / page.width
    data = pytesseract.image_to_data(pil_img, lang=OCR_LANG, output_type=pytesseract.Output.DICT)

    words = []
    n = len(data["text"])
    for i in range(n):
        txt = data["text"][i].strip()
        if not txt:
            continue
        try:
            conf = float(data["conf"][i])
        except (ValueError, TypeError):
            conf = -1
        if conf < OCR_MIN_CONF:
            continue
        x0 = data["left"][i] / scale
        w_px = data["width"][i] / scale
        top = data["top"][i] / scale
        words.append({"text": txt, "x0": x0, "x1": x0 + w_px, "top": top})
    return words


def extract_page_table(page, allow_ocr=False):
    """回傳 (col_names, records, error_message, used_ocr)"""
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    used_ocr = False

    if not words:
        if not allow_ocr:
            return None, None, "此頁沒有文字層（未啟用 OCR 輔助）", False
        try:
            words = words_from_ocr(page)
        except Exception as e:
            return None, None, f"沒有文字層，OCR 輔助也失敗：{e}", False
        used_ocr = True
        if not words:
            return None, None, "沒有文字層，OCR 輔助後仍抓不到任何文字", True

    lines = group_lines(words)
    header_idx = find_header_index(lines)
    if header_idx is None:
        return None, None, "找不到序號欄（可能不是資料表頁面）", used_ocr

    header_words = lines[header_idx]["words"]
    col_names, seen = [], {}
    for w in header_words:
        name = w["text"].strip() or "欄位"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        col_names.append(name)
    n_cols = len(col_names)

    # 欄界：資料列座標的最大 N-1 個間距（不是表頭文字位置）
    data_xs = sorted({
        round(w["x0"], 1)
        for l in lines[header_idx + 1:]
        for w in l["words"]
    })
    merged_xs = []
    for x in data_xs:
        if not merged_xs or x - merged_xs[-1] > 1.5:
            merged_xs.append(x)
    gaps = [
        (merged_xs[i + 1] - merged_xs[i], (merged_xs[i] + merged_xs[i + 1]) / 2)
        for i in range(len(merged_xs) - 1)
    ]
    gaps.sort(key=lambda g: -g[0])
    boundaries = sorted(b for _, b in gaps[:max(0, n_cols - 1)])

    def col_index(x0):
        idx = 0
        for b in boundaries:
            if x0 < b:
                break
            idx += 1
        return min(idx, n_cols - 1)

    records = []
    current = None
    for l in lines[header_idx + 1:]:
        row = [""] * n_cols
        for w in l["words"]:
            ci = col_index(w["x0"])
            row[ci] = f"{row[ci]} {w['text']}".strip() if row[ci] else w["text"]

        is_new_record = SERIAL_PATTERN.match(row[0].strip())
        if is_new_record:
            if current is not None:
                records.append(current)
            current = row
        else:
            # 沒有序號 -> 視為上一筆記錄的換行延續，併回對應欄位
            if current is not None:
                for i, cell in enumerate(row):
                    if cell:
                        current[i] = f"{current[i]} {cell}".strip() if current[i] else cell
    if current is not None:
        records.append(current)

    if not records:
        return None, None, "找到表頭但沒有資料列", used_ocr

    return col_names, records, None, used_ocr
