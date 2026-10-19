# 居盾第二階段 P0｜可信證據防護與擴充狀態（尚未部署）

上層依據：[商業化執行基線 #1](https://github.com/momopuke/judun-deploy/issues/1)，及 [擴充狀態逾時 #5](https://github.com/momopuke/judun-deploy/issues/5)。

## 目前完成
- `evidence_gate.py`：獨立、預審前「失敗關閉」的證據資格檢查，**不接觸正式資料庫**。
- `test_evidence_gate.py`：針對外行業資料、優惠廣告、重複禁用網站、無公開來源、價格缺乏可比規格、出處類型等回歸測試。
- `expansion_snapshot.py`：把控制器已知進度寫成小型原子狀態快照；讀取 API 可從快照快速回覆，不必每次重新掃描 runs/正式資料。
- `test_expansion_snapshot.py`：確認讀取快、資料匿名、寫入原子性、停滯不誤判崩潰、不會自動重啟。
- `check_public_health.py`：唯讀 HTTP 現場查核工具；**只在手動觸發 workflow 時執行**，避免持續輪詢 2GB VPS。

## 收錄與可比性決策
| 狀態 | 意義 | 自動寫正式庫? | 用作直接同規格價格比較? |
| --- | --- | --- | --- |
| REJECT | 不相關、禁止來源、非公開 URL | 禁止 | 否 |
| HOLD | 尚無充足真實價格/來源/地區/出處分類 | 禁止 | 否 |
| REFERENCE_ONLY | 台灣公開價格，但不是直接可比的實際工項 | **需經既有 QA 後才可匯入** | 否 |
| COMPARABLE | 有明確工項、單位、規格、公開價格及來源類型 | **仍須經既有 QA 後才可匯入** | 可以進入後續規格相容比對 |

**特別注意：COMPARABLE 不代表成交價、已驗證付款或建議保證價格。** 程式一律將 `transaction_confirmed=false`，不得用廣告或平台估價冒充簽約成交。來源 URL 必須由原始公開來源直出，HTML 連結另開新頁、`rel=noopener noreferrer`。

## 現行網站整合方式（取得權威原始碼後）
1. 先看現有 `source_registry / candidate -> validate -> staging -> formal import` 資料格式，建立將候選資訊映射至 `evaluate(record)` 的 adapter；目前獨立程式**尚未對接真實資料欄位**。
2. REJECT/HOLD 只在候選列表審查/隔離並保留排除理由，不執行批次刪除正式庫。被指定禁止的 domain label `twfuns` 不得再次收錄。
3. REFERENCE_ONLY 保留正確證據層級，不當成可直接精算價差的個案。
4. COMPARABLE 仍需進原本的 QA、邏輯案例去重、正式資料加法匯入。沒有用真實報價 PDF 和審核來源驗證前，**不能放行自動正式匯入**。
5. 在現行擴充控制器每次可信事件/階段結束後呼叫 `write_event_snapshot`，不要在 GET handler 內計算大型欄位；GET 狀態使用 `read_public_snapshot`，搭配控制器的真正執行活性偵測。
6. 停滯提示 `progress_stale` 不是引擎崩潰判決；不能未檢查 checkpoint 就強制重啟、重算累計或重複正式匯入。
7. 發布前必須測網頁、報告連結、真實 PDF、既有特定網站排除與所有正式 DB SHA/人數的更新策略，並經**原有 Ed25519 簽章及深度 artifact 驗證**。

## 線上發現
2026-10-20 上午（台灣時間）的線上唯讀檢查：
- `/health/build` 回 HTTP 200、v1.2.114。
- `/health/source-exclusion` 兩個剩餘數字均 0。
- `/trust-method` 回 HTTP 200。
- **`/health/data-expansion` 超過 20 秒無回應**。可能是狀態 API、服務資源或控制器競爭；目前無法判定真正擴充工作有否停止，因此另外開追蹤 issue #5。

**部署狀態：** 這裡是 GitHub 加密交付通道，沒有正式網站可編輯原始碼及私鑰。此工作為安全可整合的 P0 修正候選與已驗證的 QA，**不是已上線版本**。
