from fugle_core_router import extract_symbol, route_fugle_market_data


def test_extract_symbol_prefers_question_symbol_over_resolved_symbols():
    assert extract_symbol("請分析 2330 的 5 分K", ["2317"]) == "2330"


def test_route_market_list_question_to_tickers_endpoint():
    route = route_fugle_market_data(question="上市股票有哪些")

    assert route["intent"] == "MARKET_LIST"
    assert route["symbol"] is None
    assert route["capability_status"] == "SUPPORTED"
    assert route["next_action"] == {
        "type": "CALL_FUGLE_API",
        "endpoint": "/intraday/tickers",
        "method": "GET",
    }


def test_route_minute_kline_question_to_intraday_candles():
    route = route_fugle_market_data(question="請看台積電 5 分K走勢")

    assert route["intent"] == "TECHNICAL_ANALYSIS"
    assert route["symbol"] == "2330"
    assert route["timeframe"] == "5"
    assert route["capability_status"] == "SUPPORTED"
    assert route["next_action"]["endpoint"] == "/intraday/candles/2330"
    assert route["required_fields"] == ["date", "open", "high", "low", "close", "volume"]


def test_route_daily_kline_question_marks_intraday_candles_unsupported():
    route = route_fugle_market_data(question="請分析台積電三個月日K")

    assert route["intent"] == "TECHNICAL_ANALYSIS"
    assert route["symbol"] == "2330"
    assert route["timeframe"] == "1d"
    assert route["required_period"] == "3 months"
    assert route["capability_status"] == "UNSUPPORTED"
    assert route["api"] is None
    assert route["next_action"] is None
    assert "盤中分K" in route["reason"]


def test_route_uses_resolved_symbol_when_question_has_no_symbol():
    route = route_fugle_market_data(question="現在多少錢", resolved_symbols=["2454.TW"])

    assert route["intent"] == "REALTIME_QUOTE"
    assert route["symbol"] == "2454"
    assert route["next_action"]["endpoint"] == "/intraday/quote/2454"
