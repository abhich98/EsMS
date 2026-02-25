"""
Energy optimization using Pyomo.

This class implements a Linear Programming (LP) optimizer
for multi-battery energy management with PV generation, load, and grid connection.
The LP formulation models net battery power without explicit binary variables,
using a geometric mean efficiency to approximate charge/discharge losses while maintaining linearity.
"""

import logging
import math
from typing import List, Dict, Any, Optional, Sequence
from pyomo.environ import (
    ConcreteModel,
    Set,
    Var,
    Param,
    Objective,
    Constraint,
    NonNegativeReals,
    Reals,
    minimize,
    value,
)

from esms.models import Battery
from .base_optimizer import BaseEnergyOptimizer

logger = logging.getLogger(__name__)


class EnergyOptimizerLP(BaseEnergyOptimizer):
    """
    Energy optimizer using LP.

    Optimizes battery net power and grid interaction to minimize total
    energy cost while satisfying load and constraints.
    """

    def __init__(
        self,
        batteries: List[Battery],
        load_forecast,
        pv_forecast,
        price_forecast,
        export_price_forecast: Optional[Sequence[float]] = None,
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
        super().__init__(
            batteries=batteries,
            load_forecast=load_forecast,
            pv_forecast=pv_forecast,
            price_forecast=price_forecast,
            export_price_forecast=export_price_forecast,
            timestep_hours=timestep_hours,
            solver=solver,
        )

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
        model.Load = Param(
            model.T, initialize={t: self.load_forecast[t] for t in model.T}
        )
        model.PV = Param(model.T, initialize={t: self.pv_forecast[t] for t in model.T})
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
        # Net battery power (kW): positive = charging, negative = discharging
        model.battery_power = Var(
            model.B, model.T, domain=Reals, doc="Battery net power (kW)"
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
        # battery_power > 0 means charging (consumes energy), < 0 means discharging (supplies energy)
        def energy_balance_rule(model, t):
            total_battery_power = sum(model.battery_power[b, t] for b in model.B)
            return (
                model.Load[t]
                == model.PV[t]
                - total_battery_power
                + model.grid_import[t]
                - model.grid_export[t]
            )

        model.energy_balance = Constraint(model.T, rule=energy_balance_rule)

        # 2. SOC dynamics for each battery
        # Use geometric mean efficiency for a symmetric LP formulation
        def soc_dynamics_rule(model, b, t):
            eta = math.sqrt(model.ChargeEff[b] * model.DischargeEff[b])
            if t == 0:
                # Initial SOC
                return model.soc[b, t] == (
                    model.InitialSOC[b] + eta * model.battery_power[b, t] * model.dt
                )
            else:
                # SOC evolution
                return model.soc[b, t] == (
                    model.soc[b, t - 1] + eta * model.battery_power[b, t] * model.dt
                )

        model.soc_dynamics = Constraint(model.B, model.T, rule=soc_dynamics_rule)

        # 3. SOC limits
        def soc_min_rule(model, b, t):
            return model.soc[b, t] >= model.MinSOC[b]

        model.soc_min = Constraint(model.B, model.T, rule=soc_min_rule)

        def soc_max_rule(model, b, t):
            return model.soc[b, t] <= model.MaxSOC[b]

        model.soc_max = Constraint(model.B, model.T, rule=soc_max_rule)

        # 4. Power limits (single net power variable)
        def charge_limit_rule(model, b, t):
            return model.battery_power[b, t] <= model.MaxCharge[b]

        model.charge_limit = Constraint(model.B, model.T, rule=charge_limit_rule)

        def discharge_limit_rule(model, b, t):
            return model.battery_power[b, t] >= -model.MaxDischarge[b]

        model.discharge_limit = Constraint(model.B, model.T, rule=discharge_limit_rule)

        self.model = model
        logger.info(
            f"Model built with {len(model.T)} timesteps and {len(model.B)} batteries"
        )

        return model

    def _extract_results(self) -> Dict[str, Any]:
        """Extract results from solved model."""
        model = self.model

        # Extract battery schedules
        battery_schedules = []
        for b in model.B:
            schedule = {
                "id": self.batteries[b].id,
                "battery_power": [value(model.battery_power[b, t]) for t in model.T],
                "soc": [value(model.soc[b, t]) for t in model.T],
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

    def _add_battery_dataframe_columns(
        self, data: Dict[str, Any], results: Dict[str, Any]
    ) -> None:
        """Add battery-specific columns for the LP model."""
        for b_result in results["batteries"]:
            b_id = b_result["id"]
            data[f"{b_id}_battery_power"] = b_result["battery_power"]
            data[f"{b_id}_soc"] = b_result["soc"]
