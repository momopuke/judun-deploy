# 居盾對話 → 已簽測試候選（現行入口）

**2026-11-22 更新：現行建議入口為 protected GitHub PR，不再依賴 NEXUS staging-request 寫入插件。**

既有 staging agent `p3/staging_deploy_request.py`、隔離版快照工具、systemd service/timer、原 Ed25519 signer 與 CMS 驗證流程不變，只有「待拉取候選 commit」指標改由 `main/ops/staging-request.json` 提供。舊 NEXUS 入口是歷史設計，不應再用它誤判「已能自動拉取」。

## 一次性啟用

見 `ops/AUTOMATION_BRIDGE.md`；VPS 透過 SHA-pinned 工具啟用 `judun-staging-pull.timer` 並在當地生成 stage-only CMS recipient（若兩者皆不存在），不複製 production 的金鑰。金鑰永留 VPS、公開憑證提供原 signer 加密候選。未完成前不能宣稱零 FinalShell。

## 正常發布流程（啟用一次後每版沿用）

1. 私人建置與**原受信任簽章器**對同一候選 ZIP 產生 `staging/candidate.cms`、`staging/candidate.json` 及 `staging/candidate.json.sig.b64`；JSON 內有前一版 stage snapshot、目標 identity、加密封包與解密 ZIP SHA256；GitHub 只存加密內容。
2. 利用連接 GitHub 工具經受保護 PR 將 `ops/staging-request.json` 的 `candidate_commit` 改成**已簽候選所在的完整 40 位 Git SHA**，只接受明確授權與同 SHA QA；原主程式 `judun/release-gate` 仍須通過。不得把任意 SHA、未簽候選或純測試腳本當作可發布候選。
3. VPS 既有 timer 每三分鐘讀這個檔案，對候選驗 Ed25519 簽章、CMS SHA、解密 ZIP SHA、基準版本，然後在隔離 staging 切換。原 installer 的單一 commit 只嘗試切換一次，失敗復原舊版；同一候選已安裝則不重覆切換。
4. 獨立 QA 實測 Basic/ProMax、報告/PDF/Email、資料遷移回退，實際 owner 授權核對公開測試站。**只有 QA PASS**，原 signer 才能簽正式 `channel/stable.json` + signature + CMS release，受保護 PR 合併後由原 `judun-autodeploy.timer` 安裝正式站。
5. 確認兩站同版、逐檔零差異、正確金流模式，並在一分鐘後重驗；未達標就 rollback/HOLD。

## 重要限制

- 正式站和測試站的專用 CMS 私鑰分開保存；無任何私鑰提交公開 repo。
- `ops/staging-request.json` 是**請求指標**，並非授權憑證；**只有原 Ed25519 有效簽章的候選才會被 VPS 接受**。
- GitHub CI PASS、PR 合併、stage timer active 只代表對應關卡通過，不代表已完成實際上線。
- 舊版的 NEXUS API 依然可能存在，但現行流程不再要求它；不可同時啟動兩套互相覆寫的 stage owner。
