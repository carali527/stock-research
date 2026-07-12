from types import SimpleNamespace

from fastapi.testclient import TestClient

import main


client = TestClient(main.app)


def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_yahoo_quote_returns_normalized_payload(monkeypatch):
    def fake_fetch_quote(symbol: str):
        return SimpleNamespace(
            symbol=symbol,
            name="台積電",
            price=1010.0,
            change=10.0,
            change_percent=1.0,
            as_of="2026-07-10 13:30",
            source_url=f"https://tw.stock.yahoo.com/quote/{symbol}",
        )

    monkeypatch.setattr(main, "fetch_yahoo_tw_quote", fake_fetch_quote)

    response = client.get("/api/yahoo/quote/2330")

    assert response.status_code == 200
    assert response.json() == {
        "symbol": "2330",
        "name": "台積電",
        "price": 1010.0,
        "change": 10.0,
        "changePercent": 1.0,
        "asOf": "2026-07-10 13:30",
        "sourceUrl": "https://tw.stock.yahoo.com/quote/2330",
    }


def test_yahoo_quote_returns_502_when_scraper_fails(monkeypatch):
    def fake_fetch_quote(_symbol: str):
        raise RuntimeError("upstream changed")

    monkeypatch.setattr(main, "fetch_yahoo_tw_quote", fake_fetch_quote)

    response = client.get("/api/yahoo/quote/2330")

    assert response.status_code == 502
    assert response.json()["detail"] == "Yahoo scrape failed: upstream changed"


def test_yahoo_listed_hot_rank_returns_items(monkeypatch):
    monkeypatch.setattr(
        main,
        "fetch_yahoo_tw_listed_hot_rank_symbols",
        lambda: [
            {"symbol": "2330", "name": "台積電"},
            {"symbol": "2317", "name": "鴻海"},
        ],
    )

    response = client.get("/api/yahoo/listed-hot-rank")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"symbol": "2330", "name": "台積電"},
            {"symbol": "2317", "name": "鴻海"},
        ],
        "sourceUrl": "https://tw.stock.yahoo.com/rank/volume?exchange=TAI",
    }
