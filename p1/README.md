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
| READY_FOR_MATCHING | 候選資料具有明確工項、單位、規格、公開價格與來源類型，但尚未跟客戶報價比對 | **仍須經既有 QA 後才可匯入** | 否，還沒有直接比對 |
| COMPARABLE | 透過 `compare_with_target` 嚴格確認工項、單位、規格、地區與台幣價格相容 | **仍須經既有 QA 後才可匯入** | 可以，但仍非成交驗證 |

**特別注意：必須先 READY_FOR_MATCHING 再逐筆與客戶報價嚴格核對，才能獲得 COMPARABLE；這不代表成交價、已驗證付款或建議保證價格。** 程式一律將 `transaction_confirmed=false`，不得用廣告或平台估價冒充簽約成交。來源 URL 必須由原始公開來源直出，HTML 連結另開新頁、`rel=noopener noreferrer`。

## 現行網站整合方式（取得權威原始碼後）
1. 先看現有 `source_registry / candidate -> validate -> staging -> formal import` 資料格式，建立將候選資訊映射至 `evaluate(record)` 的 adapter；目前獨立程式**尚未對接真實資料欄位**。
2. REJECT/HOLD 只在候選列表審查/隔離並保留排除理由，不執行批次刪除正式庫。被指定禁止的 domain label `twfuns` 不得再次收錄。
3. REFERENCE_ONLY 保留正確證據層級，不當成可直接精算價差的個案。
4. READY_FOR_MATCHING 的候選仍須進原本的 QA、邏輯案例去重與正式資料加法匯入；獨立呼叫 `compare_with_target(candidate, customer_quote)` 才能判定 COMPARABLE。沒有用真實報價 PDF 和審核來源驗證前，**不能放行自動正式匯入**。
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

## 與居盾歷史真實程式格式核對（2026-10-20）
已從使用者原始檔案庫讀取 `Judun_v1.2.82_PersistentLearning_AUTODEPLOY_20261004.zip`，實際核對歷史 `data_expansion_controller/controller.py` 的 `page_candidate()`、`formal_bundle()`、`evidence_store.validate_bundle()` 與 `data_expansion_web.snapshot()`。

實際歷史候選使用 `canonical_url`、`region`、`price_stage`、`validation.pass`、`draft_records[].raw_price_text`、`amount_twd`、`unit`，且明示 `payment_verified=false` 與 `approved_comparable=false`。新增 `legacy_candidate_adapter.py` 將這些欄位**逐筆保守轉接**，其中舊版普遍欠缺明確 `spec`，絕不補猜，不以此允許正式自動匯入。已新增 9 項欄位與拒絕案例測試，當時當時合計 **40 項回歸測試通過**：https://github.com/momopuke/judun-deploy/actions/runs/39346080140 。

**重要：v1.2.82 是歷史結構，不是 v1.2.114 現行原始碼。** 整合前仍必須重新核對最新控制器／報價 QA 欄位及正式簽章，不能因歷史格式相符就宣稱線上已整合。

## 2026-10-20 安全加固（第二輪）
- **正式匯入不可由此閘門核准**：全部決策的 `eligible_for_formal_import=false`；`eligible_for_formal_qa` 僅表示可進入既有審核流程，不能繞過正式來源 QA / logical case 去重或付費驗證。
- **相同工項不代表能直接比價**：必須雙方明確記錄一致的 `price_basis`（`unit_price` 每單位價／`total_price` 整項總價）、一致的 `tax_included`（含稅與否）；整項總價還要明確一致的 `quantity`。缺資料或不一致則僅供參考，絕不產生直接價差。
- 舊版 `draft_records` 如果沒有明確計價基礎或規格，維持來源可追查、禁止自動正式匯入，不能拿測試裡的完整人造資料套用到真實施工價格。
- 已完成 **44 項本地 CI 回歸測試**：https://github.com/momopuke/judun-deploy/actions/runs/39353004035 。此為程式測試，**不是**現行 v1.2.114 正式站已部署的證據。

## 2026-10-20 安全加固（第二輪）
- **正式匯入不可由此閘門核准**：全部決策的 `eligible_for_formal_import=false`；`eligible_for_formal_qa` 僅表示可進入既有審核流程，不能繞過正式來源 QA、logical case 去重或付款驗證。
- **相同工項不代表能直接比價**：必須雙方明確記錄一致的 `price_basis`（`unit_price` 每單位價／`total_price` 整項總價）、一致的 `tax_included`（含稅與否）；整項總價還要明確一致的 `quantity`。缺資料或不一致則僅供參考，絕不產生直接價差。
- 舊版 `draft_records` 如果沒有明確計價基礎或規格，維持來源可追查、禁止自動正式匯入，不能拿測試裡的完整人造資料套用到真實施工價格。
- 已完成 **44 項 CI 回歸測試**：https://github.com/momopuke/judun-deploy/actions/runs/39353004035 。此為程式測試，**不是**現行 v1.2.114 正式站已部署的證據。

