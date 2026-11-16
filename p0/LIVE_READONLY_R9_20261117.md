# 居盾正式站唯讀驗收觸發（2026-11-17）

- 此提交只觸發既有 `judun-p0-unified-acceptance.yml` 在隔離 GitHub runner 的公開站只讀檢查。
- 不含私有原始碼、客戶資料、簽章/解密私鑰、發行物或憑證。
- 不修改 `main`、正式簽章 channel、金流或 VPS；不得把 runner 成功等同正式部署。
- 預期核對：公開站 HTTPS／首頁、健康端點、免費入口；完整測試站與 R9 正式發布另需受信任 signer 及 VPS operator 驗證。
