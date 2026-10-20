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

## 2026-10-21｜原部署通道接線調查（持續保留唯一正式站）

已從過去交付的 `Judun_v1.2.82_PersistentLearning_AUTODEPLOY_20261004.zip` 找回原版 `AUTODEPLOY_AGENT.sh` 和 `AUTODEPLOY_INSTALL.sh`：安裝預設 `BRANCH=main`，`judun-autodeploy.timer` 每分鐘檢查一次 `channel/stable.json` 及 `channel/stable.json.sig.b64`。它會先驗 Ed25519、現行 base artifact，再下載和解密 CMS payload，最後透過舊 advisor 服務更新；但**安裝包只證實設計，不能證明現行 VPS 上的 timer/config/agent 真正運行**。

歷史 v1.2.87 發布紀錄也顯示曾透過獨立 HTTPS receiver 啟動原代理。2026-10-21 的 GitHub Runner 唯讀檢查已證明 `https://deploy-judun.142-93-91-214.sslip.io/health` 及 `/version` 皆回 HTTP 200；新 `p3/receiver_readiness.py` 進一步只核對 `/version` 的公開字串是否**精確等於 `v3`**，並以固定格式輸出診斷結果，不公開原始回應、不送出任何 POST、沒有上傳和付款操作。它已加入既有 CI。

原 VPS 代理的唯讀診斷工具是 `p3/local_agent_diagnostic.py`：在原有授權的 VPS 執行環境執行後，只輸出 systemd 啟用狀態、非敏感設定（repo、branch、channel）、失敗事件計數及本機 health 版號。**絕不輸出部署 token、私鑰、原始 journal 或個資，也不會修改 VPS。** 新測試 `test_local_agent_diagnostic.py` 防止資料洩漏與錯誤推論。此工具不能從 GitHub Runner 遠端執行，必須在真正已授權的 VPS shell 或既有受控接收器上執行。

**下一必要關卡：** 取得現行 systemd timer 狀態及代理失敗分類，確認設定是否仍追蹤 GitHub `main`。若 timer 不運作才修復原 timer；若 signature/base mismatch 應核對現行 artifact 和 GitHub 發行來源；若 HTTPS receiver 的 `v3` 不符先停用部署企圖。通過後才用原權威 v1.2.114 source、受控簽章及既有接收器發行唯一版本，再作付款/報告/PDF 真實 E2E 和 deep SHA 回讀。

先前暫時發布的 v1.2.115 簽章 channel 已還原，現 GitHub `main/channel/stable.json` 是舊 v1.2.106 來源；即使 timer 運行，它也可能因為現行 live 已是 v1.2.114 而記錄 base mismatch。**不可用不一致的舊 channel 覆蓋正式站，也不可把 receiver HTTP 200 當作 agent 也正常。**


## 2026-10-21｜更正正式部署主路線：HTTPS v3，勿和 GitHub pull-agent 混用

