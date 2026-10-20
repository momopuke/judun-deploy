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

## 可直接供正式版整合的瀏覽器成品（非正式發布）

原有 `p3/report-integration.cjs` 是 CommonJS，**不能直接以瀏覽器 `<script>` 載入**。現已增加明確的瀏覽器進入點 `p3/report-browser-entry.cjs`，由 CI 使用 esbuild 打包：

```sh
npx esbuild p3/report-browser-entry.cjs --bundle --platform=browser --format=iife --target=es2020 --minify --outfile=p3/results/judun-p3-price-navigation.browser.js
```

產出的單一腳本在**受控正式報告渲染程式完成對接後**，以 `window.JudunP3AuthorizedPriceNavigation.continueToPriceAfterVerifiedUnlock(...)` 呼叫；在未經後端授權確認前不得呼叫。CI 另使用 Chromium 在桌機與手機的**隔離 HTML 報告假資料頁面**，實測 bundle 能載入、拒絕未授權及跨案件導覽、允許真實 DOM 價差區塊顯示和焦點定位，沒有任意上傳/付款/發送網路請求。產物以 `NOT-DEPLOYED` 命名存入 GitHub Actions，**不是正式網站檔案**。

為避免使用者於載入期間切換報告導致焦點落在過期案件，報告接線器在 mount、ready、find、focus、scroll **每階段**都核對當前已授權 `reportId` 與原報告容器仍然相同；切換後拒絕完成，不能跨案件導覽。正式版仍必須使用獨立後端授權校驗，不得把此 UI 比對當成權限控制。



## 2026-10-20 真正 v1.2.114 完整首頁副本前後對照

已把公開正式 v1.2.114 原始 HTML（323,152 bytes）與完全可逆的單行修正版分別在網路隔離的 Chromium 瀏覽器載入，並以沙盒 job ID 呼叫 `unlockTier`。兩份完整首頁只存於 GitHub Runner 臨時目錄、不發行副本，不接觸付款、上傳或正式 API。

