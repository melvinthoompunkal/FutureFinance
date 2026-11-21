"""Evidence panels linked to the dashboard's existing date and symbol controls."""

from typing import TYPE_CHECKING

import altair as alt
import pandas as pd
import streamlit as st

from . import charts, issuer_research, market_research, options, technical
from .market_calendar import capture_cutoff
from .scope import NEW_YORK, SECTORS
from .stock import price_risk
from .stress import stress_history

if TYPE_CHECKING:
    from .views import Session


def _value(value, suffix="", prefix=""):
    return f"{prefix}{value:,.2f}{suffix}" if pd.notna(value) else "Unavailable"


def _source(session: "Session", name: str) -> bool:
    source = session.inputs.research.sources.get(name, {})
    if source.get("label"):
        st.caption(source["label"])
    if source.get("detail"):
        st.caption(source["detail"])
    return source.get("status") in ("available", "loaded")


def market(session: "Session") -> None:
    st.subheader("Market internals")
    prices = session.split.tail(len(session.dates) + 252)
    activity = market_research.internals(session.inputs.members, prices, session.dates)
    if activity["Dated members"].notna().any():
        charts.lines(activity[["Advance/decline line"]], "Net advances (members)", height=175)
        if activity[["New highs", "New lows"]].notna().any().any():
            charts.lines(activity[["New highs", "New lows"]], "52-week extremes (members)", height=175)
        else:
            st.caption("Yearly extremes require 252 prior closes and enough eligible dated members.")
        with st.expander("Internals coverage by session"):
            st.dataframe(activity.sort_index(ascending=False), width="stretch")
        st.caption("Advance/decline accumulates within the chart window and restarts after a coverage gap. "
                   "Yearly extremes compare today's split-adjusted close with the preceding 252 closes. "
                   "Each series requires 90% coverage of the dated member list.")
    else:
        st.caption("Market internals need dated membership and split-adjusted member history.")
    with st.expander("Rates, dollar and market put/call"):
        _source(session, "market_context")
        context = market_research.market_context(session.inputs.research, session.day)
        if context.empty:
            st.caption("No dated rates, dollar or market put/call observations at this cutoff.")
        else:
            st.dataframe(market_research.context_summary(context), hide_index=True, width="stretch")
            ratios = context.loc[context["unit"].eq("ratio")]
            if not ratios.empty:
                chart = ratios.pivot(index="session", columns="series", values="reading").reindex(session.dates)
                charts.lines(chart.rename(columns=lambda item: item.replace("_", " ")), "Put/call ratio", height=165)
            st.caption("Rate changes are in basis points. Dollar index changes are in percent. "
                       "Each put/call percentile uses its own trailing calendar year and needs 60 valid observations.")


def sector(session: "Session", selected: str) -> None:
    with st.expander("Sector rotation"):
        rows = market_research.rotation(session.total, session.day)
        if rows.empty:
            st.caption("Rotation needs aligned sector ETF and SPY closes to warm up both windows.")
        else:
            current = rows.loc[rows["Session"].eq(session.day)].copy()
            current["Sector"] = current["ETF"].map(SECTORS)
            trail = rows.loc[rows["ETF"].eq(selected)]
            plotted = pd.concat([trail, current], ignore_index=True).drop_duplicates(["Session", "ETF"])
            points = alt.Chart(plotted)
            xy = {
                "x": alt.X("Relative strength:Q", scale=alt.Scale(zero=False)),
                "y": alt.Y("Relative momentum:Q", scale=alt.Scale(zero=False)),
            }
            baseline = alt.Chart(pd.DataFrame({"Center": [100]})).mark_rule(color="#8797AE")
            track = alt.Chart(trail).mark_line(color="#155CBE", opacity=.65).encode(**xy, order="Session:T")
            dots = points.mark_circle(size=90, opacity=.9).encode(
                **xy, color=alt.condition(alt.datum.ETF == selected, alt.value("#155CBE"), alt.value("#626991")),
                tooltip=["ETF:N", alt.Tooltip("Session:T", format="%b %d, %Y"), "Quadrant:N",
                         alt.Tooltip("Relative strength:Q", format=".2f"),
                         alt.Tooltip("Relative momentum:Q", format=".2f")],
            )
            st.altair_chart(alt.layer(baseline.encode(x="Center:Q"), baseline.encode(y="Center:Q"), track, dots)
                            .properties(height=235).configure_view(stroke=None), width="stretch", theme=None)
            st.dataframe(current[["ETF", "Sector", "Relative strength", "Relative momentum", "Quadrant"]].round(2),
                         width="stretch", hide_index=True)
            st.caption(f"{selected} trail uses the last available session of each week, through the selected date. "
                       "This approximation uses the dividend-adjusted ETF/SPY ratio divided by its 20-session mean, "
                       "smoothed over five sessions and then divided by its 10-session mean for momentum. "
                       "Both axes are centered on 100.")
            st.dataframe(trail.sort_values("Session", ascending=False).round(2), width="stretch", hide_index=True)

    with st.expander("Seven-day headline tone"):
        available = _source(session, "headlines")
        tone, stories = market_research.headline_tone(session.inputs.research,
                                                    session.inputs.members_on(session.day), session.day)
        if tone.empty:
            st.caption("No mapped headlines at this cutoff." if available else
                       "Headline tone needs a permitted news feed and dictionary.")
        else:
            if selected not in tone.index:
                st.caption(f"{SECTORS[selected]} has limited news coverage in this window.")
            st.dataframe(tone.rename_axis("Sector ETF").round(3), width="stretch")
            details = stories.loc[stories["sector_etf"].eq(selected)]
            if not details.empty:
                st.dataframe(details[["published_at", "title", "source", "symbol", "tone"]]
                             .sort_values("published_at", ascending=False), width="stretch", hide_index=True)
            dictionary = session.inputs.research.sources["headlines"]["dictionary_label"]
            st.caption(f"{dictionary}. Scored headlines are averaged by issuer, then issuers are weighted equally. "
                       "A score requires at least 10 matched headlines from three issuers. "
                       "Read the original wording to check for negation and ambiguity.")


