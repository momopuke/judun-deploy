# 居盾 P3｜正式 v1.2.126 與精準修補驗收

更新日期：2026-10-22（Asia/Taipei）。唯一正式站為 https://judun.142-93-91-214.sslip.io/ 。本目錄包含已透過原簽章通道發布的最小修補及未整合工具；PR #9 仍為 Draft，P0 情境入口已上線，P1 尚未完整接入。

## 現版與保留範圍

| 項目 | 已核對值 |
| --- | --- |
| 版本 | 1.2.126 |
| Artifact | `JUDUN-1.2.126-5D4BA415AA32` |
| App SHA256 | `5d4ba415aa3277b2c6753c8fc12bd160d9a1f2d22c9fea2766ff9ed40e2ca743` |
| Source tree SHA256 | `cc382cff7bd06e4020b84952aece020c2162aeaec908dc4f30db8b9b00727068` |
| 公開首頁 SHA256 | `0344222b3b42c9c6a351096c6d1431931af2d3b08ff14e673ce6fc11f211a6ed` |
| 受管檔案 | 81/81，零差異 |
| 上一版 | 1.2.125；保留完整受管來源及原 manifest |

GitHub 及 VPS 的部署回復包只保留目前版與上一版。客戶案件、正式證據及資料庫保護備份不因部署清理而刪除。原 autodeploy 設定維持 main；所有修補保留唯一正式站、原首頁與原案件權益驗證。

## 已發布的行為

- Basic／ProMax 成功解鎖後首次進入「看價差」，精華版、完整版、五大行動及 PDF 由使用者主動選擇；否定完成狀態不觸發完成分支。
- 報價總額由確認工項計算，避免模型文字混入舊示例總價。
- `preflight_render_patch.py` 以 ContextVar 只隔離 readiness 合成報告的正式證據搜尋，保留真實 renderer 與錯誤檢查。
- `quote_grounding_patch.py` 讓初次、續算、逐項、付費及重試分析依實際備註判讀；未列拆除／泥作須明示本單未涉及。
- `report_claim_guard_patch.py`／`report_claim_guard_functions.py` 共用於 HTML 與 PDF 上下文，檢查 0–10 分量尺，未知分制顯示待核對，對無佐證市場結論補上核對限制；不回寫模型結果或價格資料。
- `streaming_search_patch.py`／`streaming_search_functions.py` 將現行資料庫搜尋改為 readonly snapshot 逐筆篩選、保留每案例最佳命中，同分順序與原排序一致；相同查詢共用有界快取和既有鎖。明確傳入資料的原介面及資料瀏覽頁保留。

v124 只改三個搜尋函式、新增一個 generator 及版本資訊；其餘 80 個受管檔案不變，首頁與 PDF 模板來源不變。正式來源明文及私鑰不公開。

## 已執行驗收

- 本機 P3 162、P1 230、Node 55 個測試通過。
- `streaming-search-review.json` 保存真實正式 DB 的三種查詢對照：每種前五筆的完整紀錄、分數與順序一致；搜尋 probe 峰值 RSS 125,648 KB。這是獨立 probe 的數據，不能當成整個 API 服務記憶體或冷查詢改善倍數。
- 正常公開 API 的合成三工項報價合計 82,200 元、3.5/10，已完成 Basic 和 ProMax 測試解鎖，三筆逐項分析沿用、五份指南完整。
- 四種方案／報告 PDF 走原下載與列印佇列；最終頁數、檔案 hash 及目視檢查記錄放在 `validation/v1.2.125-acceptance.json`。
- 正式擴充保留原手動任務與目標；遭 SQLite 鎖定的那輪依原 bundle digest、原 QA 及原加法匯入機制恢復，再核對 audit，無重複匯入。計數與實際入庫分開核對。
- 網站仍為 TEST 付款模式，沒有真實扣款或 SMTP 寄信驗收。

## 工具的信任邊界

