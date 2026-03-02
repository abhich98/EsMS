"""
Example usage of EsMS Energy Optimizer for day-ahead optimization with multiple batteries.
The script reads forecast data from the `data/` directory (e.g., `data/Dataset.xlsx`).
User can either pick a specific day or a random day is chosen for optimization.
"""

import logging
import sys
import numpy as np
import pandas as pd
import json
import datetime

from esms.models import Battery
from esms.optimization import EnergyOptimizer
from esms.utils import get_available_pyomo_solvers

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Run example optimization with data from 2023 dataset in the `data/` directory."""

    day_idx = int(sys.argv[1]) if len(sys.argv) > 1 else np.random.randint(0, 365)
    battery_file = sys.argv[2] if len(sys.argv) > 2 else "scripts/sample_BESS.json"

    forecast_df = pd.read_excel('data/Dataset.xlsx', sheet_name='2023 data', usecols='A:F', nrows=8762)
    with open(battery_file, 'r') as f:
        batteries = json.load(f)

    # get date from date index
    date = forecast_df.iloc[day_idx * 24]['Date'].date()
    num_days = 1
    forecast_df_day = forecast_df.iloc[day_idx * 24:(day_idx + num_days) * 24]
    logger.info("=" * 60)
    logger.info("EsMS Energy Optimizer - Deterministic Optimization")
    logger.info(f"Selected day: {date} (index {day_idx})")
    logger.info(f"Number of batteries in BESS: {len(batteries)}")
    logger.info("=" * 60)
    
    # Define batteries
    batteries = [Battery(**bat) for bat in batteries]
    logger.info(f"Batteries configured:")
    for battery in batteries:
        logger.info(f"{battery}")
    
    # Create forecasts
    pv_forecast, load_forecast, price_forecast = forecast_df_day['PV generation (kW)'].values, forecast_df_day['Consumption (kW)'].values, forecast_df_day['Energy price (EUR/kWh)'].values
    timestep_hours = 1.0  # It is hourly data

    logger.info(f"Forecasts:")
    logger.info(f"PV range: {pv_forecast.min():.1f} - {pv_forecast.max():.1f} kW")
    logger.info(f"Load range: {load_forecast.min():.1f} - {load_forecast.max():.1f} kW")
    logger.info(f"Price range: {price_forecast.min():.3f} - {price_forecast.max():.3f} EUR/kWh")
    
    available_solvers = get_available_pyomo_solvers()
    solver_to_use = available_solvers[0] if len(available_solvers) else "glpk"
    logger.info(f"Using solver: {solver_to_use}")
    solver_args = {}
    if solver_to_use == "scip":
        solver_args = {"solver_io": "nl"}
    
    optimizer = EnergyOptimizer(
        batteries=batteries,
        load_forecast=load_forecast,
        pv_forecast=pv_forecast,
        price_forecast=price_forecast,
        timestep_hours=timestep_hours,
        solver=solver_to_use,
    )
    
    # Solve
    logger.info("=" * 60)
    logger.info("Starting optimization...")
    logger.info("=" * 60)
    start_time = datetime.datetime.now()
    
    try:
        results = optimizer.solve(verbose=True, **solver_args)

        end_time = datetime.datetime.now()
        elapsed_time = end_time - start_time
        logger.info(f"Optimization completed in {elapsed_time}")
        logger.info("=" * 60)
        logger.info("RESULTS")
        logger.info("=" * 60)
        logger.info(f"Total cost: {results['total_cost']:.2f} EUR")
        # Results without PV and management for comparison
        logger.info(f"Potential Total Cost without PV and management: {sum(l * p * timestep_hours for l, p in zip(load_forecast, price_forecast)):.2f} EUR")

        # Show battery schedules summary
        logger.info("Battery schedules:")
        for bat_result in results["batteries"]:
            if 'charge' in bat_result:
                total_charge = sum(bat_result["charge"])
                total_discharge = sum(bat_result["discharge"])
            else:
                total_charge = np.nan
                total_discharge = np.nan
    
            final_soc = bat_result["soc"][-1]
            
            logger.info(f"   {bat_result['id']}:")
            logger.info(f"    Total charge: {total_charge * optimizer.timestep_hours:.1f} kWh")
            logger.info(f"    Total discharge: {total_discharge * optimizer.timestep_hours:.1f} kWh")
            logger.info(f"    Final SOC: {final_soc:.1f} kWh")
        
        # Grid interaction
        total_import = sum(results["grid_import"])
        total_export = sum(results["grid_export"])
        logger.info(f"Grid interaction:")
        logger.info(f"   Total import: {total_import * optimizer.timestep_hours:.1f} kWh")
        logger.info(f"   Total export: {total_export * optimizer.timestep_hours:.1f} kWh")
        
        # Convert to DataFrame for detailed analysis
        df = optimizer.results_to_dataframe(results)
        logger.info(f"First 5 timesteps:")
        logger.info(df.head(5))

        # Battery SOC
        logger.info(f"Battery SOC over time:")
        logger.info(df[[col for col in df.columns if 'battery' in col and 'soc' in col]])

        # Grid import/export
        logger.info(f"Grid import/export over time:")
        logger.info(df[['grid_import', 'grid_export']])
        
        logger.info("=" * 60)
        logger.info("Optimization completed successfully!")
        logger.info("=" * 60)
        
        return results, df
        
    except Exception as e:
        logger.error(f"Optimization failed: {e}")
        raise


if __name__ == "__main__":
    results, df = main()
    df.to_csv("day_ahead_optimization_results.csv", index=False)
