"""
PDF 報表轉 Excel — Streamlit 版
部署於 share.streamlit.io，核心邏輯見 extract.py
"""

import io
import pandas as pd
import pdfplumber
import streamlit as st

from extract import extract_page_table


def build_workbook(sheet_dfs):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for page_no, df in sheet_dfs:
            df.to_excel(writer, sheet_name=f"page{page_no}"[:31], index=False)
    buf.seek(0)
    return buf


st.set_page_config(page_title="PDF 報表轉 Excel", page_icon="📊")
st.title("PDF 報表轉 Excel")
st.markdown(
    "自動判斷表頭與欄界，適用沒有實體框線、每列文字在同一基準線上的系統報表"
    "（不限定第一欄是序號）。自動偵測失敗時，可以在下面展開該頁，手動指定表頭所在行。\n\n"
    "**限制**：如果原始文件本身欄位換行高度不規則"
    "（例如同一列裡，有的儲存格1行、有的2行，導致同一列文字對不齊基準線），"
    "座標式抓取本身就不可靠，工具會偵測到並直接拒絕輸出，而不是給你一份看似正常、"
    "實際錯亂的資料。這種版面建議用手動輸入或專門的表格結構辨識工具處理。"
)

uploaded = st.file_uploader("上傳 PDF", type=["pdf"])
enable_ocr = st.checkbox(
    "沒有文字層時嘗試 OCR 輔助（較慢，數字/帳號辨識可能有誤，需人工覆核）",
    value=False,
)

if "manual_headers" not in st.session_state:
    st.session_state.manual_headers = {}  # page_no -> 手動指定的 header_idx

if uploaded is not None:
    status_lines = []
    sheet_dfs = []
    preview_frames = []
    page_debug = {}  # page_no -> lines（給手動指定表頭用）

    with st.spinner("擷取中…"):
        with pdfplumber.open(uploaded) as pdf:
            for page_no, page in enumerate(pdf.pages, start=1):
                manual_idx = st.session_state.manual_headers.get(page_no)
                col_names, records, err, used_ocr, lines, resolved_idx = extract_page_table(
                    page, allow_ocr=enable_ocr, header_idx=manual_idx
                )
                tag = "（OCR輔助，請人工覆核）" if used_ocr else ""

                if records:
                    df = pd.DataFrame(records, columns=col_names)
                    sheet_dfs.append((page_no, df))
                    status_lines.append(f"第 {page_no} 頁 {tag}：{len(records)} 筆記錄、{len(col_names)} 欄")

                    preview_df = df.copy()
                    preview_df.insert(0, "頁碼", page_no)
                    preview_frames.append(preview_df)
                else:
                    status_lines.append(f"第 {page_no} 頁 {tag}：擷取失敗 - {err}")
                    page_debug[page_no] = lines

    st.subheader("處理狀態")
    st.text("\n".join(status_lines))

    for page_no, lines in page_debug.items():
        with st.expander(f"第 {page_no} 頁：手動指定表頭 / 顯示原始文字行"):
            if not lines:
                st.write("此頁沒有可用文字。")
                continue
            debug_text = "\n".join(
                f"[{i}] " + " | ".join(w["text"] for w in l["words"])
                for i, l in enumerate(lines)
            )
            st.text(debug_text)
            chosen = st.number_input(
                "表頭在第幾行（看上面 [編號]）",
                min_value=0, max_value=max(0, len(lines) - 1),
                value=0, step=1, key=f"header_input_{page_no}",
            )
            if st.button("套用這個表頭重新擷取", key=f"apply_{page_no}"):
                st.session_state.manual_headers[page_no] = int(chosen)
                st.rerun()

    if sheet_dfs:
        preview = pd.concat(preview_frames, ignore_index=True)
        st.subheader("預覽（合併所有頁）")
        st.dataframe(preview, use_container_width=True)

        workbook_buf = build_workbook(sheet_dfs)
        base = uploaded.name.rsplit(".", 1)[0] if "." in uploaded.name else uploaded.name
        st.download_button(
            "下載 Excel",
            data=workbook_buf,
            file_name=f"{base}_extracted.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.warning("沒有任何頁面成功擷取到表格。")
