"""Run daily stochastic optimization on each day from the dataset."""

from copy import deepcopy
import json
import yaml
import logging
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from esms.models import Battery
from esms.optimization import StochasticEnergyOptimizer


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = PROJECT_ROOT / "data" / "Dataset.xlsx"
ORACLE_DATA_FILE = (
    PROJECT_ROOT / "data" / "generated" / "perfect_foresight_optimization_year.csv"
)
ORACLE_DF = pd.read_csv(ORACLE_DATA_FILE)
ORACLE_DF["Date"] = pd.to_datetime(ORACLE_DF["Date"])
ORACLE_DF.set_index("Date", inplace=True)

DEFAULT_BATTERY_FILE = PROJECT_ROOT / "examples" / "sample_BESS.json"
DEFAULT_BATTERY_SPECS = json.load(open(DEFAULT_BATTERY_FILE, "r"))

meta_data = yaml.safe_load(open(PROJECT_ROOT / "data" / "meta_data.yml", "r"))
SEASONS = meta_data["seasons"]
NUM_SCENARIOS = meta_data["num_scenarios"][0]

SOLVER = "scip"
SOLVER_ARGS = {"solver_io": "nl"}


def get_battery_specs(
    desired_date: pd.Timestamp
) -> List[Dict[str, Any]]:
    """Get battery specs for a given date. Update the initial state of charge (SOC) based on the oracle perfect foresight data"""

    previous_date = desired_date - pd.Timedelta(days=1)
    previous_datetime = pd.Timestamp(
        previous_date.year, previous_date.month, previous_date.day, 23
    )  # 11 PM of previous day]

    battery_specs = deepcopy(DEFAULT_BATTERY_SPECS)

    for bat in battery_specs:
        bat_id = bat["id"]
        default_init_soc = bat["initial_soc"]
        bat["initial_soc"] = ORACLE_DF[f"{bat_id}_soc"].get(
            previous_datetime, default_init_soc
        )

    return battery_specs


def build_batteries(battery_specs: List[Dict[str, Any]]) -> List[Battery]:
    """Create fresh `Battery` objects for each optimization run."""
    return [Battery(**spec) for spec in battery_specs]


def load_scenario_inputs(
    num_scenarios: int, scenarios_df: pd.DataFrame
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Load scenario matrices and normalized probabilities for a season."""

    load_scenarios = (
        scenarios_df["Consumption (kW)"]
        .to_numpy(dtype=float)
        .reshape(num_scenarios, 24)
    )
    pv_scenarios = (
        scenarios_df["PV generation (kW)"]
        .to_numpy(dtype=float)
        .reshape(num_scenarios, 24)
    )
    price_scenarios = (
        scenarios_df["Energy price (EUR/kWh)"]
        .to_numpy(dtype=float)
        .reshape(num_scenarios, 24)
    )

    probabilities = scenarios_df["Probability (%)"].to_numpy(dtype=float)[::24]

    return load_scenarios, pv_scenarios, price_scenarios, probabilities


def solve_day_stochastic(
    day_df: pd.DataFrame,
    num_scenarios: int,
    scenarios_df: pd.DataFrame,
    battery_specs: List[Dict[str, Any]],
) -> pd.DataFrame:

    day_df = day_df.reset_index(drop=True)
    price_da = day_df["Energy price (EUR/kWh)"].to_numpy(dtype=float)
    load_scenarios, pv_scenarios, price_rt_scenarios, scenarios_probs = (
        load_scenario_inputs(num_scenarios, scenarios_df)
    )

    stochastic_optimizer = StochasticEnergyOptimizer(
        batteries=build_batteries(battery_specs),
        load_scenarios=load_scenarios,
        pv_scenarios=pv_scenarios,
        price_forecast=price_da,
        price_rt_scenarios=price_rt_scenarios,
        scenario_probabilities=scenarios_probs,
        timestep_hours=1.0,
        solver=SOLVER,
    )

    stochastic_results = stochastic_optimizer.solve(verbose=False, **SOLVER_ARGS)
    results_df = stochastic_optimizer.results_to_dataframe(stochastic_results)
    results_df.index = pd.to_datetime(day_df["Date"].to_numpy())
    results_df.index.name = "Date"

    return results_df


def main() -> None:
    """Run daily stochastic optimization and evaluation."""

    season_dfs = {
        season: pd.read_excel(DATA_FILE, sheet_name=season) for season in SEASONS
    }
    season_scenarios_dfs = {
        season: pd.read_excel(
            DATA_FILE, sheet_name=f"Set of {NUM_SCENARIOS} {season.lower()} scenarios"
        )
        for season in SEASONS
    }

    logger.info("=" * 60)
    logger.info("EsMS Stochastic Optimization Runner")
    logger.info("Scenarios: %s | Solver: %s", NUM_SCENARIOS, SOLVER)
    logger.info("=" * 60)

    stochastic_results = []
    for season, s_df in season_dfs.items():
        logger.info("Processing season: %s", season)
        num_days = len(s_df) // 24

        season_ouput = Parallel(n_jobs=-1)(
            delayed(solve_day_stochastic)(
                day_df=s_df.iloc[day_index * 24 : (day_index + 1) * 24],
                num_scenarios=NUM_SCENARIOS,
                scenarios_df=season_scenarios_dfs[season],
                battery_specs=get_battery_specs(
                    desired_date=s_df["Date"].iloc[day_index * 24].date(),
                ),
            )
            for day_index in range(num_days)
        )

        season_output_df = pd.concat(season_ouput)
        logger.info(f"Generated output has {len(season_output_df) // 24} days, expected {num_days} days. ")
        stochastic_results.append(season_output_df)

    stochastic_results_df = pd.concat(stochastic_results, axis=0)
    stochastic_results_df.sort_index(inplace=True)
    output_file = PROJECT_ROOT / "data" / "generated" / f"stochastic_optimization_with_{NUM_SCENARIOS}_scenarios_year.csv"
    stochastic_results_df.to_csv(output_file)
    logger.info("Results saved to %s", output_file)


if __name__ == "__main__":
    main()
