# PDF 報表轉 Excel

適用「第一欄是序號」的系統報表（例如台水系統匯出的代收回送同批重複資料表、代收行庫回送錯誤資料表）：沒有實體框線、欄位密集、部分欄位會自動換行。

## 檔案結構

- `streamlit_app.py` — 介面（上傳、顯示狀態/預覽、下載 Excel）
- `extract.py` — 核心擷取邏輯（與介面框架無關，也是實際做事的地方）
- `requirements.txt` — pip 套件
- `packages.txt` — apt 套件（裝 tesseract OCR 用；Streamlit Community Cloud 支援這個檔案）

## 邏輯（extract.py）

1. 依 Y 座標分行
2. 表頭 = 第一個「第一格是純數字序號」列的前一行
3. 欄界不用表頭文字位置，改用資料列文字座標的最大間距決定
   （表頭文字若在寬欄位裡置中/偏移，用它定界容易誤判）
4. 序號欄空白的行視為上一筆記錄換行延續，自動併回
5. **OCR 只是輔助**：只有某頁完全沒有文字層、且勾選啟用時才會用 Tesseract 補文字，
   一般報表不會觸發（本身就有文字層）。OCR 結果請務必人工覆核，尤其是數字欄位。

## 部署到 share.streamlit.io

1. 把這四個檔案 push 到 GitHub repo（public 或 private 都可以，Streamlit Cloud 支援連接 private repo）
2. 到 [share.streamlit.io](https://share.streamlit.io) 用 GitHub 帳號登入，選這個 repo，Main file path 填 `streamlit_app.py`
3. Deploy 之後，到 App 設定裡把 **Sharing 設成 Private**，加白名單信箱（Google 登入或一次性 email 連結），只有你邀請的人能看
4. `packages.txt` 會在部署時自動被 Streamlit Cloud 讀取安裝 apt 套件，不用額外設定

## 本機測試

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```
