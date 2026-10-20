# 居盾 P3｜現行正式站接線（只改成功導覽，不改付款）

> **整合候選，未部署。** 本目錄不是第二套網站，不取代現有 v1.2.114 的受信任原始碼、資料庫或簽章發行。

## 已核對的正式版事實

於 2026-10-20 使用 GitHub Actions Chromium **直接讀取現行公開網站**（非歷史版、非付款模擬），桌機 1440、手機 390 都觀察到：

- `window.unlockTier`、`window.checkMicroStatus`、`window.openPreferredJudunReport` 確實存在。
- `unlockTier` 的同一個局部章節選擇段出現 `promax`、`report-five-themes`、`report-price-items`；仍存在依方案選不同預設章節的程式位置。
- `checkMicroStatus` 呼叫 `openPreferredJudunReport`；後者引用 `highlight_url`。因此後端已完成後存在可能跳精華頁／預設頁的分支，**尚未實際觸發付款成功狀態來證實使用者會走哪一支**。
- 未登入首頁沒有 `#report-price-items`，這不表示付費報告無此區塊，因為報告可能登入解鎖後才掛載。
- 現網是 v1.2.114，deep artifact integrity = PASS，首頁仍告知「付費功能測試模式」。

驗證紀錄：[GitHub Actions #39419536482](https://github.com/momopuke/judun-deploy/actions/runs/39419536482)。

## 需要對接的實際正式流程

正式後端先透過原有登入、案件所有權、付款／測試碼核銷及解鎖作業建立可靠結果。在**已確認完成**的回呼中：

1. 確認返回結果的 `reportId`、`entitlementReportId`，皆等於目前已授權報告的 ID。
2. 對 basic / promax **都**將完成後首次導覽目標設為 `report-price-items`。不要自動轉 `report-five-themes`，也不要讓 `highlight_url` 優先取代這個首次落點。
3. 透過既有正式報告渲染函式，先載入顯示該案件的價差章節，然後焦點及滾動到該區。**不得**在登入前直接造出假的價差區塊。
4. 精華版、完整版、五大行動及 PDF 仍由使用者主動切換，**不移除**原功能。
5. 逾時、找不到章節或授權不足時回傳明確錯誤，不能重複扣款、隱瞞失敗轉向精華版。

`report-integration.cjs` 提供這個 **只處理報告 UI** 的接線器，呼叫例如：

```javascript
// Place only within the original authorized, server-confirmed completion callback.
// The production build must BUNDLE p2 and p3 CJS modules; raw .cjs is NOT
// directly executable as a standalone HTML <script> with no module loader.
const {continueToPriceAfterVerifiedUnlock} = require("./p3/report-integration.cjs");
const outcome = await continueToPriceAfterVerifiedUnlock(serverVerifiedCompletion, {
  currentReportId: authorizedReportId, // obtained from trusted report session
  root: document,
  renderAuthorizedReport: (target, {reportId,signal}) =>
    existingAuthorizedReportRenderer.openSection(reportId, target, {signal}),
  whenRendered: (target, {reportId,signal}) =>
    existingAuthorizedReportRenderer.waitForSection(reportId, target, {signal}),
});
if (!outcome.ok) {
  // Show controlled error using the existing UI (do not silently fall back
  // to highlight_url and do not request another payment).
  showExistingReportNavigationError(outcome.reason);
}
```

**注意**：`serverVerifiedCompletion` 必須來自原有**可信後端、已驗證使用者及該案件權益**的回應，而不是 query string、localStorage、JSON 由前端任意宣告的 `entitlementVerified:true`。本接線器只能防錯誤導覽，不能自行成為存取控制；真實報告 API 每次仍需驗證所有權及方案權益。上述 `existingAuthorizedReportRenderer` 與錯誤顯示函式都是接線示例，**不是宣稱正式 v1.2.114 一定有這些名稱**；需在正式原始碼中映射現有實際函式，不得直接貼上執行。

## 硬性發布條件

- 取得 **v1.2.114 權威可編輯原始碼**（現在 GitHub 僅有 CMS 加密發佈/還原文件，非原始檔）、現有 QA registry schema 和可信服務部署工具。
- 不碰已核准首頁的住宅照片、文字、字型、海軍藍／墨綠／香檳金視覺。
- 使用受控付款沙盒／測試碼和受權報價資料，確認 Basic、ProMax、補差價、未付款、付款失敗、重複回呼、現有案件續接。檢驗報告 HTML、精華版、完整版、PDF、手機/桌機。
- 用原有的**單一** Ed25519 受控簽署發布，核對版本、build ID、artifact SHA、回復點。
- 未取得這些條件之前，PR #9 仍為 **Draft**，正式付費測試模式警語保留，不能宣稱整合已部署或上線。

## 本目錄的自動驗收

- `node --test p3/report-integration.test.cjs`：真實 UI 的安全接線行為模擬，不會呼叫正式付款。
- `node p3/site-contract-inventory.cjs`：Playwright 公開端點**唯讀**讀取既有章節及函式線索，不會點解鎖、上傳、輸入個資或存取權限介面。
- `python3 p3/production_readiness.py`：只讀現網 health 與品牌／付費測試模式，會阻擋缺少真正原始碼與簽署環境的正式發布。