def _gamma(checked, oi, day, session):
    profile = options.gamma_profile(checked, oi, day)
    if profile.by_strike.empty:
        st.caption(f"Gamma unavailable. {profile.modelled} of {profile.contracts} contracts met the model inputs. "
                   "At least 70% and both option sides are required.")
        return
    exposure = profile.by_strike
    call = exposure.loc[exposure["side"].eq("call"), "exposure"].sum()
    put = -exposure.loc[exposure["side"].eq("put"), "exposure"].sum()
    net = call - put
    fraction = abs(net) / (call + put) if call + put > 0 else float("nan")
    st.metric("Modeled net gamma per 1% spot move", _value(net, prefix="$"))
    st.caption(f"Gross calls ${call:,.0f}, gross puts ${put:,.0f}. "
               f"Absolute net / gross {_value(fraction * 100, '%')}. "
               f"{profile.modelled} of {profile.contracts} contracts modeled.")
    st.caption("Assumes dealers are long calls and short puts. Under that assumption positive net gamma may "
               "dampen moves and negative net gamma may amplify them.")
    vix = stress_history(session.inputs.stress, day)["VIX"].dropna()
    if not vix.empty:
        st.caption(f"Latest VIX observation {vix.iloc[-1]:.2f} on {vix.index[-1]:%b %d, %Y}.")
    spot = checked["spot"].iloc[0]
    crossings = profile.crossings
    if crossings:
        nearest = min(crossings, key=lambda level: abs(level - spot))
        st.caption(f"Nearest modeled zero crossing ${nearest:,.2f}. All detected levels "
                   + ", ".join(f"${price:,.2f}" for price in crossings) + ".")
    else:
        st.caption("No crossing in range.")
    curve = profile.curve
    chart = alt.Chart(curve).mark_line(color="#155CBE").encode(
        x=alt.X("Spot ($):Q", scale=alt.Scale(zero=False)),
        y=alt.Y("Net gamma:Q", title="Modeled dollars per 1% move"),
        tooltip=[alt.Tooltip("Spot ($):Q", format=".2f"), alt.Tooltip("Net gamma:Q", format=",.0f")])
    zero = alt.Chart(pd.DataFrame({"zero": [0]})).mark_rule(color="#8797AE").encode(y="zero:Q")
    markers = alt.Chart(pd.DataFrame({"Spot ($)": crossings})).mark_rule(color="#A25316", strokeDash=[4, 4]).encode(
        x="Spot ($):Q", tooltip=[alt.Tooltip("Spot ($):Q", format=".2f")])
    st.altair_chart(alt.layer(chart, zero, markers).properties(height=175), width="stretch", theme=None)
    st.caption("The model reprices gamma at fixed IV by contract across ±20% of spot. "
               "It uses time to settlement, rate, dividend yield, prior-session OI and verified multipliers.")
    with st.expander("Gamma profile chart data"):
        st.dataframe(curve.round(2), width="stretch", hide_index=True)
    buckets = exposure.assign(gross=exposure["exposure"].abs()).groupby("bucket", observed=True).agg(
        net=("exposure", "sum"), gross=("gross", "sum"), contracts=("oi", "sum"))
    bucket_signs = buckets["net"]
    if bucket_signs.gt(0).any() and bucket_signs.lt(0).any():
        st.caption("Expiry buckets have opposing modeled net exposures.")
    if pd.notna(fraction) and fraction < .10:
        st.caption("Net exposure is under 10% of gross exposure.")
    buckets["Gross gamma share (%)"] = (buckets["gross"] / buckets["gross"].sum() * 100
                                        if buckets["gross"].sum() else float("nan"))
    buckets["Modeled OI share (%)"] = (buckets["contracts"] / buckets["contracts"].sum() * 100
                                       if buckets["contracts"].sum() else float("nan"))
    st.dataframe(buckets.rename(columns={"net": "Net gamma ($)", "gross": "Gross gamma ($)",
                                        "contracts": "Open interest"}).round(2), width="stretch")
    _walls(exposure, spot, "exposure", "modeled gamma")
    with st.expander("Exposure by strike and expiry bucket"):
        st.dataframe(exposure.round(2), width="stretch", hide_index=True)


