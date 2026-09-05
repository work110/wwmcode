# 🐕 尾兒大人忠誠的狗 — WWM 激活碼巡邏

自動檢查 https://codes.yar.gg/ 的 **Active codes**。

- GitHub Actions 每 30 分鐘執行一次
- 發現新的有效兌換碼後推送到 Discord
- 第一次正式執行只建立基準，不會把目前全部兌換碼洗到 Discord
- `data/codes.json` 由 GitHub Actions 自動更新
- 不需要自己的電腦保持開機

## 1. 上傳到 GitHub

建立一個新的 GitHub repository，將這個 ZIP 解壓後的 **所有內容** 上傳。

請注意 `.github/workflows/check_codes.yml` 也必須存在。

## 2. 加入 Discord Webhook Secret

GitHub repository：

`Settings` → `Secrets and variables` → `Actions` → `New repository secret`

建立：

- Name: `DISCORD_WEBHOOK_URL`
- Secret: 你的 Discord Webhook URL

## 3. 先測試 Discord

進入：

`Actions` → `WWM Code Watcher` → `Run workflow`

勾選：

`Send a Discord test notification only`

然後執行。

Discord 應該會收到：

> 🧪 尾兒大人的狗狗巡邏測試成功

這個測試不會改動 `data/codes.json`。

## 4. 建立第一次基準

再次手動執行，但這次 **不要勾測試通知**。

第一次正式執行會：

1. 打開 codes.yar.gg
2. 取得目前全部 Active codes
3. 寫入 `data/codes.json`
4. 不發 Discord 通知

這樣就不會一次把舊兌換碼全部發出來。

## 5. 之後全自動

GitHub Actions 會每 30 分鐘執行。

例如原本：

- ABC123
- DEF456

網站新增：

- DOG888

Discord 就只收到 DOG888。

## Discord 機器人顯示名稱

目前固定為：

**尾兒大人忠誠的狗🐕**

如需修改，編輯 `check_codes.py`：

```python
BOT_NAME = "尾兒大人忠誠的狗🐕"
```

## 注意

網站目前使用 JavaScript 動態載入資料，所以專案使用 Playwright + Chromium，
而不是只用 requests/BeautifulSoup。若網站未來大幅修改 DOM 結構，Action 會直接失敗，
並保留上一份 `data/codes.json`，避免錯誤地把全部歷史狀態覆蓋。
