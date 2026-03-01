# 🔋 EsMS - Energy Storage Management System

Implementation of an energy management system (EMS) for optimizing the operation of a multi-asset entity with PV generation, battery storage, and grid interaction. 

While, this project provides a Dockerized REST API for accessing the optimization service (example for day-ahead scheduling, read [API docs](./API_README.md)), the main objective is to test different solvers and compare **deterministic optimization** vs **scenario-based stochastic optimization**.

there is a docker image and REST API for accessing the optimization service (eg: day-ahed scheduling), the main idea is to test solvers and compare **determinisitic optimization** vs **scenario-based stochastic optimization**.

##  Data Sources:

- Tayenne, L., Bruno, R., Pedro, F., Luis, G., & Zita, V. (2025). Dataset for daily energy management: Renewable generation, consumption, and storage (v1.0) [Data set]. Zenodo. https://doi.org/10.5281/zenodo.14918474


> The authors acquired PV generation and demand data at the GECAD research center from building N (GECAD) located at ISEP in Porto/Portugal. Additionally, the energy price data (€/MWh) were obtained from the OMIE (Operator of the Iberian Energy Market), reflecting conditions in Portugal.

.

> Real battery charging and discharging data were collected from the BMS of three battery energy storage systems (BESS) with 2.4 kWh of capacity each. These BESS are located at the GECAD research center, the building N at ISEP in Porto/Portugal.


To find more about the data used in this project, please refer to the [Data](./data/README.md) document.



## 🔧 Development

### Project Structure

```
esms/
├── api/                # FastAPI application
│   ├── main.py        # App initialization
│   ├── routes.py      # Endpoints
│   └── schemas.py     # Pydantic models
├── services/          # Business logic
│   ├── io_service.py
│   └── optimization_service.py
├── optimization/      # Optimization engines
│   ├── base_optimizer.py
│   ├── optimizer.py       # MILP
│   └── optimizer_LP.py    # LP
└── models/            # Data models
    └── battery.py
```

---

## 📊 Optimization Types/Methods

### LP (Linear Programming)
- **Speed**: Very fast ⚡
- **Use case**: Long-term optimization (weeks, months, years)
- **Trade-off**: Uses geometric mean efficiency

### MILP (Mixed-Integer Linear Programming)
- **Use case**: Short-term optimization (hours, days, use glpk), long-term optimization is also possible (months or longer with fast solvers like SCIP)
- **Benefit**: Exact efficiency modeling, prevents simultaneous charge/discharge