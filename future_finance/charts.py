import altair as alt
import pandas as pd
import streamlit as st

COLORS = ["#155CBE", "#A25316", "#626991"]


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
            x=alt.X("Session:T", title=None, scale=alt.Scale(type="utc"), axis=alt.Axis(format="%b %d")),
            y=alt.Y("Value:Q", title=unit, scale=scale, axis=alt.Axis(minExtent=46)),
            color=alt.Color("Series:N", sort=list(wide.columns), scale=alt.Scale(range=COLORS),
                            legend=alt.Legend(title=None, orient="top", symbolStrokeWidth=3)),
            strokeDash=alt.StrokeDash("Series:N", sort=list(wide.columns), legend=None),
            tooltip=[alt.Tooltip("Session:T", format="%b %d, %Y"), "Series:N",
                     alt.Tooltip("Value:Q", title=unit, format=".2f")],
        )
        .properties(height=height)
    )
    if index_baseline:
        baseline = alt.Chart(pd.DataFrame({"baseline": [100]})).mark_rule(color="#8797AE").encode(y="baseline:Q")
        chart = alt.layer(chart, baseline).properties(height=height)
    st.altair_chart(chart.configure_view(stroke=None), width="stretch", theme=None)
    with st.expander(f"{unit} chart data"):
        st.dataframe(wide.sort_index(ascending=False).round(2), width="stretch")


def sector_bars(ranking: pd.DataFrame) -> None:
    data = ranking.reset_index().dropna(subset=["20 sessions"])
    if data.empty:
        st.info("Sector rankings need aligned dividend-adjusted closes 20 sessions apart.")
        return
    span = max(float(data["20 sessions"].abs().max()), 0.1) * 1.12
    chart = (
        alt.Chart(data).mark_bar(size=13)
        .encode(
            x=alt.X("20 sessions:Q", title="Relative return (%)",
                    scale=alt.Scale(domain=[-span, span]), axis=alt.Axis(format="+.1f")),
            y=alt.Y("ETF:N", title=None, sort=list(data["ETF"]), axis=alt.Axis(labelFontSize=12)),
            color=alt.condition(alt.datum["20 sessions"] >= 0, alt.value(COLORS[0]), alt.value(COLORS[1])),
            tooltip=["Sector:N", alt.Tooltip("20 sessions:Q", title="vs. SPY (%)", format="+.2f"),
                     alt.Tooltip("Absolute, 20 sessions:Q", title="Absolute (%)", format="+.2f")],
        )
        .properties(height=max(130, len(data) * 21))
    )
    st.altair_chart(chart.configure_view(stroke=None), width="stretch", theme=None)
