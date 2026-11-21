"""Sample documented provider endpoints and report observed coverage as JSON."""

import argparse
from collections import Counter
from datetime import date, datetime, time, timedelta
import json
import math
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .scope import NEW_YORK, SAMPLE_ISSUERS, SAMPLE_SYMBOLS

ALPACA_DATA = "https://data.alpaca.markets"
SEC_DATA = "https://data.sec.gov"
BAR_FIELDS = ("t", "o", "h", "l", "c", "v")
SEC_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
    "OperatingIncomeLoss", "NetIncomeLoss", "EarningsPerShareDiluted",
    "NetCashProvidedByUsedInOperatingActivities", "PaymentsToAcquirePropertyPlantAndEquipment",
    "LongTermDebtCurrent", "LongTermDebtNoncurrent", "InterestExpense",
)


class ProbeError(Exception):
    pass


class Client:
    def __init__(self, headers: dict[str, str]):
        self.headers = {"Accept": "application/json", **headers}
        self.requests = 0

    def get(self, endpoint: str, **params) -> dict:
        url = f"{endpoint}?{urlencode(params)}" if params else endpoint
        self.requests += 1
        request = Request(url)
        for name, value in self.headers.items():
            request.add_unredirected_header(name, value)
        try:
            with urlopen(request, timeout=12) as response:
                payload = json.load(response)
        except HTTPError as error:
            raise ProbeError(f"HTTP {error.code} from {endpoint}.") from None
        except (OSError, URLError) as error:
            reason = type(error.reason).__name__ if isinstance(error, URLError) else type(error).__name__
            raise ProbeError(f"Connection failed for {endpoint} ({reason}).") from None
        except (ValueError, UnicodeError):
            raise ProbeError(f"Invalid JSON from {endpoint}.") from None
        if not isinstance(payload, dict):
            raise ProbeError(f"Unexpected JSON structure from {endpoint}.")
        return payload

    def pages(self, endpoint: str, **params):
        seen = set()
        for _ in range(15):
            payload = self.get(endpoint, **params)
            yield payload
            token = payload.get("next_page_token")
            if token is None:
                return
            if not isinstance(token, str) or not token or token in seen:
                raise ProbeError("Provider did not return a usable next-page token.")
            seen.add(token)
            params["page_token"] = token
        raise ProbeError("Sample exceeded the 15-page budget.")


def _bar_date(bar: dict) -> date:
    timestamp = datetime.fromisoformat(bar["t"])
    if timestamp.tzinfo is None:
        raise ValueError("Missing timestamp offset")
    return timestamp.astimezone(NEW_YORK).date()


def _usable_bar(bar: dict) -> bool:
    try:
        _bar_date(bar)
        return (all(math.isfinite(bar[field]) and bar[field] > 0 for field in ("o", "h", "l", "c"))
                and math.isfinite(bar["v"]) and bar["v"] >= 0)
    except (KeyError, TypeError, ValueError):
        return False


def bars_sample(client: Client, start: date, latest: date, adjustment: str) -> dict:
    request_start = client.requests
    end = datetime.combine(latest, time(16), NEW_YORK)
    rows = {symbol: [] for symbol in SAMPLE_SYMBOLS}
    for page in client.pages(f"{ALPACA_DATA}/v2/stocks/bars", symbols=",".join(rows),
                             timeframe="1Day", feed="sip", adjustment=adjustment, limit=10_000,
                             start=datetime.combine(start, time.min, NEW_YORK).isoformat(),
                             end=end.isoformat()):
        for symbol, bars in (page.get("bars") or {}).items():
            if symbol in rows:
                rows[symbol].extend(bars)
    report = {}
    checkpoints = {date(2025, 12, 4), date(2025, 12, 5), date(2025, 12, 18), date(2025, 12, 19)}
    for symbol, bars in rows.items():
        valid = {day: bar for bar in bars if _usable_bar(bar)
                 if start <= (day := _bar_date(bar)) <= latest}
        report[symbol] = {
            "rows": len(bars), "usable_sessions": len(valid), "invalid_or_duplicate_rows": len(bars) - len(valid),
            "first_session": min(valid).isoformat() if valid else None,
            "last_session": max(valid).isoformat() if valid else None,
            "requested_session_present": latest in valid,
            "missing_fields": dict(Counter(field for bar in bars for field in BAR_FIELDS if bar.get(field) is None)),
            "adjustment_checkpoints": {
                day.isoformat(): {"close": valid[day]["c"], "volume": valid[day]["v"]}
                for day in sorted(checkpoints.intersection(valid))
            } if symbol in ("SPY", "XLK", "XLE") else {},
        }
    return {"adjustment": adjustment, "requests": client.requests - request_start, "symbols": report}


def sec_sample(client: Client, symbol: str, cik: int) -> dict:
    facts = client.get(f"{SEC_DATA}/api/xbrl/companyfacts/CIK{cik:010}.json").get("facts", {})
    recent = client.get(f"{SEC_DATA}/submissions/CIK{cik:010}.json").get("filings", {}).get("recent", {})
    gaap = facts.get("us-gaap", {})
    filings = dict(zip(recent.get("accessionNumber", []), recent.get("acceptanceDateTime", [])))
    tags = {}
    for tag in SEC_TAGS:
        units = gaap.get(tag, {}).get("units", {})
        tags[tag] = {unit: {"observations": len(rows),
                           "matched_acceptance_times": sum(bool(filings.get(row.get("accn"))) for row in rows)}
                     for unit, rows in units.items()}
    return {"symbol": symbol, "cik": cik, "recent_filing_count": len(filings), "tags": tags}


