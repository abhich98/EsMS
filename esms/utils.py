

def get_available_pyomo_solvers():
    """Check for available Pyomo solvers and return a list of their names."""
    from pyomo.environ import SolverFactory
    
    # List of common solvers to check
    common_solvers = ["cbc", "scip", "glpk", "ipopt", "baron"]
    
    available_solvers = []
    for solver_name in common_solvers:
        solver = SolverFactory(solver_name)
        if solver.available():
            available_solvers.append(solver_name)
    
    return available_solvers