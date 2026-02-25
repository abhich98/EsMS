"""EsMS package."""

from importlib.metadata import version, PackageNotFoundError

from .models import Battery
from .optimization import EnergyOptimizer
from .utils import SUGGESTED_SOLVERS, get_available_pyomo_solvers

try:
    __version__ = version("esms")
except PackageNotFoundError:
    __version__ = "dev"  # Fallback for development

__all__ = ["Battery", "EnergyOptimizer", 
           "SUGGESTED_SOLVERS", "get_available_pyomo_solvers", 
           "__version__"]