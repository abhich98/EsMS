"""Run daily stochastic optimization on each day from the dataset."""

from copy import deepcopy
import json
import logging
import argparse
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from esms.optimization import StochasticEnergyOptimizer

from deterministic_optimization import build_batteries

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def evaluate_stochastic_policy_day(
    day_df: pd.DataFrame,
    battery_specs: List[Dict[str, Any]],
    solver: str = "scip",
) -> pd.DataFrame:
    # Suppress optimizer logs in each parallel worker
    logging.getLogger("esms.optimization.stochastic_optimizer").setLevel(
        logging.WARNING
    )
    logging.getLogger("esms.optimization.base_optimizer").setLevel(logging.WARNING)
    logging.getLogger("pyomo.core").setLevel(logging.ERROR)

    solver_args = {}
    if solver == "scip":
        solver_args = {"solver_io": "nl"}

    # Prepare inputs
    ahead_energy_prices = day_df["Energy price (EUR/kWh)"].to_numpy(dtype=float)

    rt_load = day_df["Consumption (kW)"].to_numpy(dtype=float).reshape(1, 24)
    rt_pv = day_df["PV generation (kW)"].to_numpy(dtype=float).reshape(1, 24)
    rt_energy_prices = (
        day_df["RT energy price (EUR/kWh)"].to_numpy(dtype=float).reshape(1, 24)
    )

    stochastic_optimizer = StochasticEnergyOptimizer(
        batteries=build_batteries(battery_specs),
        load_scenarios=rt_load,
        pv_scenarios=rt_pv,
        price_forecast=ahead_energy_prices,
        price_rt_scenarios=rt_energy_prices,
        scenario_probabilities=np.array([1.0]),  # Single scenario for evaluation
        timestep_hours=1.0,
    )

    # Use the policy's ahead grid import as input to the model for evaluation
    grid_import_ahead = day_df["grid_import_ahead"].to_numpy(dtype=float)
    grid_import_ahead = np.clip(
        grid_import_ahead, 0, None
    )  # Mainly to clip close to zero negative values
    stochastic_optimizer.build_model(
        evaluate=True, grid_import_ahead_values=grid_import_ahead
    )
    try:
        eval_results = stochastic_optimizer.solve(
            solver_name=solver, verbose=False, **solver_args
        )
    except Exception as e:
        logger.error(
            "Error solving stochastic optimization for day %s: %s",
            day_df["Date"].iloc[0].date(),
            e,
        )
        return None

    results_df = stochastic_optimizer.results_to_dataframe(eval_results)
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
        "--policy_file",
        type=str,
        required=True,
        help="Path to the policy CSV file generated from deterministic optimization",
    )
    parser.add_argument(
        "--rt_price_file",
        type=str,
        required=True,
        help="Path to the simulated RT price CSV file",
    )
    parser.add_argument(
        "--start_day_index", type=int, help="Index of the first day to optimize (0-364)"
    )
    parser.add_argument(
        "--num_days",
        type=int,
        default=1,
        required=False,
        help="Number of consecutive days to optimize",
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

    data_df = pd.read_excel(
        args.data_file, sheet_name="2023 data", usecols="A:F", nrows=8762
    )

    # Load RT price data
    logger.info("Loading RT price data from %s", args.rt_price_file)
    rt_price_df = pd.read_csv(args.rt_price_file)
    rt_price_df["Date"] = pd.to_datetime(rt_price_df["Date"])

    # Load policy data
    logger.info("Loading policy data from %s", args.policy_file)
    policy_df = pd.read_csv(args.policy_file)
    policy_df["Date"] = pd.to_datetime(policy_df["Date"])

    day_idx = args.start_day_index
    num_days = args.num_days
    relevant_data_df = data_df.iloc[day_idx * 24 : (day_idx + num_days) * 24]
    relevant_data_df = relevant_data_df.merge(rt_price_df, on="Date", how="left")
    relevant_data_df = relevant_data_df.merge(policy_df, on="Date", how="left")

    logger.info(relevant_data_df.info())

    # Load battery specs
    logger.info("Loading battery configuration from %s", args.battery_file)
    with open(args.battery_file, "r") as f:
        def_battery_specs = json.load(f)

    # get date from date index
    date = relevant_data_df.iloc[0]["Date"].date()

    logger.info("=" * 60)
    logger.info("EsMS Stochastic Optimization Evaluation")
    logger.info(f"Selected day: {date} (index {day_idx})")
    logger.info(f"Number of days to evaluate: {num_days}")
    logger.info(f"Number of batteries in BESS: {len(def_battery_specs)}")
    logger.info("=" * 60)

    evaluation_results = Parallel(n_jobs=-1)(
        delayed(evaluate_stochastic_policy_day)(
            day_df=relevant_data_df.iloc[i_d * 24 : (i_d + 1) * 24],
            battery_specs=deepcopy(def_battery_specs),
            solver=args.solver,
        )
        for i_d in range(num_days)
    )

    evaluation_results = [res for res in evaluation_results if res is not None]
    evaluation_results_df = pd.concat(evaluation_results, axis=0)
    logger.info(
        f"Generated output has {len(evaluation_results_df) // 24} days, expected {num_days} days."
    )

    evaluation_results_df.sort_index(inplace=True)

    evaluation_results_df.to_csv(args.output_file)
    logger.info("Results saved to %s", args.output_file)


if __name__ == "__main__":
    main()
