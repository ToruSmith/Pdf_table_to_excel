"""
PDF 報表擷取核心邏輯（與 UI 框架無關，Streamlit / Gradio 皆可共用）

邏輯：
1) 依 Y 座標分行
2) 找表頭：
   - 優先嘗試「序號模式」：第一個「第一格是純數字序號」列的前一行
   - 找不到就退而求其次用「通用模式」：表頭/資料列的共同特徵是「橫向鋪滿整個
     表格寬度」，這點跟標題、報表資訊這種短句或靠左的 key-value 前言不同——
     它們字數可能不少，但橫向只佔頁寬一小段。取第一個「欄位數夠多、且橫向
     跨幅達頁寬一半以上」的行當表頭
   - 兩種都找不到時，呼叫端可手動指定 header_idx（在偵錯畫面看行號）
3) 欄界不用表頭文字位置，改用資料列文字座標的「最大間距」決定
   （避免寬欄位表頭置中/偏移造成誤判，例如 行庫名稱、載具號碼 這種寬欄位）
4) 判斷「新的一列」還是「上一列換行延續」：
   看這一行有幾個欄位有內容——真正一整列資料通常大部分欄位都有值，
   換行延續的行幾乎只有 1 個欄位有內容（不限定是哪一欄），用這個一般化規則
   取代原本「只看第一欄是不是數字」的寫法，讓序號、非序號報表都能處理
5) 若某頁完全沒有文字層，且呼叫端允許，才用 Tesseract OCR 補文字
   （輔助手段：只有真的拿到掃描成圖片的 PDF 才會觸發，一般報表不會用到；
   且若原始文件本身欄位換行高度不規則 —— 例如每格各自換到不同行數，
   座標分行這套方法本身就不可靠，OCR 準不準都救不回來，需要人工輸入或
   專門的表格結構辨識模型）
"""

import re
import statistics

LINE_TOLERANCE = 3
ROW_HEIGHT_CV_LIMIT = 0.5  # 列高變異係數超過此值，視為版面不規則、座標分行不可靠
SERIAL_PATTERN = re.compile(r"^\d+$")
OCR_LANG = "chi_tra+eng"
OCR_MIN_CONF = 30       # 信心值低於此門檻的 OCR 文字直接丟棄，避免雜訊干擾欄位偵測
SPARSE_ROW_MAX_CELLS = 1  # 一行裡有內容的欄位數 <= 此值，視為換行延續而非新的一列


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


def find_header_index_serial(lines):
    """序號模式：表頭 = 第一個「序號列」的前一行"""
    for i, l in enumerate(lines):
        if i == 0:
            continue
        first_txt = l["words"][0]["text"]
        if SERIAL_PATTERN.match(first_txt):
            return i - 1
    return None


def _line_span(line):
    xs0 = [w["x0"] for w in line["words"]]
    xs1 = [w["x1"] for w in line["words"]]
    return max(xs1) - min(xs0)


def find_header_index_generic(lines, page_width, min_cols=3, min_span_ratio=0.5):
    """
    通用模式（不假設第一欄是序號）：
    表頭/資料列的特徵是「橫向鋪滿整個表格寬度」（欄位排開幾乎佔滿頁寬），
    這點跟標題、報表資訊這種短句／靠左的 key-value 前言明顯不同——
    它們字數可能也不少，但橫向只佔一小段。
    做法：第一個「欄位數夠多，且橫向跨幅達頁寬 min_span_ratio 以上」的行，判定為表頭。
    """
    for i, l in enumerate(lines):
        cnt = len(l["words"])
        if cnt < min_cols:
            continue
        span = _line_span(l)
        if page_width > 0 and span / page_width >= min_span_ratio:
            return i
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