## 第三輪 P0 防護（2026-10-20）
- **資料是否與裝修有關，必須有來源原文的正面證據**：只根據原始標題／捕捉的公開段落判斷，不接受由擷取程式自行填入 `category=油漆工程` 來挽救無關網頁。
- **轉址安全**：若已知發生轉址卻缺乏最終網址，先 HOLD；轉到禁止網站或非公開網址則 REJECT。跨站轉址須有來源擷取器確認轉址鏈，才能繼續審核；純函式不自行連網，也不保證已檢查實際 DNS／所有 HTTP 轉址，需在採集器做 SSRF 防護。
- 舊版候選資料的 `final_url / resolved_url / redirected` 若存在，轉接後同樣受品質閘門約束。
- 最新 **54 項程式回歸測試通過**：https://github.com/momopuke/judun-deploy/actions/runs/39361875048 。未對正式站資料進行刪除或發布。


## 2026-10-20 下一步：只讀正式核准紀錄 → 真正的報告證據 HTML（整合候選）

本輪新增：
- `formal_registry_adapter.py`：受信任後端透過 SQLite `mode=ro`、`PRAGMA query_only` 讀取 `judun_formal_evidence_approvals_v1` 的正式 QA 核准快照。缺表、缺 DB、核准撤銷、無效日期、資料列不一致、來源變更均「失敗關閉」；不自動建立表、不改正式庫、不執行 schema migration。
- `report_evidence_section.py`：將來源分類、防護、同規格比對、正式 QA 核對及外部引用連結整合成一個具界線的 HTML 區塊；REJECT/HOLD 不顯示；不符合精算條件的來源只能作參考；上限 200 筆待處理來源／20 筆顯示，超出顯示數必告知，不會偽稱全部列出。
- 新增 `test_formal_registry_adapter.py` 和 `test_report_evidence_section.py`：完全合成的臨時 SQLite、失敗/撤銷/過期來源快照、SQL 注入、保留真正不同個案、XSS 逸出、超量處理、完整來源→核准→報告流程的回歸測試。

### 信任界線（不得省略）
1. 正式網站的**既有身分驗證、案件所有權與付款權益**必須先通過，才能由後端產生客戶的報告內容。此模組不提供身分或付款功能。
2. 來源資料必須來自經現有收錄流程覆核的真實資料；正式 QA 必須在自身核准時持久保存**完全一致的來源快照 SHA-256**。不能讓前端自行建立審核旗標或核准內容。未經 QA 即使欄位完全一致仍不給精確價差。
3. `judun_formal_evidence_approvals_v1` 只是**候選版本的新表契約，不是聲稱線上已有此表**；需要先拿到現行 v1.2.114 可編輯程式及真實 schema，與原本核准流程映射後，才能依正式遷移程序建立或改接表，不可直接對原 DB 執行上方 schema。
4. 既有正式證據完全不清空、不重建、不依本模組自動入庫。候選工具不能取代原本去重、人工/既有 QA 與逐跳 DNS/SSRF 防護。
5. 報告引用及預覽仍要進行實際瀏覽器與 PDF E2E 驗收；目前只是伺服器端候選 HTML，**尚未接入正式網頁或 PDF 模板**。

### 內部接線示意（不是目前線上 API）

```python
from formal_registry_adapter import ReadOnlyFormalApprovalRegistry
from report_evidence_section import render_report_public_price_sources

# 只在通過身分／案件所有權／權益驗證的報告 route 裡執行
registry = ReadOnlyFormalApprovalRegistry(TRUSTED_SERVER_APPROVAL_DB_PATH)
result = render_report_public_price_sources(
    server_verified_public_source_rows_for_one_item,
    server_verified_customer_quote_item,
    approved_record_lookup=registry,
)
if result["status"] == "OK":
    html_evidence_section = result["html"]
```

不得將以上 DB 路徑、callback、核准資料、case ID 的所有權結果交由 HTTP 請求內容指定。既有頁面品牌與上傳流程維持不變；下一步是**原始碼與真實 DB schema 映射＋隔離 E2E 驗證**，通過後才可由原單一來源部署流程發布。


## 2026-10-20 持續修正：不得遺漏原始報價工項與完整來源

本輪已新增四個整合候選檔案：`paged_evidence_report.py`、`test_paged_evidence_report.py`、`complete_quote_report.py`、`test_complete_quote_report.py`。

