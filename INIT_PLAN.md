# ⚡ Primary Project Plan: Day-Ahead Energy Optimizer as a REST Service

## 🎯 Goal

Build a **day-ahead energy management API** for a small multi-asset plant:

* PV generation
* Battery storage (one or more batteries)
* Grid connection
* Electricity market prices

The system:

1. Receives time series data via REST API
2. Runs optimization with Pyomo
3. Returns optimal battery schedule + grid schedule

This looks very close to a real EMS (Energy Management System).

---

# 🏗 System Architecture

```
Client → REST API → Optimizer (Pyomo) → Schedule Output
```

Use:

* FastAPI → REST API
* Pyomo → optimization
* Pandas → time series handling
* Dataclasses / Pydantic → clean data models
* pytest → tests
* Logging → structured logs

---

# 📊 Real Data Source

Use one of:

* Open Power System Data (prices + load)
* Kaggle solar generation dataset
* ENTSO-E export (CSV download)

You only need:

* PV generation forecast
* Load forecast
* Electricity price forecast

Even 24–48 hours is enough.

---

# 🔋 Optimization Problem (Pyomo)

## Decision Variables

For each timestep t and battery b:

* Battery charge power (per battery)
* Battery discharge power (per battery)
* Binary variable for charge/discharge state (per battery)
* Grid import
* Grid export
* State of charge (SOC) (per battery)

---

## Objective

Minimize total cost:

$$
\sum_t (gridImport_t \cdot price_t - gridExport_t \cdot price_t)
$$

Or if you want more advanced:

* Include battery degradation cost
* Add peak power penalty

---

## Constraints

1. Energy balance:
  $$
  Load = PV + \sum_b Discharge_{b,t} + GridImport - \sum_b Charge_{b,t} - GridExport
  $$

2. SOC dynamics (per battery b):
   
   $$
   SOC_{b,t+1} = SOC_{b,t} + \eta_{c,b} \cdot Charge_{b,t} - Discharge_{b,t} / \eta_{d,b}
   $$

3. SOC limits (per battery):
   $$
   SOC_{min,b} \leq SOC_{b,t} \leq SOC_{max,b}
   $$

4. Power limits (per battery):
   $$
   Charge_{b,t} \leq MaxCharge_b \cdot u_{b,t}
   $$
   $$
   Discharge_{b,t} \leq MaxDischarge_b \cdot (1 - u_{b,t})
   $$

5. **No simultaneous charge and discharge (MILP - core feature):**
   * Binary variable $u_{b,t} \in \{0,1\}$ for each battery
   * $u_{b,t} = 1$ → can charge, cannot discharge
   * $u_{b,t} = 0$ → can discharge, cannot charge

---

# 🌐 REST API Design

## Endpoint 1: Optimize

POST `/optimize`

Input (JSON):

```json
{
  "pv_forecast": [...],
  "load_forecast": [...],
  "price_forecast": [...],
  "batteries": [
    {
      "id": "battery_1",
      "capacity": 100,
      "max_charge": 50,
      "max_discharge": 50,
      "charge_efficiency": 0.95,
      "discharge_efficiency": 0.95,
      "initial_soc": 50
    },
    {
      "id": "battery_2",
      "capacity": 150,
      "max_charge": 75,
      "max_discharge": 75,
      "charge_efficiency": 0.93,
      "discharge_efficiency": 0.93,
      "initial_soc": 75
    }
  ]
}
```

Output:

```json
{
  "schedule": {
    "batteries": [
      {
        "id": "battery_1",
        "charge": [...],
        "discharge": [...],
        "soc": [...]
      },
      {
        "id": "battery_2",
        "charge": [...],
        "discharge": [...],
        "soc": [...]
      }
    ],
    "grid_import": [...],
    "grid_export": [...]
  },
  "total_cost": 123.45,
  "solver_status": "optimal"
}
```

---

# 🧠 Why This Is Strong

This directly demonstrates:

* “Decision-making”
* “Schedule/setpoint generation”
* “Time series”
* “Optimization (LP/MILP, Pyomo)”
* “REST APIs”
* “Clean architecture”
* “Structured software design”

It basically mirrors a real EMS backend.

---

# 🔥 Optional Advanced Add-ons (If You Have Time)

### 1️⃣ Dockerize it

Shows CI-ready deployment mindset.

### 2️⃣ Add Unit Tests

* Test SOC limits
* Test feasibility
* Test optimizer convergence
* Test multi-battery coordination
* Test simultaneous charge/discharge prevention

### 3️⃣ Add Logging

Log solver status, infeasibility warnings, per-battery decisions.

### 4️⃣ Battery Degradation Cost

Add wear cost per charge/discharge cycle to objective function.

---

# 📂 Suggested Repo Structure

```
energy_api/
│
├── api/
│   └── routes.py
│
├── models/
│   └── battery.py
│
├── optimization/
│   └── optimizer.py
│
├── services/
│   └── scheduler_service.py
│
├── tests/
│
├── main.py
└── Dockerfile
```

---

# 🏆 How It Looks to a Hiring Manager

They will see:

* You understand energy systems
* You can formulate optimization mathematically
* You can build backend systems
* You think in architecture
* You can connect modeling + engineering

That is exactly what such a job requires.

---

If you want, I can:

* Write the exact Pyomo formulation template
* Suggest solver setup (GLPK vs CBC)
* Help you design the cleanest architecture version
* Or suggest a version that also includes simple control theory elements