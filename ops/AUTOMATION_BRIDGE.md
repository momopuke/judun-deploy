# 居盾現有簽章代理：GitHub 受保護發布請求

> 本操作**不是** v1.2.190 上線。部署 Gate0、獨立 QA、原 CMS+Ed25519 signer、正式站發布、回退仍全部照原 `ops/RELEASE_CONTROL.md`。任何失敗都拒絕發布。

## 2026-11-22 VPS 原始探測

- production `judun-autodeploy.timer` enabled/active PASS
- isolated staging service/marker PASS，既有 stage agent/manager PASS，原 Ed25519 公鑰固定 PASS
- NEXUS token/授權 FAIL；staging CMS recipient pair FAIL；stage pull timer disabled/inactive
- `bridge=BLOCKED`，`full_release_gate0=NOT_VERIFIED`
- 決策：NEXUS connector 不提供 staging request 寫入，不另建第二套機制；只把既有 `p3/staging_deploy_request.py` 的**請求指標**改為受保護 GitHub `main/ops/staging-request.json`，其餘候選的 CMS 加密／Ed25519 驗簽／SHA256／基準校驗／stage rollback 均不變。
- 原 `main` 的 release gate 僅對 `channel/`、`keys/`、`releases/` 強制已簽三檔；`ops/staging-request.json` 是「候選請求」不是正式 release channel。需要受保護 PR 才修改，且候選本身必須由原簽章器簽署。

## 一次性初始化（原 VPS root，**無需每版重作**）

在已核對 SHA 的固定 Git commit 檔案集內運行：

```sh
bash ops/bootstrap_staging_github_pull.sh --check-only
bash ops/bootstrap_staging_github_pull.sh --enable
python3 -I -B ops/automation_bridge.py --json
```

- 僅接受 root、stage already isolated 且正在運行、釘死的 Ed25519 公鑰；比對既有 stage agent 的 Git blob ID。任何陌生版本不覆蓋。
- 若 stage **專用** CMS 收件憑證與私鑰都不存在，可在 VPS 當地**只建立一次**；私鑰權限 0600，不上傳 GitHub；自測真 CMS 加密→解密，公開證書 fingerprint 可交既有 authorized signer 做加密。不是簽章器私鑰，不改正式金流。
- 僅在受保護 main 目前 `ops/staging-request.json` 嚴格等於 `{"candidate_commit":null}` 才啟用 timer，避免初始化時立即套用任何候選。
- 舊 staging agent 若恰好是原 main `10222d8a...`，留 root-only 備份後以新版覆蓋；未知 SHA 嚴格 STOP。這是**唯一一次** agent 升級，不影響正式應用服務。
- 最後確認 `judun-staging-pull.timer` enabled/active，並用原代理的 `request_commit(fetch)` 真讀回 no_request。
- `ops/automation_bridge.py` 12 項檢查不再需要 NEXUS token；仍只判斷**必要前置**，不能將 bridge READY 當作完整發布能力。

## 後續真正全自動須過的 Gate

1. 原 private signer 讀到 stage 公開證書後，用原 Ed25519 簽署 immutable `staging/candidate.json` 和 CMS 加密的候選 ZIP（上 GitHub 僅限加密檔案）；同一 candidate SHA 綁定獨立 QA。
2. 先用 GitHub protected PR 修改 `ops/staging-request.json` 指向候選完整 40 位 commit。VPS timer 使用同一**既有** signed-candidate installer 做真實原子 stage 切換；未通過不准發布正式站。
3. 測試站既有合成案件 Basic/ProMax、四宮格、PDF、Email、金流測試模式、rollback 全 PASS 後，原發布器簽署正式 channel 三檔、protected PR 合併，原 `judun-autodeploy.timer` 安裝到正式站。
4. 正式／測試站 build/deep/ready、正確金流模式，零 mismatch；失敗回退，完成後 1 分鐘再查。三次端到端發布與回退演練通過，才能宣告零 FinalShell 機制完成。

**已知未知：**本對話不能直接執行 VPS Shell；原私有 signer / v190 4/4/PDF / signed stage candidate 仍待實機證據。程式與 PR CI PASS 不等於上線；先完成一次性 bootstrap，再補這些 Gate。
