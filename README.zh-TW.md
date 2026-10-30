# LKSTRU Edge

在 Mac 本機收集與驗證公開代理，並將 Shadowrocket 遠端設定以靜態檔案發布到 Cloudflare Pages。Pages 只提供檔案，不轉送用戶流量，也不執行 VPN 隧道。

**本專案會重新發布公開 HTTP／SOCKS5 代理端點。公開清單不代表已取得所有者授權，也不代表節點安全、私密或穩定。使用或發布前請確認來源條款及當地法規；不要用這些代理登入敏感帳號或傳送機密資料。**

英文說明：[README.md](README.md)

## 功能

- 在 Mac 從 ProxySpace、HProxy、ProxyScrape 與 Proxio 取得候選節點。
- 過濾無效位址、埠、國碼、離線項目與已知 TLS 攔截端點。
- 由系統 `curl` 抽樣驗證 HTTPS 憑證、兩個端點回報的出口國家，以及 YouTube 基本連通性。
- 只把通過驗證的節點產生為 Shadowrocket 設定及分國設定。
- 將靜態快照發布到你設定的 Pages 專案。
- 沒有任何節點通過時停止發布，保留線上最後一份快照。

Shadowrocket 直接連到所選代理。Cloudflare Pages 僅提供快照，不轉送代理流量。本專案沒有 Worker、VLESS 轉送、排程掃描或 Mac 背景服務。

## 需求

- macOS、Python 3.11 以上、`curl`、Node.js 與 npm。
- 你自己的 Cloudflare 帳戶及 Pages 專案。
- Mac 上已登入 Wrangler。首次部署時可能會開啟瀏覽器要求授權。
- 用來載入遠端設定的 Shadowrocket。

## 首次設定

1. 建立一個 Cloudflare Pages 專案，或選擇你已擁有的專案。
2. 在 Finder 雙擊 `run-macos.command`。首次執行會在需要時安裝鎖定版本的 Wrangler，並從範例建立 `deploy/project.env`。
3. 在 `deploy/project.env` 填入你的 Pages 專案名稱並儲存，再雙擊 `run-macos.command`。
4. 若瀏覽器提示，完成 Wrangler 授權。指令接著會收集、驗證、產生快照並發布。

專案名稱與本機授權狀態不會提交到 Git。不要把 Cloudflare Token、帳密或個人設定加到儲存庫。

## 日常使用

雙擊 `run-macos.command` 重新掃描並發布。先重新驗證上一版成功發布的節點，再為每國抽樣最多 16 個不同的新候選；同時最多驗證 8 個。全球掃描可能需要十多分鐘。指令不會更改 macOS 系統代理、啟動 VPN 或修改既有 Shadowrocket 設定。

在小火箭「配置」頁加入網站提供的遠端設定網址。Pages 發布新快照後，在小火箭內更新這份遠端設定。選用設定和下載／匯入是不同步驟。

`collect-only.command` 只掃描，不發布。終端等效指令：

```sh
# 首次安裝鎖定的 Wrangler 依賴
npm ci --ignore-scripts

# 掃描所有目錄國家，不發布
python3 collect.py --countries ALL --limit 16 --workers 8

# 對指定國家增加抽樣量
python3 collect.py --countries JP,TW,HK,US --limit 24 --workers 8

# 發布 30 分鐘內的新快照
python3 publish.py --skip-refresh

# 對照線上部署與本機 dist/ 快照
python3 check_live.py https://YOUR-PAGES-PROJECT.pages.dev
```

預設不會發布零節點快照。只有在你明確要發布僅含 REJECT 的設定時，才使用 `--allow-empty`。

## 驗證範圍與限制

掃描器會下載一次 HProxy 全球清單，再依國家和協定取得 ProxySpace 清單。它限制來源及驗證並行數，拒絕私有或無效端點；代理驗證失敗時不會改為直連。驗證會比對 Cloudflare Trace 與 ProxySpace Geo 回報的國家和 IP，再測試一個小型 YouTube 公開資源。這些檢查不代表影片可播放、iPhone 可連線、DNS／IPv6 不洩漏、UDP 可用、速度足夠或節點會持續在線。

來源可能完全沒有某些國家的候選。增加抽樣數只會幫助已有候選的國家，不能憑空增加來源未提供的出口。公開代理可能隨時失效，也可能由未知人士控制。使用一般 HTTP／SOCKS5 代理時，裝置到代理的連線本身未加密，即使目的網站使用 HTTPS 亦然。

30 分鐘期限只會讓網站顯示警告並關閉下載入口，不會刪除已發布的靜態檔案，也不會撤銷用戶端已匯入的設定。請重新掃描並發布；用戶端上的舊設定需要自行移除。

## 公開資料提醒

