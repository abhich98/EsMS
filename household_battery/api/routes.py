from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from re import A

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from household_battery.api import VERSION as API_VERSION

from .errors import DataValidationError
from .models import DeterministicRequest, StochasticRequest
from .service import run_dayahead_deterministic, run_dayahead_stochastic

ROOT_DIR = Path(__file__).resolve().parents[2]
CHAMPION_POLICY_PATH = ROOT_DIR / "artifacts" / "champion.json"

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/dayahead/deterministic")
def dayahead_deterministic(req: DeterministicRequest):
    try:
        df = run_dayahead_deterministic(
            batteries_specs=[b.model_dump() for b in req.batteries],
            forecasts_csv_text=req.forecasts_csv,
            timestep_hours=req.timestep_hours,
        )
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d %H:%M:%S")
        return JSONResponse(content=df.to_dict(orient="list"))
    except DataValidationError as e:
        # Data/format validation errors should be returned to the client
        logger.error("Deterministic scheduling validation error: %s", str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Log internally at info level without stack trace leakage to clients
        logger.exception("Deterministic scheduling failed")
        raise HTTPException(
            status_code=400,
            detail="Invalid request or scheduling failed. Please verify inputs.",
        )


@router.post("/dayahead/deterministic/upload")
async def dayahead_deterministic_upload(
    batteries_json: UploadFile = File(
        ..., description="Battery configuration JSON file"
    ),
    forecasts_csv: UploadFile = File(..., description="Forecast CSV file"),
    timestep_hours: float | None = Form(None),
):
    try:
        batteries_text = (await batteries_json.read()).decode("utf-8")
        forecasts_text = (await forecasts_csv.read()).decode("utf-8")

        batteries_payload = json.loads(batteries_text)

        req = DeterministicRequest(
            batteries=batteries_payload,
            forecasts_csv=forecasts_text,
            timestep_hours=timestep_hours,
        )

        df = run_dayahead_deterministic(
            batteries_specs=[b.model_dump() for b in req.batteries],
            forecasts_csv_text=req.forecasts_csv,
            timestep_hours=req.timestep_hours,
        )

        csv_bytes = df.to_csv(index=False).encode("utf-8")
        return StreamingResponse(
            io.BytesIO(csv_bytes),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=dayahead_deterministic_schedule.csv"
            },
        )

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid batteries JSON file.")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400, detail="Uploaded files must be UTF-8 text."
        )
    except DataValidationError as e:
        logger.error("Deterministic upload validation error: %s", str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Deterministic upload scheduling failed")
        raise HTTPException(
            status_code=400,
            detail="Invalid upload request or scheduling failed. Please verify inputs.",
        )


@router.post("/dayahead/stochastic")
def dayahead_stochastic(req: StochasticRequest):
    try:
        df = run_dayahead_stochastic(
            batteries_specs=[b.model_dump() for b in req.batteries],
            history_csv_text=req.history_csv,
            ahead_prices_csv_text=req.ahead_prices_csv,
            policy_override=(
                req.policy_override.model_dump() if req.policy_override else None
            ),
            champion_path=str(CHAMPION_POLICY_PATH),
            timestep_hours=req.timestep_hours,
        )
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d %H:%M:%S")
        return JSONResponse(content=df.to_dict(orient="list"))
    except DataValidationError as e:
        logger.error("Stochastic scheduling validation error: %s", str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        logger.error("Champion policy file missing")
        raise HTTPException(
            status_code=503, detail="Champion policy is not configured on the server."
        )
    except Exception as e:
        logger.exception("Stochastic scheduling failed")
        raise HTTPException(
            status_code=400,
            detail="Invalid request or scheduling failed. Please verify inputs and champion policy.",
        )


@router.get("/health")
def health():
    """Basic health and solver availability check."""
    try:
        from esms import __version__, get_available_pyomo_solvers

        solvers = get_available_pyomo_solvers()
        champion_exists = CHAMPION_POLICY_PATH.exists()
        status = {
            "service": "Household Day-Ahead Scheduling API",
            "version": API_VERSION,
            "esms_version": __version__,
            "status": "Healthy" if (solvers and champion_exists) else "Degraded",
            "available_solvers": solvers,
            "champion_policy": {
                "exists": champion_exists,
            },
        }
        return JSONResponse(content=status)
    except Exception:
        return JSONResponse(content={"status": "Unhealthy"}, status_code=500)
