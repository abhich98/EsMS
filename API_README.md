REST API for day-ahead or long-term energy optimization with multi-battery systems, PV generation, and grid interaction.

## 🚀 Quick Start

### Using Docker (Recommended)

```bash
# Build and start the API
docker-compose up -d

# Check health
curl http://localhost:8000/health

# View API documentation
open http://localhost:8000/docs
```

### Local Development

```bash
# Install dependencies
uv sync

# Run API server
uvicorn esms.api.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 📡 API Usage

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/optimize` | POST | Run energy optimization |
| `/docs` | GET | Interactive API documentation |

### Optimization Request

**Required Files:**
1. `batteries.json` - Battery configuration
2. `forecasts.csv` - Time series forecasts
3. `config.json` - Solver configuration (optional)

#### Example Request

```bash
curl -X POST http://localhost:8000/optimize \
  -F "batteries_json=@batteries.json" \
  -F "forecasts_csv=@forecasts.csv" \
  -F "config_json=@config.json" \
  -o schedule.csv
```

#### Using Python

```python
import requests

files = {
    'batteries_json': open('batteries.json', 'rb'),
    'forecasts_csv': open('forecasts.csv', 'rb'),
    'config_json': open('config.json', 'rb')
}

response = requests.post('http://localhost:8000/optimize', files=files)

with open('schedule.csv', 'wb') as f:
    f.write(response.content)
```

---

## 📄 Input File Formats

### 1. batteries.json

Array of battery configurations:

```json
[
  {
    "id": "battery_1",
    "capacity": 100.0,
    "max_charge": 50.0,
    "max_discharge": 50.0,
    "charge_efficiency": 0.95,
    "discharge_efficiency": 0.95,
    "initial_soc": 50.0,
    "min_soc": 10.0,
    "max_soc": 100.0
  }
]
```

**Fields:**
- `id` (string): Unique battery identifier
- `capacity` (float): Total energy capacity in kWh
- `max_charge` (float): Maximum charging power in kW
- `max_discharge` (float): Maximum discharging power in kW
- `charge_efficiency` (float): Charging efficiency (0-1)
- `discharge_efficiency` (float): Discharging efficiency (0-1)
- `initial_soc` (float): Initial state of charge in kWh
- `min_soc` (float, optional): Minimum SOC in kWh (default: 0)
- `max_soc` (float, optional): Maximum SOC in kWh (default: capacity)

### 2. forecasts.csv

Time series with required columns:

```csv
timestep,pv,load,price,export_price
0,0.0,30.0,0.10,0.08
1,5.0,32.0,0.11,0.08
...
```

**Columns:**
- `pv` (float): PV generation forecast in kW
- `load` (float): Load demand forecast in kW
- `price` (float): Electricity import price in EUR/kWh
- `export_price` (float, optional): Export price in EUR/kWh

### 3. config.json (Optional)

Solver configuration:

```json
{
  "solver": "scip",
  "timestep_hours": 1.0,
  "optimization_type": "lp",
  "verbose": false
}
```

**Fields:**
- `solver` (string): Solver name - `scip` (default), `glpk`, `cbc`
- `timestep_hours` (float): Duration of each timestep in hours (default: 1.0)
- `optimization_type` (string): `lp` (fast, recommended) or `milp` (slower, more accurate)
- `verbose` (bool): Show solver output (default: false)

---

## 📤 Output Format

Returns CSV with optimization schedule:

```csv
timestep,pv,load,price,export_price,battery_1_battery_power,battery_1_soc,grid_import,grid_export
0,0.0,30.0,0.10,0.08,25.0,75.0,5.0,0.0
1,5.0,32.0,0.11,0.08,-10.0,65.0,37.0,0.0
...
```

**Columns:**
- Input data: `pv`, `load`, `price`, `export_price`
- Per battery: `{battery_id}_battery_power`, `{battery_id}_soc`
  - `battery_power`: Positive = charging, Negative = discharging (kW)
  - `soc`: State of charge (kWh)
- Grid: `grid_import`, `grid_export` (kW)

---

## 🐳 Docker Details

### Included Solvers

- **SCIP 9.2.0** - High-performance academic/non-commercial solver (recommended)
- **GLPK**

### Build Locally

```bash
docker build -t esms-optimizer .
```

### Run Container

```bash
docker run -d \
  -p 8000:8000 \
  --name esms-api \
  esms-optimizer
```

---

## 🧪 Testing

### Example Files

Sample input files are in `examples/api/`:

```bash
cd examples/api
./test_api.sh
```

### Manual Test

```bash
# 1. Health check
curl http://localhost:8000/health

# 2. Run optimization
curl -X POST http://localhost:8000/optimize \
  -F "batteries_json=@examples/api/batteries.json" \
  -F "forecasts_csv=@examples/api/forecasts.csv" \
  -F "config_json=@examples/api/config.json" \
  -o schedule.csv

# 3. View results
head -20 schedule.csv
```
