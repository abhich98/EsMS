from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from app.data_loader import load_daily_costs, read_battery_specs, read_num_scenarios


st.set_page_config(
    page_title="EsMS Results Explorer",
    page_icon="⚡",
    layout="wide",
)


@st.cache_data
def get_daily_costs() -> pd.DataFrame:
    return load_daily_costs()


@st.cache_data
def get_battery_specs() -> list[dict]:
    return read_battery_specs()


@st.cache_data
def get_num_scenarios() -> int | None:
    return read_num_scenarios()


def render_multi_panel_plot(filtered_costs: pd.DataFrame) -> None:
    season_colors = {
        "winter": "#93c5fd",
        "spring": "#86efac",
        "summer": "#fcd34d",
        "autumn": "#fca5a5",
        "unknown": "#d1d5db",
    }

    plot_df = filtered_costs.sort_values("day").reset_index(drop=True)
    plot_df["season"] = plot_df["season"].fillna("unknown")
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.28, 0.38, 0.34],
        subplot_titles=(
            "Daily energy prices",
            "Daily cost incurred",
            "Daily and cumulative cost gap",
        ),
    )

    current_season = None
    season_start_idx = 0
    x_values = plot_df["day"].to_list()
    season_segments: list[tuple[int, int, str]] = []

    for idx, season in enumerate(plot_df["season"].to_list()):
        if current_season is None:
            current_season = season
            season_start_idx = idx
            continue
        if season != current_season:
            season_segments.append((season_start_idx, idx - 1, current_season))
            season_start_idx = idx
            current_season = season

    if current_season is not None:
        season_segments.append((season_start_idx, len(plot_df) - 1, current_season))

    for start_idx, end_idx, season in season_segments:
        start_x = x_values[start_idx]
        end_x = x_values[end_idx]
        fig.add_vrect(
            x0=start_x,
            x1=end_x,
            fillcolor=season_colors.get(str(season).lower(), season_colors["unknown"]),
            opacity=0.38,
            line_width=0,
            row="all",
            col=1,
        )
        mid_idx = (start_idx + end_idx) // 2
        fig.add_annotation(
            x=x_values[mid_idx],
            y=1.0,
            yref="paper",
            text=str(season),
            showarrow=False,
            yanchor="bottom",
            font={"size": 10, "color": "#111827"},
        )

    for _, end_idx, _ in season_segments[:-1]:
        fig.add_vline(
            x=x_values[end_idx],
            line_color="#374151",
            line_dash="dash",
            line_width=1.4,
            opacity=0.95,
            row="all",
            col=1,
        )

    fig.add_trace(
        go.Scatter(
            x=plot_df["day"],
            y=plot_df["price_median_eur_per_kwh"],
            mode="lines",
            name="Median price",
            line={"width": 2, "color": "#2563eb"},
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=plot_df["day"],
            y=plot_df["price_max_eur_per_kwh"],
            mode="lines",
            name="Max price",
            line={"width": 2, "color": "#dc2626"},
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=plot_df["day"],
            y=plot_df["deterministic_cost_eur"],
            mode="lines",
            name="Deterministic cost",
            line={"width": 2, "color": "#1d4ed8"},
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=plot_df["day"],
            y=plot_df["stochastic_total_cost_eur"],
            mode="lines",
            name="Stochastic cost",
            line={"width": 2, "color": "#30721F"},
        ),
        row=2,
        col=1,
    )

    cumulative_gap = plot_df["cost_gap_eur"].cumsum()
    fig.add_trace(
        go.Bar(
            x=plot_df["day"],
            y=plot_df["cost_gap_eur"],
            name="Daily gap",
            marker_color="#f59e0b",
            opacity=0.45,
        ),
        row=3,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=plot_df["day"],
            y=cumulative_gap,
            mode="lines",
            name="Cumulative gap",
            line={"width": 2.2, "color": "#b91c1c"},
        ),
        row=3,
        col=1,
    )

    fig.update_yaxes(title_text="Price (EUR/kWh)", row=1, col=1)
    fig.update_yaxes(title_text="Cost (EUR)", row=2, col=1)
    fig.update_yaxes(title_text="Gap (EUR)", row=3, col=1)
    fig.update_xaxes(title_text="Date", row=3, col=1)
    fig.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.12)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.12)")

    fig.update_layout(
        height=920,
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        margin={"l": 50, "r": 20, "t": 80, "b": 40},
    )

    st.plotly_chart(fig, width="stretch")


def main() -> None:
    st.title("⚡ EsMS Results Explorer")
    st.caption(
        "Compare daily costs from deterministic perfect-foresight optimization and stochastic policy evaluation."
    )

    daily_costs = get_daily_costs()
    battery_specs = get_battery_specs()
    num_scenarios = get_num_scenarios()

    min_day = daily_costs["day"].min().date()
    max_day = daily_costs["day"].max().date()

    with st.sidebar:
        st.header("Configuration")
        selected_range = st.date_input(
            "Date range",
            value=(min_day, max_day),
            min_value=min_day,
            max_value=max_day,
        )

        if isinstance(selected_range, tuple) and len(selected_range) == 2:
            start_day, end_day = selected_range
            num_days_selected = (end_day - start_day).days + 1
            st.write(f"Days selected: {num_days_selected}")

        st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
        st.divider()
        st.caption("Static run metadata")

        st.subheader("Stochastic setup")
        st.write(f"Scenarios used: {num_scenarios if num_scenarios is not None else 'Unknown'}")

        st.subheader("BESS details")
        st.dataframe(pd.DataFrame(battery_specs), width="stretch", hide_index=True)

    if not isinstance(selected_range, tuple) or len(selected_range) != 2:
        st.info("Select a start and end date to view results.")
        return

    start_day, end_day = selected_range
    filtered = daily_costs[
        (daily_costs["day"].dt.date >= start_day)
        & (daily_costs["day"].dt.date <= end_day)
    ].copy()

    if filtered.empty:
        st.warning("No rows found for the selected date range.")
        return

    metric_1, metric_2, metric_3 = st.columns(3)
    metric_1.metric(
        "Deterministic total cost",
        f"€{filtered['deterministic_cost_eur'].sum():,.2f}",
    )
    metric_2.metric(
        "Stochastic total cost",
        f"€{filtered['stochastic_total_cost_eur'].sum():,.2f}",
    )
    metric_3.metric(
        "Cost gap",
        f"€{filtered['cost_gap_eur'].sum():,.2f}",
    )

    st.subheader("Daily trends and seasonal transitions")
    render_multi_panel_plot(filtered)

    st.subheader("Daily values")
    st.dataframe(
        filtered.rename(
            columns={
                "day": "Date",
                "season": "Season",
                "price_median_eur_per_kwh": "Median price (EUR/kWh)",
                "price_max_eur_per_kwh": "Max price (EUR/kWh)",
                "deterministic_cost_eur": "Deterministic cost (EUR)",
                "stochastic_total_cost_eur": "Stochastic cost (EUR)",
                "cost_gap_eur": "Gap (EUR)",
            }
        ),
        width="stretch",
        hide_index=True,
    )


if __name__ == "__main__":
    main()