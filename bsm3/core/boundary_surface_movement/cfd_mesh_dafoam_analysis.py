"""E175 geometry -> surface motion -> volume motion -> DAFoam in CSDL.

This executable is intentionally configured in Python: there is no argument
parser and no environment-variable configuration. Fill in ``CASE.case_directory``
when an OpenFOAM/DAFoam case template is available.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
from typing import Any

# Support module execution and direct execution by absolute file path.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import csdl_alpha as csdl
import numpy as np

from bsm3.core.boundary_surface_movement.dafoam_csdl import (
    DAFoamAnalysisOperation,
    PYDAFoamBackend,
    add_csdl_inputs_to_da_options,
    make_patch_velocity,
)
from bsm3.core.boundary_surface_movement.e175_mesh_motion_config import (
    E175GeometryVariables,
    E175MeshMotionResult,
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
from bsm3.core.boundary_surface_movement.run_dafoam_gmsh import (
    FlowConfig,
    build_da_options,
    convert_and_check_mesh,
    validate_case_template,
    validate_reused_mesh,
)
from bsm3.core.boundary_surface_movement.volume_mesh_motion import (
    read_gmsh22_volume,
)


ASSET_DIRECTORY = Path(__file__).resolve().parent
OPENVSP_MESH_DIRECTORY = ASSET_DIRECTORY / "openvsp_euler_volume_mesh"


# ---------------------------------------------------------------------------
# 1. Geometry and matching mesh files
# ---------------------------------------------------------------------------
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
DEFORMATION_OUTPUT_DIRECTORY = OPENVSP_MESH_DIRECTORY / "deformation_results"


# ---------------------------------------------------------------------------
# 2. Geometry design point
# ---------------------------------------------------------------------------
# Small nonzero changes avoid evaluating derivative checks exactly at CAD seams.
GEOMETRY_VALUES = {
    "wing_translation_x": 0.01,
    "wing_rotation_degrees": 0.01,
    "tail_rotation_degrees": 0.01,
    "wing_area": 70.01,
    "wing_aspect_ratio": 8.41,
    "fuselage_diameter_scale": 1.001,
}


def create_geometry_design_variables() -> E175GeometryVariables:
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
            reprojection="final_only",
        ),
        graph_distance_weighting=GraphDistanceWeightingConfig(
            enabled=True,
            beta=2.0,
            length_scale=4.0,
            decay="exp",
            seeds="both",
        ),
    ),
    volume_motion=VolumeMotionConfig(
        mode="elasticity",
        # One differentiable reference-stiffness volume solve after the final
        # surface load step is the default CFD/optimization path.
        load_mode="final",
        elasticity_poisson_ratio=0.3,
        elasticity_stiffening_exponent=0.75,
        output_directory=DEFORMATION_OUTPUT_DIRECTORY,
        write_meshes=True,
    ),
    quality=MeshQualityOutputConfig(
        # These diagnostics are evaluated before DAFoam is called.
        surface=True,
        volume=True,
        gmsh_volume_metrics=True,
        fail_on_surface_inversion=True,
        fail_on_volume_inversion=True,
    ),
    visualization=VisualizationConfig(enabled=False),
    finite_difference=FiniteDifferenceConfig(
        enabled=False,
        objective="CD",
        step_sizes=(1.0e-2, 1.0e-3, 1.0e-4, 1.0e-5),
    ),
    symmetry=False,
)


# ---------------------------------------------------------------------------
# 4. DAFoam flow and OpenFOAM case settings
# ---------------------------------------------------------------------------
FLOW = FlowConfig(
    solver_name="DARhoSimpleCFoam",
    velocity_m_per_s=242.52,
    angle_of_attack_deg=0.0,
    pressure_pa=30089.6,
    temperature_k=228.714,
    nu_tilda_m2_per_s=4.5e-5,
    reference_area_m2=70.0,
    normal_axis="z",
    use_wall_functions=False,
    primal_min_res_tol=1.0e-7,
)


@dataclass(frozen=True)
class OpenFOAMCaseConfig:
    # TODO: set this once the E175 OpenFOAM case template exists.
    case_directory: Path | None = None
    reuse_openfoam_mesh: bool = False
    overwrite_existing_polymesh: bool = False
    run_check_mesh: bool = True
    wall_patches: tuple[str, ...] = ("aircraft",)
    farfield_patches: tuple[str, ...] = ("inlet", "outlet", "farfield")
    symmetry_patches: tuple[str, ...] = ("symmetry",)
    function_names: tuple[str, ...] = ("CL", "CD")
    results_file: Path = Path("bsm3_dafoam_results.json")


CASE = OpenFOAMCaseConfig(case_directory=None)


@dataclass(frozen=True)
class EndToEndDerivativeCheckConfig:
    """Optimization-level FD check through geometry, mesh motion, and DAFoam."""

    enabled: bool = False
    lift_constraint_target: float = 0.5
    step_size: float = 1.0e-5
    print_results: bool = True
    raise_on_error: bool = False

    def __post_init__(self):
        if self.step_size <= 0.0:
            raise ValueError("Derivative-check step_size must be positive.")


END_TO_END_DERIVATIVE_CHECK = EndToEndDerivativeCheckConfig(
    enabled=False,
    lift_constraint_target=0.5,
    step_size=1.0e-5,
)


@dataclass
class E175DAFoamResult:
    mesh_motion: E175MeshMotionResult
    flow_outputs: dict[str, csdl.Variable]
    cl: csdl.Variable
    cd: csdl.Variable


def _require_case_directory(config: OpenFOAMCaseConfig) -> Path:
    if config.case_directory is None:
        raise RuntimeError(
            "DAFoam is not configured yet: set CASE.case_directory to a "
            "complete OpenFOAM case containing 0/, constant/, and system/."
        )
    return Path(config.case_directory).expanduser().resolve()


def prepare_openfoam_case(
    config: OpenFOAMCaseConfig,
    model_files: E175ModelFiles,
    comm,
) -> Path:
    """Convert/validate the mesh on rank zero and synchronize all ranks."""

    case_directory = _require_case_directory(config)
    expected_patches = (
        config.wall_patches
        + config.farfield_patches
        + config.symmetry_patches
    )
    error_message = None
    if comm.rank == 0:
        try:
            validate_case_template(case_directory)
            if config.reuse_openfoam_mesh:
                validate_reused_mesh(
                    case_directory,
                    expected_patches,
                    not config.run_check_mesh,
                )
            else:
                convert_and_check_mesh(
                    case_dir=case_directory,
                    mesh_file=model_files.volume_mesh_file,
                    wall_patches=config.wall_patches,
                    farfield_patches=config.farfield_patches,
                    symmetry_patches=config.symmetry_patches,
                    overwrite_existing=config.overwrite_existing_polymesh,
                    skip_check_mesh=not config.run_check_mesh,
                )
        except Exception as error:
            error_message = f"{type(error).__name__}: {error}"
    error_message = comm.bcast(error_message, root=0)
    if error_message is not None:
        raise RuntimeError(
            "OpenFOAM mesh/case preparation failed: " + error_message
        )
    comm.Barrier()
    return case_directory


def create_dafoam_backend(
    flow: FlowConfig,
    case: OpenFOAMCaseConfig,
    model_files: E175ModelFiles,
    comm,
) -> PYDAFoamBackend:
    case_directory = prepare_openfoam_case(case, model_files, comm)
    da_options = add_csdl_inputs_to_da_options(
        build_da_options(
            flow,
            case.wall_patches,
            case.farfield_patches,
        ),
        volume_input_name="aero_vol_coords",
        patch_velocity_input_name="patch_velocity",
        farfield_patches=case.farfield_patches,
        flow_axis="x",
        normal_axis=flow.normal_axis,
    )
    reference_mesh = read_gmsh22_volume(model_files.volume_mesh_file)
    return PYDAFoamBackend.from_options(
        da_options,
        comm,
        reference_mesh.vertices,
        case_directory=case_directory,
        volume_input_name="aero_vol_coords",
        function_names=case.function_names,
        check_mesh=case.run_check_mesh,
    )


def build_cfd_analysis(
    recorder: csdl.Recorder,
    model_files: E175ModelFiles,
    geometry_variables: E175GeometryVariables,
    mesh_motion: E175PipelineConfig,
    flow: FlowConfig,
    backend: PYDAFoamBackend,
) -> E175DAFoamResult:
    """Build the end-to-end graph and return CL/CD as CSDL variables."""

    if mesh_motion.volume_motion.load_mode != "final":
        raise ValueError(
            "DAFoam coupling requires volume_motion.load_mode='final'; the "
            "synchronized re-factorization path is forward-only."
        )
    if "elasticity" not in mesh_motion.volume_motion.methods:
        raise ValueError(
            "DAFoam coupling requires the elasticity volume-motion method."
        )
    operation = DAFoamAnalysisOperation(backend)

    def aerodynamic_analysis(volume_coordinates):
        airspeed = csdl.Variable(
            name="dafoam_airspeed_m_per_s",
            value=np.array([flow.velocity_m_per_s]),
        )
        angle_of_attack = csdl.Variable(
            name="dafoam_angle_of_attack_deg",
            value=np.array([flow.angle_of_attack_deg]),
        )
        outputs = operation.evaluate(
            volume_coordinates,
            patch_velocity=make_patch_velocity(
                airspeed,
                angle_of_attack,
            ),
        )
        for name, variable in outputs.items():
            variable.add_name(f"dafoam_{name}")
        return outputs

    motion_result = build_e175_mesh_motion_model(
        recorder=recorder,
        model_files=model_files,
        geometry_variables=geometry_variables,
        config=mesh_motion,
        aerodynamic_analysis=aerodynamic_analysis,
        aerodynamic_volume_method="elasticity",
    )
    outputs = motion_result.aerodynamic_outputs
    return E175DAFoamResult(
        mesh_motion=motion_result,
        flow_outputs=outputs,
        cl=outputs["CL"],
        cd=outputs["CD"],
    )


def configure_end_to_end_derivative_check(
    result: E175DAFoamResult,
    config: EndToEndDerivativeCheckConfig,
) -> None:
    """Register the aerodynamic optimization outputs before stopping CSDL."""

    result.cl.set_as_constraint(equals=config.lift_constraint_target)
    result.cd.set_as_objective()


def run_end_to_end_derivative_check(
    recorder: csdl.Recorder,
    config: EndToEndDerivativeCheckConfig,
):
    """Run CSDL's Python-backend total-derivative finite-difference check."""

    simulator = csdl.experimental.PySimulator(recorder=recorder)
    return simulator.check_optimization_derivatives(
        step_size=config.step_size,
        print_results=config.print_results,
        raise_on_error=config.raise_on_error,
    )