- `patch_paid_preference.py --public-review` 對獨立核對 SHA 的現版為 no-op；`--historical-stage` 僅還原出固定 SHA 的 v1.2.114 隔離回歸 fixture，不是正式現版。
- 可逆 source patch 工具要求獨立 release SHA、語法／函式範圍核對及排他輸出，不能用舊版 source 覆蓋現站。
- `production_delta_patch.py`、`https_receiver_bundle_audit.py` 驗證原排序、結尾換行及 manifest 封裝契約；不替代原代理驗簽、備份、回復或正式 QA。
- `attest_encrypted_source.py` 稽核目前保留的上一版 v125 CMS 指紋和 recipient；不解密、不發布。
- `report-integration.cjs` 及瀏覽器 bundle 是候選 UI 轉接器，必須由可信後端確認案件、權益及完成狀態後呼叫；不能作為 API 授權。
- `production_readiness.py`、`public_deep_contract.py`、`receiver_readiness.py` 與公開函式 inventory 僅讀公開端點；CI 沒有私鑰、部署憑證、owner cookies 或客戶資料。

## 執行本機回歸

```sh
python3 -m unittest discover -s p1 -p 'test_*.py'
python3 -m unittest discover -s p3 -p 'test_*.py'
node --test p2/paid-price-route.test.cjs p3/report-integration.test.cjs
```

P1 完整接線、真實付款、寄信及真實屋主報價配對仍須另作實際整合與驗收。歷史狀態由 Git 保留，這份文件只反映目前已核對的範圍。

## v125 調閱等待修正

舊案件冷查詢可能超過調閱頁原本的 18 秒限制。`report_retrieval_timeout_patch.py` 僅把 `serve_search` 的等待上限調為 90 秒，保留原中止與錯誤處理；不修改報告、PDF、付款、權益或資料。v124 四份實際 PDF 驗收仍適用於未變更的渲染來源；v125 另實測已授權舊案件的瀏覽器調閱。

## v126 首頁整合

`home_entry_patch.py` 只更動首頁與版本資訊，保留內嵌 JavaScript 的報告預覽關閉標籤。五尺寸的頁面載入、原檔案選擇器、二次健檢參數、焦點、同意選項與 Logo 寬度通過實際瀏覽器驗收。正式四入口另經逐一點測；見 `validation/v1.2.126-acceptance.json`。

## 恢復既有簽章通道直接部署（2026-10-22）

新增 p3/direct_deploy_publish.py：用已通過原權威 builder 驗收的 Ed25519 簽章 manifest 及 CMS 密文封包，發布至原 GitHub main 自動部署通道。
發布前必須驗證公開簽章、公鑰與 main 一致、封包 SHA256、當前正式 artifact、81 檔深度 SHA、source tree 摘要、既有通道基準以及新密文路徑未被使用。
密文、簽章、channel/stable.json 以同一個 Git commit 原子更新，避免 VPS 輪詢讀到一半更新的發行。
發布後自動核對目標版本、build instance、deep SHA 及 readiness。未達標只回報失敗，不會宣稱部署成功。

執行範例（原受信任 builder／發行環境；不得把 GITHUB_TOKEN 或 signing private key 放入 repository）：

```sh
python3 p3/direct_deploy_publish.py \
  --manifest /trusted/stable.json \
  --signature /trusted/stable.json.sig.b64 \
  --payload /trusted/v-next.cms.b64 \
  --public-key keys/release_signing_public.pem \
  --expected-base-artifact JUDUN-1.2.126-5D4BA415AA32 \
  --expected-source-tree-sha256 cc382cff7bd06e4020b84952aece020c2162aeaec908dc4f30db8b9b00727068
```

不加 --publish 僅作唯讀預檢；通過後由授權發行環境設定 GITHUB_TOKEN，並加 --publish 才會提交到正式通道。
輸入的 3 個檔案必須由現行 v1.2.126 權威原始碼改版、完整 E2E 與原簽章器產生；本 GitHub 候選程式或歷史 v82 原始碼不能直接被簽發。
原 VPS 自動部署代理的簽章驗證、加密解密、回復與正式資料保護均維持原有機制。
付款與報告 PDF 仍須按該次實際修改內容做端到端驗收；單純 deep SHA PASS 不等於全部商用功能通過。
