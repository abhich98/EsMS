"""
Day-ahead energy optimization using Pyomo.

This module implements a Mixed-Integer Linear Programming (MILP) optimizer
for multi-battery energy management with PV generation, load, and grid connection.
"""

import logging
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
from pyomo.environ import (
    ConcreteModel,
    Set,
    Var,
    Param,
    Objective,
    Constraint,
    Binary,
    NonNegativeReals,
    minimize,
    SolverFactory,
    value,
)

from esms.models import Battery

logger = logging.getLogger(__name__)


class EnergyOptimizer:
    """
    Day-ahead energy optimizer using MILP.

    Optimizes battery charging/discharging and grid interaction
    to minimize total energy cost while satisfying load and constraints.
    """

    def __init__(
        self,
        batteries: List[Battery],
        load_forecast: np.ndarray,
        pv_forecast: np.ndarray,
        price_forecast: np.ndarray,
        export_price_forecast: Optional[np.ndarray] = None,
        timestep_hours: float = 1.0,
        solver: str = "glpk",
    ):
        """
        Initialize the optimizer.

        Args:
            batteries: List of Battery objects
            load_forecast: Load demand forecast (kW) for each timestep
            pv_forecast: PV generation forecast (kW) for each timestep
            price_forecast: Electricity price forecast (EUR/kWh) for each timestep
            export_price_forecast: Electricity export price forecast (EUR/kWh) for each timestep
            timestep_hours: Duration of each timestep in hours (default: 1.0)
            solver: Solver to use ('glpk', 'cbc', 'gurobi', etc.)
        """
        self.batteries = batteries
        self.load_forecast = np.array(load_forecast)
        self.pv_forecast = np.array(pv_forecast)
        self.price_forecast = np.array(price_forecast)
        self.export_price_forecast = (
            np.array(export_price_forecast)
            if export_price_forecast is not None
            else np.zeros_like(price_forecast)
        )
        self.timestep_hours = timestep_hours
        self.solver_name = solver

        # Validate inputs
        self._validate_inputs()

        # Model components
        self.model: Optional[ConcreteModel] = None
        self.results = None

    def _validate_inputs(self):
        """Validate input dimensions and values."""
        n_timesteps = len(self.load_forecast)

        if len(self.pv_forecast) != n_timesteps:
            raise ValueError("pv_forecast must have same length as load_forecast")

        if len(self.price_forecast) != n_timesteps:
            raise ValueError("price_forecast must have same length as load_forecast")

        if len(self.export_price_forecast) != n_timesteps:
            raise ValueError(
                "export_price_forecast must have same length as load_forecast"
            )

        if n_timesteps == 0:
            raise ValueError("Forecasts must have at least one timestep")

        if len(self.batteries) == 0:
            raise ValueError("At least one battery must be provided")

        if self.timestep_hours <= 0:
            raise ValueError("timestep_hours must be positive")

    def build_model(self) -> ConcreteModel:
        """
        Build the Pyomo optimization model.

        Returns:
            Pyomo ConcreteModel
        """
        logger.info("Building optimization model...")

        model = ConcreteModel()

        # Sets
        n_timesteps = len(self.pv_forecast)
        model.T = Set(initialize=range(n_timesteps), doc="Timesteps")
        model.B = Set(initialize=range(len(self.batteries)), doc="Batteries")

        # Parameters
        model.PV = Param(model.T, initialize={t: self.pv_forecast[t] for t in model.T})
        model.Load = Param(
            model.T, initialize={t: self.load_forecast[t] for t in model.T}
        )
        model.Price = Param(
            model.T, initialize={t: self.price_forecast[t] for t in model.T}
        )
        model.ExportPrice = Param(
            model.T, initialize={t: self.export_price_forecast[t] for t in model.T}
        )
        model.dt = Param(initialize=self.timestep_hours)

        # Battery parameters
        def init_capacity(model, b):
            return self.batteries[b].capacity

        model.Capacity = Param(model.B, initialize=init_capacity)

        def init_max_charge(model, b):
            return self.batteries[b].max_charge

        model.MaxCharge = Param(model.B, initialize=init_max_charge)

        def init_max_discharge(model, b):
            return self.batteries[b].max_discharge

        model.MaxDischarge = Param(model.B, initialize=init_max_discharge)

        def init_charge_eff(model, b):
            return self.batteries[b].charge_efficiency

        model.ChargeEff = Param(model.B, initialize=init_charge_eff)

        def init_discharge_eff(model, b):
            return self.batteries[b].discharge_efficiency

        model.DischargeEff = Param(model.B, initialize=init_discharge_eff)

        def init_initial_soc(model, b):
            return self.batteries[b].initial_soc

        model.InitialSOC = Param(model.B, initialize=init_initial_soc)

        def init_min_soc(model, b):
            return self.batteries[b].min_soc

        model.MinSOC = Param(model.B, initialize=init_min_soc)

        def init_max_soc(model, b):
            return self.batteries[b].max_soc

        model.MaxSOC = Param(model.B, initialize=init_max_soc)

        # Decision Variables
        model.charge = Var(
            model.B, model.T, domain=NonNegativeReals, doc="Battery charge power (kW)"
        )
        model.discharge = Var(
            model.B,
            model.T,
            domain=NonNegativeReals,
            doc="Battery discharge power (kW)",
        )
        model.soc = Var(
            model.B, model.T, domain=NonNegativeReals, doc="State of charge (kWh)"
        )
        model.grid_import = Var(
            model.T, domain=NonNegativeReals, doc="Grid import power (kW)"
        )
        model.grid_export = Var(
            model.T, domain=NonNegativeReals, doc="Grid export power (kW)"
        )

        # Binary variable for charge/discharge state (MILP constraint)
        model.u = Var(
            model.B,
            model.T,
            domain=Binary,
            doc="Charge state binary (1=can charge, 0=can discharge)",
        )

        # Objective: Minimize total cost
        def objective_rule(model):
            return sum(
                (
                    model.grid_import[t] * model.Price[t]
                    - model.grid_export[t] * model.ExportPrice[t]
                )
                * model.dt
                for t in model.T
            )

        model.total_cost = Objective(rule=objective_rule, sense=minimize)

        # Constraints

        # 1. Energy balance at each timestep
        def energy_balance_rule(model, t):
            total_discharge = sum(model.discharge[b, t] for b in model.B)
            total_charge = sum(model.charge[b, t] for b in model.B)
            return (
                model.Load[t]
                == model.PV[t]
                + total_discharge
                + model.grid_import[t]
                - total_charge
                - model.grid_export[t]
            )

        model.energy_balance = Constraint(model.T, rule=energy_balance_rule)

        # 2. SOC dynamics for each battery
        def soc_dynamics_rule(model, b, t):
            if t == 0:
                # Initial SOC
                return model.soc[b, t] == (
                    model.InitialSOC[b]
                    + model.ChargeEff[b] * model.charge[b, t] * model.dt
                    - model.discharge[b, t] * model.dt / model.DischargeEff[b]
                )
            else:
                # SOC evolution
                return model.soc[b, t] == (
                    model.soc[b, t - 1]
                    + model.ChargeEff[b] * model.charge[b, t] * model.dt
                    - model.discharge[b, t] * model.dt / model.DischargeEff[b]
                )

        model.soc_dynamics = Constraint(model.B, model.T, rule=soc_dynamics_rule)

        # 3. SOC limits
        def soc_min_rule(model, b, t):
            return model.soc[b, t] >= model.MinSOC[b]

        model.soc_min = Constraint(model.B, model.T, rule=soc_min_rule)

        def soc_max_rule(model, b, t):
            return model.soc[b, t] <= model.MaxSOC[b]

        model.soc_max = Constraint(model.B, model.T, rule=soc_max_rule)

        # 4. Power limits with binary constraint (no simultaneous charge/discharge)
        def charge_limit_rule(model, b, t):
            return model.charge[b, t] <= model.MaxCharge[b] * model.u[b, t]

        model.charge_limit = Constraint(model.B, model.T, rule=charge_limit_rule)

        def discharge_limit_rule(model, b, t):
            return model.discharge[b, t] <= model.MaxDischarge[b] * (1 - model.u[b, t])

        model.discharge_limit = Constraint(model.B, model.T, rule=discharge_limit_rule)

        self.model = model
        logger.info(
            f"Model built with {len(model.T)} timesteps and {len(model.B)} batteries"
        )

        return model

    def solve(self, verbose: bool = False) -> Dict[str, Any]:
        """
        Solve the optimization problem.

        Args:
            verbose: Whether to display solver output

        Returns:
            Dictionary containing the optimization results
        """
        if self.model is None:
            self.build_model()

        logger.info(f"Solving with {self.solver_name}...")

        solver = SolverFactory(self.solver_name)

        if not solver.available():
            raise RuntimeError(f"Solver '{self.solver_name}' is not available")

        self.results = solver.solve(self.model, tee=verbose)

        # Check solver status
        from pyomo.opt import SolverStatus, TerminationCondition

        if self.results.solver.status == SolverStatus.ok:
            if (
                self.results.solver.termination_condition
                == TerminationCondition.optimal
            ):
                logger.info("Optimal solution found")
                return self._extract_results()
            elif (
                self.results.solver.termination_condition
                == TerminationCondition.feasible
            ):
                logger.warning("Feasible solution found (not proven optimal)")
                return self._extract_results()

        logger.error(f"Solver failed: {self.results.solver.status}")
        logger.error(
            f"Termination condition: {self.results.solver.termination_condition}"
        )

        raise RuntimeError(
            f"Optimization failed: {self.results.solver.status}, "
            f"{self.results.solver.termination_condition}"
        )

    def _extract_results(self) -> Dict[str, Any]:
        """Extract results from solved model."""
        model = self.model

        # Extract battery schedules
        battery_schedules = []
        for b in model.B:
            schedule = {
                "id": self.batteries[b].id,
                "charge": [value(model.charge[b, t]) for t in model.T],
                "discharge": [value(model.discharge[b, t]) for t in model.T],
                "soc": [value(model.soc[b, t]) for t in model.T],
                "binary_state": [value(model.u[b, t]) for t in model.T],
            }
            battery_schedules.append(schedule)

        # Extract grid schedule
        grid_import = [value(model.grid_import[t]) for t in model.T]
        grid_export = [value(model.grid_export[t]) for t in model.T]

        # Calculate total cost
        total_cost = value(model.total_cost)

        results = {
            "batteries": battery_schedules,
            "grid_import": grid_import,
            "grid_export": grid_export,
            "total_cost": total_cost,
            "solver_status": str(self.results.solver.termination_condition),
            "objective_value": total_cost,
        }

        logger.info(f"Total cost: {total_cost:.2f} EUR")

        return results

    def results_to_dataframe(self, results: Dict[str, Any]) -> pd.DataFrame:
        """
        Convert results to a pandas DataFrame for easy analysis.

        Args:
            results: Results dictionary from solve()

        Returns:
            DataFrame with timestep-indexed results
        """
        n_timesteps = len(self.pv_forecast)

        data = {
            "timestep": range(n_timesteps),
            "pv": self.pv_forecast,
            "load": self.load_forecast,
            "price": self.price_forecast,
            "export_price": self.export_price_forecast,
            "grid_import": results["grid_import"],
            "grid_export": results["grid_export"],
        }

        # Add battery data
        for b_result in results["batteries"]:
            b_id = b_result["id"]
            data[f"{b_id}_charge"] = b_result["charge"]
            data[f"{b_id}_discharge"] = b_result["discharge"]
            data[f"{b_id}_soc"] = b_result["soc"]

        df = pd.DataFrame(data)
        df.set_index("timestep", inplace=True)

        return df
