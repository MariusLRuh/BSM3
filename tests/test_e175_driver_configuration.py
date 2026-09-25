from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import csdl_alpha as csdl
import pytest

from bsm3.core.boundary_surface_movement.cfd_mesh_dafoam_analysis import (
    EndToEndDerivativeCheckConfig,
    configure_end_to_end_derivative_check,
    run_end_to_end_derivative_check,
)
from bsm3.core.boundary_surface_movement.mesh_motion_config import (
    InputFiles,
    PolygonRegularization,
    MeshMotion,
    SurfaceMotion,
    VolumeMotion,
)


PACKAGE_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "bsm3"
    / "core"
    / "boundary_surface_movement"
)


def test_public_e175_drivers_do_not_use_cli_configuration():
    for filename in (
        "cfd_mesh_movement_test.py",
        "cfd_mesh_dafoam_analysis.py",
    ):
        source = (PACKAGE_DIRECTORY / filename).read_text(encoding="utf-8")
        assert "argparse" not in source
        assert "parse_args(" not in source

    surface_source = (
        PACKAGE_DIRECTORY / "cfd_mesh_movement_test.py"
    ).read_text(encoding="utf-8")
    assert "os.environ" not in surface_source

    dafoam_source = (
        PACKAGE_DIRECTORY / "cfd_mesh_dafoam_analysis.py"
    ).read_text(encoding="utf-8")
    assert dafoam_source.count("os.environ.get(") == 1
    assert '"DAFOAM_CASE_DIRECTORY"' in dafoam_source


def test_default_mesh_motion_is_surface_only_and_headless():
    """The safe default runs surface-only, headless, and writes nothing."""
    config = MeshMotion()
    assert config.surface.distance_weighting.enabled
    # Surface-only and headless by default; the DAFoam driver opts in to
    # volume motion and CFD diagnostics explicitly.
    assert config.volume.mode == "off"
    assert config.volume.write_meshes is False
    assert config.quality.surface is True
    assert config.quality.volume is False
    assert config.quality.gmsh_volume_metrics is False
    assert config.visualization.enabled is False
    assert config.derivative_check.enabled is False


def test_dafoam_driver_opts_into_volume_and_cfd_behaviour():
    """The tracked DAFoam driver still requests volume motion explicitly."""
    from bsm3.core.boundary_surface_movement import cfd_mesh_dafoam_analysis

    motion = cfd_mesh_dafoam_analysis.MESH_MOTION
    assert motion.volume.mode == "elasticity"
    assert motion.volume.load_mode == "final"
    assert motion.volume.methods == ("elasticity",)
    assert motion.quality.volume is True
    assert motion.quality.gmsh_volume_metrics is True


def test_public_drivers_expose_explicit_matching_model_files():
    from bsm3.core.boundary_surface_movement import (
        cfd_mesh_dafoam_analysis,
        cfd_mesh_movement_test,
    )

    movement_files = cfd_mesh_movement_test.MODEL_FILES
    assert isinstance(movement_files, InputFiles)
    assert movement_files.geometry_file.name == "embraer_175_no_winglets.stp"
    assert (
        movement_files.surface_mesh_file.name
        == "e175_fluent_R4_aircraft_wall_tri.msh"
    )
    assert (
        movement_files.volume_mesh_file.name
        == "e175_fluent_R4_tet_euler_volume.msh"
    )
    assert (
        movement_files.volume_wall_map_file.name
        == "e175_fluent_R4_aircraft_wall_tri.volume_map.npz"
    )
    assert cfd_mesh_movement_test.MESH_MOTION.volume.mode == "off"
    assert (
        cfd_mesh_movement_test.MESH_MOTION.volume.load_mode
        == "synchronized"
    )
    # The wall extracted from the volume mesh is already the y >= 0 half.
    assert cfd_mesh_movement_test.MESH_MOTION.symmetry

    dafoam_files = cfd_mesh_dafoam_analysis.MODEL_FILES
    assert isinstance(dafoam_files, InputFiles)
    assert dafoam_files.geometry_file.name == "embraer_175_no_winglets.stp"
    assert dafoam_files.surface_mesh_file.name == "e175_openvsp_aircraft_wall.msh"
    assert dafoam_files.volume_mesh_file.name == "e175_euler_volume.msh"
    assert (
        dafoam_files.volume_wall_map_file.name
        == "e175_openvsp_aircraft_wall.volume_map.npz"
    )
    assert dafoam_files.geometry_file.is_file()
    assert dafoam_files.surface_mesh_file.is_file()
    assert dafoam_files.volume_mesh_file.is_file()
    assert dafoam_files.volume_wall_map_file.is_file()

    dafoam_source = (
        PACKAGE_DIRECTORY / "cfd_mesh_dafoam_analysis.py"
    ).read_text(encoding="utf-8")
    assert "mesh_file=input_files.volume_mesh_file" in dafoam_source
    assert "read_gmsh22_volume(input_files.volume_mesh_file)" in dafoam_source