- **來源分頁**：先前超過 200 筆證據直接回 `INVALID_INPUT`；現在可呼叫 `render_paged_public_price_sources` 每次 1～5 頁、每頁最多 200 筆，成功返回 `MORE`＋`next_offset`，繼續到 `COMPLETE`。單一來源快照最多 10000 筆，超過這個邊界不能當作處理完成。分頁會對跨頁完全相同來源快照去重，但同 URL 不同公開報價仍保留。
- **分頁一致性**：來源續頁必須傳回第一頁的 `snapshot_digest`；沒有這項身分或資料內容／次序已更動，明確回覆 `SOURCE_SNAPSHOT_CHANGED`，不拼接不同批次。
- **屋主估價工項完整列出**：`render_authorized_quote_items` 對每個原始工項建立 HTML 區塊，即使該工項沒有來源、OCR 欄位不完整、報價金額不可判定，也會保留並提示人工核對。一次最多 30 個工項、總計最多 5000 個工項；分頁未完成回覆 `MORE_ITEMS`，續頁必須傳 `quote_digest`，避免案件來源被改動後仍混接。
- **報價貨幣不亂換算**：僅在明確 TWD/NTD 時顯示 NT$；非台幣／未確認金額以安全逸出的原始文字和警語保留，不會虛構新台幣價值，也不把每單位價的合計誤稱總價。
- **原文計價基準確認**：`source_price_basis_supported` 對同一個來源價格數字附近的 `每坪`、`／坪` 或 `總價` 證據進行確認。只有 parser 自行填入 `price_basis=unit_price` 但原文其實是整項總價時，會降級參考，不出精確價差。
- **衝突價格描述**：來源同金額有精確與約略／起價說法並存，從嚴只作參考；沒有已核對證據類型或價格階段的約略行情維持 HOLD。
- **正式 QA 身分再保護**：受信任只讀 registry 不接受同一 evidence ID 對應多份來源快照，也不信任審核時間晚於目前時間太多的核准列；候選表的 evidence_id 另加 UNIQUE。既有正式 DB 不自動修改。

所有新增功能**尚未接線到正式網站，也未執行真實客戶報價或付款、PDF 的完整 E2E**。此處的 synthetic SQLite 不等於目前真實正式證據庫 schema。商用部署前仍要取得可編輯權威原始碼與簽章權限；任何單元測試通過都不能當成已發布證據。


## 2026-10-20 追加：擴充控制器健康狀態不得偽裝正常（候選）

- `write_event_snapshot` 不再把每次寫入時間當作實際進度時間：執行中未提供 `last_progress_at` 時保留未知，而不是製造「剛有進度」的假訊號。必須由真正完成批次、驗證 checkpoint 等可信事件更新實際進度時間。
- `read_public_snapshot` 獨立提供 `snapshot_age_seconds`、`snapshot_stale` 與 `last_progress_age_seconds`；區分 API 狀態快照是否有更新、工作是否有真進展。原本 `progress_stale` 仍表示**停滯跡象，不是已證實崩潰**；未知進度則為 `progress_unknown`，未經 checkpoint 認證永遠不可自動重啟。
- 讀取的是最多 8192 bytes 的單一 JSON 檔，對不合法資料結構、負數計數、未帶時區或超前的時間戳一律回報 `unknown`，不讓異常 JSON 導致 health handler 丟出未處理例外。
- `phase` 改為公開可揭露的固定階段名稱清單；無法辨識的階段顯示 `other`，杜絕把原始例外、檔案路徑、帶 token 的 URL 直接寫到對外快照。
- 原子寫入新增檔案 `fsync`，在成功替換前先寫入完整內容。仍須由正式控制器在可信事件呼叫 writer、公開 GET 只讀 reader，才會改善線上 `/health/data-expansion` 卡住狀態。
- 加入「只有 heartbeat、沒有實際進度」、「進度時間在未來」、「狀態快照被破壞」、「敏感 phase」、「空/陣列 JSON」回歸驗證。以上**不保證現行 VPS 的擴充引擎已正常**，也不提供自動強制重啟；正式整合仍需現行可編輯原始碼及受控部署。


## 2026-10-20 後續一輪：可信擴充診斷、安全快照與參考價防誤判

本輪只修改候選分支，沒有部署到現行 FastAPI。

