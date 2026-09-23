"""Run the flagship E175 surface-deformation example on tracked assets.

This top-level example demonstrates the general mesh-motion API on a realistic
aircraft rather than introducing an aircraft-specific library interface.  The
pipeline proceeds through five stages:

1. Load the STEP geometry and the matching surface mesh.
2. Apply differentiable design variables to the wing, tail, and fuselage.
3. Recompute their closed intersection curves at each continuation step.
4. Propagate those boundary displacements with the graph-Laplacian solver.
5. Reproject the moved nodes onto the deformed geometry and report quality.

The tracked triangle wall is the default.  Pass ``--mesh quad`` to use the
tracked quad-dominant panel and activate nonzero affine-residual regularization
for its n-gons.  Volume motion and interactive visualization remain disabled,
so both paths are suitable for headless execution from a clean checkout.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
import tempfile
import time
from typing import Mapping, Sequence

import csdl_alpha as csdl
import numpy as np

# Direct script execution puts ``examples/`` rather than the repository root
# on ``sys.path``. Add the root before importing the local package so the exact
# documented command works without an editable installation.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from bsm3.component_parameters import (
    FuselageParameters,
    TailParameters,
    WingParameters,
)
from bsm3.core.boundary_surface_movement import (
    AxisRange,
    ComponentFreeRegion,
    ComponentSpec,
    DeclarativeGeometryParameterization,
    FiniteDifferenceConfig,
    GeometryParameterization,
    GraphDistanceWeightingConfig,
    IntersectionSpec,
    MeshMotionResult,
    MeshQualityOutputConfig,
    ModelFiles,
    NgonAffineRegularizationConfig,
    PipelineConfig,
    SurfaceMotionConfig,
    VisualizationConfig,
    VolumeMotionConfig,
    build_mesh_motion_model,
    deform_geometry,
)


ASSET_DIRECTORY = (
    REPOSITORY_ROOT / "bsm3" / "core" / "boundary_surface_movement"
)
STEP_FILE = ASSET_DIRECTORY / "embraer_175_no_winglets.stp"
TRI_SURFACE_FILE = (
    ASSET_DIRECTORY
    / "fluent_R1_tet_euler_volume_mesh"
    / "e175_fluent_R1_aircraft_wall_tri.msh"
)
QUAD_SURFACE_FILE = (
    ASSET_DIRECTORY / "embraer_175_quad_dominant_symmetric_no_winglets.msh"
)
DEFAULT_CACHE_DIRECTORY = (
    Path(tempfile.gettempdir()) / "bsm3_e175_surface_deformation_cache"
)

# This mild, nonzero design point exercises all three component builders while
# preserving a useful quality margin for a fast integration smoke test.
DEFAULT_DESIGN_VALUES: Mapping[str, float] = {
    "wing_translation_x": 0.0,
    "wing_rotation_degrees": 0.0,
    "tail_rotation_degrees": 0.0,
    "wing_area": 70.01 * 1.001,
    "wing_aspect_ratio": 8.41,
    "fuselage_diameter_scale": 1.001,
}


@dataclass(frozen=True)
class ExampleRun:
    """Summarize one completed example run.

    Attributes
    ----------
    result
        Differentiable pipeline outputs and forward quality diagnostics.
    mesh_kind
        Selected input topology, either ``"tri"`` or ``"quad"``.
    vertex_count
        Number of surface vertices before and after deformation.
    cell_count
        Number of polygonal surface cells.
    fold_count
        Cells whose area-weighted normal reverses relative to the baseline.
    elapsed_seconds
        Wall-clock duration of the pipeline build and evaluation.
    """

    result: MeshMotionResult
    mesh_kind: str
    vertex_count: int
    cell_count: int
    fold_count: int
    elapsed_seconds: float


def create_design_variables(
    values: Mapping[str, float] | None = None,
) -> dict[str, csdl.Variable]:
    """Create and register the differentiable geometry controls.

    Parameters
    ----------
    values
        Optional complete or partial overrides of the documented design point.

    Returns
    -------
    dict[str, csdl.Variable]
        Named CSDL variables registered as optimization design variables.

    Raises
    ------
    KeyError
        If an override names a control not used by this example.
    """

    design_values = dict(DEFAULT_DESIGN_VALUES)
    if values is not None:
        unknown = set(values).difference(design_values)
        if unknown:
            raise KeyError(f"Unknown design variables: {sorted(unknown)}")
        design_values.update(values)

    variables = {
        name: csdl.Variable(name=name, value=value)
        for name, value in design_values.items()
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
    return variables


def build_geometry_parameterization(
    variables: Mapping[str, csdl.Variable],
) -> GeometryParameterization:
    """Describe component deformations and their independent intersections.

    Parameters
    ----------
    variables
        Named CSDL design variables used by the coefficient builders.

    Returns
    -------
    GeometryParameterization
        General declarative component and intersection specification.
    """

    def _wing_coefficients(component, fraction, intersections):
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
                    8.4
                    + fraction * (variables["wing_aspect_ratio"] - 8.4)
                ),
                reference_area=70.0,
                reference_aspect_ratio=8.4,
                pivot=pivot.reshape((1, 3)),
                spanwise_scaling_root=float(
                    np.median(np.abs(vertices[:, 1]))
                ),
            ),
        )

    def _tail_coefficients(component, fraction, intersections):
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

    def _fuselage_coefficients(component, fraction, intersections):
        del intersections
        control_points = np.vstack(
            [
                np.asarray(
                    component.functions[key].coefficients.value,
                    dtype=float,
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
                coefficient_builder=_wing_coefficients,
                free_region_factory=lambda component: ComponentFreeRegion(
                    component=component,
                    y=AxisRange(upper=0.3, mode="abs"),
                ),
                projection_mode="lifting_surface",
            ),
            ComponentSpec(
                name="tail",
                search_name="HT",
                coefficient_builder=_tail_coefficients,
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
                coefficient_builder=_fuselage_coefficients,
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


def build_model_files(
    mesh_kind: str = "tri",
    cache_directory: Path | None = None,
) -> ModelFiles:
    """Select tracked inputs and a writable setup-cache location.

    Parameters
    ----------
    mesh_kind
        ``"tri"`` for the R1 CFD wall or ``"quad"`` for the panel mesh.
    cache_directory
        Optional setup-cache directory. The default is outside the repository.

    Returns
    -------
    ModelFiles
        Geometry, surface mesh, and cache paths for a surface-only run.

    Raises
    ------
    ValueError
        If ``mesh_kind`` is not one of the two documented choices.
    """

    surface_files = {"tri": TRI_SURFACE_FILE, "quad": QUAD_SURFACE_FILE}
    if mesh_kind not in surface_files:
        raise ValueError("mesh_kind must be 'tri' or 'quad'")
    return ModelFiles(
        geometry_step_file=STEP_FILE,
        surface_mesh_file=surface_files[mesh_kind],
        setup_cache_directory=(
            DEFAULT_CACHE_DIRECTORY
            if cache_directory is None
            else Path(cache_directory)
        ),
    )


def build_pipeline_config(mesh_kind: str = "tri") -> PipelineConfig:
    """Configure headless, surface-only graph-Laplacian motion.

    Parameters
    ----------
    mesh_kind
        Surface topology selected by :func:`build_model_files`.

    Returns
    -------
    PipelineConfig
        Surface-motion, diagnostics, and execution policy.

    Raises
    ------
    ValueError
        If ``mesh_kind`` is not one of the two documented choices.
    """

    if mesh_kind not in {"tri", "quad"}:
        raise ValueError("mesh_kind must be 'tri' or 'quad'")

    # Triangles have no affine-residual hourglass mode. The quad panel does,
    # so a nonzero weight stabilizes its non-affine per-element corrections.
    ngon_affine_weight = 0.0 if mesh_kind == "tri" else 0.3
    return PipelineConfig(
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
            ngon_affine=NgonAffineRegularizationConfig(
                weight=ngon_affine_weight
            ),
        ),
        volume_motion=VolumeMotionConfig(
            mode="off",
            load_mode="synchronized",
            synchronized_load_steps=None,
            write_meshes=False,
        ),
        quality=MeshQualityOutputConfig(
            surface=True,
            volume=False,
            gmsh_volume_metrics=False,
        ),
        visualization=VisualizationConfig(enabled=False),
        finite_difference=FiniteDifferenceConfig(enabled=False),
        symmetry=True,
    )


def run_example(
    mesh_kind: str = "tri",
    cache_directory: Path | None = None,
    design_values: Mapping[str, float] | None = None,
    *,
    print_report: bool = True,
) -> ExampleRun:
    """Build and evaluate the documented surface-deformation pipeline.

    Parameters
    ----------
    mesh_kind
        ``"tri"`` for the default CFD wall or ``"quad"`` for the n-gon path.
    cache_directory
        Optional reusable setup-cache directory outside the source tree.
    design_values
        Optional complete or partial overrides of the design point.
    print_report
        Whether to print the compact example-level summary.

    Returns
    -------
    ExampleRun
        Pipeline outputs, topology counts, fold count, and elapsed time.
    """

    recorder = csdl.Recorder(inline=True)
    recorder.start()
    started_at = time.perf_counter()
    try:
        variables = create_design_variables(design_values)
        geometry_parameterization = build_geometry_parameterization(variables)
        model_files = build_model_files(mesh_kind, cache_directory)
        config = build_pipeline_config(mesh_kind)
        result = build_mesh_motion_model(
            recorder=recorder,
            model_files=model_files,
            geometry_parameterization=geometry_parameterization,
            config=config,
        )
    finally:
        recorder.stop()

    elapsed_seconds = time.perf_counter() - started_at
    cells = _surface_cells(result.surface_mesh)
    final_coordinates = np.asarray(result.surface_coordinates.value, dtype=float)
    fold_count = _count_polygon_folds(
        np.asarray(result.initial_surface_coordinates, dtype=float),
        final_coordinates,
        cells,
    )
    run = ExampleRun(
        result=result,
        mesh_kind=mesh_kind,
        vertex_count=int(final_coordinates.shape[0]),
        cell_count=len(cells),
        fold_count=fold_count,
        elapsed_seconds=elapsed_seconds,
    )
    if print_report:
        _print_report(run, config)
    return run


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line example.

    Parameters
    ----------
    argv
        Optional argument sequence; defaults to the process command line.

    Returns
    -------
    int
        Zero after a successful deformation and quality report.
    """

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--mesh",
        choices=("tri", "quad"),
        default="tri",
        help="surface topology (default: tri CFD wall)",
    )
    parser.add_argument(
        "--cache-directory",
        type=Path,
        default=None,
        help="setup cache (default: a reusable directory under the OS temp dir)",
    )
    arguments = parser.parse_args(argv)
    run_example(
        mesh_kind=arguments.mesh,
        cache_directory=arguments.cache_directory,
    )
    return 0


