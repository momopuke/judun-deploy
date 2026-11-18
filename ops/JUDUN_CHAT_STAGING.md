# 從 ChatGPT 對話請求部署居盾測試版

一般 ChatGPT 對話透過已連接的私人 NEXUS 外掛送出要驗收的候選。既有 VPS 的測試服務定期讀取 NEXUS 請求，從 GitHub 取得已簽候選包，驗簽、安裝並檢查候選。候選的獨立 QA 和正式發布沿用 [居盾發布作業](RELEASE_CONTROL.md)。

## 發布執行環境一次啟用

1. 依 [居盾候選測試站隔離](JUDUN_STAGING_ISOLATION.md) 確認既有測試網址指向獨立候選服務，並以現行已驗收版本建立基準。使用相容的獨立 Python 環境。
2. 由既有受授權的發布執行環境將 `p3/staging_release.py` 與 `p3/staging_deploy_request.py` 安裝到 `/srv/judun-staging`，檔案由 root 擁有。將儲存庫固定 Ed25519 公鑰 `keys/release_signing_public.pem` 安裝到 `/etc/judun-staging-pull/release_signing_public.pem`。
3. 為測試站建立專用的 CMS 接收者憑證。將公開憑證安裝為 `/etc/judun-staging-pull/recipient.pem`，私鑰安裝為同目錄的 `recipient-key.pem`，權限由 root 管理且私鑰為 `0600`。授權建置程序以公開憑證加密候選包。
4. 使用已授權的 NEXUS Sites 程式讀取憑證，將其保存在 root 專用的 `/etc/judun-staging-pull/nexus-read-token`，設為 `0600`。測試站拉取程式只會將此憑證送往固定的 NEXUS 讀取端點。
5. 安裝 `ops/judun-staging-pull.service` 和 `ops/judun-staging-pull.timer` 後重新載入 systemd，啟用 timer。先以無請求、拒絕無效簽章、同基準成功切換與失敗回復四個情境驗收。比對正式站的版本與服務進程，並用原有 Sites 授權驗證對外測試網址。

## 候選包

可信任的建置及簽章程序產生三個檔案，存於同一 GitHub commit 的固定路徑。

| 路徑 | 內容 |
| --- | --- |
| `staging/candidate.json` | 已簽章的測試版身分、目前測試基準、CMS SHA-256、解密後 ZIP SHA-256 |
| `staging/candidate.json.sig.b64` | 原 Ed25519 簽章器對 JSON 原始位元組簽章後的 Base64 |
| `staging/candidate.cms` | 使用測試專用憑證加密、DER 格式的完整候選 ZIP，最多 64 MiB |

清單的 `schema` 為 `judun.staging-deploy.v1`，`base_snapshot` 來自現行測試站 `staging_release.py status` 的 `snapshot`。其餘欄位為 `cms_sha256`、`zip_sha256` 與 `target`。目標物件包含 `version`、`artifact_id`、`build_instance_id`、`source_tree_sha256`、`file_count`。ZIP 使用既有的 `payload/DEPLOY_MANIFEST.json` 和受管程式檔格式。加密可沿用 OpenSSL CMS 的 `-encrypt -binary -aes256 -outform DER`，簽章使用現有 Ed25519 簽章器的 `pkeyutl -sign -rawin`。GitHub 只接收加密檔、清單和簽章。

## 一般 ChatGPT 對話的使用方式

請 NEXUS 外掛呼叫 `nexus_request_judun_staging`，送出已核對的候選版。 `candidate_commit` 是已簽候選包所在的完整 40 位 Git SHA。外掛使用工作區版本比對及請求 ID，避免覆用過期版本或在重試時重複送出。

服務從該不可變提交讀取候選檔、驗簽及檔案雜湊，核對目前測試基準後切換。每筆候選最多嘗試切換一次，失敗時既有安裝器回復上一版並重驗。中斷留下的切換紀錄由下一輪恢復。成功以既有測試網址的 `build`、`artifact?deep=true` 和 `ready` 讀回為準。獨立功能驗收通過後，由原發布流程將正式版送至正式簽章通道，最後將雙站回執與完整包記入 NEXUS。