除非另行加上存取控制，Pages 產生的 `nodes.json`、`subscribe.conf` 及分國設定都是公開靜態檔案，任何能取得網址的人都能讀取代理端點。本儲存庫不含帳戶專用網域、帳戶 ID、Token、部署報告或即時代理快照。

## 專案內容

- `collect.py`、`publish.py`：本機收集、驗證、輸出與 Pages 發布。
- `web/`：國家與狀態靜態頁面、安全標頭。
- `countries.json`：ISO 國家／地區清單。
- `test_collect.py`、`test_publish.py`：使用模擬網路回應的離線測試。
- `deploy/`：Pages 建置設定及本機專案名稱範例。
- `run-macos.command`、`collect-only.command`：Finder 啟動指令。

另請閱讀 [安全政策](SECURITY.md)、[貢獻指南](CONTRIBUTING.md) 與 [MIT 授權](LICENSE)。

資料來源文件：[ProxySpace](https://proxyspace.pro/) 與 [HProxy 公開代理清單](https://hproxy.com/docs/free-proxy-list)。本專案與來源服務、Cloudflare 或 Shadowrocket 均無隸屬或背書關係。

## v1.1.0：多來源與舊節點複查

每次掃描先重新完整驗證上一版節點；舊節點不占每國 16 個新候選的名額。新候選跨來源去重、依來源與協定均衡抽樣，並依本機探測歷史輪換，優先處理尚無成功出口的國家。新舊節點都需在導出前再次通過 HTTPS 憑證、國家及 YouTube robots 檢查；歷史成功不會直接沿用，國家數也不保證持續增加。

`.scan-history.json` 是近 30 日探測時間記錄；`.published-nodes.json` 是成功發布後的節點池。兩者都僅存本機、排除於 Git。首次升級會以既有 `dist/nodes.json` 作為複查基準。來源失效時記錄錯誤，仍可驗證其他來源；零節點則停止發布。發布器拒絕缺少複驗標記的非空快照，升級後請先重新掃描。

Proxio 的資料授權為 CC BY 4.0；來源與協定解讀詳見 [SOURCES.md](SOURCES.md)。本機報告的來源歸屬是去重後的歸屬，不代表該來源獨家提供或保證新增的節點數。

## 日常更新與深度掃描

雙擊一鍵發布指令後，輸入 1（日常更新，按 Enter 預設）或 2（深度掃描）。日常模式每國最多 16 個新候選；深度模式每國分批探測，最多 64 個新候選，每批最多 4 個，累計找到 4 個初測成功節點後停止該國新候選探測。當輪驗證成功的舊節點計入 4 個目標，但不占新候選名額。最終複驗仍可能淘汰節點，目標數量不代表保證。兩種模式皆最多 8 個同時驗證，深度掃描可能耗時更久。非互動呼叫預設日常模式；在 command 後傳入參數則直接使用參數而不顯示選單。

終端可用 `python3 publish.py --mode deep` 一次完成深度掃描與發布，或 `python3 collect.py --mode deep` 只掃描。

時效改以每個節點最後複驗的 `checked_at` 判斷，`validated_at` 記錄最早的有效複驗時間，不因整輪掃描較長而放寬期限。發布時每個節點都須在 30 分鐘內；頁面在任何節點過期後停用完整快照下載。網站的過期顯示無法撤銷靜態檔案網址或已匯入的用戶端設定。

## 來源抓取與候選排序改善（2026-10-30）

來源清單下載與代理探測分開設定：下載來源連線逾時 10 秒、總逾時 45 秒，暫時性的網路錯誤及 HTTP 408／429／5xx 最多嘗試 3 次，間隔 1、2 秒；404、TLS 憑證錯誤及過大回應不重試。代理探測維持原本連線 5 秒、總計 12 秒與完整安全複驗。

每個來源／協定組內，候選優先參考本機歷史驗證成功率，再參考來源可用的 `last_checked`、`latency_ms`／`latency_s`；缺少或格式不符的欄位不參與排序。每 4 個名額保留 1 個給未測或較久未測候選，繼續維持跨來源／協定的均衡取樣。`.scan-history.json` 相容既有數字時間記錄，之後改存探測時間與成功／失敗次數；歷史及來源標記都不能取代當輪驗證。每國掃描額度與深度模式目標不變。

終端與本機 `output/report.json` 的 `source_summary` 新增原始筆數、有效唯一候選、跨來源去重後歸屬數、涵蓋國家、新候選實測數與最終通過數。JSON 來源原始筆數包含下載的全部國家與協定；ProxySpace 原始行數以及有效／去重數僅涵蓋本次選定國家及 HTTP／SOCKS5。同一端點只歸給第一個來源，不能解讀成其他來源沒有此 IP。抓取失敗時保留錯誤；全域 JSON 來源另有 `fetch_complete`，分頁中斷時原始筆數可能只含已收到的部分，此時候選整批不採用。統計只在本機報告及終端顯示，不上傳節點歷史。
