"""仿真计算模块。"""

from .fe3d import (
    Mesh3D,
    SimulationResult3D,
    generate_assembly_mesh,
    solve_thermal_structural_3d,
    run_mesh_convergence_study,
    run_structure_fair_comparison,
)

__all__ = [
    "Mesh3D",
    "SimulationResult3D",
    "generate_assembly_mesh",
    "solve_thermal_structural_3d",
    "run_mesh_convergence_study",
    "run_structure_fair_comparison",
]
