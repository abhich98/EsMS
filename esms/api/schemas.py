"""Pydantic schemas for API validation."""

from typing import Optional
from pydantic import BaseModel, Field, field_validator
from esms.utils import get_available_pyomo_solvers


class SolverConfig(BaseModel):
    """Solver configuration schema."""

    solver: str = Field(default="glpk", description="Solver name (scip, glpk, cbc)")
    timestep_hours: float = Field(
        default=1.0, gt=0, description="Duration of each timestep in hours"
    )
    optimization_type: str = Field(
        default="lp", description="Optimization type: 'lp' or 'milp'"
    )
    verbose: bool = Field(default=False, description="Show solver output")
    opts: Optional[dict] = Field(
        default={}, description="Additional solver options as a dictionary"
    )

    @field_validator("optimization_type")
    @classmethod
    def validate_optimization_type(cls, v):
        """Validate optimization type."""
        if v.lower() not in ["lp", "milp"]:
            raise ValueError("optimization_type must be 'lp' or 'milp'")
        return v.lower()

    @field_validator("solver")
    @classmethod
    def validate_solver(cls, v):
        """Validate solver name."""
        valid_solvers = get_available_pyomo_solvers()
        if v.lower() not in valid_solvers:
            raise ValueError(
                f"solver must be one of {valid_solvers}, got '{v}'"
            )
        return v.lower()
