# 居盾第三階段｜付費後直接「看價差」驗收契約（尚未部署）

## 核心要求
一旦後端確認用戶已取得 basic / promax 使用權、付款或測試碼真實核准，且相應報告已準備完成，前端**直接顯示 #report-price-items（看價差）**，不能：
- 先跳精華版、五大簽約行動或回到報告首頁；
- 要使用者再按一次解鎖；
- 從本機瀏覽器的字串自行推定付款成功；
- 因查詢中斷重覆請求付款。

## 歷史程式差異（僅供相容修復）
從使用者檔案庫讀取的 **v1.2.82（2026-10-04）** 完整原始碼，確認當時存在以下風險：
- `window.unlockTier`：`promax` 的首選章節是 `report-five-themes` 而非看價差；
- `checkMicroStatus`：解鎖完成時先呼叫 `window.openPreferredJudunReport(data)`，若有 `highlight_url` 會導向精華版；
- 局部任務回復會讀取先前記住的章節，付費完成後可能不是 `report-price-items`。

這些是**歷史版證據**，不能宣稱目前正式 v1.2.114 必然相同。整合時先核對正式原始碼，再用現有報告 API 及身分驗證方式改動成功分支，絕不以注入腳本假造完成。

## 待接入的獨立邏輯
`paid-price-route.cjs` 僅處理**可信後端結果已驗證之後**的畫面導航，不接觸付款 API、解鎖權限、原始碼中的 private keys 或報價資料。它要求：
- `entitlementVerified === true`：由既有安全 API／後端權益狀態確實驗證；
- `tier` 為 basic 或 promax；
- `reportReady === true`；
- `paymentPending !== true`，而且 `unlockTaskState === "completed"`（缺少欄位、未知狀態、執行中或失敗都不可當成成功）。
- 先將已授權的價差章節掛載，再查找 DOM 元件；若章節未產生或畫面載入失敗，回傳可診斷的受控錯誤，不得假裝已進入報告。

滿足以上條件才指定 `report-price-items`。缺少價格章節時顯示受控錯誤，**不隱瞞地跳去其他頁**。

## 線上唯讀探測
`audit_public_funnel.py` 只讀公開首頁，檢查：
- 已核准的 Hero 文案、原上傳欄位/隱私同意與提交按鈕；
- 報告預覽、新版比較、舊報告入口；
- 既有 299 / 599 文案；
- 是否顯示「付費功能測試模式」。

此流程**不會上傳任何個資、不會測試付款、也不會提交測試碼**。讀到測試模式提示不代表付款已經通過正式驗收。真的要上線商業收款，須有正式授權的測試帳單或受控沙盒資料做後端端到端驗收。

## 整合順序
1. 取得現行正式版可編輯 source（目前 GitHub 是加密部署通道）。
2. 確認 `/status/{job_id}` 和付款後 return 對應的**權益核驗事實**；不得僅依前端查詢參數或 localStorage。
3. 在原本成功解鎖/報告渲染回呼中，對 basic、promax 使用 `#report-price-items`，不要再走精華版自動 redirect；維持用戶自己主動選精華版功能。
4. 針對免費→basic、免費→promax、同案件補差價、已有解鎖、付款失敗／查詢逾時、報告生成超時、手機與桌機執行 E2E。
5. 保留正式視覺和完整下載能力，核對版號、報告 PDF 功能、回復點、既有簽章。
6. **驗證前，不刪除首頁「付費測試模式」警告來假裝正式支付已開通。**

## 第二輪修正與驗證（2026-10-20）
- 修正不完整付款任務資料的誤判：`unlockTaskState` 缺少或為未知值時一律拒絕自動跳轉。
- 修正單頁報告顯示時序：先執行 `mount`、再找 `#report-price-items`；若渲染發生例外，回傳 `REPORT_UI_RENDER_FAILED`。
- 追加 3 項測試，現在 **12/12 項通過**：https://github.com/momopuke/judun-deploy/actions/runs/39353272850 。
- 此導航契約仍由現有後端確認權益才能呼叫，並非前端解鎖方法。非同步渲染的實際整合方式仍待現版原始碼確認。

## 目前結果
獨立導航契約的 JS 單元測試、免費首頁唯讀存在性檢查已有自動化流程。`production_payment_ready_verified=false`、`verified_post_payment_see_price=false` 均是忠實狀態，不是故障推測。

## 第三輪 P0 非同步導航加固（2026-10-20）
- 增加 `showVerifiedPriceSectionAsync()`：支援等待 report mount/whenRendered，並具有限時回覆，不把仍在渲染中的價差章節宣稱為完成。
- 超時後不再進行 focus/scroll；同步 `showVerifiedPriceSection()` 偵測到 Promise 型 mount 會明確要求使用非同步版本。
- 若提供 `reportId` 或 `entitlementReportId`，兩者必須存在且一致，防止拿 A 案件的導覽結果去跳 B 案件。**這是用戶端一致性檢查，無法替代後端案件所有權查驗。**
- 最新 **18 項導覽契約測試通過**：https://github.com/momopuke/judun-deploy/actions/runs/39361835577 。正式付款仍未執行 E2E。
