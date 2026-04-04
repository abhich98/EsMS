from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ENV_VARS = (
    "DATA_DIR",
    "GENERATED_DATA_DIR",
    "EXAMPLES_DIR",
    "BESS_FILE",
    "GROUND_TRUTH_FILE",
    "STOC_OP_SCENARIOS",
)


def _require_makefile_env_vars() -> None:
    missing_in_env = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]

    if missing_in_env:
        error_message = (
            "Configuration error: required Makefile/environment variables are missing. "
            f"Missing in environment: {missing_in_env or 'none'}. "
            "Please make corrections in Makefile (ensure variables are exported) and run the app with `make app`."
        )
        raise RuntimeError(error_message)


_require_makefile_env_vars()

DATA_DIR = PROJECT_ROOT / os.environ["DATA_DIR"]
DATASET_PATH = PROJECT_ROOT / os.environ["GROUND_TRUTH_FILE"]
GENERATED_DIR = PROJECT_ROOT / os.environ["GENERATED_DATA_DIR"]
EXAMPLES_DIR = PROJECT_ROOT / os.environ["EXAMPLES_DIR"]
BATTERY_FILE_PATH = PROJECT_ROOT / os.environ["BESS_FILE"]

PERFECT_FORESIGHT_PATH = GENERATED_DIR / "perfect_foresight_optimization_year.csv"
SIMULATED_RT_PRICE_PATH = GENERATED_DIR / "simulated_rt_prices_year.csv"
STOCHASTIC_EVALUATION_PATH = GENERATED_DIR / f"stochastic_policy_evaluation_with_{os.environ['STOC_OP_SCENARIOS']}_scenarios_year.csv"

META_DATA_PATH = DATA_DIR / "meta_data.yml"


def read_battery_specs() -> list[dict]:
    with BATTERY_FILE_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def read_num_scenarios() -> int | None:
    value = os.environ["STOC_OP_SCENARIOS"]
    try:
        return int(value)
    except ValueError:
        return None


def _load_perfect_foresight_df() -> pd.DataFrame:
    df = pd.read_csv(PERFECT_FORESIGHT_PATH, parse_dates=["Date"])
    df["deterministic_cost_eur"] = df["price"] * df["grid_import"]
    return df


def _load_stochastic_evaluation_df() -> pd.DataFrame:
    evaluation_df = pd.read_csv(STOCHASTIC_EVALUATION_PATH, parse_dates=["Date"])
    rt_price_df = pd.read_csv(SIMULATED_RT_PRICE_PATH, parse_dates=["Date"])
    merged_df = evaluation_df.merge(rt_price_df, on="Date", how="left")
    merged_df["stochastic_ahead_cost_eur"] = (
        merged_df["price_ahead"] * merged_df["grid_import_ahead"]
    )
    merged_df["stochastic_rt_cost_eur"] = (
        merged_df["RT energy price (EUR/kWh)"] * merged_df["expected_grid_import_rt"]
    )
    merged_df["stochastic_total_cost_eur"] = (
        merged_df["stochastic_ahead_cost_eur"] + merged_df["stochastic_rt_cost_eur"]
    )
    return merged_df


def _build_day_to_season_map() -> dict[pd.Timestamp, str]:
    meta_data = yaml.safe_load(META_DATA_PATH.read_text(encoding="utf-8"))
    seasons = meta_data["seasons"]
    day_to_season: dict[pd.Timestamp, str] = {}

    for season in seasons:
        season_df = pd.read_excel(DATASET_PATH, sheet_name=season, usecols=["Date"])
        season_days = pd.to_datetime(season_df["Date"]).dt.normalize().unique()
        for day in season_days:
            day_to_season[pd.Timestamp(day)] = season

    return day_to_season


def load_daily_costs() -> pd.DataFrame:
    perfect_foresight_df = _load_perfect_foresight_df()
    stochastic_df = _load_stochastic_evaluation_df()

    daily_price_stats = (
        perfect_foresight_df.assign(day=perfect_foresight_df["Date"].dt.date)
        .groupby("day", as_index=False)["price"]
        .agg(price_median_eur_per_kwh="median", price_max_eur_per_kwh="max")
    )

    deterministic_daily = (
        perfect_foresight_df.assign(day=perfect_foresight_df["Date"].dt.date)
        .groupby("day", as_index=False)["deterministic_cost_eur"]
        .sum()
    )
    stochastic_daily = (
        stochastic_df.assign(day=stochastic_df["Date"].dt.date)
        .groupby("day", as_index=False)["stochastic_total_cost_eur"]
        .sum()
    )

    daily_costs = deterministic_daily.merge(stochastic_daily, on="day", how="inner")
    daily_costs = daily_costs.merge(daily_price_stats, on="day", how="left")
    daily_costs["day"] = pd.to_datetime(daily_costs["day"])
    daily_costs = daily_costs.sort_values("day").reset_index(drop=True)
    daily_costs["cost_gap_eur"] = (
        daily_costs["stochastic_total_cost_eur"] - daily_costs["deterministic_cost_eur"]
    )
    day_to_season = _build_day_to_season_map()
    daily_costs["season"] = daily_costs["day"].dt.normalize().map(day_to_season)
    return daily_costs