def _walls(frame: pd.DataFrame, spot: float, field: str, label: str) -> None:
    for side, bounds in (("call", frame["strike"].gt(spot)), ("put", frame["strike"].lt(spot))):
        candidates = frame.loc[frame["side"].eq(side) & bounds].groupby("strike")[field].sum().abs()
        if not candidates.empty and candidates.max() > 0:
            st.caption(f"{side.capitalize()} wall by {label} ${candidates.idxmax():,.2f}.")


def _chain(session: "Session", ticker: str, split: pd.Series, cutoff) -> None:
    with st.expander("Options, implied moves and positioning"):
        _source(session, "options")
        history = options.visible_history(session.inputs.research, ticker, session.day)
        if history.empty:
            st.caption("No permitted chain snapshots for this symbol at the selected cutoff.")
            return
        day = session.day
        current = options.latest_chain(history, day)
        checked = options.assess_quotes(current, day)
        sample = options.iv_history(history, split.index)
        count, rank, percentile = options.iv_reading(sample)
        latest = sample.iloc[-1]
        left, middle, right = st.columns(3)
        left.metric("30-day ATM IV", _value(latest, "%"))
        middle.metric("IV rank", _value(rank, "%"))
        right.metric("IV percentile", _value(percentile, "%"))
        status = "Collecting history" if count < 60 else "Provisional window" if count < 252 else "Full 252 sessions"
        st.caption(f"{status}. {count} valid observations in the latest 252 sessions. "
                   "Rank measures position in the observed range. Percentile counts readings strictly below today's.")
        if count:
            charts.lines(sample.loc[session.dates].to_frame(), "Annualized implied volatility (%)", height=160)
        risk = price_risk(session.inputs, ticker, split, session.dates)
        rv = risk["Realized volatility (20)"]
        st.caption(f"20-session realized volatility {_value(rv, '%')}. 60-session realized volatility "
                   f"{_value(risk['Realized volatility (60)'], '%')}. IV minus 20-session realized "
                   f"{_value(latest - rv, ' pp')}.")
        if current.empty:
            st.caption("No chain on the selected session.")
        else:
            observed = current["observed_at"].iloc[0].tz_convert(NEW_YORK)
            st.caption(f"Chain captured {observed:%b %d, %Y at %I:%M %p %Z}. Spot ${current['spot'].iloc[0]:,.2f}.")
            with st.expander("Quote quality and contract timestamps"):
                st.dataframe(checked["quality"].value_counts().rename("Contracts"), width="stretch")
                st.dataframe(checked[["contract", "expiry", "quote_at", "spot_at", "bid", "ask", "quality"]],
                             width="stretch", hide_index=True)
                st.caption("Quotes need standard verified terms, a positive bid, a spread no wider than 35% of mid, "
                           "and spot within 20 minutes of the quote. Both must be within 30 minutes of the snapshot.")
            term = options.term_structure(checked, day)
            if not term.empty:
                st.dataframe(term.round(2), width="stretch", hide_index=True)
                st.caption("Straddle adds the call and put mids at the nearest shared strike. "
                           "The one-standard-deviation range uses spot × annualized IV × √(days/365). "
                           "30-day IV interpolates total variance and needs expiries bracketing 30 days.")
                if pd.isna(latest):
                    st.caption("30-day IV needs a usable ATM call and put at 30 days or at expiries on both sides.")
            else:
                st.caption("No expiration had a usable quote at this capture.")
        oi, effective = options.open_interest(history, day)
        vol_value, vol_count = options.put_call(checked.loc[checked["quality"].eq("Retained")], "volume")
        oi_value, oi_count = options.put_call(oi, "oi")
        st.caption(f"Put/call volume {_value(vol_value)} across {vol_count} quoted contracts. "
                   f"Put/call OI {_value(oi_value)} across {oi_count} dated contracts.")
        if oi.empty or oi["change"].isna().all():
            st.caption(f"OI update or comparison pending. Expected effective date {effective:%b %d, %Y}.")
        if not oi.empty:
            with st.expander(f"Open interest effective {effective:%b %d, %Y}"):
                st.dataframe(oi[["contract", "expiry", "strike", "side", "oi", "change"]], width="stretch",
                             hide_index=True)
                if not current.empty:
                    _walls(oi, current["spot"].iloc[0], "oi", "dated open interest")
        if current.empty:
            st.caption("Gamma needs a chain and prior-session open interest.")
        else:
            at_capture = history.loc[history["available_at"].le(current["available_at"].iloc[0])]
            aligned_oi, _ = options.open_interest(at_capture, day)
            _gamma(checked, aligned_oi, day, session)
        retained = checked.loc[checked["quality"].eq("Retained")]
        zero = options.pre_expiry_chain(history, day)
        if not zero.empty:
            earlier = zero["observed_at"].iloc[0]
            if (current.empty or earlier != current["observed_at"].iloc[0]
                    or zero["available_at"].iloc[0] != current["available_at"].iloc[0]):
                st.caption(f"Earlier pre-expiry snapshot at {earlier.tz_convert(NEW_YORK):%I:%M %p %Z}.")
                pre_expiry = options.assess_quotes(zero, day)
                retained = pre_expiry.loc[pre_expiry["quality"].eq("Retained")]
                at_capture = history.loc[history["available_at"].le(zero["available_at"].iloc[0])]
                aligned_oi, _ = options.open_interest(at_capture, day)
                earlier_profile = options.gamma_profile(pre_expiry, aligned_oi, day)
                if not earlier_profile.by_strike.empty:
                    gross = earlier_profile.by_strike["exposure"].abs()
                    zero_days = earlier_profile.by_strike["bucket"].eq(options.BUCKETS[0])
                    if gross.sum():
                        st.caption(f"0-day share of gross modeled gamma {gross.loc[zero_days].sum() / gross.sum():.1%} "
                                   "at the pre-expiry snapshot.")
            volume = retained["volume"].sum()
            if volume > 0 and retained["volume"].notna().all():
                share = retained.loc[retained["expiry"].eq(day), "volume"].sum() / volume
                st.caption(f"0-day share of quoted-contract volume {share:.1%}.")
        else:
            st.caption("0-day concentration needs a timed snapshot before settlement.")
        releases = issuer_research.earning_releases(session.inputs.research.known("estimates", cutoff, ticker))
        moves = options.event_moves(history, releases, split)
        if not moves.empty:
            st.caption("Earnings moves use the last close before release and the first completed close after it. "
                       "The options range uses the first eligible expiry covering that comparison.")
            st.dataframe(moves.round(2), width="stretch", hide_index=True)


