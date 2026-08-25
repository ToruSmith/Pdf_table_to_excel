# PDF 報表轉 Excel

適用沒有實體框線、每列文字在同一基準線上的系統報表（不限定第一欄是序號）。例如台水系統匯出的代收回送同批重複資料表、代收行庫回送錯誤資料表，也適用一般「表頭+資料列，欄位密集」的其他報表。

## 檔案結構

- `streamlit_app.py` — 介面（上傳、顯示狀態/預覽、手動指定表頭、下載 Excel）
- `extract.py` — 核心擷取邏輯（與介面框架無關，也是實際做事的地方）
- `requirements.txt` — pip 套件
- `packages.txt` — apt 套件（裝 tesseract OCR 用；Streamlit Community Cloud 支援這個檔案）

## 邏輯（extract.py）

1. 依 Y 座標分行
2. 找表頭：
   - 優先嘗試「序號模式」：第一個「第一格是純數字序號」列的前一行
   - 找不到就用「通用模式」：表頭/資料列的共同特徵是「橫向鋪滿整個表格寬度」，
     跟標題、報表資訊這種短句或靠左的 key-value 前言不同。取第一個「欄位數
     夠多、且橫向跨幅達頁寬一半以上」的行當表頭
   - 兩種都找不到，畫面上會顯示該頁原始文字行，可手動指定表頭在第幾行
3. 欄界不用表頭文字位置，改用資料列文字座標的最大間距決定
   （表頭文字若在寬欄位裡置中/偏移，用它定界容易誤判）
4. 判斷「新的一列」還是「上一列換行延續」：看這一行有幾個欄位有內容——
   真正一整列資料通常大部分欄位都有值，換行延續的行幾乎只有 1 個欄位有內容
   （不限定是哪一欄），不再綁定「序號欄」這個特定假設
5. **列高規律性檢查**：如果同一頁裡不同列的高度變異過大（例如同一列裡，
   有的儲存格 1 行、有的 2 行，導致座標分行本身對不齊），工具會偵測到並
   直接拒絕輸出，而不是給一份看似正常、實際錯亂的資料。這種版面（常見於
   掃描/截圖來源、儲存格各自不規則換行的文件）建議用手動輸入或專門的表格
   結構辨識工具處理，不是本工具的適用範圍
6. **OCR 只是輔助**：只有某頁完全沒有文字層、且勾選啟用時才會用 Tesseract 補文字，
   一般報表不會觸發（本身就有文字層）。OCR 結果請務必人工覆核，尤其是數字欄位

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
