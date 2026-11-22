# 居盾既有自動部署通道：一次接通，不另造一套

**本文件只處理一次性啟用及證據；不是 v1.2.190 已上線聲明。** 唯一發布主線仍為 `ops/RELEASE_CONTROL.md`、原 Ed25519/CMS signer、原 `judun-autodeploy.timer`、原 staging isolation 與 `judun/release-gate`。不改 `main/channel/stable.json`，不在公開 repo 放私鑰、私有候選原始碼或憑證。

## 先分清楚三種能力

1. **正式站自動拉取**：`judun-autodeploy.timer` 已有機制，但只有 timer active 不代表受信任 signer 可操作、可部署或已上線。
2. **測試站自動拉取**：現有 `p3/staging_deploy_request.py`、`ops/judun-staging-pull.{service,timer}` 可從有權的 NEXUS request 拉取不可變 Git commit 的已簽候選。一次啟用之前需要既有隔離服務、root 所有的專用 CMS 收件憑證、固定 Ed25519 公鑰及 NEXUS 唯讀 token。私鑰只留 VPS；切換前會驗簽、驗 hash 和基準版本，失敗會回復。NEXUS 插件實際上必須具備 request 寫入操作；只提供 `get_workspace` / `resume_project` 不足以觸發發布。
3. **完整自動發布**：還需要原 signer 的真實操作回執、獨立 QA 與有權執行正式發布 PR/merge 的控制通道。這三者目前不由 staging 拉取 timer 自動提供，不能稱完成。

## 一次性啟用（只允許在原受權 VPS 操作）

在可信任、**固定 SHA 的 GitHub 版本工作樹**執行。先 `bash ops/activate_existing_staging_pull.sh --check-only`，確認無 `STOP`；再由已授權操作者執行 `bash ops/activate_existing_staging_pull.sh --enable`。這不是要求每版重跑。啟用器只會安裝缺少的既有 staging pull 程式與 systemd 單元；若已安裝但與來源不同，拒絕覆寫，防止干擾 v190 測試站。沒有既有 CMS 憑證／NEXUS 授權時，**停止，不會生成金鑰或放寬權限**。不會修改正式站。

使用 `python3 -I -B ops/automation_bridge.py --json` 將機器可覆核的連線檢查輸出保存到內部 QA；**只回傳 PASS/FAIL，不輸出 token/私鑰**。它會實際對 NEXUS 唯讀端點驗證授權；同時確認測試 pull timer 及正式 timer 的啟動狀態。`bridge=READY` 只代表 *必要前置*，仍不能宣告 Gate0 或 v190 完成。

## 下一個阻擋點與責任

| 工作 | 負責環境 | 驗證證據 |
|---|---|---|
| 調通 NEXUS staging request 寫入工具（或讓原受權發布環境執行同等合法操作） | 原 NEXUS / staging owner | 寫入 immutable commit，VPS pull journal 讀回相同 commit |
| 原 signer 不觸及正式版的真實自測 | 原受信發布工程 | 原簽章、驗簽、QA digest、簽章身分與時間 |
| v190 既有候選完整 QA | 原獨立 staging QA | 同一 candidate SHA：Basic/ProMax、四宮格、PDF、Email、回退 |
| 受保護 PR、正式 agent、雙站自動驗證及回滾 | 原發布工程／QA | `judun/release-gate`，正式與測試站 build/deep/ready、資料與回退證據 |

## 防止下次再拖一週

每次開發新版本**前**，用此 read-only probe + 私有 signer 自測 + staging QA 操作通道證據做 Gate0；不通過即停止發布排程，只修復同一 blocker。新版本 QA 使用同一候選 SHA，未通過不准簽章。正式發布採既有 agent 原子更新，失敗自動 rollback，要求「前一版再讀回 PASS」；成功及一分鐘復驗才可結案。

此改動的本機驗收僅為 `python3 -m unittest ops/test_automation_bridge.py` 和 `bash -n ops/activate_existing_staging_pull.sh`。真正 VPS 啟用、NEXUS 授權、實際 signer、完整 QA **均需獨立實機驗收**。
