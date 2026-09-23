"""Quality-first E175 surface and Euler volume-mesh deformation pipeline.

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
import numpy as np

from bsm3.component_parameters import (
    FuselageParameters,
    TailParameters,
    WingParameters,
)
from bsm3.core.boundary_surface_movement import (
    AxisRange,
    ComponentFreeRegion,
    deform_geometry,
)
from bsm3.core.boundary_surface_movement.mesh_motion_config import (
    ComponentSpec,
    DeclarativeGeometryParameterization,
    FiniteDifferenceConfig,
    GraphDistanceWeightingConfig,
    IntersectionSpec,
    MeshQualityOutputConfig,
    ModelFiles,
    NgonAffineRegularizationConfig,
    PipelineConfig,
    SurfaceMotionConfig,
    VisualizationConfig,
    VolumeMotionConfig,
)
from bsm3.core.boundary_surface_movement.mesh_motion_pipeline import (
    build_mesh_motion_model,
    run_fd_sweep,
    select_fd_objective,
)


# ---------------------------------------------------------------------------
# 1. Geometry and matching mesh files
# ---------------------------------------------------------------------------
ASSET_DIRECTORY = Path(__file__).resolve().parent
# Rebuilt from ``embraer_175_no_winglets_fluent_mesh.msh`` by
# ``fluent_to_gmsh_euler_volume.py``: 2.17 M tetrahedra inside a 400 m
# half-sphere, 87 412 aircraft-wall triangles, converted from millimetres to
# metres.  The previous mesh was
# ``quality_first_native_tri_tet_euler_volume_mesh/e175_production_*``.
FLUENT_MESH_DIRECTORY = ASSET_DIRECTORY / "fluent_R4_tet_euler_volume_mesh"

MODEL_FILES = ModelFiles(
    geometry_step_file=ASSET_DIRECTORY / "embraer_175_no_winglets.stp",
    surface_mesh_file=(
        FLUENT_MESH_DIRECTORY / "e175_fluent_R4_aircraft_wall_tri.msh"
    ),
    volume_mesh_file=(
        FLUENT_MESH_DIRECTORY / "e175_fluent_R4_tet_euler_volume.msh"
    ),
    volume_wall_map_file=(
        FLUENT_MESH_DIRECTORY
        / "e175_fluent_R4_aircraft_wall_tri.volume_map.npz"
    ),
    setup_cache_directory=ASSET_DIRECTORY,
)


# ---------------------------------------------------------------------------
# 2. Geometry design point
# ---------------------------------------------------------------------------
# Deliberately extreme deformation used by the mesh-validity regression.
GEOMETRY_VALUES = {
    "wing_translation_x": 0.0, # 4.51,       # m
    "wing_rotation_degrees": 0.0, #5.01,    # deg
    "tail_rotation_degrees": 0.0, #8.01,    # deg
    "wing_area": 70.01 * 1.001, #1.25,        # m^2 (reference: 70.0)
    "wing_aspect_ratio": 8.41 * 1.0, # 0.75,  # reference: 8.4
    "fuselage_diameter_scale": 1.001 * 1., # 1.25,
}


def _build_geometry_parameterization(
    variables: dict[str, csdl.Variable],
) -> DeclarativeGeometryParameterization:
    """Bind the E175 design variables to declarative component behavior."""

    def wing_coefficients(component, fraction, intersections):
        vertices = intersections["wing_fuse"]
        leading = vertices[int(np.argmin(vertices[:, 0]))]
        trailing = vertices[int(np.argmax(vertices[:, 0]))]
        pivot = leading + 0.25 * (trailing - leading)
        pivot[1] = 0.0
        return deform_geometry(
            component=component,
            parameters=WingParameters(
                translation_x=fraction * variables["wing_translation_x"],
                rotation_y_degrees=(
                    fraction * variables["wing_rotation_degrees"]
                ),
                area=70.0 + fraction * (variables["wing_area"] - 70.0),
                aspect_ratio=(
                    8.4 + fraction * (variables["wing_aspect_ratio"] - 8.4)
                ),
                reference_area=70.0,
                reference_aspect_ratio=8.4,
                pivot=pivot.reshape((1, 3)),
                spanwise_scaling_root=float(
                    np.median(np.abs(vertices[:, 1]))
                ),
            ),
        )

    def tail_coefficients(component, fraction, intersections):
        vertices = intersections["tail_fuse"]
        leading = vertices[int(np.argmin(vertices[:, 0]))]
        trailing = vertices[int(np.argmax(vertices[:, 0]))]
        pivot = leading + 0.25 * (trailing - leading)
        pivot[1] = 0.0
        return deform_geometry(
            component=component,
            parameters=TailParameters(
                rotation_y_degrees=(
                    fraction * variables["tail_rotation_degrees"]
                ),
                pivot=pivot.reshape((1, 3)),
            ),
        )

    def fuselage_coefficients(component, fraction, intersections):
        del intersections
        control_points = np.vstack(
            [
                np.asarray(
                    component.functions[key].coefficients.value, dtype=float
                ).reshape((-1, 3))
                for key in sorted(component.functions)
            ]
        )
        pivot = 0.5 * (
            control_points.min(axis=0) + control_points.max(axis=0)
        )
        pivot[1] = 0.0
        return deform_geometry(
            component=component,
            parameters=FuselageParameters(
                diameter_scale=(
                    1.0
                    + fraction
                    * (variables["fuselage_diameter_scale"] - 1.0)
                ),
                pivot=pivot.reshape((1, 3)),
            ),
        )

    return DeclarativeGeometryParameterization(
        design_variables=variables,
        component_specs=[
            ComponentSpec(
                name="wing",
                search_name="wing",
                coefficient_builder=wing_coefficients,
                free_region_factory=lambda component: ComponentFreeRegion(
                    component=component,
                    y=AxisRange(upper=0.3, mode="abs"),
                ),
                projection_mode="lifting_surface",
            ),
            ComponentSpec(
                name="tail",
                search_name="HT",
                coefficient_builder=tail_coefficients,
                free_region_factory=lambda component: ComponentFreeRegion(
                    component=component,
                    y=AxisRange(upper=0.3, mode="abs"),
                ),
                projection_name="horizontal_tail",
                projection_mode="lifting_surface",
            ),
            ComponentSpec(
                name="fuselage",
                search_name="fuselage",
                coefficient_builder=fuselage_coefficients,
                free_region_factory=lambda component: ComponentFreeRegion(
                    component=component,
                    x=AxisRange(lower=0.05, upper=0.97, mode="extent"),
                ),
            ),
        ],
        intersection_specs=[
            IntersectionSpec(
                name="wing_fuse",
                driving_component="wing",
                query_component="fuselage",
                solver_name="wing_fuselage",
            ),
            IntersectionSpec(
                name="tail_fuse",
                driving_component="tail",
                query_component="fuselage",
                solver_name="tail_fuselage",
            ),
        ],
    )


def create_geometry_parameterization() -> DeclarativeGeometryParameterization:
    """Instantiate and register every E175 geometry design variable.

    Returns
    -------
    DeclarativeGeometryParameterization
        Driver-owned variables, components, intersections, and deformations.
    """

    variables = {
        name: csdl.Variable(name=name, value=value)
        for name, value in GEOMETRY_VALUES.items()
    }
    variables["wing_translation_x"].set_as_design_variable(
        lower=-4.0, upper=4.0, scaler=1.0 / 3.0
    )
    variables["wing_rotation_degrees"].set_as_design_variable(
        lower=-5.0, upper=5.0, scaler=1.0 / 5.0
    )
    variables["tail_rotation_degrees"].set_as_design_variable(
        lower=-8.0, upper=8.0, scaler=1.0 / 8.0
    )
    variables["wing_area"].set_as_design_variable(
        lower=56.0, upper=84.0, scaler=1.0 / 70.0
    )
    variables["wing_aspect_ratio"].set_as_design_variable(
        lower=6.3, upper=10.08, scaler=1.0 / 8.4
    )
    variables["fuselage_diameter_scale"].set_as_design_variable(
        lower=0.8, upper=1.25, scaler=1.0
    )
    return _build_geometry_parameterization(variables)


# ---------------------------------------------------------------------------
# 3. Surface and volume deformation settings
# ---------------------------------------------------------------------------
OUTPUT_DIRECTORY = FLUENT_MESH_DIRECTORY / "deformation_results"

MESH_MOTION = PipelineConfig(
    surface_motion=SurfaceMotionConfig(
        load_steps=2,
        stiffening_exponent=1.5,
        graph_distance_weighting=GraphDistanceWeightingConfig(
            enabled=True,
            beta=5.0,
            length_scale=10.0,
            cap=float("inf"),
            decay="exp",
            power=1.0,
        ),
        # The production wall is triangle-only, so there are no n-gon
        # hourglass modes for the affine regularizer to constrain.
        ngon_affine=NgonAffineRegularizationConfig(weight=0.0),
    ),
    volume_motion=VolumeMotionConfig(
        mode="off",
        load_mode="synchronized",
        # Follow the two nonlinear surface states exactly.
        synchronized_load_steps=None,
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
    # The extracted wall is already the y>=0 half mesh.
    symmetry=True,
)


def run_deformation_test():
    recorder = csdl.Recorder(inline=True)
    recorder.start()

    geometry_parameterization = create_geometry_parameterization()
    result = build_mesh_motion_model(
        recorder=recorder,
        model_files=MODEL_FILES,
        geometry_parameterization=geometry_parameterization,
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
