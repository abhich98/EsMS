# Optimization Formulations

This document describes the mathematical models implemented in:

- [esms/optimization/optimizer.py](../esms/optimization/optimizer.py) (deterministic MILP)
- [esms/optimization/stochastic_optimizer.py](../esms/optimization/stochastic_optimizer.py) (two-stage stochastic MILP)

All powers are in kW, energy in kWh, prices in EUR/kWh, and $\Delta t$ in hours.

## 1) Deterministic MILP (`optimizer.py`)

### Sets

- $t \in \mathcal{T} = \{0,\dots,T-1\}$ timesteps
- $b \in \mathcal{B} = \{0,\dots,B-1\}$ batteries

### Parameters

- $L_t$: load demand
- $PV_t$: PV generation
- $\pi_t^{\text{imp}}$: import price
- $\pi_t^{\text{exp}}$: export price
- $\Delta t$: timestep duration
- $\overline{P}^{\text{ch}}_b$: max charge power
- $\overline{P}^{\text{dis}}_b$: max discharge power
- $\eta_b^{\text{ch}}$: charge efficiency
- $\eta_b^{\text{dis}}$: discharge efficiency
- $SOC_b^{0}$: initial SOC
- $\underline{SOC}_b,\overline{SOC}_b$: SOC bounds
- $M=10^6$: big-M constant used in implementation for grid import/export exclusivity

### Decision variables

- $P_{b,t}^{\text{ch}} \ge 0$: battery charging power
- $P_{b,t}^{\text{dis}} \ge 0$: battery discharging power
- $SOC_{b,t} \ge 0$: battery state of charge
- $G_t^{\text{imp}} \ge 0$: grid import
- $G_t^{\text{exp}} \ge 0$: grid export
- $u_{b,t} \in \{0,1\}$: battery mode (1 = charge enabled, 0 = discharge enabled)
- $v_t \in \{0,1\}$: grid mode (1 = import enabled, 0 = export enabled)

The grid variable $G_t$ is split into import/export with mutual exclusivity enforced by $v_t$ to support cases where import price is different from export price.

### Objective

Minimize total energy cost:

$$
\min \sum_{t\in\mathcal{T}} \left( \pi_t^{\text{imp}} G_t^{\text{imp}} - \pi_t^{\text{exp}} G_t^{\text{exp}} \right)\Delta t
$$

### Constraints

#### (a) Power balance (each timestep)

$$
L_t = PV_t + \sum_{b\in\mathcal{B}} P_{b,t}^{\text{dis}} + G_t^{\text{imp}} - \sum_{b\in\mathcal{B}} P_{b,t}^{\text{ch}} - G_t^{\text{exp}}, \quad \forall t
$$

#### (b) SOC dynamics

For $t=0$:

$$
SOC_{b,0} = SOC_b^{0} + \eta_b^{\text{ch}} P_{b,0}^{\text{ch}}\Delta t - \frac{P_{b,0}^{\text{dis}}\Delta t}{\eta_b^{\text{dis}}}, \quad \forall b
$$

For $t>0$:

$$
SOC_{b,t} = SOC_{b,t-1} + \eta_b^{\text{ch}} P_{b,t}^{\text{ch}}\Delta t - \frac{P_{b,t}^{\text{dis}}\Delta t}{\eta_b^{\text{dis}}}, \quad \forall b,t>0
$$

#### (c) SOC bounds

$$
\underline{SOC}_b \le SOC_{b,t} \le \overline{SOC}_b, \quad \forall b,t
$$

#### (d) Charge/discharge exclusivity and power limits

$$
P_{b,t}^{\text{ch}} \le \overline{P}^{\text{ch}}_b\,u_{b,t}, \quad \forall b,t
$$

$$
P_{b,t}^{\text{dis}} \le \overline{P}^{\text{dis}}_b\,(1-u_{b,t}), \quad \forall b,t
$$

This enforces no simultaneous charging and discharging per battery and timestep.

### (e) Grid import/export mutual exclusivity
$$G_t^{\text{imp}} \le M v_t, \quad \forall t
$$ 

$$
G_{t}^{\text{exp}} \le M\,(1-v_t), \quad \forall t
$$

This prevents simultaneous import and export in each timestep (up to big-M logic).

## 2) Two-stage stochastic MILP (`stochastic_optimizer.py`)

In general, industries use stochastic optimization to handle uncertainty in load, PV, and prices. They typically buy in the day-ahead market (first-stage decision) and then adjust in real-time (second-stage recourse) based on actual conditions. To obtain the policy (decide the power to commit in the day-ahead market) for a given day, we solve a two-stage stochastic MILP with the following structure, we keep first-stage decisions scenario-independent and adapt second-stage recourse per scenario.

### Sets

