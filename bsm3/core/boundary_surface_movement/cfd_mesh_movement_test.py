"""Clean deformation-only E175 CSDL pipeline.

Edit the three configuration sections below, then run this module directly.
There is deliberately no command-line or environment-variable configuration.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Support both:
#   python -m bsm3.core.boundary_surface_movement.cfd_mesh_movement_test
# and:
#   python /absolute/path/to/cfd_mesh_movement_test.py
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import csdl_alpha as csdl

from bsm3.core.boundary_surface_movement.e175_mesh_motion_config import (
    E175GeometryVariables,
    E175ModelFiles,
    E175PipelineConfig,
    FiniteDifferenceConfig,
    GraphDistanceWeightingConfig,
    MeshQualityOutputConfig,
    SurfaceMotionConfig,
    TangentialSmoothingConfig,
    VisualizationConfig,
    VolumeMotionConfig,
)
from bsm3.core.boundary_surface_movement.e175_mesh_motion_pipeline import (
    build_e175_mesh_motion_model,
    run_fd_sweep,
    select_fd_objective,
)


# ---------------------------------------------------------------------------
# 1. Geometry and matching mesh files
# ---------------------------------------------------------------------------
ASSET_DIRECTORY = Path(__file__).resolve().parent
OPENVSP_MESH_DIRECTORY = ASSET_DIRECTORY / "openvsp_euler_volume_mesh"

MODEL_FILES = E175ModelFiles(
    geometry_step_file=ASSET_DIRECTORY / "embraer_175_no_winglets.stp",
    surface_mesh_file=OPENVSP_MESH_DIRECTORY / "e175_openvsp_aircraft_wall.msh",
    volume_mesh_file=OPENVSP_MESH_DIRECTORY / "e175_euler_volume.msh",
    volume_wall_map_file=(
        OPENVSP_MESH_DIRECTORY
        / "e175_openvsp_aircraft_wall.volume_map.npz"
    ),
    setup_cache_directory=ASSET_DIRECTORY,
)


# ---------------------------------------------------------------------------
# 2. Geometry design point
# ---------------------------------------------------------------------------
# Small nonzero perturbations provide an FD signal while remaining essentially
# at the undeformed reference geometry.
GEOMETRY_VALUES = {
    "wing_translation_x": 0.01,       # m
    "wing_rotation_degrees": 0.01,    # deg
    "tail_rotation_degrees": 0.01,    # deg
    "wing_area": 70.01,               # m^2 (reference: 70.0)
    "wing_aspect_ratio": 8.41,        # reference: 8.4
    "fuselage_diameter_scale": 1.001,
}


def create_geometry_design_variables() -> E175GeometryVariables:
    """Instantiate and register every geometry variable in the CSDL graph."""

    variables = E175GeometryVariables(
        **{
            name: csdl.Variable(name=name, value=value)
            for name, value in GEOMETRY_VALUES.items()
        }
    )
    variables.wing_translation_x.set_as_design_variable(
        lower=-4.0, upper=4.0, scaler=1.0 / 3.0
    )
    variables.wing_rotation_degrees.set_as_design_variable(
        lower=-5.0, upper=5.0, scaler=1.0 / 5.0
    )
    variables.tail_rotation_degrees.set_as_design_variable(
        lower=-8.0, upper=8.0, scaler=1.0 / 8.0
    )
    variables.wing_area.set_as_design_variable(
        lower=56.0, upper=84.0, scaler=1.0 / 70.0
    )
    variables.wing_aspect_ratio.set_as_design_variable(
        lower=6.3, upper=10.08, scaler=1.0 / 8.4
    )
    variables.fuselage_diameter_scale.set_as_design_variable(
        lower=0.8, upper=1.25, scaler=1.0
    )
    return variables


# ---------------------------------------------------------------------------
# 3. Surface and volume deformation settings
# ---------------------------------------------------------------------------
OUTPUT_DIRECTORY = OPENVSP_MESH_DIRECTORY / "deformation_results"

MESH_MOTION = E175PipelineConfig(
    surface_motion=SurfaceMotionConfig(
        mode="graph",
        load_steps=2,
        stiffening_exponent=1.5,
        tangential_smoothing=TangentialSmoothingConfig(
            enabled=True,
            layers=16,
            iterations=3,
            relaxation=1.0,
            preserve_reference=False,
            reprojection="final_only",
        ),
        graph_distance_weighting=GraphDistanceWeightingConfig(
            enabled=True,
            beta=2.0,
            length_scale=4.0,
            cap=float("inf"),
            decay="exp",
            power=1.0,
            seeds="both",
        ),
    ),
    volume_motion=VolumeMotionConfig(
        mode="elasticity",
        # Default: deform the volume once from the final surface displacement.
        load_mode="final",
        elasticity_poisson_ratio=0.3,
        elasticity_stiffening_exponent=0.75,
        output_directory=OUTPUT_DIRECTORY,
        write_meshes=True,
    ),
    quality=MeshQualityOutputConfig(
        surface=True,
        volume=True,
        gmsh_volume_metrics=True,
    ),
    visualization=VisualizationConfig(enabled=True, opacity=1.0),
    finite_difference=FiniteDifferenceConfig(
        enabled=False,
        objective="surface_coordinates",
        step_sizes=(1.0e-2, 1.0e-3, 1.0e-4, 1.0e-5, 1.0e-6),
    ),
    symmetry=False,
)


def run_deformation_test():
    recorder = csdl.Recorder(inline=True)
    recorder.start()

    geometry_variables = create_geometry_design_variables()
    result = build_e175_mesh_motion_model(
        recorder=recorder,
        model_files=MODEL_FILES,
        geometry_variables=geometry_variables,
        config=MESH_MOTION,
    )

    if MESH_MOTION.finite_difference.enabled:
        select_fd_objective(
            result,
            MESH_MOTION.finite_difference.objective,
        )
    recorder.stop()

    if MESH_MOTION.finite_difference.enabled:
        run_fd_sweep(
            recorder,
            MESH_MOTION.finite_difference.step_sizes,
        )
    return result


if __name__ == "__main__":
    run_deformation_test()
