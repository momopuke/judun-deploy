# 居盾發布作業

> **最新受信配置（2026-11-22 OIDC 閘門）**：正式 signed release PR 與 60 秒後驗改用 GitHub Actions 每次工作取得的短效 OIDC 身分，再向**獨立 VPS 本機測試站健康唯讀入口**查核；不應再把 ChatGPT Sites 全站 SIWC bypass `JUDUN_STAGE_AUTH_TOKEN` 配成 GitHub Secrets。以下舊章節提及該 secret 的描述保留為歷史失敗/RCA，**已由此 OIDC 設計取代**。唯有 `ops/JUDUN_STAGE_OIDC_GATEWAY.md` 所列 TLS ingress 和 VPS 本機實機啟用、真正 OIDC CI 完整雙站 60 秒 PASS 後，才可解除下一版發布 HOLD。程式碼及 GitHub 單測 PASS 不代表此入口已上線。

每次發布由總管接手到兩站驗收完成。站主只需要提出發布需求，後續簽章、測試、安裝及回讀全部由發布團隊與既有代理處理。

| 角色 | 責任 |
| --- | --- |
| 工程 | 從上一個已驗收版本建立候選包，在隔離測試站部署，演練升級及資料遷移後回退。 |
| 獨立品管 | 使用合成資料實測上傳、評分、Basic／ProMax 解鎖、報告、PDF 與回退，對同一候選包留下私有回執。 |
| 總管 | 核對候選測試站與品管回執，簽署同一候選包並開發布 PR。檢查確切提交的驗簽結果，合併後追蹤正式安裝、自動回讀兩站、處理失敗及保存完整交付包。 |

## 前置硬門檻 Gate 0（每次改版前，總管必查）

**目標：避免「程式寫完才發現不能簽章或部署」重複發生。** 在安排下一版功能開發、切換新候選或宣稱可上線前，總管必須以新鮮、可覆核的**原執行環境證據**確認：

1. **受信任簽章器真可操作**：原 CMS 加密／Ed25519 簽章程序、固定公鑰與已授權發布身分可完成一次不影響正式站的安全自測；只有公鑰、舊簽章或文字聲稱不算成功。私鑰不得外傳或寫入 GitHub。
2. **VPS／部署代理真可操作**：原有 VPS 授權遠端執行通道、安裝代理、版本回讀與可回退基準能實際通過唯讀探測。Droplet active、HTTP 健康或 GitHub CI 單獨 PASS 不等於可安裝。
3. **獨立測試站與獨立 QA 可操作**：隔離程式／資料／金流的候選環境可真實啟動、owner 授權有效，且獨立 QA 回執可安全寫入、重新取回並核對；離線模擬不等於實站通過。
4. **原子發布保護有效**：main 受保護、同一候選的 `judun/release-gate` 可實際檢查確切 PR head；原加密封包、簽章與清單仍須由原發布器以同一簽章身分產生。