def _row_height_irregularity(lines, header_idx):
    """算表頭後每行 top 座標間距的變異係數，抓「同一列裡不同欄換行數不一致，
    導致座標分行本身就對不齊」這種情況。回傳 None 表示樣本太少無法判斷。"""
    tops = [l["top"] for l in lines[header_idx:]]
    gaps = [tops[i + 1] - tops[i] for i in range(len(tops) - 1)]
    gaps = [g for g in gaps if g > 0]
    if len(gaps) < 3:
        return None
    mean = statistics.mean(gaps)
    if not mean:
        return None
    return statistics.pstdev(gaps) / mean


def _build_col_names(header_words):
    col_names, seen = [], {}
    for w in header_words:
        name = w["text"].strip() or "欄位"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        col_names.append(name)
    return col_names


def _compute_boundaries(lines, header_idx, n_cols):
    """欄界：資料列座標的最大 N-1 個間距（不是表頭文字位置）"""
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
    return sorted(b for _, b in gaps[:max(0, n_cols - 1)])


def _build_records(lines, header_idx, n_cols, boundaries):
    """把表頭後的每一行歸位成欄位，並用「有內容的欄位數」判斷斷行/續行"""

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

        non_empty = sum(1 for c in row if c)
        is_continuation = current is not None and non_empty <= SPARSE_ROW_MAX_CELLS

        if is_continuation:
            for i, cell in enumerate(row):
                if cell:
                    current[i] = f"{current[i]} {cell}".strip() if current[i] else cell
        else:
            if current is not None:
                records.append(current)
            current = row
    if current is not None:
        records.append(current)
    return records


def extract_page_table(page, allow_ocr=False, header_idx=None, header_mode="auto"):
    """
    回傳 (col_names, records, error_message, used_ocr, lines, resolved_header_idx)

    header_mode:
      "auto"    - 先試序號模式，找不到再試通用模式（預設）
      "serial"  - 只用序號模式
      "generic" - 只用通用模式
    header_idx: 手動指定表頭在 lines 中的索引（0-based），指定時跳過自動偵測
    """
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    used_ocr = False

    if not words:
        if not allow_ocr:
            return None, None, "此頁沒有文字層（未啟用 OCR 輔助）", False, [], None
        try:
            words = words_from_ocr(page)
        except Exception as e:
            return None, None, f"沒有文字層，OCR 輔助也失敗：{e}", False, [], None
        used_ocr = True
        if not words:
            return None, None, "沒有文字層，OCR 輔助後仍抓不到任何文字", True, [], None

    lines = group_lines(words)

    resolved_idx = header_idx
    if resolved_idx is None:
        if header_mode in ("auto", "serial"):
            resolved_idx = find_header_index_serial(lines)
        if resolved_idx is None and header_mode in ("auto", "generic"):
            resolved_idx = find_header_index_generic(lines, page.width)

    if resolved_idx is None or resolved_idx >= len(lines):
        return None, None, "找不到表頭（可能不是資料表頁面，或格式較特殊，可嘗試手動指定表頭行）", used_ocr, lines, None

    cv = _row_height_irregularity(lines, resolved_idx)
    if cv is not None and cv > ROW_HEIGHT_CV_LIMIT:
        return (
            None, None,
            "這頁列高很不規則（可能是欄位各自換成不同行數，例如同一列裡有的儲存格1行、"
            "有的2行），座標分行本身就對不齊，繼續抓只會產生看似正常、實際錯亂的資料，"
            "已停止輸出。這種版面建議用手動輸入或專門的表格結構辨識工具處理。",
            used_ocr, lines, resolved_idx,
        )

    header_words = lines[resolved_idx]["words"]
    col_names = _build_col_names(header_words)
    n_cols = len(col_names)

    boundaries = _compute_boundaries(lines, resolved_idx, n_cols)
    records = _build_records(lines, resolved_idx, n_cols, boundaries)

    if not records:
        return None, None, "找到表頭但沒有資料列", used_ocr, lines, resolved_idx

    return col_names, records, None, used_ocr, lines, resolved_idx
