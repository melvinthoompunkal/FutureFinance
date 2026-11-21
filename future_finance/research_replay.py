"""Replay Phase 5 readings from a pinned archive publication."""

import json

import pandas as pd

from . import issuer_research, market_research, options, technical
from .inputs import Inputs
from .market_calendar import capture_cutoff


def _rows(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def research_readings(inputs: Inputs, day: pd.Timestamp, sector: str, ticker: str) -> dict:
    research = inputs.research
    cutoff = capture_cutoff(day.date())
    split = inputs.prices("split_close").loc[:day]
    bars = inputs.bars_for(ticker).reindex(split.index)
    tone, _ = market_research.headline_tone(research, inputs.members_on(day), day)
    if not tone.empty:
        tone = tone.reset_index()
    history = options.visible_history(research, ticker, day)
    current = options.latest_chain(history, day)
    checked = options.assess_quotes(current, day)
    interest, effective = options.open_interest(history, day)
    sample = options.iv_history(history, split.index)
    count, rank, percentile = options.iv_reading(sample)
    iv = pd.DataFrame({"IV30 (%)": [sample.iloc[-1]], "Rank (%)": [rank], "Percentile (%)": [percentile]})
    profile = None
    if not current.empty:
        eligible = history.loc[history["available_at"].le(current["available_at"].iloc[0])]
        aligned, _ = options.open_interest(eligible, day)
        profile = options.gamma_profile(checked, aligned, day)
    estimates = research.known("estimates", cutoff, ticker)
    earnings = issuer_research.earning_releases(estimates)
    filings, _ = issuer_research.issuer_history(inputs.filings, ticker, day)
    return {
        "formula_version": 1,
        "market": _rows(market_research.internals(inputs.members, split.tail(253), split.index[-1:])),
        "market_context": _rows(market_research.context_summary(market_research.market_context(research, day))),
        "rotation": _rows(market_research.rotation(inputs.prices("total_return_close"), day).query("ETF == @sector")),
        "headline_tone": _rows(tone),
        "stock": {
            "technical": _rows(technical.technical(bars).tail(1)),
            "swing_levels": _rows(technical.swings(bars.tail(60))),
            "filing_history": _rows(filings),
            "earnings_surprises": _rows(issuer_research.earnings_surprises(estimates)),
            "estimate_revisions": _rows(issuer_research.estimate_revisions(estimates, cutoff)),
            "insiders": _rows(issuer_research.insider_trades(research.known("insiders", cutoff, ticker))),
            "positioning": _rows(issuer_research.positioning(research.known("positioning", cutoff, ticker))),
            "options": {
                "quote_quality": {name: int(count) for name, count in checked["quality"].value_counts().items()},
                "term_structure": _rows(options.term_structure(checked, day)),
                "volatility": _rows(iv)[0],
                "iv_observations": count,
                "oi_effective_session_expected": effective.date().isoformat(),
                "open_interest": _rows(interest),
                "gamma_by_strike": _rows(profile.by_strike) if profile else [],
                "gamma_crossings": profile.crossings if profile else [],
                "earnings_moves": _rows(options.event_moves(history, earnings, bars["split_close"])),
            },
        },
    }
