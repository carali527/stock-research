# Roadmap：市場管線（Template → Fugle → Gemini）

**狀態**：工程規劃／tech spec，非承諾排期。實作時以 issue 拆項。

---

## 1. 架構本質與現況定位

```
Template（或 Rule Router）
        ↓
   Fugle Market Data API
        ↓
   Gemini（Streaming Stage2）
```

- **正確性**：資料先於模型、責任邊界清楚，適合 production 管線雛形。
- **定位**：**「可用」**的市場敘事輔助；要升級為 **「可信金融分析系統」**，瓶頸通常不在 Router／模型本身，而在 **資料粒度是否足以支撐敘事，且可稽核**。

---

## 2. 系統瓶頸（一句話）

> **「資料是否足夠讓模型不需要猜。」**

---

## 3. Trade-off 核心（決策用）

| 面向 | 取捨 |
|------|------|
| **成本** | 多打 `volumes`／`quote` → Fugle 呼叫與 token 成本上升 |
| **深度** | 資料越豐富 → 支撐「價＋量→行為」敘事的能力越強 |
| **延遲** | 序列／並行多 API → end-to-end latency ↑ |
| **可信度** | 結構化表＋欄位齊全 → 幻覺空間 ↓（仍須工程防線） |

**原則**：進階資料源 **不由全域預設全開**，改由 **`marketTemplateId`（或 routing）明確選用**，避免每題都打滿配。

---

## 4. 四條主線

### 4.1 資料層升級（Data Fidelity）

**問題本質**：Fugle 給的粒度，是否撐得住產品要的「行為解釋」。

| 層級 | 典型 API | 成本 | 敘事能力 |
|------|-----------|------|----------|
| 基礎 | `intraday/candles`（OHLCV） | 低 | 趨勢、區間、極值 |
| 結構 | `intraday/volumes`（分價量） | 中 | 密集區、支撐／壓力語彙 |
| 即時 | `intraday/quote`（／last） | 依產品 | 盤中狀態、與 K 對照 |

**建議組合（示意）**

- 現況：`candles` only（部分模板已複合 candles＋volumes）。
- 升級方向：**依 template 組合** `candles` + **選配** `volumes`、**選配** `quote`，寫入 `fugle`／`fugle_api_response` 與 Stage2 prompt 的優先順序（表格式資料優先於大段 JSON）。

### 4.2 可信度層（Anti-Hallucination）

**問題本質**：模型「可以講」，但系統要 **縮小亂推論的空間**。

| 手段 | 說明 | 建議落地 |
|------|------|----------|
| Prompt | 僅使用 `market_data` 內顯式出現的數字；禁止帶入表格外假設 | 已部分在 `gemini_service` Stage2 system；可再收斂成一句英文硬規則供模型遵守 |
| Data binding（強） | 回文中數字應可追溯至輸入表 | 進階：輕量規則或二次模型檢核 |
| Backend validator（輕） | 抽樣比對「回文數字 ⊆ 允許集合」 | 第一版：**只 flag + log**（`hallucination_risk`），不阻擋使用者 |

**目標**：不是「禁止 AI 說話」，而是 **讓沒根據的數字難以混進去**，且 **可查 log 追責**。

### 4.3 可觀測性（Observability）

| 項目 | 說明 |
|------|------|
| **Request ID** | `frontend → backend → Fugle → Gemini stream` 同一 `request_id`（header 或 body 回傳給前端可選） |
| **Structured log** | 避免僅 `"fetch candles success"`；改為 JSON 欄位：`request_id`、`stage`（如 `fugle_fetch`）、`symbol`、`timeframe`、`row_count`、`http_status`、`template_id` |
| **Prompt snapshot（debug）** | 可開關：保存 Router 輸出、Fugle 摘要、**送進 Gemini 的最終 user payload**（注意 PII／金鑰脫敏、檔案 rotation） |

此層決定 **能否在 production 有效率除錯**（預估可覆蓋多數「模型講錯／資料錯」類 bug 的根因分析）。

### 4.4 UX（信任與預期）

**洞察**：使用者不一定是「不信 AI」，而是 **不知道 AI 是否真的有資料**。

**建議**：**Data transparency**（例如 badge／摘要列）

- 已載入：N 根 M 分 K、是否含 volume profile、是否含 quote（依本次 template 實際呼叫）。
- 效果：降低「在亂講嗎？」的認知成本；與後端 `fugle_route.calls` 等結構對齊最佳。

---

## 5. 實作優先級（建議）

### P1 — 可觀測與除錯（強烈建議先做）

- [x] Request ID 全鏈路透傳（前端 `X-Request-ID` → 後端 `ContextVar` + 回應標頭 `X-Request-ID`；`safe_data._requestId` 不進 Gemini 正文）
- [x] Fugle／prepare／Stage2 關鍵步驟 **structured log**（`request_trace.log_json`：`fugle_http_ok`、`production_template_done`、`prepare_done`、`gemini_stream_start` 等）

### P2 — 產品質感與資料深度

- [ ] 依 template 組合 **candles + volumes**（及必要時 quote），文件化每模板實際打的 endpoint
- [ ] 前端 **已載入資料摘要**（與 P1 的 `row_count`／`calls` 對齊）

### P3 — 進階可信度與多源

- [ ] Anti-hallucination **輕量 validator**（flag + log → 再考慮 UI 提示）
- [ ] 多源融合敘事規範（quote vs candles 時間對齊、非交易時段說明等）

---

## 6. North Star（方向句）

從 **「股票查詢 + 文案生成」** 演進為 **「可追溯的市場資料驅動推理」**：每一句有數字的陳述，原則上應能指回 **同一次請求載入的 market_data** 與 **request_id** 下的稽核軌跡。

---

## 7. 與本 repo 模組的對應（實作錨點）

| 能力 | 主要錨點 |
|------|----------|
| Template → Fugle | `backend/market_template.py`、`backend/fugle_market_fetch.py` |
| Router → Fugle | `backend/fugle_core_router.py`、`execute_market_fetch_with_fallback` |
| Prepare / 合併 safe_data | `backend/main.py`（`_prepare_stream_structured_and_market_data`） |
| Stage2 prompt | `backend/gemini_service.py`（`_render_market_data_for_prompt`、`_stage2_stream_system`、`iter_stage2_stream_chunks`） |
| 前端模板與 payload | `frontend/src/views/Research.vue`、串流呼叫鏈 |

---

*文件版本：依目前架構整理；實作細節以程式與 API 文件為準。*
