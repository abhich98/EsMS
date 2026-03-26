"""
Stochastic Energy Optimization using two-stage stochastic programming.

Implements rolling-horizon stochastic optimization as described in STOC_PLAN.md.
First-stage decisions (day-ahead or arbitrary period ahead market) are scenario-independent.
Second-stage decisions (real-time balancing, battery operation) adapt to scenarios.
"""

import logging
from typing import List, Dict, Any, Optional, Sequence
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
        price_rt_scenarios: Optional[np.ndarray] = None,  # Real-time prices per scenario (n_scenarios, n_timesteps)
        export_price_rt_scenarios: Optional[np.ndarray] = None,  # Real-time export prices per scenario (n_scenarios, n_timesteps)
        scenario_probabilities: Optional[Sequence[float]] = None,
        timestep_hours: float = 1.0,
    ):
        """
        Initialize the stochastic optimizer.

        Args:
            batteries: List of Battery objects
            load_scenarios: Load demand scenarios (kW) - shape (n_scenarios, n_timesteps)
            pv_scenarios: PV generation scenarios (kW) - shape (n_scenarios, n_timesteps)
            price_forecast: Forecasted/Ahead electricity prices (EUR/kWh) for each timestep
            price_rt_scenarios: Real-time electricity prices per scenario (EUR/kWh) - shape (n_scenarios, n_timesteps)
            export_price_rt_scenarios: Real-time export prices per scenario (EUR/kWh) - shape (n_scenarios, n_timesteps)
            scenario_probabilities: Probability of each scenario (defaults to uniform)
            timestep_hours: Duration of each timestep in hours (default: 1.0)
            solver: Solver to use ('glpk', 'cbc', 'gurobi', etc.)
        """
        # Convert scenarios to numpy arrays
        self.load_scenarios = np.array(load_scenarios)
        self.pv_scenarios = np.array(pv_scenarios)

        # Day-ahead prices (known, scenario-independent)
        self.price_ahead = np.array(price_forecast)

        if price_rt_scenarios is None:
            self.price_rt_scenarios = np.ones_like(self.load_scenarios) * np.max(self.price_ahead)  # Set to very high price if not provided to discourage real-time purchases
        else:
            self.price_rt_scenarios = np.array(price_rt_scenarios)

        if export_price_rt_scenarios is None:
            self.export_price_rt_scenarios = np.zeros_like(self.price_rt_scenarios)  # Assuming no export price for simplicity
        else:
            self.export_price_rt_scenarios = np.array(export_price_rt_scenarios)
        
        # Validate scenario dimensions
        if self.load_scenarios.ndim != 2:
            raise ValueError("load_scenarios must be 2D array (n_scenarios, n_timesteps)")
        if self.pv_scenarios.shape != self.load_scenarios.shape:
            raise ValueError("pv_scenarios must have same shape as load_scenarios")
        if self.price_rt_scenarios.shape != self.load_scenarios.shape:
            raise ValueError("price_rt_scenarios must have same shape as load_scenarios")
        if self.export_price_rt_scenarios.shape != self.load_scenarios.shape:
            raise ValueError("export_price_rt_scenarios must have same shape as load_scenarios")
        
        self.n_scenarios, self.n_timesteps = self.load_scenarios.shape

        if len(self.price_ahead) != self.n_timesteps:
            raise ValueError("price_ahead must have same length as timesteps")
        
        # Set scenario probabilities (uniform if not provided)
        if scenario_probabilities is None:
            self.scenario_probabilities = np.ones(self.n_scenarios) / self.n_scenarios
        else:
            self.scenario_probabilities = np.array(scenario_probabilities)
            if len(self.scenario_probabilities) != self.n_scenarios:
                raise ValueError("scenario_probabilities must match number of scenarios")
            if not np.isclose(self.scenario_probabilities.sum(), 1.0, atol=1e-3):
                raise ValueError("scenario_probabilities must sum to 1.0, but sums to %.4f" % self.scenario_probabilities.sum())
        
        super().__init__(
            batteries=batteries,
            load_forecast=np.zeros(self.n_timesteps),  # Placeholder, actual load is scenario-dependent
            pv_forecast=np.zeros(self.n_timesteps),  # Placeholder, actual PV is scenario-dependent
            price_forecast=price_forecast,  # Use forecasted prices as base forecast
            export_price_forecast=None,
            timestep_hours=timestep_hours,
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

        def init_export_price_rt(model, s, t):
            return self.export_price_rt_scenarios[s, t]
        model.ExportPriceRT = Param(
            model.S, model.T,
            initialize=init_export_price_rt,
            doc="Real-time electricity export price (EUR/kWh)"
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
        model.grid_import_ahead = Var(
            model.T, 
            domain=NonNegativeReals, 
            doc="Forecasted/Ahead market purchase (kW)"
        )
        
        # Second-stage decisions (scenario-dependent)
        model.grid_import_rt = Var(
            model.S, model.T,
            domain=NonNegativeReals, 
            doc="Real-time market balancing (kW), set to be positive, that is real-time purchase."
        )

        model.grid_export_rt = Var(
            model.S, model.T,
            domain=NonNegativeReals,
            doc="Real-time market export (kW), set to be positive, negative values, that is real-time sales. This variable if for testing and to stablize optimization. The export price is set to zero for now."
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

        # Binary variable for grid import/export state (MILP constraint)
        model.v = Var(
            model.S, model.T,
            domain=Binary,
            doc="Grid import/export state binary (1=can import, 0=can export)",
        )

        # =================================================================
        # OBJECTIVE FUNCTION
        # =================================================================
        
        def objective_rule(model):
            # First-stage cost: ahead market
            ahead_cost = sum(
                model.PriceAhead[t] * model.grid_import_ahead[t] * model.dt
                for t in model.T
            )
            
            # Second-stage expected cost: real-time balancing
            rt_expected_cost = sum(
                model.Prob[s] * (
                    model.PriceRT[s, t] * model.grid_import_rt[s, t]  - 
                    model.ExportPriceRT[s, t] * model.grid_export_rt[s, t]\
                        ) * model.dt
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
                model.grid_import_ahead[t] + model.grid_import_rt[s, t] + model.PV[s, t] + total_discharge
                == model.Load[s, t] + model.grid_export_rt[s, t] + total_charge
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

        # Grid import/export limits
        def grid_import_rule(model, s, t):
            return model.grid_import_ahead[t] + model.grid_import_rt[s, t] <= 1e6 * model.v[s, t]  # Large constant to allow full range when v=1
        model.grid_import_limit = Constraint(
            model.S, model.T,
            rule=grid_import_rule,
            doc="Grid import limit constraint"
        )

        def grid_export_rule(model, s, t):
            return model.grid_export_rt[s, t] <= 1e6 * (1 - model.v[s, t])  # Allow export when v=0
        model.grid_export_limit = Constraint(
            model.S, model.T,
            rule=grid_export_rule,
            doc="Grid export limit constraint"
        )

        # Store model for later use
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
        grid_import_ahead = [value(model.grid_import_ahead[t]) for t in model.T]
        
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
            
            grid_import_rt = [value(model.grid_import_rt[s, t]) for t in model.T]
            grid_export_rt = [value(model.grid_export_rt[s, t]) for t in model.T]
            
            scenario_results.append({
                "scenario": s,
                "probability": self.scenario_probabilities[s],
                "batteries": battery_schedules,
                "grid_import_rt": grid_import_rt,
                "grid_export_rt": grid_export_rt,
            })
        
        # Compute expected (probability-weighted) second-stage variables
        expected_grid_import_rt = np.zeros(self.n_timesteps)
        expected_grid_export_rt = np.zeros(self.n_timesteps)
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
            expected_grid_import_rt += prob * np.array([value(model.grid_import_rt[s, t]) for t in model.T])
            expected_grid_export_rt += prob * np.array([value(model.grid_export_rt[s, t]) for t in model.T])

        
        # Calculate total cost
        total_cost = value(model.total_cost)

        results = {
            "scenarios": scenario_results,  # All scenario results
            "batteries": expected_batteries,  # Expected battery schedules
            "price_ahead": self.price_ahead.tolist(),
            "grid_import": (np.array(grid_import_ahead) + expected_grid_import_rt).tolist(),
            "grid_import_ahead": grid_import_ahead,  # First-stage decision
            "expected_grid_import_rt": expected_grid_import_rt.tolist(),
            "expected_grid_export_rt": expected_grid_export_rt.tolist(),
            "total_cost": total_cost,
            "solver_status": str(self.results.solver.termination_condition),
            "objective_value": total_cost,
            "n_scenarios": self.n_scenarios,
        }

        logger.info(f"Expected total cost: {total_cost:.2f} EUR")

        return results

    def results_to_dataframe(self, results = None) -> pd.DataFrame:
        """
        Convert results to a pandas DataFrame for easy analysis.

        Args:
            results: Results dictionary from solve() (defaults to self.results)
        Returns:
            DataFrame with timestep-indexed results, including expected values across scenarios.
        """
        if results is None:
            results = self._extract_results()

        n_timesteps = len(self.price_ahead)
        
        data: Dict[str, Any] = {
            "timestep": range(n_timesteps),
            "price_ahead": results["price_ahead"],
            "grid_import": results["grid_import"],
            "grid_import_ahead": results["grid_import_ahead"],
            "expected_grid_import_rt": results["expected_grid_import_rt"],
            "expected_grid_export_rt": results["expected_grid_export_rt"],
        }

        self._add_battery_dataframe_columns(data, results)

        df = pd.DataFrame(data)
        df = df.set_index("timestep")

        return df

    def _add_battery_dataframe_columns(
        self, data: Dict[str, Any], results: Dict[str, Any]
    ) -> None:
        """Add battery-specific columns using expected values."""
        for b in results["batteries"]:
            bat_id = b["id"]
            data[f"expected_{bat_id}_charge"] = b["charge"]
            data[f"expected_{bat_id}_discharge"] = b["discharge"]
            data[f"expected_{bat_id}_soc"] = b["soc"]

    def scenario_results_to_dataframe(self, results: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
        """Convert scenario-specific results to a DataFrame for detailed analysis."""
        if results is None:
            results = self._extract_results()

        scenario_dfs = []
        n_timesteps = len(self.price_ahead)

        for scenario_result in results["scenarios"]:
            s = scenario_result["scenario"]
            prob = scenario_result["probability"]
            df = pd.DataFrame({
                "timestep": range(n_timesteps),
                "grid_import_rt": scenario_result["grid_import_rt"],
                "grid_export_rt": scenario_result["grid_export_rt"],
            })
            for b in scenario_result["batteries"]:
                bat_id = b["id"]
                df[f"{bat_id}_charge"] = b["charge"]
                df[f"{bat_id}_discharge"] = b["discharge"]
                df[f"{bat_id}_soc"] = b["soc"]
            df["scenario"] = s
            df["probability"] = prob
            scenario_dfs.append(df)

        return pd.concat(scenario_dfs, ignore_index=True)
