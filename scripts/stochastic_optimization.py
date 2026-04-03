"""Run daily stochastic optimization on each day from the dataset."""

from copy import deepcopy
import json
import yaml
import logging
import argparse
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from esms.optimization import StochasticEnergyOptimizer
from esms.utils import simulate_rt_prices

from deterministic_optimization import build_batteries

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
META_DATA = yaml.safe_load(open(PROJECT_ROOT / "data" / "meta_data.yml", "r"))


def load_scenario_inputs(
    scenarios_df: pd.DataFrame, num_scenarios: int, noise_params: Dict[str, Any]
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

    price_df = pd.DataFrame(
        {"price": scenarios_df["Energy price (EUR/kWh)"].to_numpy(dtype=float)}
    )
    price_rt_scenarios = simulate_rt_prices(
        price_df,
        volatility=np.random.uniform(*noise_params["volatility_range"]),
        jump_prob=noise_params["jump_prob"],
        jump_magnitude=np.random.uniform(*noise_params["jump_magnitude_range"]),
    )["rt_price"]
    price_rt_scenarios = price_rt_scenarios.to_numpy(dtype=float).reshape(
        num_scenarios, 24
    )

    probabilities = scenarios_df["Probability (%)"].to_numpy(dtype=float)[::24]

    return load_scenarios, pv_scenarios, price_rt_scenarios, probabilities


def solve_day_stochastic(
    day_df: pd.DataFrame,
    num_scenarios: int,
    scenarios_df: pd.DataFrame,
    battery_specs: List[Dict[str, Any]],
    noise_params: Dict[str, Any],
    solver: str = "scip",
) -> pd.DataFrame:

    # Suppress optimizer logs in each parallel worker
    logging.getLogger("esms.optimization.stochastic_optimizer").setLevel(
        logging.WARNING
    )
    logging.getLogger("esms.optimization.base_optimizer").setLevel(logging.WARNING)
    logging.getLogger("pyomo.core").setLevel(logging.ERROR)

    price_da = day_df["Energy price (EUR/kWh)"].to_numpy(dtype=float)
    load_scenarios, pv_scenarios, price_rt_scenarios, scenarios_probs = (
        load_scenario_inputs(scenarios_df, num_scenarios, noise_params)
    )

    solver_args = {}
    if solver == "scip":
        solver_args = {"solver_io": "nl"}

    stochastic_optimizer = StochasticEnergyOptimizer(
        batteries=build_batteries(battery_specs),
        load_scenarios=load_scenarios,
        pv_scenarios=pv_scenarios,
        price_forecast=price_da,
        price_rt_scenarios=price_rt_scenarios,
        scenario_probabilities=scenarios_probs,
        timestep_hours=1.0,
    )

    stochastic_results = stochastic_optimizer.solve(
        solver_name=solver, verbose=False, **solver_args
    )
    results_df = stochastic_optimizer.results_to_dataframe(stochastic_results)
    results_df.index = pd.to_datetime(day_df["Date"].to_numpy())
    results_df.index.name = "Date"

    return results_df


def main() -> None:
    """Run daily stochastic optimization and evaluation."""

    parser = argparse.ArgumentParser(
        description="Run stochastic optimization for selected seasons."
    )
    parser.add_argument(
        "--data_file",
        type=str,
        required=True,
        help="Path to the dataset Excel file",
    )
    parser.add_argument(
        "--battery_file",
        type=str,
        required=True,
        help="Path to the battery configuration JSON file",
    )
    parser.add_argument(
        "--noise_params_file",
        type=str,
        required=True,
        help="Path to the noise parameters YAML file",
    )
    parser.add_argument(
        "--seasons",
        type=str,
        nargs="+",
        default=["all"],
        help="Seasons to process ('all' for all seasons, or list specific seasons like 'Winter Spring')",
    )
    parser.add_argument(
        "--num_scenarios",
        type=int,
        required=True,
        help="Number of scenarios to use for optimization",
    )
    parser.add_argument(
        "--output_file",
        type=str,
        default="stochastic_optimization_results.csv",
        help="Path to save optimization results CSV",
    )
    parser.add_argument(
        "--solver",
        type=str,
        default="scip",
        help="Pyomo solver to use (e.g., 'glpk', 'scip')",
    )

    args = parser.parse_args()

    # Load battery specs
    logger.info("Loading battery configuration from %s", args.battery_file)
    with open(args.battery_file, "r") as f:
        def_battery_specs = json.load(f)

    # Load noise parameters
    logger.info("Loading noise parameters from %s", args.noise_params_file)
    noise_params = yaml.safe_load(open(args.noise_params_file))

    # Load metadata to get all seasons if "all" is specified
    all_seasons = META_DATA["seasons"]

    # Determine which seasons to process
    if "all" in args.seasons:
        seasons_to_process = all_seasons
    else:
        seasons_to_process = args.seasons

    logger.info("=" * 60)
    logger.info("EsMS Stochastic Optimization Runner")
    logger.info(
        "Seasons: %s | Scenarios: %s | Solver: %s",
        seasons_to_process,
        args.num_scenarios,
        args.solver,
    )
    logger.info("=" * 60)

    # Load data for all seasons
    logger.info("Loading data from %s", args.data_file)
    season_dfs = {
        season: pd.read_excel(args.data_file, sheet_name=season)
        for season in seasons_to_process
    }
    season_scenarios_dfs = {
        season: pd.read_excel(
            args.data_file,
            sheet_name=f"Set of {args.num_scenarios} {season.lower()} scenarios",
        )
        for season in seasons_to_process
    }

    stochastic_results = []
    for season, s_df in season_dfs.items():
        logger.info("Processing season: %s", season)
        num_days = len(s_df) // 24

        season_output = Parallel(n_jobs=-1)(
            delayed(solve_day_stochastic)(
                day_df=s_df.iloc[day_index * 24 : (day_index + 1) * 24],
                num_scenarios=args.num_scenarios,
                scenarios_df=season_scenarios_dfs[season],
                battery_specs=deepcopy(def_battery_specs),
                noise_params=noise_params,
                solver=args.solver,
            )
            for day_index in range(num_days)
        )

        season_output_df = pd.concat(season_output)
        logger.info(
            f"Generated output has {len(season_output_df) // 24} days, expected {num_days} days."
        )
        stochastic_results.append(season_output_df)

    stochastic_results_df = pd.concat(stochastic_results, axis=0)
    stochastic_results_df.sort_index(inplace=True)

    stochastic_results_df.to_csv(args.output_file)
    logger.info("Results saved to %s", args.output_file)


if __name__ == "__main__":
    main()
