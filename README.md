# JUDUN signed deployment channel

This repository contains deployment metadata and encrypted payloads only. The VPS accepts a release only when the channel manifest passes its pinned Ed25519 signature check, the live base artifact matches, the encrypted payload SHA256 matches, and post-deploy health/deep-SHA checks pass.

Do not place the payload decryption private key or the release signing private key in this repository.

## 發布與驗收

1. 工程以同一份發布候選包在隔離環境實際啟動。先用上一版建立合成資料庫，讓候選版遷移後，再啟動上一版讀取同一份已遷移的資料庫並重新驗證報告、訂單及解鎖。品管另驗上傳、辨識、評分、Basic → ProMax、報告和 PDF。
2. 新簽章清單須包含 `expected_source_tree_sha256`、`expected_managed_file_count` 及 `candidate_acceptance_sha256`。總管以 `p3/direct_deploy_publish.py --publish --candidate-acceptance PATH` 核對私有 QA 回執、測試站的同一候選包和現有正式版，才建立只含三個發布檔的 PR。執行環境沿用既有 GitHub 發布權限，透過 `JUDUN_STAGE_AUTH_TOKEN` 傳入本輪測試站擁有者授權。
3. `judun/release-gate` 在 PR 的確切提交上回報驗簽結果、基準版本、發布檔集合及簽章承諾的品管摘要。總管只在本次提交通過後合併。原 VPS 代理安裝後，發布工具的 `--verify-published` 或 `python3 .github/scripts/verify_release.py dual` 核對兩站的版本、部署身分、原始碼樹、精確檔數、零差異、就緒與金流環境。GitHub 上既有正式站檢查執行同一個驗證器的 `live` 模式。
4. 正式啟動或完整性驗證失敗時，使用既有回退流程，再確認上一版的身分、深度完整性與就緒。若只有測試站異常，先確認正式仍正常，再追查測試站。代理尚未套用時，查代理回執後決定下一步。
5. 總管交付兩站網址、版本與獨立品管結果，並保存完整可解壓交付包。健康驗證、實際功能驗收與正式金流測試各自留證。

正式站與目前測試站共用應用程式路徑。發布前候選測試應使用獨立程式目錄與隔離資料，在確認遷移和回退後再推正式。

QA 回執為 JSON，`schema` 是 `judun-candidate-acceptance-v1`。填入 `release_id`、`base_artifact_id`、`target_artifact_id`、`target_build_instance_id`、`payload_sha256`、`source_tree_sha256` 和 `managed_file_count`。在 `checks` 分別記錄 `isolated_startup`、`quote_scoring`、`basic_to_promax`、`report_pdf`、`rollback_after_migration` 的 `status` 與可供覆核的 `evidence`。全部實測通過後才填 `pass`。簽章前將回執原始位元組的 SHA256 寫入清單。私有回執與原始證據隨交付包保存。