def options_sample(client: Client, trading_base: str, today: date) -> dict:
    ticker = "SPY"
    expiry = today + timedelta(days=35)
    chain = {}
    for page in client.pages(f"{ALPACA_DATA}/v1beta1/options/snapshots/{ticker}",
                             feed="indicative", expiration_date_gte=today.isoformat(),
                             expiration_date_lte=expiry.isoformat(), limit=1000):
        chain.update(page.get("snapshots") or {})
    spot = client.get(f"{ALPACA_DATA}/v2/stocks/{ticker}/quotes/latest", feed="iex").get("quote") or {}
    reference = {}
    for page in client.pages(f"{trading_base}/v2/options/contracts", underlying_symbols=ticker,
                             expiration_date_gte=today.isoformat(), expiration_date_lte=expiry.isoformat(),
                             status="active", limit=1000):
        reference.update({row["symbol"]: row for row in page.get("option_contracts") or []})
    matched = chain.keys() & reference.keys()
    oi = {symbol: reference[symbol].get("open_interest_date") for symbol in sorted(matched)
          if reference[symbol].get("open_interest") is not None}
    oi_days = Counter(day or "missing" for day in oi.values())
    quote_times = [stamp for row in chain.values() if (stamp := (row.get("latestQuote") or {}).get("t"))]
    return {
        "symbol": ticker, "expiration_start": today.isoformat(), "expiration_end": expiry.isoformat(),
        "chain_contracts": len(chain), "reference_contracts": len(reference), "joined_contracts": len(matched),
        "joined_oi_effective_dates": dict(sorted(oi_days.items())),
        "oi_date_examples": dict(list(oi.items())[:5]),
        "joined_with_oi": sum(oi_days.values()),
        "quote_timestamps": len(quote_times), "latest_quote_timestamp": max(quote_times, default=None),
        "spot_feed": "iex", "spot_quote_timestamp": spot.get("t"),
    }


def _attempt(sample, *args) -> dict:
    try:
        return {"status": "sampled", **sample(*args)}
    except ProbeError as error:
        return {"status": "blocked", "reason": str(error)}
    except (AttributeError, KeyError, TypeError, ValueError):
        return {"status": "invalid response", "reason": "Response did not match the documented fields."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True, type=date.fromisoformat, help="Completed New York session.")
    parser.add_argument("--start", type=date.fromisoformat, help="First day of the sample. Defaults to two years.")
    parser.add_argument("--options", action="store_true", help="Also sample today's indicative SPY chain and dated OI.")
    parser.add_argument("--live-keys", action="store_true", help="Use the live trading host for option contract reference.")
    args = parser.parse_args()
    now = datetime.now(tz=NEW_YORK)
    if args.session.year < 3:
        parser.error("Provide a session in year 3 or later.")
    lookback_year = args.session.year - 2
    lookback_day = 28 if (args.session.month, args.session.day) == (2, 29) else args.session.day
    start = args.start or args.session.replace(year=lookback_year, day=lookback_day)
    if not start <= args.session <= now.date() or args.session.weekday() >= 5:
        parser.error("Provide a completed weekday session with a start on or before it.")
    if args.session == now.date() and now.time() < time(16, 30):
        parser.error("For today's session, run the sample after 4:30 p.m. New York time.")

    key = os.getenv("APCA_API_KEY_ID")
    secret = os.getenv("APCA_API_SECRET_KEY")
    identity = os.getenv("SEC_USER_AGENT", "")
    report = {"observed_at": now.isoformat(), "start": start.isoformat(), "session": args.session.isoformat()}
    if key and secret:
        alpaca = Client({"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})
        report["bars"] = {adjustment: _attempt(bars_sample, alpaca, start, args.session, adjustment)
                          for adjustment in ("raw", "split", "all")}
        if args.options:
            trading_base = "https://api.alpaca.markets" if args.live_keys else "https://paper-api.alpaca.markets"
            report["options"] = _attempt(options_sample, alpaca, trading_base, now.date())
        report["alpaca_requests"] = alpaca.requests
    else:
        reason = "Set APCA_API_KEY_ID and APCA_API_SECRET_KEY to sample Alpaca."
        report["bars"] = {"status": "blocked", "reason": reason}
        if args.options:
            report["options"] = {"status": "blocked", "reason": reason}
    if re.search(r"[^\s@]+@[^\s@]+\.[^\s@]+", identity) and "\n" not in identity and "\r" not in identity:
        sec = Client({"User-Agent": identity})
        report["sec"] = {symbol: _attempt(sec_sample, sec, symbol, cik) for symbol, cik in SAMPLE_ISSUERS.items()}
        report["sec_requests"] = sec.requests
    else:
        report["sec"] = {"status": "blocked", "reason": "Set SEC_USER_AGENT to your app name and contact email."}
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