從先前交付的正式安裝包實際查證：\`_SYSTEM/DEPLOY_HTTPS.cmd\` 是 **直接 HTTPS ZIP 上傳路線**，向原來的 v3 receiver 送出 \`application/zip\` 封裝，由受控接收器處理部署；它不依賴 \`judun-autodeploy.timer\`。另一份 \`AUTODEPLOY_AGENT.sh\` 才是每分鐘從 GitHub 讀取 Ed25519 簽章 channel + CMS payload 的**獨立路線**。不能把 pull-agent CMS 的包拿去走 HTTPS v3，也不能因 GitHub stable channel 未更新便認定 HTTPS receiver 不可部署。

先前 \`p3/production_delta_patch.py\` 是為 **pull-agent 簽章路線**準備，**不是** HTTPS v3 的正式 ZIP 包。先前推送到 GitHub channel 的 v1.2.115 沒有讓現網升級，已確實撤銷及還原；不能把這當成 HTTPS v3 曾拒絕此更新的證據。下一步應以早期成功的直接 HTTPS v3 路線為優先，定時代理僅作非必要的平行診斷。

### 修正官方 source-tree SHA 雜湊相容性

發現 P3 初版 \`computed_tree_sha\` 與歷史 \`BUILD_PAYLOAD.ps1\` 不同。原打包器使用**檔名 Ordinal 排序、每列「path + NUL + 十進位 size + NUL + lowercase SHA256 + LF」**，包括最後一筆也必須有結尾 LF；初版誤成 \`path + NUL + SHA + NUL + size\` 且沒有最後 LF。已修正，加入獨立固定測試向量、原測試包回歸檢查，避免合成測試自己驗自己卻與正式 Windows 打包器不相容。更正後才允許下一步離線封裝審核；這不代表實際正式 v1.2.114 來源已取得。

### HTTPS v3 原封裝的本機離線驗收

新增 \`p3/https_receiver_bundle_audit.py\` 及 \`test_https_receiver_bundle_audit.py\`：按照歷史 Windows \`BUILD_PAYLOAD.ps1\` 實際格式，驗證 ZIP 中的 \`RELEASE.json\`、\`RUNTIME_RELEASE_LOCK.json\`、\`system_files/DEPLOY_MANIFEST.json\`，目標 artifact/instance/build signature、正式 evidence SHA 鎖定、所有 source ZIP 成員雜湊、另外的 runtime tree SHA、三版本備份與正式資料增量保護策略。禁止路徑穿越、重複路徑、符號連結、額外未列入管理清單的內容及壓縮解壓超限；**只讀本地 ZIP，沒有 HTTP、密碼或任何部署操作**。

> 歷史規格是為了正確建立驗收邊界。當前 v1.2.114 的權威完整來源仍需驗證；不能直接拿舊的 v1.2.82 發行包重新打包覆蓋網站。原 HTTPS receiver 的存活與 v3 協定已由 Runner 驗證，下一個必要條件是取得同現網一致的現行可編輯來源、建立新版本完整 ZIP 並在隔離環境驗證後，才可使用原授權部署憑證直接上傳，最後檢查真實付費/報告/PDF 與 deep-SHA。**未滿足這些條件不發布。**


## 2026-10-21｜加密現版來源實證與雙層封裝驗收（同一 PR）

### 現版加密來源已確實存在，並通過原始封存指紋比對

- GitHub 的 `assets/v1.2.114-expansion-resilience-source-20261017.cms.b64` 解出 **152,551 bytes CMS ciphertext**；以原始 SHA-256 重新計算得到 `82bad0e7fce3dd6000f84d6ecaaf991f10d254fad9baaf2978fd39da7ccd2fd9`，和 2026-10-17 `assets/v1.2.114-expansion-resilience-verification-20261017.json` 裡的歷史正式記錄**完全一致**。這證明密文未漂移，**不代表已解出或獨立驗證 v1.2.114 的原始碼內容**。
- 在不輸出私鑰內容的本地隔離驗證中，早期 `Judun_v1.2.82_PersistentLearning_AUTODEPLOY_20261004.zip` 的 `payload_decrypt_private.pem` 與 `payload_encrypt_cert.pem` 公鑰配對一致；**尚未證明這把歷史金鑰可解開 v1.2.114 的 CMS 密文**。
- 新增 `p3/offline_source_recovery.py` 和 `p3/test_offline_source_recovery.py`：允許在授權的、具有**同一份加密來源與歷史私有封存檔**的本機離線環境中，先比對密文 SHA，再以 OpenSSL CMS 解密到限權暫存；拒絕任意 tar/zip 特殊成員、舊版 APP_VERSION、無效 Python、輸出覆蓋、共用/Git 工作樹。預設只輸出脫敏 hash/版本，不保存明文原始碼；只有指定受限私有資料夾才可選擇存放單一 app.py。**不會自動發布到 GitHub、VPS 或其他雲端**。
- GitHub 連接可唯讀取得密文原始內容，但此次執行環境**未能將 connector 密文檔安全帶入同一個本機容器**與歷史私鑰配對進行真正解密；因此仍不可稱為權威 app.py 已還原。完整來源必須核對現網版本、artifact 及官方 manifest 的獨立 app SHA，才能進入正式 HTTPS v3 發版。

### 已修復 HTTPS v3 的內嵌 runtime 缺口

- 原 Windows `BUILD_PAYLOAD.ps1` 不只檢查外層 `system_files/DEPLOY_MANIFEST.json`，還必須驗證 `system_files/deploy_paid_test.sh` 裡的 `JUDUN_RUNTIME_B64` **二層 ZIP**。原 P3 離線驗收漏掉這一層，是另一個實際安全/相容缺口。
- `p3/https_receiver_bundle_audit.py` 現在還檢驗內嵌 CMS 之外的 runtime ZIP bytes/SHA、對照 `RUNTIME_RELEASE_LOCK.json`、內層 `DEPLOY_MANIFEST.json`、全部已鎖定 runtime 路徑/雜湊、必要的 source registry 與 controller 檔案；支援 LF/CRLF 標記、拒絕重複或缺少標記和過量解壓。合成檔案包含真正雙層 ZIP，變造任一層都被阻擋。
- `p3/public_deep_contract.py` 已由獨立 Runner 唯讀證實現網站 deep-health 的 `deep_verified`、`formal_evidence_sha256`、`source_tree_sha256`、`files_verified` 等欄位確實存在。既有 live preflight 的關鍵欄位**不需放寬**。
- **本輪全部程式仍在 PR #9，沒有部署到 v1.2.114，沒有變更簽章 stable channel、品牌外觀、實際付款或正式資料。** 正式發布卡在「現行來源真實解密/比對、產生完整 v3 ZIP、驗證現有 HTTPS receiver 的實際授權部署」；不得以加密資產 hash 或單元測試通過冒充已上線。