def _quality_payload(
    result: E175MeshMotionResult,
    config: MeshQualityOutputConfig,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if config.surface:
        payload["surface"] = {
            "inverted_elements": int(
                result.surface_inversion_report.num_inverted
            ),
            "minimum_scaled_jacobian": float(
                result.surface_quality_report.minimum_scaled_jacobian
            ),
            "scaled_jacobian_p05": float(
                result.surface_quality_report.scaled_jacobian_p05
            ),
            "maximum_aspect_ratio": float(
                result.surface_quality_report.maximum_aspect_ratio
            ),
        }
    if config.volume:
        payload["volume"] = result.volume_quality_summary
    return payload


def main() -> E175DAFoamResult:
    # Fail before an expensive mesh-motion setup when no OpenFOAM case exists.
    _require_case_directory(CASE)
    try:
        from mpi4py import MPI
    except ImportError as error:
        raise RuntimeError(
            "mpi4py is unavailable. Source the DAFoam environment and launch "
            "this module with mpirun."
        ) from error

    comm = MPI.COMM_WORLD
    backend = create_dafoam_backend(FLOW, CASE, MODEL_FILES, comm)

    recorder = csdl.Recorder(inline=True)
    recorder.start()
    geometry_variables = create_geometry_design_variables()
    result = build_cfd_analysis(
        recorder,
        MODEL_FILES,
        geometry_variables,
        MESH_MOTION,
        FLOW,
        backend,
    )

    if (
        END_TO_END_DERIVATIVE_CHECK.enabled
        and MESH_MOTION.finite_difference.enabled
    ):
        raise ValueError(
            "Enable either END_TO_END_DERIVATIVE_CHECK or the generic "
            "MESH_MOTION finite-difference sweep, not both."
        )
    if END_TO_END_DERIVATIVE_CHECK.enabled:
        configure_end_to_end_derivative_check(
            result,
            END_TO_END_DERIVATIVE_CHECK,
        )
    elif MESH_MOTION.finite_difference.enabled:
        select_fd_objective(
            result.mesh_motion,
            MESH_MOTION.finite_difference.objective,
    )
    recorder.stop()

    if END_TO_END_DERIVATIVE_CHECK.enabled:
        run_end_to_end_derivative_check(
            recorder,
            END_TO_END_DERIVATIVE_CHECK,
        )
    elif MESH_MOTION.finite_difference.enabled:
        run_fd_sweep(
            recorder,
            MESH_MOTION.finite_difference.step_sizes,
        )

    if comm.rank == 0:
        case_directory = _require_case_directory(CASE)
        results_path = CASE.results_file
        if not results_path.is_absolute():
            results_path = case_directory / results_path
        payload = {
            "case_directory": str(case_directory),
            "mpi_ranks": int(comm.size),
            "geometry_design_variables": {
                name: np.asarray(variable.value).tolist()
                for name, variable in geometry_variables.as_dict().items()
            },
            "flow_config": asdict(FLOW),
            "mesh_quality": _quality_payload(
                result.mesh_motion,
                MESH_MOTION.quality,
            ),
            "functions": {
                name: float(np.asarray(variable.value).reshape(-1)[0])
                for name, variable in result.flow_outputs.items()
            },
        }
        results_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(payload, indent=2, sort_keys=True), flush=True)
    return result


if __name__ == "__main__":
    main()