def stock(session: "Session", ticker: str, split: pd.Series, fund: bool) -> None:
    cutoff = capture_cutoff(session.day.date())
    bars = session.inputs.bars_for(ticker).reindex(split.index)
    with st.expander("Trend strength and confirmed swing levels"):
        values = technical.technical(bars).loc[session.dates]
        st.caption(f"ADX (14) {_value(values['ADX (14)'].iloc[-1])}. "
                   f"Bollinger bandwidth {_value(values['Bandwidth (%)'].iloc[-1], '%')}.")
        if values.notna().any().any():
            if values["ADX (14)"].notna().any():
                charts.lines(values[["ADX (14)", "+DI", "−DI"]], "Directional movement (0–100)", height=160)
            if values["Bandwidth (%)"].notna().any():
                charts.lines(values[["Bandwidth (%)"]], "Bollinger bandwidth (%)", height=150)
        swings = technical.swings(bars.loc[session.dates])
        if swings.empty:
            st.caption("No swing highs or lows have three completed sessions on both sides in this window.")
        else:
            st.dataframe(swings.round(2), width="stretch", hide_index=True)
            st.caption("Each split-adjusted level appears after the third confirming session closes.")

    _chain(session, ticker, split, cutoff)
    with st.expander("Intraday VWAP and volume profile"):
        _source(session, "intraday")
        known = session.inputs.research.known("intraday", cutoff, ticker)
        rows, profile = technical.intraday_profile(known, session.day)
        if profile.empty:
            st.caption(f"VWAP and profile require complete regular-session bars with volume. "
                       f"{len(rows)} bars available in the session.")
        else:
            st.metric("Session VWAP approximation", _value(rows["VWAP proxy"].iloc[-1], prefix="$"))
            st.caption("Uses each bar's typical price and reported volume. The 70% volume area expands from the "
                       "largest bin. Volume represents the venue coverage listed above.")
            chart = alt.Chart(profile).mark_bar().encode(
                x=alt.X("Shares:Q", title="Reported shares"),
                y=alt.Y("Bin low ($):Q", title="Quoted price ($)", scale=alt.Scale(zero=False)),
                y2="Bin high ($):Q",
                color=alt.condition(alt.datum["70% value area"], alt.value("#155CBE"), alt.value("#8797AE")),
                tooltip=[alt.Tooltip("Bin low ($):Q", format=".2f"), alt.Tooltip("Bin high ($):Q", format=".2f"),
                         "Shares:Q", "70% value area:N", "Point of control:N"],
            ).properties(height=185)
            st.altair_chart(chart, width="stretch", theme=None)
            st.dataframe(profile.round(2), width="stretch", hide_index=True)
            with st.expander("Intraday bars and cumulative VWAP"):
                st.dataframe(rows[["start_at", "end_at", "volume", "VWAP proxy"]].round(2), width="stretch",
                             hide_index=True)
    if not fund:
        _issuer(session, ticker, cutoff)


