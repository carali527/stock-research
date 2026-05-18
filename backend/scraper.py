from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup
import re


@dataclass(frozen=True)
class YahooTwQuote:
    symbol: str
    name: Optional[str]
    price: Optional[float]
    change: Optional[float]
    change_percent: Optional[float]
    as_of: Optional[str]
    source_url: str


def _to_float(s: str) -> Optional[float]:
    s = (s or "").strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fetch_yahoo_tw_quote(symbol: str, timeout_s: int = 15) -> YahooTwQuote:
    """
    Best-effort scrape from Yahoo TW quote page.
    Yahoo may change markup or block requests; caller should handle failures.
    """
    symbol = symbol.strip()
    url = f"https://tw.stock.yahoo.com/quote/{symbol}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        )
    }

    resp = requests.get(url, headers=headers, timeout=timeout_s)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")

    # These selectors are fragile; keep them conservative.
    name_el = soup.select_one("h1")
    price_el = soup.select_one('[data-testid="qsp-price"]') or soup.select_one("span.Fz\\(32px\\)")
    change_el = soup.select_one('[data-testid="qsp-price-change"]')
    pct_el = soup.select_one('[data-testid="qsp-price-change-percent"]')
    time_el = soup.select_one('[data-testid="qsp-price-timestamp"]')

    return YahooTwQuote(
        symbol=symbol,
        name=name_el.get_text(strip=True) if name_el else None,
        price=_to_float(price_el.get_text(strip=True)) if price_el else None,
        change=_to_float(change_el.get_text(strip=True)) if change_el else None,
        change_percent=_to_float(pct_el.get_text(strip=True).replace("%", "")) if pct_el else None,
        as_of=time_el.get_text(strip=True) if time_el else None,
        source_url=url,
    )


def fetch_yahoo_tw_listed_hot_rank_symbols(timeout_s: int = 15) -> list[dict[str, str]]:
    """
    Scrape Yahoo TW "上市成交量排行" items (name + symbol).

    Requirements:
    - Use href containing "/quote/" (avoid brittle class selectors)
    - Return items like {"symbol": "00981A.TW", "name": "主動統一台股增長"}
    """
    url = "https://tw.stock.yahoo.com/rank/volume?exchange=TAI"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=timeout_s)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    anchors = soup.find_all("a", href=True)
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for a in anchors:
        href = str(a.get("href") or "")
        if "/quote/" not in href:
            continue
        m = re.search(r"/quote/([^/?#]+)", href)
        if not m:
            continue
        sym = m.group(1).strip()
        # Yahoo TW quote links sometimes include extra segments; keep the core symbol.
        sym = sym.split("/")[0].strip()
        # Rank page includes lots of /quote/ links (tools, promos, etc).
        # The volume rank items we want are Taiwan symbols like "00981A.TW".
        if not sym.endswith(".TW"):
            continue
        # Only accept links pointing to the quote root page: /quote/<SYMBOL>.TW (no extra path segments)
        # This filters out tools like "新版個股健診" which usually link under /quote/<SYMBOL>.TW/<tool>
        if not re.search(rf"/quote/{re.escape(sym)}(?:[?#].*)?$", href):
            continue
        if not sym or sym in seen:
            continue
        seen.add(sym)
        # Best-effort name extraction: use nearby text, avoid brittle selectors.
        name = ""
        parent_text = ""
        try:
            parent = a.parent
            if parent:
                parent_text = parent.get_text("\n", strip=True)
        except Exception:
            parent_text = ""
        a_text = a.get_text("\n", strip=True)
        blob = "\n".join([t for t in [a_text, parent_text] if t])
        parts = [p.strip() for p in re.split(r"[\s\n]+", blob) if p.strip()]
        # Find first token that's not the symbol and not rank number.
        for p in parts:
            if p == sym:
                continue
            if re.fullmatch(r"\d+", p):
                continue
            # Skip values that look like prices/percents
            if re.fullmatch(r"[\d.,]+%?", p):
                continue
            name = p
            break
        if not name:
            # Prefer anchor text if it contains CJK characters (stock name).
            t = a_text.replace(sym, "").strip()
            if re.search(r"[\u4e00-\u9fff]", t):
                name = t
            else:
                name = sym

        out.append({"symbol": sym.removesuffix(".TW"), "name": name})
        if len(out) >= 5:
            break
    return out


def fetch_yahoo_tw_listed_change_up_rank_items(timeout_s: int = 15) -> list[dict[str, str]]:
    """
    Scrape Yahoo TW "上市漲幅排行" items (name + symbol).

    Source:
    - https://tw.stock.yahoo.com/rank/change-up?exchange=TAI
    """
    url = "https://tw.stock.yahoo.com/rank/change-up?exchange=TAI"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=timeout_s)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    anchors = soup.find_all("a", href=True)
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for a in anchors:
        href = str(a.get("href") or "")
        if "/quote/" not in href:
            continue
        m = re.search(r"/quote/([^/?#]+)", href)
        if not m:
            continue
        sym = m.group(1).strip()
        sym = sym.split("/")[0].strip()
        if not sym.endswith(".TW"):
            continue
        if not re.search(rf"/quote/{re.escape(sym)}(?:[?#].*)?$", href):
            continue
        if not sym or sym in seen:
            continue
        seen.add(sym)

        name = ""
        parent_text = ""
        try:
            parent = a.parent
            if parent:
                parent_text = parent.get_text("\n", strip=True)
        except Exception:
            parent_text = ""
        a_text = a.get_text("\n", strip=True)
        blob = "\n".join([t for t in [a_text, parent_text] if t])
        parts = [p.strip() for p in re.split(r"[\s\n]+", blob) if p.strip()]
        for p in parts:
            if p == sym:
                continue
            if re.fullmatch(r"\d+", p):
                continue
            if re.fullmatch(r"[\d.,]+%?", p):
                continue
            name = p
            break
        if not name:
            t = a_text.replace(sym, "").strip()
            if re.search(r"[\u4e00-\u9fff]", t):
                name = t
            else:
                name = sym

        out.append({"symbol": sym.removesuffix(".TW"), "name": name})
        if len(out) >= 5:
            break
    return out

