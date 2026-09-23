"""End-to-end protection for the documented E175 surface example."""

import numpy as np
import pytest

from examples import e175_surface_deformation as example


CURATED_ASSETS = (
    example.STEP_FILE,
    example.TRI_SURFACE_FILE,
    example.QUAD_SURFACE_FILE,
)
requires_curated_assets = pytest.mark.skipif(
    not all(path.is_file() for path in CURATED_ASSETS),
    reason="curated E175 assets are not available in this checkout",
)


def test_quad_configuration_enables_ngon_affine_regularization():
    """Keep the documented real-mesh n-gon switch active."""

    config = example.build_pipeline_config("quad")
    assert config.surface_motion.ngon_affine.weight > 0.0
    assert example.build_model_files("quad").surface_mesh_file == (
        example.QUAD_SURFACE_FILE
    )


@pytest.mark.integration
# A cold local run measured 106 s; 600 s is the explicit CI/turn stop ceiling
# and leaves headroom for slower runners without accepting an unbounded test.
@pytest.mark.timeout(600)
@requires_curated_assets
def test_triangle_example_runs_end_to_end():
    """Deform the tracked triangle wall without folds or inversions."""

    run = example.run_example(mesh_kind="tri", print_report=False)
    result = run.result

    assert run.vertex_count == result.initial_surface_coordinates.shape[0]
    assert np.asarray(result.surface_coordinates.value).shape == (
        result.initial_surface_coordinates.shape
    )
    assert run.cell_count == 32522
    assert run.fold_count == 0
    assert result.surface_inversion_report.num_inverted == 0
    assert result.surface_quality_report.inverted_elements == 0
    assert result.volume_coordinates == {}
    assert result.aerodynamic_outputs == {}

    expected_fields = {
        "model_files",
        "geometry_parameterization",
        "initial_surface_coordinates",
        "preprojected_surface_coordinates",
        "surface_coordinates",
        "volume_coordinates",
        "aerodynamic_outputs",
        "surface_inversion_report",
        "surface_quality_report",
        "volume_quality_summary",
        "volume_mesh",
        "surface_mesh",
    }
    assert expected_fields <= vars(result).keys()
