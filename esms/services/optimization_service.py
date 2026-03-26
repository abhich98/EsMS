"""Optimization service for orchestrating optimizer calls."""

import logging
from typing import List, Dict, Any
import pandas as pd

from esms.models import Battery
from esms.optimization import EnergyOptimizer
from esms.api.schemas import SolverConfig

logger = logging.getLogger(__name__)


class OptimizationService:
    """Service for running energy optimization."""

    @staticmethod
    def optimize(
        batteries: List[Battery],
        forecasts: Dict[str, Any],
        config: SolverConfig,
    ) -> pd.DataFrame:
        """
        Run energy optimization.

        Args:
            batteries: List of Battery objects
            forecasts: Dictionary with pv, load, price, export_price arrays
            config: Solver configuration

        Returns:
            DataFrame with optimization results

        Raises:
            RuntimeError: If optimization fails
        """
        logger.info(
            f"Starting optimization with {config.solver}"
        )
        logger.info(f"Number of batteries: {len(batteries)}")
        logger.info(f"Number of timesteps: {len(forecasts['pv'])}")

        try:
            # Initialize optimizer
            optimizer = EnergyOptimizer(
                batteries=batteries,
                load_forecast=forecasts["load"],
                pv_forecast=forecasts["pv"],
                price_forecast=forecasts["price"],
                export_price_forecast=forecasts["export_price"],
                timestep_hours=config.timestep_hours,
            )

            # Run optimization
            results = optimizer.solve(solver_name=config.solver, verbose=config.verbose, **config.opts)

            # Convert to DataFrame
            results_df = optimizer.results_to_dataframe(results)

            logger.info(f"Optimization completed successfully")
            logger.info(f"Total cost: {results['total_cost']:.2f} EUR")
            logger.info(f"Solver status: {results['solver_status']}")

            return results_df

        except Exception as e:
            logger.error(f"Optimization failed: {e}")
            raise RuntimeError(f"Optimization failed: {e}")
