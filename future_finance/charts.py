import altair as alt
import pandas as pd
import streamlit as st

from .analytics import change

COLORS = ["#B5A7F5", "#A0A1AA", "#71727B"]
REFERENCE = "#71727B"
GAIN = "#6EC49C"
LOSS = "#EE9397"
AXIS_FONT = "IBM Plex Mono"


def render(chart) -> None:
    st.altair_chart(chart.configure(
        background="transparent",
        font="IBM Plex Sans",
        view=alt.ViewConfig(stroke=None),
        axis=alt.AxisConfig(
            gridColor="#303137", gridOpacity=.72, domain=False, ticks=False,
            labelColor="#A0A1AA", titleColor="#A0A1AA", labelPadding=5, titlePadding=8,
            labelFont=AXIS_FONT, labelFontSize=10, titleFontSize=11, titleFontWeight="normal",
            titleFont="IBM Plex Sans",
        ),
        legend=alt.LegendConfig(labelColor="#EBEBEE", titleColor="#A0A1AA", labelFontSize=11),
    ), width="stretch", theme=None)


def daily_price(bars: pd.DataFrame, dates: pd.DatetimeIndex, ticker: str) -> None:
    data = bars[["split_high", "split_low", "split_close", "volume"]].assign(
        move=change(bars["split_close"], 1)
    ).loc[dates].rename_axis("Session").reset_index()
    show_price = data["split_close"].notna().any()
    show_volume = data["volume"].notna().any()
    if not show_price:
        st.info(f"No split-adjusted closes for {ticker} in this window.")
        if not show_volume:
            return

    date_axis = alt.Axis(format="%b %d", tickCount=5, grid=False)
    margin = pd.Timedelta(hours=12)
    time = alt.X("Session:T", title=None,
                 scale=alt.Scale(type="utc", domain=[dates[0] - margin, dates[-1] + margin], nice=False))
    price = alt.Y(field="split_close", type="quantitative", title="Price (USD)", scale=alt.Scale(zero=False),
                  axis=alt.Axis(orient="right", minExtent=54, maxExtent=54, tickCount=5, format=",.2f",
                                labelAlign="right", labelPadding=49))
    color = (alt.when(alt.datum.move > 0).then(alt.value(GAIN))
             .when(alt.datum.move < 0).then(alt.value(LOSS)).otherwise(alt.value(REFERENCE)))
    tooltip = [alt.Tooltip("Session:T", format="%b %d, %Y"),
               alt.Tooltip("split_close:Q", title="Adjusted close", format="$.2f"),
               alt.Tooltip("split_high:Q", title="Adjusted high", format="$.2f"),
               alt.Tooltip("split_low:Q", title="Adjusted low", format="$.2f"),
               alt.Tooltip("move:Q", title="Session change (%)", format="+.2f"),
               alt.Tooltip("volume:Q", title="Reported shares", format=",.0f")]
    base = alt.Chart(data).encode(x=time.axis(None if show_volume else date_axis))
    line = base.mark_line(color=COLORS[0], strokeWidth=1.6, invalid="break-paths-show-domains",
                          point=alt.OverlayMarkDef(size=16, filled=True)).encode(y=price, tooltip=tooltip)
    ranges = base.mark_rule(strokeWidth=2, opacity=.7).encode(
        y=price.field("split_low"), y2="split_high:Q", color=color, tooltip=tooltip,
    )
    has_range = data[["split_low", "split_high"]].notna().all(axis=1).any()
    with st.container(key="price-plot"):
        if show_price:
            render((ranges + line if has_range else line).properties(height=238))
        if show_volume:
            volume_axis = alt.Axis(orient="right", minExtent=54, maxExtent=54, tickCount=3, format="~s",
                                   labelAlign="right", labelPadding=49)
            volume = alt.Chart(data).mark_bar(size=4, opacity=.72).encode(
                x=time.axis(date_axis), y=alt.Y("volume:Q", title="Volume", axis=volume_axis),
                color=color, tooltip=tooltip,
            ).properties(height=72)
            render(volume)
    with st.expander("Daily price and volume data"):
        table = data.set_index("Session")[["split_high", "split_low", "split_close", "volume"]]
        st.dataframe(table.sort_index(ascending=False).rename(columns={
            "split_high": "Adjusted high", "split_low": "Adjusted low",
            "split_close": "Adjusted close", "volume": "Reported shares",
        }), width="stretch")


def lines(values: pd.DataFrame, unit: str, *, height: int = 220,
          domain: list[float] | None = None, index_baseline: bool = False) -> None:
    if values.empty or not values.notna().any().any():
        st.info("No observations in this window.")
        return
    wide = values.rename_axis("Session").rename_axis(None, axis=1)
    chart_data = wide.reset_index().melt("Session", var_name="Series", value_name="Value")
    scale = alt.Scale(domain=domain, nice=False) if domain else alt.Scale(zero=False)
    chart = (
        alt.Chart(chart_data).mark_line(strokeWidth=2.5, invalid="break-paths-show-domains")
        .encode(
            x=alt.X("Session:T", title=None, scale=alt.Scale(type="utc"),
                    axis=alt.Axis(format="%b %d", tickCount=5, grid=False)),
            y=alt.Y("Value:Q", title=unit, scale=scale, axis=alt.Axis(minExtent=42, tickCount=5)),
            color=alt.Color("Series:N", sort=list(wide.columns), scale=alt.Scale(range=COLORS),
                            legend=alt.Legend(title=None, orient="top", symbolStrokeWidth=3)),
            strokeDash=alt.StrokeDash("Series:N", sort=list(wide.columns), legend=None),
            tooltip=[alt.Tooltip("Session:T", format="%b %d, %Y"), "Series:N",
                     alt.Tooltip("Value:Q", title=unit, format=".2f")],
        )
        .properties(height=height)
    )
    if index_baseline:
        baseline = alt.Chart(pd.DataFrame({"baseline": [100]})).mark_rule(
            color=REFERENCE, strokeDash=[3, 4]
        ).encode(y="baseline:Q")
        chart = alt.layer(chart, baseline).properties(height=height)
    render(chart)
    with st.expander(f"{unit} chart data"):
        st.dataframe(wide.sort_index(ascending=False).round(2), width="stretch")


def sector_bars(ranking: pd.DataFrame) -> None:
    data = ranking.reset_index().dropna(subset=["20 sessions"])
    if data.empty:
        st.info("Sector rankings need aligned dividend-adjusted closes 20 sessions apart.")
        return
    span = max(float(data["20 sessions"].abs().max()), 0.1) * 1.12
    chart = (
        alt.Chart(data).mark_bar(size=13, cornerRadius=3)
        .encode(
            x=alt.X("20 sessions:Q", title="Relative return (%)",
                    scale=alt.Scale(domain=[-span, span]), axis=alt.Axis(format="+.1f", tickCount=7)),
            y=alt.Y("ETF:N", title=None, sort=list(data["ETF"]), axis=alt.Axis(labelFontSize=12)),
            color=(alt.when(alt.datum["20 sessions"] > 0).then(alt.value(GAIN))
                   .when(alt.datum["20 sessions"] < 0).then(alt.value(LOSS)).otherwise(alt.value(REFERENCE))),
            tooltip=["Sector:N", alt.Tooltip("20 sessions:Q", title="vs. SPY (%)", format="+.2f"),
                     alt.Tooltip("Absolute, 20 sessions:Q", title="Absolute (%)", format="+.2f")],
        )
        .properties(height=max(130, len(data) * 21))
    )
    render(chart)