def _surface_cells(mesh) -> list[np.ndarray]:
    ordered_types = ["triangle", "quad"] + [
        name
        for name in mesh.cell_blocks
        if name not in {"triangle", "quad"}
    ]
    return [
        np.asarray(cell, dtype=np.int64)
        for cell_type in ordered_types
        for cell in np.asarray(mesh.cell_blocks.get(cell_type, []))
    ]


def _polygon_normals(
    vertices: np.ndarray,
    connectivity: list[np.ndarray],
) -> np.ndarray:
    poly_ids = np.concatenate(
        [
            np.full(face.size, polygon_id, dtype=np.int64)
            for polygon_id, face in enumerate(connectivity)
        ]
    )
    start_ids = np.concatenate(connectivity)
    end_ids = np.concatenate([np.roll(face, -1) for face in connectivity])
    start = vertices[start_ids]
    end = vertices[end_ids]
    contributions = np.empty_like(start)
    contributions[:, 0] = (start[:, 1] - end[:, 1]) * (
        start[:, 2] + end[:, 2]
    )
    contributions[:, 1] = (start[:, 2] - end[:, 2]) * (
        start[:, 0] + end[:, 0]
    )
    contributions[:, 2] = (start[:, 0] - end[:, 0]) * (
        start[:, 1] + end[:, 1]
    )
    normals = np.zeros((len(connectivity), 3), dtype=float)
    np.add.at(normals, poly_ids, contributions)
    return normals


