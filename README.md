# JUDUN signed deployment channel

This repository contains deployment metadata and encrypted payloads only. The VPS accepts a release only when the channel manifest passes its pinned Ed25519 signature check, the live base artifact matches, the encrypted payload SHA256 matches, and post-deploy health/deep-SHA checks pass.

Do not place the payload decryption private key or the release signing private key in this repository.

## 發布與驗收

1. 工程先在隔離環境以發布候選包實際啟動，驗證資料遷移與回退。品管使用合成報價驗上傳、辨識、評分、Basic → ProMax、報告和 PDF。保留同一份候選包、原始碼樹 SHA256、檔數及驗收結果。新簽章清單必須包含 `expected_source_tree_sha256` 與 `expected_managed_file_count`。
2. 總管確認目前正式版完整且就緒，再用 `p3/direct_deploy_publish.py --publish` 原子發布簽章三檔。執行環境需具備既有 GitHub 發布權限與測試站擁有者授權。透過環境變數 `JUDUN_STAGE_AUTH_TOKEN` 傳入本輪授權。
3. 原 VPS 代理安裝後，`python3 .github/scripts/verify_release.py dual` 核對兩站的版本、部署身分、原始碼樹、精確檔數、零差異、就緒與金流環境。GitHub 上既有正式站檢查執行同一個驗證器的 `live` 模式。
4. 正式啟動或完整性驗證失敗時，使用既有回退流程，再確認上一版的身分、深度完整性與就緒。若只有測試站異常，先確認正式仍正常，再追查測試站。代理尚未套用時，查代理回執後決定下一步。
5. 總管交付兩站網址、版本與獨立品管結果，並保存完整可解壓交付包。健康驗證、實際功能驗收與正式金流測試各自留證。

正式站與目前測試站共用應用程式路徑。發布前候選測試應使用獨立程式目錄與隔離資料，在確認遷移和回退後再推正式。