- $t \in \mathcal{T}$ timesteps
- $s \in \mathcal{S}$ scenarios
- $b \in \mathcal{B}$ batteries

### Parameters

- $L_{s,t}$: scenario load
- $PV_{s,t}$: scenario PV
- $\pi_t^{\text{ahead}}$: ahead-market import price (scenario-independent)
- $\pi_{s,t}^{\text{rt}}$: real-time import price
- $\pi_{s,t}^{\text{rt,exp}}$: real-time export price
- $p_s$: scenario probability, $\sum_s p_s = 1$
- Battery parameters: $\overline{P}^{\text{ch}}_b, \overline{P}^{\text{dis}}_b, \eta_b^{\text{ch}}, \eta_b^{\text{dis}}, SOC_b^0, \underline{SOC}_b, \overline{SOC}_b$
- $\Delta t$: timestep duration
- $M=10^6$ (big-M constant used in implementation)

If export RT price is not provided, implementation sets $\pi_{s,t}^{\text{rt,exp}}=0$.

### Decision variables

#### First-stage (scenario-independent)

- $G_t^{\text{ahead}} \ge 0$: ahead-market import commitment. We solve for this which becomes our policy decision.

#### Second-stage (scenario-dependent)

- $G_{s,t}^{\text{rt,imp}} \ge 0$: real-time import
- $G_{s,t}^{\text{rt,exp}} \ge 0$: real-time export
- $P_{b,s,t}^{\text{ch}} \ge 0$: battery charge
- $P_{b,s,t}^{\text{dis}} \ge 0$: battery discharge
- $SOC_{b,s,t} \ge 0$: battery SOC
- $u_{b,s,t}\in\{0,1\}$: battery mode binary
- $v_{s,t}\in\{0,1\}$: grid mode binary (1 import mode, 0 export mode)

### Objective (expected total cost)

$$
\min \sum_{t\in\mathcal{T}} \pi_t^{\text{ahead}} G_t^{\text{ahead}}\Delta t
+ \sum_{s\in\mathcal{S}} p_s \sum_{t\in\mathcal{T}}\left( \pi_{s,t}^{\text{rt}} G_{s,t}^{\text{rt,imp}} - \pi_{s,t}^{\text{rt,exp}} G_{s,t}^{\text{rt,exp}} \right)\Delta t
$$

### Constraints

#### (a) Scenario-wise power balance

$$
G_t^{\text{ahead}} + G_{s,t}^{\text{rt,imp}} + PV_{s,t} + \sum_{b\in\mathcal{B}} P_{b,s,t}^{\text{dis}}
= L_{s,t} + G_{s,t}^{\text{rt,exp}} + \sum_{b\in\mathcal{B}} P_{b,s,t}^{\text{ch}},
\quad \forall s,t
$$

#### (b) Scenario-wise SOC dynamics

For $t=0$:

$$
SOC_{b,s,0} = SOC_b^0 + \eta_b^{\text{ch}} P_{b,s,0}^{\text{ch}}\Delta t - \frac{P_{b,s,0}^{\text{dis}}\Delta t}{\eta_b^{\text{dis}}},
\quad \forall b,s
$$

For $t>0$:

$$
SOC_{b,s,t} = SOC_{b,s,t-1} + \eta_b^{\text{ch}} P_{b,s,t}^{\text{ch}}\Delta t - \frac{P_{b,s,t}^{\text{dis}}\Delta t}{\eta_b^{\text{dis}}},
\quad \forall b,s,t>0
$$

#### (c) SOC bounds

$$
\underline{SOC}_b \le SOC_{b,s,t} \le \overline{SOC}_b, \quad \forall b,s,t
$$

#### (d) Battery charge/discharge exclusivity

$$
P_{b,s,t}^{\text{ch}} \le \overline{P}^{\text{ch}}_b\,u_{b,s,t}, \quad \forall b,s,t
$$

$$
P_{b,s,t}^{\text{dis}} \le \overline{P}^{\text{dis}}_b\,(1-u_{b,s,t}), \quad \forall b,s,t
$$

#### (e) Grid import/export mutual exclusivity (big-M)

$$
G_t^{\text{ahead}} + G_{s,t}^{\text{rt,imp}} \le M\,v_{s,t}, \quad \forall s,t
$$

$$
G_{s,t}^{\text{rt,exp}} \le M\,(1-v_{s,t}), \quad \forall s,t
$$

This prevents simultaneous import and export in each scenario/timestep (up to big-M logic).


## Notes on implementation mapping

- Deterministic model output columns correspond to `charge`, `discharge`, `soc`, `grid_import`, `grid_export`.
- Stochastic model stores full scenario results plus expected (probability-weighted) schedules.
- Both formulations are MILP due to binary variables ($u$ and $v$ for battery and grid respectively).
