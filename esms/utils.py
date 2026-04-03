import numpy as np
import pandas as pd

SUGGESTED_SOLVERS = ["cbc", "scip", "glpk", "ipopt"]


def get_available_pyomo_solvers():
    """Check for available Pyomo solvers and return a list of their names."""
    from pyomo.environ import SolverFactory

    available_solvers = []
    for solver_name in SUGGESTED_SOLVERS:
        solver = SolverFactory(solver_name)
        if solver.available():
            available_solvers.append(solver_name)

    return available_solvers


def simulate_rt_prices(
    da_prices_df: pd.DataFrame, volatility=0.1, jump_prob=0.1, jump_magnitude=1.0
):
    """Simulates Real-Time (RT) prices based on Day-Ahead (DA) prices.
    Parameters:
    - da_prices_df: Dataframe of Day-Ahead prices along with timestamps
    - volatility: Standard deviation of the Gaussian noise (as a fraction of DA price)
    - jump_prob: Probability of a price jump occurring at each time step
    - jump_magnitude: Magnitude of the price jump (as a fraction of DA price)
    - seed: Random seed for reproducibility
    Returns:
    - rt_prices_df: Simulated Real-Time prices dataframe with timestamps
    """

    rt_prices = da_prices_df["price"].copy()
    num_prices = len(da_prices_df)

    # 3. Add Gaussian Noise (Daily fluctuations)
    # Represents small errors in demand or solar/wind forecasts
    noise = np.random.normal(0, da_prices_df["price"] * volatility)
    rt_prices = da_prices_df["price"] + noise

    # 4. Add Jumps (Grid spikes/crashes)
    # Represents sudden outages or extreme weather events
    jumps = (
        (np.random.rand(num_prices) < jump_prob)
        * np.random.choice([-1, 1], num_prices)
        * jump_magnitude
        * da_prices_df["price"]
    )
    rt_prices += jumps

    rt_prices_df = pd.DataFrame(
        {"rt_price": rt_prices.clip(lower=0)}  # Ensure prices don't go negative
    )
    if "timestamp" in da_prices_df.columns:
        rt_prices_df["timestamp"] = da_prices_df["timestamp"]

    return rt_prices_df
