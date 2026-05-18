# Stock Research（台股研究）

Vue 3 前端 + FastAPI 後端：結合 **Fugle Market Data** 與 **Gemini** 串流分析。

## 專案結構

| 目錄 | 說明 |
|------|------|
| `frontend/` | Vue 3、Vite、Tailwind、Pinia；行情圖表與股票小幫手 |
| `backend/` | FastAPI、`gemini_service`、`fugle_market_fetch`（規則預抓）、`fugle_core_router`（結構化 routing JSON）、Yahoo 爬榜等 |

## 環境需求

- **Node.js** ≥ 20.19（前端目錄建議見 `frontend/.nvmrc`）
- **Python** 3.10+（建議使用 venv）

## 後端設定與啟動

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

在 **`backend/.env.local`**（勿提交版控）設定：

| 變數 | 說明 |
|------|------|
| `GEMINI_API_KEY` 或 `GOOGLE_API_KEY` | Google Generative AI（擇一） |
| `GEMINI_MODEL` | 模型名稱（可選；見 `GET /api/debug/gemini-models`） |
| `FUGLE_API_KEY` | Fugle Market Data（REST 與即時線 WS 皆由後端代理，前端不帶 secret） |
| `DEMO_TOKEN` | 選填；AI demo API 的簡易 header token，預設 `stock-research-demo`（需與前端一致） |
| `DEMO_DAILY_IP_LIMIT` | 選填；同一 IP 每日可用 AI demo 次數，預設 `2`；設為 `0` 可關閉 |

串流分析時前端會送 **`X-Request-ID`**，後端回應標頭帶同一值，並寫入單行 JSON log 的 `request_id` 欄位，便於對齊 Fugle／Gemini 日誌。

啟動 API（預設與 Vite proxy 對齊 **8000**）：

```bash
cd backend
uvicorn main:app --reload
```

## 前端設定與啟動

```bash
cd frontend
npm install
```

Fugle 金鑰只放在 **`backend/.env.local` 的 `FUGLE_API_KEY`**。

```bash
cd frontend
npm run dev
```

開發時 **同源代理**（見 `frontend/vite.config.ts`）：

- `/api`、`/fugle`、`/ws/fugle/*` → 後端 `localhost:8000`（Fugle 請求由後端帶 key）

## 主要功能與路由

- **首頁** `/`
- **股票總覽** `/stock/:id`
- **股價／成交** `/stock/:id/price`
- **股票小幫手（Gemini）** `/research` — 搜尋標的、選固定分析模板（`marketTemplateId`）；請求可帶 `prefetchFugleMarketData` 由後端預抓 Fugle
- **自選** `/favorites`

## API 摘要（後端）

- `POST /api/ai/stream` — 意圖 gate + Gemini 串流分析（body：`question`、`data`）
- `POST /api/gemini` — 相容路徑（含 stream 模式）
- `GET /api/debug/gemini-models` — 除錯：列出可用生成模型
- `GET /health` — 健康檢查

## 建置前端

```bash
cd frontend
npm run build
npm run preview   # 本機預覽 production bundle
```

## 說明文件

- 前端環境變數細節：**`frontend/README.md`**