@pytest.mark.integration
def test_local_r4_driver_assets_exist_when_available():
    """Validate the local R4 asset set without requiring it in fresh clones."""
    from bsm3.core.boundary_surface_movement import cfd_mesh_movement_test

    model_files = cfd_mesh_movement_test.MODEL_FILES
    local_assets = (
        model_files.geometry_file,
        model_files.surface_mesh_file,
        model_files.volume_mesh_file,
        model_files.volume_wall_map_file,
    )
    missing = [path for path in local_assets if not path.is_file()]
    if missing:
        pytest.skip(
            "local R4 assets are unavailable: "
            + ", ".join(path.name for path in missing)
        )
    assert all(path.is_file() for path in local_assets)


def test_quad_diagonal_controls_are_validated():
    with pytest.raises(ValueError, match="finite and non-negative"):
        SurfaceMotion(quad_diagonal_weight=-0.1)
    with pytest.raises(ValueError, match="quad_bracing_mode"):
        SurfaceMotion(quad_bracing_mode="unknown")


def test_ngon_affine_weight_is_validated():
    with pytest.raises(ValueError, match="finite and nonnegative"):
        PolygonRegularization(weight=-0.1)


def test_invalid_synchronized_name_is_rejected():
    with pytest.raises(ValueError, match="final or synchronized"):
        VolumeMotion(load_mode="last")


def test_independent_synchronized_volume_steps_are_validated():
    config = VolumeMotion(
        load_mode="synchronized", synchronized_load_steps=5
    )
    assert config.synchronized_load_steps == 5
    with pytest.raises(ValueError, match="must be positive"):
        VolumeMotion(
            load_mode="synchronized", synchronized_load_steps=0
        )
    with pytest.raises(ValueError, match="requires synchronized mode"):
        VolumeMotion(load_mode="final", synchronized_load_steps=5)


def test_end_to_end_cl_constraint_cd_objective_uses_py_simulator():
    recorder = csdl.Recorder(inline=True)
    recorder.start()
    design_variable = csdl.Variable(name="x", value=0.25)
    design_variable.set_as_design_variable()
    result = SimpleNamespace(
        cl=2.0 * design_variable,
        cd=design_variable**2,
    )
    config = EndToEndDerivativeCheckConfig(
        enabled=True,
        lift_constraint_target=0.5,
        step_size=1.0e-6,
        print_results=False,
    )
    configure_end_to_end_derivative_check(result, config)
    recorder.stop()

    checks = run_end_to_end_derivative_check(recorder, config)
    assert checks
    assert max(float(entry["rel_error"]) for entry in checks.values()) < 1.0e-5


def test_e175_dafoam_result_mesh_motion_is_optional():
    """Require the optional annotation the rank-0 snapshot actually needs."""
    import dataclasses
    import typing

    from bsm3.core.boundary_surface_movement.cfd_mesh_dafoam_analysis import (
        E175DAFoamResult,
    )
    from bsm3.core.boundary_surface_movement.mesh_motion_config import (
        MeshMotionResult,
    )

    field = {f.name: f for f in dataclasses.fields(E175DAFoamResult)}[
        "mesh_motion"
    ]
    assert field.type == "MeshMotionResult | None"

    hints = typing.get_type_hints(E175DAFoamResult)
    assert hints["mesh_motion"] == typing.Optional[MeshMotionResult]

    # A non-root or lazy-root construction stores None without a type error.
    result = E175DAFoamResult(
        mesh_motion=None, flow_outputs={}, cl=None, cd=None
    )
    assert result.mesh_motion is None
