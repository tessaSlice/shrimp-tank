from __future__ import annotations

import asyncio
import copy
import math
import time
from datetime import datetime, timedelta, timezone

import httpx


COINBASE_MARKET_URL = "https://api.coinbase.com/api/v3/brokerage/market/products"
MARKET_PRODUCTS = ("BTC-USD", "ETH-USD", "SOL-USD")
PAPER_PORTFOLIO_SIZE = 100_000.0
PAPER_TRADE_FRACTION = 0.02
MARKET_CACHE_SECONDS = 60.0

PORTFOLIO_POLICIES = {
    "kevin": {
        "strategy": "Capital preservation",
        "cash_weight": 0.62,
        "asset_weights": {"BTC-USD": 0.22, "ETH-USD": 0.12, "SOL-USD": 0.04},
        "minimum_cash_weight": 0.50,
        "maximum_asset_weight": 0.45,
        "buy_threshold": 1.75,
        "sell_threshold": -2.5,
        "volatility_penalty": 0.5,
    },
    "lori": {
        "strategy": "Balanced growth",
        "cash_weight": 0.38,
        "asset_weights": {"BTC-USD": 0.35, "ETH-USD": 0.20, "SOL-USD": 0.07},
        "minimum_cash_weight": 0.25,
        "maximum_asset_weight": 0.50,
        "buy_threshold": 1.0,
        "sell_threshold": -2.0,
        "volatility_penalty": 0.32,
    },
    "mark": {
        "strategy": "Growth focused",
        "cash_weight": 0.15,
        "asset_weights": {"BTC-USD": 0.40, "ETH-USD": 0.30, "SOL-USD": 0.15},
        "minimum_cash_weight": 0.10,
        "maximum_asset_weight": 0.55,
        "buy_threshold": 0.55,
        "sell_threshold": -2.75,
        "volatility_penalty": 0.18,
    },
}

_market_cache: dict[str, dict] | None = None
_market_cache_expires = 0.0
_market_cache_lock = asyncio.Lock()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def _fetch_product_market(client: httpx.AsyncClient, product_id: str, now: datetime) -> dict:
    end = int(now.timestamp())
    start = int((now - timedelta(hours=25)).timestamp())
    response = await client.get(
        f"{COINBASE_MARKET_URL}/{product_id}/candles",
        params={
            "start": str(start),
            "end": str(end),
            "granularity": "ONE_HOUR",
            "limit": 25,
        },
    )
    response.raise_for_status()
    payload = response.json()
    candles = payload.get("candles") if isinstance(payload, dict) else None
    if not isinstance(candles, list):
        raise ValueError("Coinbase returned no candle list.")

    normalized = []
    for candle in candles:
        try:
            row = {
                "start": int(candle["start"]),
                "open": float(candle["open"]),
                "close": float(candle["close"]),
                "high": float(candle["high"]),
                "low": float(candle["low"]),
            }
        except (KeyError, TypeError, ValueError):
            continue
        if row["open"] > 0 and row["close"] > 0:
            normalized.append(row)
    normalized.sort(key=lambda candle: candle["start"])
    if len(normalized) < 2:
        raise ValueError("Coinbase returned too few usable candles.")

    # Candles can be returned newest-first. Compare the oldest opening price with
    # the most recent close and use realized hourly movement as a simple risk cost.
    first, last = normalized[0], normalized[-1]
    change_24h = (last["close"] / first["open"] - 1) * 100
    returns = [
        normalized[index]["close"] / normalized[index - 1]["close"] - 1
        for index in range(1, len(normalized))
        if normalized[index - 1]["close"] > 0
    ]
    volatility_24h = math.sqrt(sum(change * change for change in returns)) * 100
    return {
        "product_id": product_id,
        "asset": product_id.removesuffix("-USD"),
        "price_usd": round(last["close"], 8),
        "change_24h_pct": round(change_24h, 3),
        "volatility_24h_pct": round(volatility_24h, 3),
        "source": "coinbase_public_market_data",
        "as_of": now.isoformat(),
    }


async def get_coinbase_market_snapshot() -> dict[str, dict]:
    """Read public Coinbase candles; failures are handled as missing market data."""
    global _market_cache, _market_cache_expires
    async with _market_cache_lock:
        if _market_cache is not None and time.monotonic() < _market_cache_expires:
            return copy.deepcopy(_market_cache)

        now = _utc_now()
        timeout = httpx.Timeout(3.0, connect=1.5)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                results = await asyncio.gather(
                    *(_fetch_product_market(client, product_id, now) for product_id in MARKET_PRODUCTS),
                    return_exceptions=True,
                )
        except httpx.HTTPError:
            results = []

        snapshot: dict[str, dict] = {}
        for product_id, result in zip(MARKET_PRODUCTS, results):
            if isinstance(result, dict):
                snapshot[product_id] = result
        _market_cache = snapshot
        _market_cache_expires = time.monotonic() + MARKET_CACHE_SECONDS
        return copy.deepcopy(snapshot)