def _count_polygon_folds(
    initial_vertices: np.ndarray,
    final_vertices: np.ndarray,
    connectivity: list[np.ndarray],
) -> int:
    baseline_normals = _polygon_normals(initial_vertices, connectivity)
    final_normals = _polygon_normals(final_vertices, connectivity)
    normal_dots = np.einsum(
        "ij,ij->i", baseline_normals, final_normals
    )
    return int(np.sum(normal_dots < 0.0))


def _print_report(run: ExampleRun, config: PipelineConfig) -> None:
    quality = run.result.surface_quality_report
    inversions = run.result.surface_inversion_report.num_inverted
    print("\nE175 surface-deformation example")
    print(f"  mesh: {run.mesh_kind}")
    print(f"  vertices / cells: {run.vertex_count} / {run.cell_count}")
    print(f"  load steps: {config.surface_motion.load_steps}")
    print(f"  folds / inversions: {run.fold_count} / {inversions}")
    print(f"  elapsed: {run.elapsed_seconds:.1f} s")
    print("  surface quality:")
    print(f"    minimum angle: {quality.minimum_angle_degrees:.3f} deg")
    print(f"    maximum aspect ratio: {quality.maximum_aspect_ratio:.3f}")
    print(f"    minimum scaled Jacobian: {quality.minimum_scaled_jacobian:.6f}")
    print(
        "    area-ratio range: "
        f"[{quality.minimum_area_ratio:.6f}, "
        f"{quality.maximum_area_ratio:.6f}]"
    )
    print(
        "    inverted / degenerate elements: "
        f"{quality.inverted_elements} / {quality.degenerate_elements}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
