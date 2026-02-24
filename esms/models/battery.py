"""
Battery Energy Storage System (BESS) model.

Defines the data structure and validation for battery parameters
used in the optimization.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Battery:
    """
    Represents a Battery Energy Storage System with its operational parameters.
    
    Attributes:
        id: Unique identifier for the battery
        capacity: Total energy capacity in kWh
        max_charge: Maximum charging power in kW
        max_discharge: Maximum discharging power in kW
        charge_efficiency: Charging efficiency (0 to 1)
        discharge_efficiency: Discharging efficiency (0 to 1)
        initial_soc: Initial state of charge in kWh
        min_soc: Minimum allowed state of charge in kWh or percentage (defaults to 0 kWh)
        max_soc: Maximum allowed state of charge in kWh or percentage (defaults to capacity)
    """
    
    id: str
    capacity: float  # kWh
    max_charge: float  # kW
    max_discharge: float  # kW
    charge_efficiency: float  # 0-1
    discharge_efficiency: float  # 0-1
    initial_soc: float  # kWh
    min_soc: float = 0.0  # kWh
    max_soc: Optional[float] = None  # kWhpercentage
    
    def __post_init__(self):
        """Validate battery parameters after initialization."""
        # Set max_soc to capacity if not specified
        if self.max_soc is None:
            self.max_soc = self.capacity
        
        # Validation
        if self.capacity <= 0:
            raise ValueError(f"Battery {self.id}: capacity must be positive")
        
        if self.max_charge <= 0:
            raise ValueError(f"Battery {self.id}: max_charge must be positive")
        
        if self.max_discharge <= 0:
            raise ValueError(f"Battery {self.id}: max_discharge must be positive")
        
        if not 0 < self.charge_efficiency <= 1:
            raise ValueError(f"Battery {self.id}: charge_efficiency must be in (0, 1]")
        
        if not 0 < self.discharge_efficiency <= 1:
            raise ValueError(f"Battery {self.id}: discharge_efficiency must be in (0, 1]")
        
        if not 0 <= self.min_soc < self.max_soc <= self.capacity:
            raise ValueError(
                f"Battery {self.id}: SOC limits must satisfy "
                f"0 <= min_soc ({self.min_soc}) < max_soc ({self.max_soc}) <= capacity ({self.capacity})"
            )
        
        if not self.min_soc <= self.initial_soc <= self.max_soc:
            raise ValueError(
                f"Battery {self.id}: initial_soc ({self.initial_soc}) must be "
                f"between min_soc ({self.min_soc}) and max_soc ({self.max_soc})"
            )

    @classmethod
    def from_dict(cls, data: dict) -> "Battery":
        """Create a Battery from a dict and validate via __post_init__."""
        return cls(**data)
    
    @property
    def round_trip_efficiency(self) -> float:
        """Calculate round-trip efficiency."""
        return self.charge_efficiency * self.discharge_efficiency
    
    def __repr__(self) -> str:
        """String representation of the battery."""
        return (
            f"Battery(id='{self.id}', capacity={self.capacity}kWh, "
            f"max_charge={self.max_charge}kW, max_discharge={self.max_discharge}kW, "
            f"η_rt={self.round_trip_efficiency:.2%})"
        )