任一項 FAIL、證據過期或無法核實 → **Gate0=BLOCKED，RELEASE HOLD**。總管將具體失敗位置、原始證據、唯一負責人及可重試條件記錄在 [GitHub #22](https://github.com/momopuke/judun-deploy/issues/22)，並先交既有發布專責修通原通道；**不增加第二發布系統、不重新生成產品候選包、不要求站主每版登入 VPS／貼指令**。原通道恢復且 Gate0 真 PASS 後，才按本文件原有步驟往下。

## 唯一版本交棒與可驗收結案

每份候選都使用同一 `candidate SHA256`、`source_tree_sha256`、版本、原基準與私有 QA 證據，分別記錄以下狀態（每個 PASS 都需證據）：

`SOURCE_READY` → `GATE0_PASS` → `QA_PASS` → `SIGNED` → `DEPLOYED` → `LIVE_VERIFIED`。

**只有 `LIVE_VERIFIED` 才能對使用者報「上線完成」。** 同一故障連續兩次發生，工程必須交出根因分析（RCA）、改變處理方法並加入重現／防回歸測試；不可只重試、改無關程式或再次派同一工作。工程交件立即交獨立 QA，QA 真通過後交發布專責，正式與測試雙站同版真驗收後由總管唯一結案並保存原始碼全包。監控排程只負責檢查與交棒，**不等於部署權限或自動復原能力已存在**。

狀態視圖沿用 [GitHub #22](https://github.com/momopuke/judun-deploy/issues/22) 和 NEXUS；不新增客戶可見管理頁、常駐 VPS 服務或第二套儀表板。當事實過時，須讀原始 release manifest、Actions run 及站點回執更新，不能沿用舊版檢查點。

## 每版如何結案

1. 隔離測試站先通過候選版健康與功能驗收，才提交正式發布 PR。正式站在此階段繼續服務原版本。
2. 總管在確切 PR 提交收到 `judun/release-gate` 通過後才合併。清單、簽章及唯一引用的加密封包須屬同一候選版。
3. 合併啟動既有正式部署代理的拉取流程。保留原有安裝及回退機制，由發布工具透過兩站健康端點核對簽章清單上的版本、部署識別、原始碼樹和完整檔案數。兩站必須就緒、零差異，正式站與測試站各自回報預期金流模式。
4. 到期無法取得部署或檢查證據時，先保留失敗診斷與回退結果，再回報阻礙。兩站通過且品質回執可覆核後，才宣告完成。

## 一次性啟用與驗收

- 先讓發布閘門進入 `main`，以一般 PR 取得確切提交的 `judun/release-gate` 狀態。確認來源為 GitHub Actions，再由既有 GitHub 管理員套用 [main-release-protection.json](main-release-protection.json)。查詢對 `main` 實際生效的 PR、禁止強制推送及指定狀態規則。開一個乾淨 PR 重驗，並以本機測試驗證竄改封包、混入其他檔及舊發版基準會被拒絕。
- 在既有 VPS 透過授權的維運通道啟用 [隔離測試服務](JUDUN_STAGING_ISOLATION.md)。以現有版本切換，保留原測試站的網址及擁有者權限，驗證正式站部署識別與程序。再以不同候選版本證明測試與正式的程式路徑、檔案身分及程序彼此隔離。
- 試跑一輪完整發布，保留測試站先行、正式代理安裝，以及兩站自動回讀三段時間戳與結果。GitHub 發布授權、簽章與測試站擁有者權限使用既有核准環境。傳給發布工具的 `GITHUB_TOKEN` 使用已獲授權的 GitHub App 安裝憑證或 PAT，以觸發 `pull_request_target`。續版流程從同一授權環境執行並自行驗收。


## 已發布版自動雙站複驗：2026-11-22

本次 v1.2.190 的正式簽章發布由 PR #35 和原 `judun-autodeploy.timer` 完成，GitHub Actions `Verify JUDUN signed release and production` 已能核對 CMS+Ed25519、正式站 build/deep/ready、98/98、零差異及受保護業務路徑。本項只在**該流程完成後**新增另一個**唯讀** `postrelease-dual-site-recheck` 工作，不重新發布 v190、不操作現有付款、DB 或 rollback。

- 第一回合：獨立讀取 `channel/stable.json` 的受信簽章，正式與測試兩站各取 build、deep、ready；要求 release、artifact、build instance、source tree、受管檔案數**跨兩站完全一致**，正式 `payment_mode=ecpay_live`、測試 `payment_mode=test_unlock`；再即刻重讀正式站以擋切版中 split-brain。
- 隔至少 60 秒後：重驗原簽章及兩站相同五欄和各自金流模式；兩次收據的 signed manifest SHA、版本與兩站檢查結果都必須一致。任何 mismatch、stage 401/403、授權缺失、簽章不符即 **BLOCKED/CI FAILURE**，不是 PASS。
- 第一回合收據以 0600 寫入 GitHub runner 暫存，僅含 release 身分與兩站**非秘密**的健康欄位。Actions 留存 30 天，不含 session token、客戶資料、API key、Email 或 PDF 內容。
- 觸發：未來 `main` 有 signed stable channel / encrypted release 更新時，由原 `.github/workflows/verify-v1286-live.yml` 在既有 production verification 通過後自動執行；workflow 變更本身也會觸發。
- **唯一待驗的環境前提：**GitHub Actions 必須有專用、**最小權限且僅可讀 staging health** 的 secret `JUDUN_STAGE_AUTH_TOKEN`。如未設定或權限不足，CI 必然 FAIL；不得改成跳過 staging 或把一般 Sites owner 登入憑證貼上對話／提交 repo。使用 GitHub Repository Actions Secrets 或既有授權發行環境管理，變更/撤銷憑證應有權限審核。這並不提供 VPS Shell 或 CMS/Ed25519 簽章權限。
- **失敗處理：**此工作只做唯讀驗收、輸出精確故障代碼並將該 Actions 標記失敗；不自動替換正式包或私下回退。正式 agent 的**原有**安全回退機制與正式發布者仍是唯一具權限的修復入口；需要保留失敗 run URL、舊新版本/target SHA 與 RCA，再由授權 owner 處理。
- 仍需另外證明原 signer 的下一版安全自測、同 SHA 獨立 QA、一次真正 v191+ 測試站與正式站端到端發布，以及回滾演練。只有實際重跑、原代理與雙站複驗俱全才能宣稱「未來每版零 FinalShell」**完整達標**。


## 2026-11-22 二次穩定化：真證據保留、避免不相關變更造成誤報

- 首次健康驗證成功 **不再**上傳為「雙站已完成」證據。新 `p3/release_postcheck.py --phase minute` 在兩次網站結果、固定 signed channel manifest SHA、60 秒以上間隔均 PASS 後，才使用 `--final-receipt` 將 **`judun-postrelease-final-evidence.v1`** 回執以 mode 0600、不可覆寫的檔案寫入。GitHub Actions 只上傳這份真正 PASS 的雙次回執，不上傳未完成的初始回執。若任一失敗，沒有完成證據且 job FAIL，防止把「只跑一次」誤當結案。
- `receipt` 改為在跨兩站核對**前後再次計算 GitHub signed manifest bytes SHA**。若期間 main channel 改變，立即 FAIL，避免切版競態。
- 新增 `classify-push` 判斷 GitHub push 是否包含 `channel/stable.json`、對應簽章或 `releases/**`。**新正式 signed release** 或有權限的明確 `workflow_dispatch`，一定觸發正式站與 owner-only staging 的雙次實測；**只有文件／工具變更**時改跑獨立 offline guard，不對既有正式 v190 無端宣告雙站異常、也不消耗有權限的 Site owner session。未知 push base 則 fail-closed 視同正式變更。
- 已知環境失敗 `POST_RELEASE_STAGING_AUTH_MISSING`：GitHub Actions Repository Secrets 尚未配置 `JUDUN_STAGE_AUTH_TOKEN`。這不是 v190 正式站故障，**當下一次有正式簽章發布時仍會使雙站 gate FAIL**；在最小權限測試站讀取身份合法接通前，不准宣稱自動雙站發布/自我回退已完成。
- 一個新的只讀 checker 無權擅自回滾。若正式站版本錯誤，`verify` job 也 FAIL；由原受信任部署代理及有權限發布者針對真根因操作，禁止 GitHub Actions 偽造回滾。


## 2026-11-22 自動失敗收據：事件觸發，不用每小時輪詢

- 每次 GitHub `Verify JUDUN signed release and production` 執行，當正式簽章/版本校驗、分類、離線回歸或**應執行**的雙站一分鐘複驗 FAIL/CANCELLED 時，`report-failed-release` 會在原既有 [GitHub #22](https://github.com/momopuke/judun-deploy/issues/22) 自動發出**不含秘密**的機器事故紀錄；平常完全不觸發，也不新增 cron/systemd timer。
- 每筆記錄固定 workflow run URL、attempt、受保護 commit、失敗 job 名稱與各工作狀態。每輪同 run+attempt 使用特定 marker 去重，只信任 GitHub Actions bot 自己的留言，防止公開留言冒充完成。**真根因尚未讀取原日誌前只能標 BLOCKED/NOT_VERIFIED，絕不亂寫「網站壞了」。**
- 此寫入程序的 `GITHUB_TOKEN` 僅短期存在於 CI 新增的報告 job，權限僅 `issues:write` 和 `contents:read`；從不獲得任何 staging owner token、Ed25519/CMS 私鑰、VPS 權限，也不存取客戶 DB/付款紀錄。
- 發生失敗並不代表自動修復成功；真正修復由原有授權部署專責負責，必須在 #22 紀錄 failure_id、root cause、最小修正與 regression test，才能重跑下一輪，不得把事件記錄本身當做 rollback/再次上線。
- 此流程具事件驅動，可代替每小時輪詢檢查「有否失敗」，但**不能代替**已授權 staging-only health credential `JUDUN_STAGE_AUTH_TOKEN` 的一次性安全配置。正式版後驗缺授權仍會明確 FAIL 並留下可追溯事故。



## 2026-11-22 Gate0 再前移：**先驗測試站，再允許簽章 PR 合併**

過去 v1.2.190 的後驗簽章版雙站工作第一次真執行（run 45030491302）出現 `POST_RELEASE_STAGING_AUTH_MISSING`，代表即使已發布，後驗 CI 才發現 GitHub runner 沒有 stage health 讀取授權。這個阻擋點不得留到**下一次正式版本合併後**才發現。

- 從本次改進起，既有唯一受保護 `judun/release-gate` 在驗證到真正 **signed release PR** 時，除了舊有的三檔、Ed25519、CMS、SHA、私有 QA receipt hash 與正式站基準，**強制**執行原 `verify_staging_live(candidate, stage_token, attempts=1)`；必須讀到**與正準備發布之 signed manifest 完全同 identity/tree/98+ 檔案**的測試站，且 stage `payment_mode=test_unlock`。驗不過前，主線 **不得合併 PR**。
- 使用原 `pull_request_target` 的 **trusted base only** Python 程式，由 GitHub Actions Secret `JUDUN_STAGE_AUTH_TOKEN` 帶入 stage health 只讀授權。不從 PR 候選執行任何程式；不開放任意 Site URL、redirect、私鑰或登入操作；GitHub 自動化只擁有既有 `contents:read, statuses:write`。
- 缺授權輸出 `DIRECT_DEPLOY_PR_STAGE_READ_ONLY_AUTH_MISSING`，測試站 401/403、舊版本或錯 SHA 則由既有 `DIRECT_DEPLOY_STAGING_NOT_VERIFIED` 等原 guard 拒絕；不得以假樣本、舊 token、裸公有 health 或「CI 顯示綠色」代替。
- **一般非 release PR 完全不需要 stage token**，開發工具維護不受此依賴誤阻。下一版正式 release 必須在 GitHub Secrets 確實設定 staging-only **最小讀取權限**並由真實 Site API 接受後才能通過。本對話沒有 GitHub Secrets 或 Sites owner 管理權限，不會要求使用者把令牌貼上公開訊息，也不會把一般管理者大權限 token 偽稱 read-only。
- 這只是「發布前阻斷不可驗收候選」，不是自動簽署新版本，也沒有取消發布後 **60 秒雙站再驗**、正式 VPS 原有回滾權限或私有 QA 完整責任。尚未用下一個新版本實測 stage+正式站+rollback 三輪全自動成功之前，零 FinalShell 目標保持**未驗收**。



## 新版發布閘門：維運修改與正式發版的判斷標準

| 受保護 PR 類別 | 執行條件 | 安全結果 |
| --- | --- | --- |
| 普通文件／ops／QA PR | 原受信 base gate 檢查差異不是受管 signed release 三檔 | 不要求 Sites 授權；可經原 `judun/release-gate` 正常合併 |
| 正式已簽章版本 PR | 僅 manifest、原簽章及單一 CMS 加密包；來源 SHA/QA/目前正式基準通過 | 再驗**候選版本**已在授權測試站且與 signed source SHA 完全相同；否則合併前 HOLD |
| 未簽章、錯誤版本、不同公鑰或混入其他檔案 | 任何前述受信 release gate 條件不成立 | Fail-closed，不得合併，也不能靠手工取消 staging gate |

**可重現驗證**：`p3/test_release_pr_gate.py` 以真 disposable Git object / 合成 Ed25519 fixture 反證上述四條；一般 PR 只需實際 GitHub `judun/release-gate` PASS，不能冒充有授權的正式新版本發布已實測。


## 2026-11-22 測試站健康授權範圍：實證後修正

ChatGPT Sites 文件 https://learn.chatgpt.com/docs/sites/data-and-connections 指出 `OAI-Sites-Authorization: Bearer ...` 是 **SIWC sign-in gate bypass**，不提供 endpoint-level read-only 權限；產生新 token 也會使舊 token 失效。**不可因原 GitHub 驗收程式只使用健康路徑，就宣稱此 bearer token 本身僅能讀健康狀態。**

- 原 `p3/direct_deploy_publish.py::site_get()` 現強制：**攜帶測試站 bearer 的請求只能是** `/health/build`、`/health/artifact?deep=true`、`/health/ready`，且 origin 必須為已固定的 STAGING URL，方法固定 GET，禁止 redirect。任意 admin/payment/query 延伸路徑、正式站 origin、換行或非法 token 皆 fail closed；此為**驗收 client 的最小行為範圍**，不是 Sites 平台對 token 的真正授權限制。
- **尚需部署側獨立最小權限**：不把可跨整個私有 Site 的 SIWC bypass 當 read-only GitHub CI 長效金鑰。優先由原授權 VPS 環境設置健康資料**專用**受信唯讀入口（只能讀上述三路徑，無其他代理、付款/後台讀取或管理能力），並具有獨立可撤銷的認證；或待 Sites 提供可證明 endpoint-scoped 的正式授權能力，先核實再安全配置。原 Sites 繼續 owner-only，不直接改成公開。
- 在未取得前，正式版新候選仍由原 `judun/release-gate` 因 stage health 不能受信驗證而 **HOLD**。不得為了顯示綠燈跳過此 Gate，也不得把已通過的 v190 正式驗證錯稱 v191 的 stage QA。
- 受信簽章器/部署者並不需要匯出私人 Ed25519/CMS 鑰匙到 GitHub；既有原代理、受保護 PR、獨立 QA、rollback 皆不變。

