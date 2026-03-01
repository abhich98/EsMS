"""
Stochastic Energy Optimization using two-stage stochastic programming.

Implements rolling-horizon stochastic optimization as described in STOC_PLAN.md.
First-stage decisions (day-ahead or arbitrary period ahead market) are scenario-independent.
Second-stage decisions (real-time balancing, battery operation) adapt to scenarios.
"""

import logging
from typing import List, Dict, Any, Optional, Sequence
import numpy as np
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
    value,
)

from esms.models import Battery
from .base_optimizer import BaseEnergyOptimizer

logger = logging.getLogger(__name__)


class StochasticEnergyOptimizer(BaseEnergyOptimizer):
    """
    Two-stage stochastic energy optimizer.

    First-stage: Ahead market decisions (scenario-independent)
    Second-stage: Real-time balancing and battery operation (scenario-dependent)
    
    Minimizes expected total cost across scenarios.
    """

    def __init__(
        self,
        batteries: List[Battery],
        load_scenarios: np.ndarray,  # Shape: (n_scenarios, n_timesteps)
        pv_scenarios: np.ndarray,  # Shape: (n_scenarios, n_timesteps)
        price_forecast: Sequence[float],  # Forecasted prices (known)
        price_rt_scenarios: np.ndarray,  # Real-time prices per scenario (n_scenarios, n_timesteps)
        scenario_probabilities: Optional[Sequence[float]] = None,
        timestep_hours: float = 1.0,
        solver: str = "glpk",
    ):
        """
        Initialize the stochastic optimizer.

        Args:
            batteries: List of Battery objects
            load_scenarios: Load demand scenarios (kW) - shape (n_scenarios, n_timesteps)
            pv_scenarios: PV generation scenarios (kW) - shape (n_scenarios, n_timesteps)
            price_forecast: Forecasted/Ahead electricity prices (EUR/kWh) for each timestep
            price_rt_scenarios: Real-time electricity prices per scenario (EUR/kWh) - shape (n_scenarios, n_timesteps)
            scenario_probabilities: Probability of each scenario (defaults to uniform)
            timestep_hours: Duration of each timestep in hours (default: 1.0)
            solver: Solver to use ('glpk', 'cbc', 'gurobi', etc.)
        """
        # Convert scenarios to numpy arrays
        self.load_scenarios = np.array(load_scenarios)
        self.pv_scenarios = np.array(pv_scenarios)
        self.price_rt_scenarios = np.array(price_rt_scenarios)
        
        # Validate scenario dimensions
        if self.load_scenarios.ndim != 2:
            raise ValueError("load_scenarios must be 2D array (n_scenarios, n_timesteps)")
        if self.pv_scenarios.shape != self.load_scenarios.shape:
            raise ValueError("pv_scenarios must have same shape as load_scenarios")
        if self.price_rt_scenarios.shape != self.load_scenarios.shape:
            raise ValueError("price_rt_scenarios must have same shape as load_scenarios")
        
        self.n_scenarios, self.n_timesteps = self.load_scenarios.shape
        
        # Set scenario probabilities (uniform if not provided)
        if scenario_probabilities is None:
            self.scenario_probabilities = np.ones(self.n_scenarios) / self.n_scenarios
        else:
            self.scenario_probabilities = np.array(scenario_probabilities)
            if len(self.scenario_probabilities) != self.n_scenarios:
                raise ValueError("scenario_probabilities must match number of scenarios")
            if not np.isclose(self.scenario_probabilities.sum(), 1.0):
                raise ValueError("scenario_probabilities must sum to 1.0")
        
        # Day-ahead prices (known, scenario-independent)
        self.price_ahead = np.array(price_forecast)
        if len(self.price_ahead) != self.n_timesteps:
            raise ValueError("price_ahead must have same length as timesteps")
        
        # Use mean load and PV for base class initialization (for compatibility)
        load_forecast = self.load_scenarios.mean(axis=0)
        pv_forecast = self.pv_scenarios.mean(axis=0)
        
        super().__init__(
            batteries=batteries,
            load_forecast=load_forecast,
            pv_forecast=pv_forecast,
            price_forecast=price_forecast,  # Use forecasted prices as base forecast
            export_price_forecast=None,
            timestep_hours=timestep_hours,
            solver=solver,
        )

    def build_model(self) -> ConcreteModel:
        """
        Build the two-stage stochastic optimization model.

        First-stage: P_forecast (day-ahead/forecasted market purchases)
        Second-stage: P_RT, P_ch, P_dis, SOC (all scenario-dependent)

        Returns:
            Pyomo ConcreteModel
        """
        logger.info("Building stochastic optimization model...")
        logger.info(f"Scenarios: {self.n_scenarios}, Timesteps: {self.n_timesteps}, Batteries: {len(self.batteries)}")

        model = ConcreteModel()

        # Sets
        model.T = Set(initialize=range(self.n_timesteps), doc="Timesteps")
        model.S = Set(initialize=range(self.n_scenarios), doc="Scenarios")
        model.B = Set(initialize=range(len(self.batteries)), doc="Batteries")

        # Parameters - Period-ahead prices (known)
        model.PriceAhead = Param(
            model.T, 
            initialize={t: self.price_ahead[t] for t in model.T},
            doc="Forecasted/Ahead electricity price (EUR/kWh)"
        )
        
        # Parameters - Scenario-dependent
        def init_load(model, s, t):
            return self.load_scenarios[s, t]
        model.Load = Param(model.S, model.T, initialize=init_load, doc="Load demand (kW)")
        
        def init_pv(model, s, t):
            return self.pv_scenarios[s, t]
        model.PV = Param(model.S, model.T, initialize=init_pv, doc="PV generation (kW)")
        
        def init_price_rt(model, s, t):
            return self.price_rt_scenarios[s, t]
        model.PriceRT = Param(
            model.S, model.T, 
            initialize=init_price_rt,
            doc="Real-time electricity price (EUR/kWh)"
        )
        
        def init_prob(model, s):
            return self.scenario_probabilities[s]
        model.Prob = Param(model.S, initialize=init_prob, doc="Scenario probability")
        
        model.dt = Param(initialize=self.timestep_hours, doc="Timestep duration (hours)")

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

        # =================================================================
        # DECISION VARIABLES
        # =================================================================
        
        # First-stage decision (scenario-independent)
        model.P_ahead = Var(
            model.T, 
            domain=NonNegativeReals, 
            doc="Forecasted/Ahead market purchase (kW)"
        )
        
        # Second-stage decisions (scenario-dependent)
        model.P_RT = Var(
            model.S, model.T,
            domain=NonNegativeReals, 
            doc="Real-time market balancing (kW), set to be positive, negative values are not permitted here as they would represent selling back to the grid which is not considered in this model"
        )
        
        model.charge = Var(
            model.B, model.S, model.T, 
            domain=NonNegativeReals, 
            doc="Battery charge power (kW)"
        )
        
        model.discharge = Var(
            model.B, model.S, model.T, 
            domain=NonNegativeReals, 
            doc="Battery discharge power (kW)"
        )
        
        model.SOC = Var(
            model.B, model.S, model.T, 
            domain=NonNegativeReals, 
            doc="State of charge (kWh)"
        )

        # Binary variable for charge/discharge state (MILP constraint)
        model.u = Var(
            model.B, model.S, model.T,
            domain=Binary,
            doc="Charge state binary (1=can charge, 0=can discharge)",
        )

        # =================================================================
        # OBJECTIVE FUNCTION
        # =================================================================
        
        def objective_rule(model):
            # First-stage cost: ahead market
            ahead_cost = sum(
                model.PriceAhead[t] * model.P_ahead[t] * model.dt
                for t in model.T
            )
            
            # Second-stage expected cost: real-time balancing
            rt_expected_cost = sum(
                model.Prob[s] * model.PriceRT[s, t] * model.P_RT[s, t] * model.dt
                for s in model.S
                for t in model.T
            )
            
            return ahead_cost + rt_expected_cost

        model.total_cost = Objective(rule=objective_rule, sense=minimize)

        # =================================================================
        # CONSTRAINTS
        # =================================================================

        # (A) Power Balance - for each scenario and timestep
        def power_balance_rule(model, s, t):
            total_discharge = sum(model.discharge[b, s, t] for b in model.B)
            total_charge = sum(model.charge[b, s, t] for b in model.B)
            
            return (
                model.P_ahead[t] + model.P_RT[s, t] + model.PV[s, t] + total_discharge
                == model.Load[s, t] + total_charge
            )

        model.power_balance = Constraint(
            model.S, model.T, 
            rule=power_balance_rule,
            doc="Power balance constraint"
        )

        # (B) Battery Dynamics - scenario-dependent SOC evolution
        def soc_dynamics_rule(model, b, s, t):
            if t == 0:
                # Initial SOC (same for all scenarios)
                return model.SOC[b, s, t] == (
                    model.InitialSOC[b]
                    + model.ChargeEff[b] * model.charge[b, s, t] * model.dt
                    - model.discharge[b, s, t] * model.dt / model.DischargeEff[b]
                )
            else:
                # SOC evolution
                return model.SOC[b, s, t] == (
                    model.SOC[b, s, t - 1]
                    + model.ChargeEff[b] * model.charge[b, s, t] * model.dt
                    - model.discharge[b, s, t] * model.dt / model.DischargeEff[b]
                )

        model.soc_dynamics = Constraint(
            model.B, model.S, model.T,
            rule=soc_dynamics_rule,
            doc="Battery SOC dynamics"
        )

        # (C) Bounds

        # SOC bounds
        def soc_min_rule(model, b, s, t):
            return model.SOC[b, s, t] >= model.MinSOC[b]

        model.soc_min = Constraint(
            model.B, model.S, model.T,
            rule=soc_min_rule,
            doc="Minimum SOC constraint"
        )

        def soc_max_rule(model, b, s, t):
            return model.SOC[b, s, t] <= model.MaxSOC[b]

        model.soc_max = Constraint(
            model.B, model.S, model.T,
            rule=soc_max_rule,
            doc="Maximum SOC constraint"
        )

        # Power bounds
        def charge_limit_rule(model, b, s, t):
            return model.charge[b, s, t] <= model.MaxCharge[b] * model.u[b, s, t]

        model.charge_limit = Constraint(
            model.B, model.S, model.T,
            rule=charge_limit_rule,
            doc="Maximum charge power constraint"
        )

        def discharge_limit_rule(model, b, s, t):
            return model.discharge[b, s, t] <= model.MaxDischarge[b] * (1 - model.u[b, s, t])

        model.discharge_limit = Constraint(
            model.B, model.S, model.T,
            rule=discharge_limit_rule,
            doc="Maximum discharge power constraint"
        )

        self.model = model
        logger.info(
            f"Stochastic model built: {self.n_scenarios} scenarios, "
            f"{self.n_timesteps} timesteps, {len(self.batteries)} batteries"
        )

        return model

    def _extract_results(self) -> Dict[str, Any]:
        """
        Extract results from solved stochastic model.
        
        Returns first-stage decisions and scenario-averaged second-stage decisions.
        """
        model = self.model

        # First-stage decision (Ahead market)
        p_ahead = [value(model.P_ahead[t]) for t in model.T]
        
        # Second-stage decisions - extract for each scenario
        scenario_results = []
        for s in model.S:
            battery_schedules = []
            for b in model.B:
                schedule = {
                    "id": self.batteries[b].id,
                    "charge": [value(model.charge[b, s, t]) for t in model.T],
                    "discharge": [value(model.discharge[b, s, t]) for t in model.T],
                    "soc": [value(model.SOC[b, s, t]) for t in model.T],
                }
                battery_schedules.append(schedule)
            
            p_rt = [value(model.P_RT[s, t]) for t in model.T]
            
            scenario_results.append({
                "scenario": s,
                "probability": self.scenario_probabilities[s],
                "batteries": battery_schedules,
                "P_RT": p_rt,
            })
        
        # Compute expected (probability-weighted) second-stage variables
        expected_p_rt = np.zeros(self.n_timesteps)
        expected_batteries = []
        
        for b in model.B:
            expected_charge = np.zeros(self.n_timesteps)
            expected_discharge = np.zeros(self.n_timesteps)
            expected_soc = np.zeros(self.n_timesteps)
            
            for s in model.S:
                prob = self.scenario_probabilities[s]
                expected_charge += prob * np.array([value(model.charge[b, s, t]) for t in model.T])
                expected_discharge += prob * np.array([value(model.discharge[b, s, t]) for t in model.T])
                expected_soc += prob * np.array([value(model.SOC[b, s, t]) for t in model.T])
            
            expected_batteries.append({
                "id": self.batteries[b].id,
                "charge": expected_charge.tolist(),
                "discharge": expected_discharge.tolist(),
                "soc": expected_soc.tolist(),
            })
        
        for s in model.S:
            prob = self.scenario_probabilities[s]
            expected_p_rt += prob * np.array([value(model.P_RT[s, t]) for t in model.T])
        
        # Calculate grid import/export from ahead and expected real-time
        grid_import = []
        grid_export = []
        for t in model.T:
            net_grid = p_ahead[t] + expected_p_rt[t]
            if net_grid >= 0:
                grid_import.append(net_grid)
                grid_export.append(0.0)
            else:
                grid_import.append(0.0)
                grid_export.append(-net_grid)
        
        # Calculate total cost
        total_cost = value(model.total_cost)

        results = {
            "P_ahead": p_ahead,  # First-stage decision
            "scenarios": scenario_results,  # All scenario results
            "expected_P_RT": expected_p_rt.tolist(),
            "batteries": expected_batteries,  # Expected battery schedules
            "grid_import": grid_import,
            "grid_export": grid_export,
            "total_cost": total_cost,
            "solver_status": str(self.results.solver.termination_condition),
            "objective_value": total_cost,
            "n_scenarios": self.n_scenarios,
        }

        logger.info(f"Expected total cost: {total_cost:.2f} EUR")

        return results

    def _add_battery_dataframe_columns(
        self, data: Dict[str, Any], results: Dict[str, Any]
    ) -> None:
        """Add battery-specific columns using expected values."""
        # Add ahead purchase
        data["P_ahead"] = results["P_ahead"]
        data["expected_P_RT"] = results["expected_P_RT"]
        
        # Add expected battery schedules
        for b_result in results["batteries"]:
            b_id = b_result["id"]
            data[f"{b_id}_charge"] = b_result["charge"]
            data[f"{b_id}_discharge"] = b_result["discharge"]
            data[f"{b_id}_soc"] = b_result["soc"]
