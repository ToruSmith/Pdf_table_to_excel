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
    "以表頭定位、資料間距抓欄界，適用「第一欄是序號」的系統報表"
    "（例如代收回送同批重複資料表、代收行庫回送錯誤資料表）。\n\n"
    "**OCR 只是輔助**：一般情況不需要勾選，這些報表本身就有文字層。"
    "只有萬一哪天拿到的是掃描成圖片、沒有文字層的 PDF 才會用到，"
    "而且辨識結果務必人工覆核，尤其是水號、金額這類數字欄位。"
)

uploaded = st.file_uploader("上傳 PDF", type=["pdf"])
enable_ocr = st.checkbox(
    "沒有文字層時嘗試 OCR 輔助（較慢，數字/帳號辨識可能有誤，需人工覆核）",
    value=False,
)

if uploaded is not None:
    status_lines = []
    sheet_dfs = []
    preview_frames = []

    with st.spinner("擷取中…"):
        with pdfplumber.open(uploaded) as pdf:
            for page_no, page in enumerate(pdf.pages, start=1):
                col_names, records, err, used_ocr = extract_page_table(page, allow_ocr=enable_ocr)
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

    st.subheader("處理狀態")
    st.text("\n".join(status_lines))

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
