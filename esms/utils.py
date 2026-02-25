

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