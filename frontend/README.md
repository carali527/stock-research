# Stock Research (Frontend)

全專案說明（後端、環境變數總覽）見上層 **[`../README.md`](../README.md)**。

## Requirements

- **Node.js ≥ 20.19**（建議用 `.nvmrc`：`22.12.0`）

## Setup

```bash
cd frontend
nvm use
npm install
```

前端 **不向瀏覽器 bundle Fugle 金鑰**。Fugle REST 走同源 `/fugle`、WebSocket 走 `/ws/fugle/streaming`，均由 **後端** 以 `FUGLE_API_KEY` 對 Fugle 通訊。

## Run dev server

```bash
cd frontend
npm run dev
```

預設開發時 Vite 會把 `/api`、`/fugle`、`/ws/fugle` 轉到本機後端 `:8000`（見 [`vite.config.ts`](vite.config.ts)），請先在 `backend/` 啟動 API。
