# 居盾候選測試站隔離

獨立服務 `judun-staging-isolated.service` 使用 `/srv/judun-staging/releases` 的版本快照、自己的 Python 虛擬環境與 `/var/lib/judun-staging` 測試資料。正式程式路徑、資料路徑和自動部署工作目錄對服務不可見。既有測試專用環境設定、擁有者授權、資料和測試連接埠 8011 沿用。公開測試網址仍經正式應用程式的橋接入口轉送，正式應用停機時會影響公開測試網址。切換完成後，應用程式和 systemd 服務各自運行。

## 由有權部署程序切換一次

1. 在 `/srv/judun-staging` 建立 root 擁有的 0755 目錄。將 `p3/staging_release.py` 安裝為該目錄的 root 擁有唯讀檔案。以 VPS 相容的 Python 建立獨立 `venv`，從既有受信任來源安裝候選的依賴並執行 `pip check`。切勿直接指向正式站 venv。
2. 以現行已通過驗收的測試站同版本與完整發布包先建立基準。使用已驗證的簽章與原始碼身分資料提供版本、部署識別碼、實例 ID、來源樹 SHA256 和檔數。以下參數皆來自受信任的交付記錄。

```sh
stage=/srv/judun-staging/staging_release.py
python3 -I -B "$stage" prepare "$FULL_BASELINE_PACKAGE" \
  --version "$VERSION" --artifact-id "$ARTIFACT_ID" \
  --build-instance-id "$BUILD_INSTANCE_ID" --source-tree-sha256 "$TREE_SHA256" \
  --file-count "$MANAGED_FILE_COUNT"
python3 -I -B "$stage" init "$ARTIFACT_ID-$TREE_SHA256"
bash ops/enable_judun_staging_isolation.sh
```

3. 啟用腳本建立新的服務和舊服務的條件檔，切換時只停止舊測試服務、啟動新測試服務。新服務必須通過指定版本、部署識別碼、實例 ID、來源樹、逐檔深驗、就緒和測試金流模式，且正式服務 PID 與 InvocationID 必須保持原值。切換失敗會移除本輪啟用標記並嘗試恢復舊測試服務，指令維持失敗狀態。完成後，發布總管另外使用原本的擁有者授權從公開測試網址驗收。

## 後續每次候選發布

將下列程序接到現有可信任且有 VPS 執行權的部署流程。輸入只接受受權建置程序產出的完整候選包。把 `prepare` 的五個身分值綁定經驗證的簽章、受保護的建置輸出或等效的私有包驗證，不直接使用待驗 ZIP 內自行宣稱的值作為信任來源。程式校對精確檔數、重算來源樹 SHA256、逐檔校驗並且只複製清單內檔案。無論來源是完整 ZIP 的 `payload/` 還是解壓後的 payload 目錄，程式只讀來源。

1. 建置流程預備候選快照與獨立測試依賴，執行 `prepare`。
2. 執行 `switch ARTIFACT_ID-TREE_SHA256`。程式要求目前測試版健康，只重啟獨立測試服務。切換或健康檢查失敗即恢復上一個版本快照、重啟及重驗；中斷留下待處理記錄，受權程序可用 `recover` 恢復。
3. 獨立品管用既有擁有者授權驗收公開測試網址上的候選，建立與該候選雜湊對應的 QA 回執。對正式發布簽章並放行前核對回執及測試站現行身分完全相符。
4. 新簽章包的正式套用腳本應移除呼叫舊 `staging/install_staging.py` 的步驟，由獨立測試流程管理候選。現行 v189 的舊呼叫會重寫正式程式目錄內的 legacy launcher、重寫舊測試 unit，失敗時只記訊息不會令正式套用失敗。條件檔擋住舊 unit 搶測試埠，但不攔截舊腳本寫入檔案。現行已簽包不可更改。
5. 正式發布後核對正式及測試網址版本相符並逐檔驗收。所有步驟都能由受權程序執行，每次發布不需使用者上 VPS 貼指令。啟用一次所需的 VPS 權限及可用 runner 需以實機驗證。

測試站與正式站資料分離，不拿正式資料作測試。版本切換回復程式快照，測試資料保留。新版本如有破壞式資料遷移，需要在候選發布前先對測試資料演練回退。

管理工具需 Python 3.9 以上標準函式庫，初次切換另需 Linux systemd、Bash、flock 與 Coreutils。運行居盾需候選版本的 Python 相依環境。不得把生產帳密、候選私有原始碼或簽署私鑰提交到這個儲存庫。

本專案的離線驗收以 v188 和 v189 完整交付包，在唯讀程式與可寫測試資料的 mount namespace 啟動真正 launcher，驗證候選失效時回到 v188、候選成功與版本往返。未執行 VPS cutover、實機 systemd 及公開網址驗收。