def _issuer(session: "Session", ticker: str, cutoff) -> None:
    research = session.inputs.research
    with st.expander("Filing history, earnings and estimates"):
        history, filings = issuer_research.issuer_history(session.inputs.filings, ticker, session.day)
        if history.empty:
            st.caption("No filing history for this issuer at the selected cutoff.")
        else:
            st.dataframe(history.round(2), width="stretch", hide_index=True,
                         column_config={"Filing": st.column_config.LinkColumn("Filing")})
            values = issuer_research.valuation_history(filings, session.inputs.bars_for(ticker), session.day)
            for label in values:
                observations = values[label].count()
                if observations:
                    st.caption(f"{label} · {observations} available sessions within five years. "
                               "Each close uses the filing known that evening.")
                    charts.lines(values[[label]], label, height=150)
        _source(session, "estimates")
        estimates = research.known("estimates", cutoff, ticker)
        if estimates.empty:
            st.caption("No dated earnings results or estimate snapshots on file.")
        else:
            surprises = issuer_research.earnings_surprises(estimates)
            revisions = issuer_research.estimate_revisions(estimates, cutoff)
            if not surprises.empty:
                st.markdown("**Last eight reported earnings**")
                st.dataframe(surprises.round(2), width="stretch", hide_index=True)
            if not revisions.empty:
                st.markdown("**30- and 90-day consensus revisions**")
                st.dataframe(revisions.round(2), width="stretch", hide_index=True)
    with st.expander("Insider transactions and reported short activity"):
        _source(session, "insiders")
        trades = issuer_research.insider_trades(research.known("insiders", cutoff, ticker))
        if trades.empty:
            st.caption("No verified open-market Form 4 purchases or sales at this cutoff.")
        else:
            recent = trades.loc[trades["session"].gt(session.day - pd.Timedelta(days=90))]
            values = recent.groupby("Side")["Value ($)"].sum(min_count=1)
            if not values.empty:
                st.caption(f"Reported 90-day open-market purchases {_value(values.get('Purchase', 0), prefix='$')}. "
                           f"Sales {_value(values.get('Sale', 0), prefix='$')}.")
            st.dataframe(trades[["session", "available_at", "Side", "shares", "price", "Value ($)", "Filing"]],
                         width="stretch", hide_index=True,
                         column_config={"Filing": st.column_config.LinkColumn("Filing")})
        _source(session, "positioning")
        activity = issuer_research.positioning(research.known("positioning", cutoff, ticker))
        if activity.empty:
            st.caption("No dated short interest, ATS or off-exchange short volume observations.")
        else:
            labels = {"short_float": "Short interest / float", "days_to_cover": "Days to cover",
                      "ats_share": "ATS share", "off_exchange_short_share": "Reported off-exchange short volume share"}
            activity["metric"] = activity["metric"].map(labels)
            st.dataframe(activity.drop(columns="symbol").sort_values("session", ascending=False).round(2),
                         width="stretch", hide_index=True)
            st.caption("Short interest measures outstanding positions. Short volume measures reported trades. "
                       "ATS volume has no trade direction. Ratios require matched, sourced denominators.")