def create_simulated_portfolios(sharks: list[dict]) -> list[dict]:
    portfolios = []
    for shark in sharks:
        policy = PORTFOLIO_POLICIES.get(shark["id"], PORTFOLIO_POLICIES["lori"])
        cash = PAPER_PORTFOLIO_SIZE * policy["cash_weight"]
        positions = [
            {
                "product_id": product_id,
                "asset": product_id.removesuffix("-USD"),
                "units": None,
                "market_value_usd": round(PAPER_PORTFOLIO_SIZE * weight, 2),
                "mark_price_usd": None,
                "change_24h_pct": None,
                "volatility_24h_pct": None,
                "market_source": "unavailable",
            }
            for product_id, weight in policy["asset_weights"].items()
        ]
        portfolios.append({
            "investor_id": shark["id"],
            "investor": shark["name"],
            "strategy": policy["strategy"],
            "starting_value_usd": PAPER_PORTFOLIO_SIZE,
            "cash_usd": round(cash, 2),
            "total_value_usd": PAPER_PORTFOLIO_SIZE,
            "return_pct": 0.0,
            "minimum_cash_weight": policy["minimum_cash_weight"],
            "maximum_asset_weight": policy["maximum_asset_weight"],
            "buy_threshold": policy["buy_threshold"],
            "sell_threshold": policy["sell_threshold"],
            "volatility_penalty": policy["volatility_penalty"],
            "positions": positions,
            "market_data": [],
            "market_mode": "unavailable",
            "updated_at": None,
            "recommendation": {
                "action": "hold",
                "asset": None,
                "amount_usd": 0.0,
                "signal_pct": None,
                "summary": "The live market feed is unavailable, so the portfolio agent recommends holding.",
                "reason": "No paper trade was made because a current market signal was unavailable.",
                "status": "no_market_data",
            },
            "trades": [],
        })
    return portfolios


def _refresh_position_marks(portfolio: dict, market: dict[str, dict]) -> None:
    for position in portfolio["positions"]:
        quote = market.get(position["product_id"])
        if not quote:
            continue
        price = float(quote["price_usd"])
        units = position.get("units")
        if units is None:
            units = float(position["market_value_usd"]) / price
        position["units"] = units
        position["mark_price_usd"] = price
        position["market_value_usd"] = round(units * price, 2)
        position["change_24h_pct"] = quote["change_24h_pct"]
        position["volatility_24h_pct"] = quote["volatility_24h_pct"]
        position["market_source"] = quote["source"]


def _portfolio_total(portfolio: dict) -> float:
    return round(
        float(portfolio["cash_usd"])
        + sum(float(position["market_value_usd"]) for position in portfolio["positions"]),
        2,
    )


def _recommendation(portfolio: dict, market: dict[str, dict], now: str) -> dict:
    total = max(0.0, _portfolio_total(portfolio))
    if not market:
        return {
            "action": "hold",
            "asset": None,
            "amount_usd": 0.0,
            "signal_pct": None,
            "summary": "A complete Coinbase quote set is unavailable, so the portfolio agent recommends holding.",
            "reason": "No paper trade was made because current quotes were missing for one or more watched assets.",
            "status": "no_market_data",
            "as_of": now,
        }

    risk_scores = {
        product_id: quote["change_24h_pct"]
        - portfolio["volatility_penalty"] * quote["volatility_24h_pct"]
        for product_id, quote in market.items()
    }
    cash_weight = float(portfolio["cash_usd"]) / max(total, 1.0)
    cash_floor = float(portfolio["minimum_cash_weight"])
    positions = {position["product_id"]: position for position in portfolio["positions"]}
    buys = sorted(risk_scores.items(), key=lambda row: row[1], reverse=True)
    for product_id, score in buys:
        position = positions.get(product_id)
        if (
            score >= float(portfolio["buy_threshold"])
            and cash_weight > cash_floor
            and position is not None
            and float(position["market_value_usd"]) / max(total, 1.0) < float(portfolio["maximum_asset_weight"])
        ):
            quote = market[product_id]
            reserve_available = max(0.0, float(portfolio["cash_usd"]) - total * cash_floor)
            asset_room = max(
                0.0,
                total * float(portfolio["maximum_asset_weight"])
                - float(position["market_value_usd"]),
            )
            amount = round(min(total * PAPER_TRADE_FRACTION, reserve_available, asset_room), 2)
            if amount >= 100:
                return {
                    "action": "buy",
                    "asset": product_id.removesuffix("-USD"),
                    "product_id": product_id,
                    "amount_usd": amount,
                    "signal_pct": quote["change_24h_pct"],
                    "risk_adjusted_score": round(score, 3),
                    "summary": f"The portfolio agent recommends a small paper buy in {product_id.removesuffix('-USD')} based on positive risk-adjusted momentum.",
                    "reason": "The positive Coinbase market signal cleared this investor's rule-based threshold and cash-reserve limit.",
                    "status": "paper_trade",
                    "price_usd": quote["price_usd"],
                    "as_of": quote["as_of"],
                }

    sells = sorted(risk_scores.items(), key=lambda row: row[1])
    for product_id, score in sells:
        position = positions.get(product_id)
        if (
            score <= float(portfolio["sell_threshold"])
            and position is not None
            and float(position["market_value_usd"]) >= 100
        ):
            quote = market[product_id]
            amount = round(min(total * PAPER_TRADE_FRACTION, float(position["market_value_usd"])), 2)
            if amount >= 100:
                return {
                    "action": "trim",
                    "asset": product_id.removesuffix("-USD"),
                    "product_id": product_id,
                    "amount_usd": amount,
                    "signal_pct": quote["change_24h_pct"],
                    "risk_adjusted_score": round(score, 3),
                    "summary": f"The portfolio agent recommends a small paper trim of {product_id.removesuffix('-USD')} after weak risk-adjusted momentum.",
                    "reason": "The negative Coinbase market signal crossed this investor's rule-based risk threshold.",
                    "status": "paper_trade",
                    "price_usd": quote["price_usd"],
                    "as_of": quote["as_of"],
                }

    strongest = buys[0]
    quote = market[strongest[0]]
    return {
        "action": "hold",
        "asset": strongest[0].removesuffix("-USD"),
        "amount_usd": 0.0,
        "signal_pct": quote["change_24h_pct"],
        "risk_adjusted_score": round(strongest[1], 3),
        "summary": "The market signal did not clear this investor's risk-adjusted paper-trading threshold; the portfolio agent recommends holding.",
        "reason": "No proposed paper trade satisfied the strategy and portfolio limits.",
        "status": "no_trade",
        "as_of": now,
    }