- 桌機 1440px 與手機 390px：原版 ProMax 儲存 `report-five-themes`，修正版寫入 **`report-price-items`**；Basic 前後均是 **`report-price-items`**。
- 原品牌標語、`fileInput`、`dataConsentInput`、`submitBtn` 保留；`checkMicroStatus` 與 `openPreferredJudunReport` 函式原文完全一致。
- 原版 HTML SHA-256：`092f952d45b44e1ca5f526d610864a34893f861cc4ee3f587f8fc808ffcbbad8`；修正版 SHA-256：`2fbf3e3fd69d1bd20e56eed88678e4ed9a3542126c8307aba79ae302f5b6604d`。若公開來源 SHA 變動即停止，且不允許兩個 staging 輸出路徑相同或覆寫既有檔案。
- [GitHub Actions #39428564483](https://github.com/momopuke/judun-deploy/actions/runs/39428564483)：桌機及手機 `P3_ACTUAL_HOMEPAGE_SANDBOX_PASS`，quality、首頁五尺寸和正式發布區保護均成功。

**這證明公開正式首頁的單行修補在隔離瀏覽器中有效；不代表真實付款 E2E、PDF 或正式部署完成。** 必須透過原權威 v1.2.114 可編輯來源與既有受控 Ed25519 簽署發布通道，完成同案件付款、報告/PDF 實測，才可正式發布唯一新版本。不可用 GitHub 候選源碼假冒正式網站。


## 2026-10-20 P3 新發現：否定完成狀態被誤認為成功

對 v1.2.114 公開前端 `checkMicroStatus` 的完整執行，揭露 `String(data.status || '').includes('完成')` 會把**未完成、付款尚未完成、完成失敗**等文字當作完成；若模擬後端同時返回 `unlock_task.state=completed` 和一段假的報告 HTML，原版會進入看價差。此外，若狀態文字為完成但 `unlock_task.state=pending`，原版也會掛載。**這是隔離測試中，刻意製造彼此矛盾的後端資料，不代表實際正式後端會回傳這些值、也不代表現網未付款可以取得報告。**

因此現有 `p3/patch_paid_preference.py` 擴為**唯一兩敘述修補**，不建立第二個網站或新發行通道：

1. `unlockTier`：ProMax 和 Basic 的預設章節均為 `report-price-items`。
2. `checkMicroStatus`：原有完成分支增加常見否定詞（未完成／未能完成／完成失敗／失敗／取消／中止）排除條件；在 tierMonitor 下如果有 unlock_task，必須是 `completed` 才能進完成區塊。保持原有成功回呼的報告渲染與使用者主動選擇章節，**不更改實際後端權益與付款 API**。

完整 v1.2.114 公開 HTML 原始 SHA-256：`092f952d45b44e1ca5f526d610864a34893f861cc4ee3f587f8fc808ffcbbad8`；本輪唯一兩敘述修正版 SHA-256：`de4115397ce7e1aa0267243dab75d4bd61dbe04f9bb8eef04a69971491605c1f`。與此 SHA 不符時禁止直接套用，必須回到正式原始碼再審。

最新 [GitHub Actions #39442619160](https://github.com/momopuke/judun-deploy/actions/runs/39442619160)：Python 230/230、Node 40/40、P3 patch 3/3、**12/12 個真實前端回呼隔離狀態比較**、首頁五尺寸、正式站唯讀完整性、簽章邊界均 success。原版的否定完成狀態會錯誤掛載；修正版全阻擋；正向完成仍能掛載價差。網路、使用者資料、付款及正式站均未受到測試影響。

**非正式付款安全保證**：正式付款/解鎖身分與所有權必須由受信任後端驗證，前端字串檢查不能代替授權；本修補只防錯誤的視覺完成分支。權威原始碼、既有受控 Ed25519 發布與真正支付/報告/PDF E2E 仍為正式上線必要條件。舊文件中「只需修一行」是上一輪歷史狀態，**已由本段最新兩敘述修補取代**。


## 2026-10-21 真正 FastAPI 原始碼的可逆修補與版本相容性

從使用者先前交付的私人 `Judun_v1.2.87_Deployment_Repair_20261005.tar.gz` 確認：
- `runtime/app.py` 是完整 FastAPI 後端（2,700,308 bytes／11,424 行），不是純部署描述；原 SHA-256：`1c5c2c12bcc956af98e9349fefc35c7d0fb6b47568be50921d4ef27ca335247d`。
- `GLOBAL_JS = r"""..."""` 是 Python 中的真實前端 JS 原始區塊；`window.unlockTier` 與 `function checkMicroStatus(...)` 都在其中，兩個欲修敘述各只出現 **1 次**。
- 在本地唯讀解封後，以 Python `compile()` 實測原版和只替換這兩句的 v1.2.87 後端都能通過語法解析，反向替換完全還原原始碼；舊版修補後 SHA-256：`7c4d5369ea739ca0c249c9dc9d48e6718fca0738f5a825aa01cb1d79ada33bbd`。
- v1.2.87 包含此前的 HTTPS receiver、受控發布代理及 rollback 設計痕跡，但**不可直接用 v1.2.87 源碼覆蓋線上 v1.2.114**；不得把私人完整原始碼或簽章私鑰上傳公開 GitHub Repo/CI。

新工具 `p3/patch_authoritative_app.py` 接受**正式受信任工作目錄的完整 `app.py`**，強制使用操作者核對的整份來源 SHA-256、確認 `GLOBAL_JS` 與兩個已知函式內的目標敘述、原版及修正版 Python `compile()`、逐位元可逆，只建立**不同路徑的唯讀驗收候選檔**，且用檔案排他建立避免覆蓋任何已存在的路徑：

```bash
python3 p3/patch_authoritative_app.py \
  --input /trusted/authorized/current/app.py \
  --expect-sha256 "<SHA256_FROM_INDEPENDENT_TRUSTED_RELEASE_MANIFEST>" \
  --output /trusted/staging/judun_p3/app.py
```

⚠️ **來源版號鎖定**：`--expect-sha256` 不可直接拿待修的同一個檔案即時計算後當作版本認證，必須先從**獨立且受信任的現行正式發行紀錄**取得預期 SHA-256，並確認該筆發行是線上現版（非倉庫過去的 stable 指標）。已知歷史 `v1.2.87` 後端 SHA `1c5c2c12...` 已納入硬性拒絕名單。新增 AST 檢驗要求兩個改動只存在於真正模組層級 `GLOBAL_JS` 字串常數內，不接受偽造／巢狀／運算結果文字；通過此關也**不等於**取得現版或權益驗證權限。

上方命令是**在已授權的正式原始碼工作環境中**執行的流程範例，不應在不明機器、不明版本直接使用。產生候選仍需查現版 backend API 權益、真實 Basic/ProMax/付款失敗/重複回呼、報告與 PDF，通過後由原授權發行者以**既有簽章、同一正式版本發布**。新工具既不碰 VPS、不使用簽章私鑰、不變更 DB，也不自行宣布付款已開放。

自動測試包括拒絕錯 SHA、錯版本、錯函式區塊、無效 Python、輸入/輸出重疊、覆寫既有檔案；唯有取得**現行 v1.2.114 的權威 `app.py`**才能完成正式版本驗收。DigitalOcean 插件提供 VM 管理而沒有此對話內的 SSH Shell；此工具不可替代實際部署權限。
