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
from bsm3.core.boundary_surface_movement.e175_mesh_motion_config import (
    E175ModelFiles,
    E175PipelineConfig,
    SurfaceMotionConfig,
    TangentialSmoothingConfig,
    VolumeMotionConfig,
)


PACKAGE_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "bsm3"
    / "core"
    / "boundary_surface_movement"
)


def test_public_e175_drivers_do_not_use_cli_or_environment_configuration():
    forbidden = ("argparse", "parse_args(", "os.environ")
    for filename in (
        "cfd_mesh_movement_test.py",
        "cfd_mesh_dafoam_analysis.py",
    ):
        source = (PACKAGE_DIRECTORY / filename).read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source


def test_default_volume_motion_is_final_only_and_differentiable():
    config = E175PipelineConfig()
    assert (
        config.surface_motion.tangential_smoothing.reprojection
        == "final_only"
    )
    assert config.surface_motion.graph_distance_weighting.enabled
    assert config.volume_motion.mode == "elasticity"
    assert config.volume_motion.load_mode == "final"
    assert config.volume_motion.methods == ("elasticity",)


def test_public_drivers_expose_explicit_matching_model_files():
    from bsm3.core.boundary_surface_movement import (
        cfd_mesh_dafoam_analysis,
        cfd_mesh_movement_test,
    )

    for driver in (cfd_mesh_movement_test, cfd_mesh_dafoam_analysis):
        files = driver.MODEL_FILES
        assert isinstance(files, E175ModelFiles)
        assert files.geometry_step_file.name == "embraer_175_no_winglets.stp"
        assert files.surface_mesh_file.name == "e175_openvsp_aircraft_wall.msh"
        assert files.volume_mesh_file.name == "e175_euler_volume.msh"
        assert (
            files.volume_wall_map_file.name
            == "e175_openvsp_aircraft_wall.volume_map.npz"
        )
        assert files.geometry_step_file.is_file()
        assert files.surface_mesh_file.is_file()
        assert files.volume_mesh_file.is_file()
        assert files.volume_wall_map_file.is_file()

    dafoam_source = (
        PACKAGE_DIRECTORY / "cfd_mesh_dafoam_analysis.py"
    ).read_text(encoding="utf-8")
    assert "mesh_file=model_files.volume_mesh_file" in dafoam_source
    assert "read_gmsh22_volume(model_files.volume_mesh_file)" in dafoam_source


def test_final_only_tangential_reprojection_is_a_supported_fixed_option():
    config = SurfaceMotionConfig(
        tangential_smoothing=TangentialSmoothingConfig(
            reprojection="final_only"
        )
    )
    assert config.tangential_smoothing.reprojection == "final_only"


def test_invalid_synchronized_name_is_rejected():
    with pytest.raises(ValueError, match="final or synchronized"):
        VolumeMotionConfig(load_mode="last")


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