def _apply_paper_trade(portfolio: dict, recommendation: dict, pitch_index: int, now: str) -> None:
    if recommendation["status"] != "paper_trade":
        return
    product_id = recommendation["product_id"]
    position = next((row for row in portfolio["positions"] if row["product_id"] == product_id), None)
    price = float(recommendation["price_usd"])
    amount = float(recommendation["amount_usd"])
    if position is None or price <= 0 or amount <= 0:
        return
    units = amount / price
    if recommendation["action"] == "buy":
        portfolio["cash_usd"] = round(float(portfolio["cash_usd"]) - amount, 2)
        position["units"] = float(position["units"] or 0) + units
        position["market_value_usd"] = round(float(position["market_value_usd"]) + amount, 2)
    else:
        amount = min(amount, float(position["market_value_usd"]))
        units = min(units, float(position["units"] or 0))
        portfolio["cash_usd"] = round(float(portfolio["cash_usd"]) + amount, 2)
        position["units"] = max(0.0, float(position["units"] or 0) - units)
        position["market_value_usd"] = round(max(0.0, float(position["market_value_usd"]) - amount), 2)

    portfolio["trades"].append({
        "pitch_index": pitch_index,
        "time": now,
        "side": recommendation["action"],
        "asset": recommendation["asset"],
        "notional_usd": round(amount, 2),
        "price_usd": price,
        "units": round(units, 10),
        "source": "paper_only",
    })
    recommendation["status"] = "paper_trade_applied"


async def refresh_simulated_portfolios(portfolios: list[dict], pitch_index: int) -> None:
    """Mark paper portfolios to market and apply at most one paper rebalance per pitch."""
    market = await get_coinbase_market_snapshot()
    now = _utc_now().isoformat()
    for portfolio in portfolios:
        _refresh_position_marks(portfolio, market)
        complete_market = all(product_id in market for product_id in MARKET_PRODUCTS)
        recommendation = _recommendation(portfolio, market if complete_market else {}, now)
        _apply_paper_trade(portfolio, recommendation, pitch_index, now)
        portfolio["recommendation"] = recommendation
        portfolio["total_value_usd"] = _portfolio_total(portfolio)
        starting = max(float(portfolio["starting_value_usd"]), 1.0)
        portfolio["return_pct"] = round((portfolio["total_value_usd"] / starting - 1) * 100, 2)
        cash_weight = float(portfolio["cash_usd"]) / max(float(portfolio["total_value_usd"]), 1.0)
        reserve_target = float(portfolio["minimum_cash_weight"])
        portfolio["cash_posture"] = (
            "above reserve" if cash_weight > reserve_target + 0.05
            else "near reserve" if cash_weight >= reserve_target
            else "below reserve"
        )
        portfolio["market_data"] = [copy.deepcopy(market[key]) for key in MARKET_PRODUCTS if key in market]
        portfolio["market_mode"] = "coinbase_live" if complete_market else "partial" if market else "unavailable"
        portfolio["updated_at"] = now


def dialogue_portfolio_context(portfolios: list[dict], investor_ids: set[str]) -> list[dict]:
    """Return concise qualitative paper-portfolio facts for Grok, without applicant data."""
    result = []
    for portfolio in portfolios:
        if portfolio.get("investor_id") not in investor_ids:
            continue
        recommendation = portfolio.get("recommendation") or {}
        result.append({
            "investor_id": portfolio.get("investor_id"),
            "investor": portfolio.get("investor"),
            "strategy": portfolio.get("strategy"),
            "cash_posture": portfolio.get("cash_posture", "unknown"),
            "paper_trading_recommendation": recommendation.get("summary", "No portfolio recommendation is available."),
            "simulated_only": True,
        })
    return result