- `read_public_snapshot` 對**過期的閒置/完成狀態**改回報 `snapshot_stale` 並保留 `last_known_status`，避免拿舊狀態誤稱現在正常；完成但 `checkpoint_verified` 未證實時改為 `completion_unverified`。
- 狀態快照額外給出 `status_confident`，它只代表**最近狀態觀察可信**，不表示實際資料匯入已獲核准，也不表示整個擴充引擎進行了有效工作。未提供真實 `last_progress_at` 時，不論狀態是否執行中均不得自動捏造。
- 記錄時間與進度時間不合理（前後超過安全時鐘差）、非有限數值的觀察時間、異常狀態物件，一律降為 `unknown`。比目前已存在快照更舊的**順序寫入**會拒絕覆蓋；若實際上存在多個並行寫入程序，正式控制器仍須另行實施序列化／鎖，不能把這項檢查當作並行一致性的證明。
- 新增 `expansion_health_adapter.py` 與 `test_expansion_health_adapter.py`：只讀小型 JSON 回覆來源、狀態、真進度時齡、快照時齡、人工建議檢查；不掃描 runs，不公開來源 URL/token/錯誤全文，也不允許從 GET 啟動 worker、重建資料庫或進行正式匯入。**不是已經接進現行 /health/data-expansion 的 API。**
- `evidence_gate.py` 增列預估、粗估、概算、參考價、建議價、均價、起步價等約略措詞，這些價格只可作來源參考，不能當成相同規格的精確報價計算價差；需正式 QA 和真實報價後端再核對。

下一個仍需正式站可編輯原始碼、擴充控制器實際呼叫點、原正式 QA schema 與簽章部署能力；僅有單元測試和隔離 HTML 不等於修復了線上逾時問題。


## 2026-10-20 追加可靠性：累計數字、真正的並行寫入鎖與來源稅況

這輪直接修正三個之前的候選整合缺口：

1. **擴充正式新增筆數等累計數字不得倒退**：在同一狀態快照 lineage 上，`rounds_completed`、`validated_total`、`formal_records_added_total` 若低於前次值，即使提供較新的 `updated_at` 也拒絕覆寫。若是合法的控制器重新起算，必須由正式控制器建立新的已授權 lineage，不能默默清零既有歷史。
2. **Linux VPS 並行寫入保護**：新增 `snapshot_write_lock.py`，由 POSIX `flock` 包住舊快照比較及 `os.replace` 完整交易，預設等候最多 0.75 秒；逾時拒絕寫入、由上層做有界重試，而不是繞過鎖去破壞紀錄。鎖檔必須常駐，不能使用後刪除；Linux-only 模組，Windows 需另做合法的跨程序鎖設計，不能假設此版可直接跨平台。
3. **公開報價的稅況必須來自原文**：來源`tax_included=True/False`即使和屋主欄位吻合，也不能獲得精確價差資格，除非**同一個公開價格所在原文**明確標示含稅或未稅；缺稅況、與欄位矛盾或文字同時衝突都只允許參考。避免把未稅來源直接當作含稅報價比較。
4. **完整版的證據覆蓋不能冒充已驗證**：新增 `source_coverage_status`、有來源與缺來源工項數及 `source_price_verification_claimed=False`。即使完整列出每一項客戶估價，仍需區分完全沒有來源、部分有來源、全部具有候選來源與來源錯位；「列完報價單」不是「全部通過正式 QA」。
5. **回歸測試**：並行鎖競爭、鎖釋放、較舊進度或較小累計數字拒絕、無證據／部分證據清晰標示、稅況未記載或與來源矛盾，以及明確未稅仍有機會正確比較等。

以上皆只是候選 GitHub PR #9；**現行服務的狀態 API、擴充控制器、正式報告與付款尚未接線**。Linux 鎖須在正式 controller 事件寫入端以受信任配置路徑調用，GET 路由只應讀取原子快照；部署前必須先核對原正式 DB 及環境版本，不能重放、覆蓋或自行核准既有證據。


## 2026-10-20 效能修復：完整版多工項重複計算來源指紋

既有 `render_complete_authorized_quote_report` 按每頁 30 工項重讀完整屋主工項/來源關聯快照，工項數大時會把相同快照重複雜湊數十至數百次。在 VPS 記憶體／CPU 有限時，這會無謂延長報告產生時間。

目前修改成：**同一次授權同步產生整份報告**時只在開始先對來源/工項各計算一次快照，逐頁共用同一份內部已確認的指紋資訊，最後在發出 HTML 前再完整核對一次，若任何來源、工項數值或排序在處理中更動則返回 `SOURCE_SNAPSHOT_CHANGED` 且 `html=""`，不能輸出拼接報告。這對整份報告的來源/工項雜湊工作量從跟頁數成正比，降低為前後兩次核對；各單頁公開續接 API **仍每次重新計算指紋**，保留獨立使用時的完整性防護。

必要使用前提：只能在已認證、已驗證案件所有權的可信伺服器端，用同一個連續同步請求內的來源清單執行；不可從瀏覽器／HTTP 請求傳入私有 `_trusted_orchestrator_snapshot`。由於清單可能由其他執行緒更改，最終 hash mismatch 會丟棄結果。此修正降低重複雜湊耗時，但**不代表完成真實 VPS 壓測**，也不會替原本超量資料審查新增證據或變更既有 QA。
