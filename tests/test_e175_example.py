"""End-to-end and structural checks for the flagship E175 example."""

import ast
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PATH = REPOSITORY_ROOT / "examples" / "e175_surface_deformation.py"
ASSET_DIRECTORY = (
    REPOSITORY_ROOT / "bsm3" / "core" / "boundary_surface_movement"
)
STEP_FILE = ASSET_DIRECTORY / "embraer_175_no_winglets.stp"
TRIANGLE_SURFACE_FILE = (
    ASSET_DIRECTORY
    / "fluent_R1_tet_euler_volume_mesh"
    / "e175_fluent_R1_aircraft_wall_tri.msh"
)
QUAD_SURFACE_FILE = (
    ASSET_DIRECTORY / "embraer_175_quad_dominant_symmetric_no_winglets.msh"
)

requires_assets = pytest.mark.skipif(
    not (STEP_FILE.is_file() and TRIANGLE_SURFACE_FILE.is_file()),
    reason="Curated E175 example assets are not present in this checkout.",
)


def _load_example():
    """Import the example module from the repository ``examples`` directory."""
    if str(REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(REPOSITORY_ROOT))
    import examples.e175_surface_deformation as example

    return example


def test_example_is_small_and_uncluttered():
    """Enforce the example's shape so it stays readable."""
    source = EXAMPLE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = [
        node
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    assert len(source.splitlines()) <= 220
    assert len(imports) <= 5
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    assert [node.name for node in functions] == ["main"]
    assert ast.get_docstring(tree)

    for forbidden in (
        "argparse",
        "argv",
        "mesh_kind",
        "ExampleRun",
        "dataclass",
        "_wing_coefficients",
        "_tail_coefficients",
        "_fuselage_coefficients",
        "_surface_cells",
        "_polygon_normals",
        "_count_polygon_folds",
        "sys.path",
    ):
        assert forbidden not in source, forbidden

    positions = [source.index(f"# {index}.") for index in range(1, 6)]
    assert positions == sorted(positions)


def test_quad_path_is_a_file_swap_with_the_same_regularization():
    """The quad mesh is selected by path alone, with one shared setting."""
    source = EXAMPLE_PATH.read_text(encoding="utf-8")
    assert "QUAD_SURFACE_MESH_FILE" in source
    assert "PolygonRegularization(weight=0.3)" in source
    # A single regularization setting serves both meshes: no topology label,
    # no branch, and no second configuration block.
    assert source.count("PolygonRegularization(") == 1
    assert "if " not in source.split("def main(")[1].split("return result")[0]


@pytest.mark.integration
@pytest.mark.timeout(600)
@requires_assets
def test_example_deforms_the_triangle_wall_without_folds(tmp_path):
    """Run the example end to end and require a valid deformed surface."""
    example = _load_example()
    result = example.main(
        surface_mesh_file=TRIANGLE_SURFACE_FILE,
        cache_directory=tmp_path / "cache",
    )

    assert result.surface_coordinates.value.shape[0] == 16400
    assert result.surface_cell_count == 32522
    assert result.surface_fold_count == 0
    assert result.baseline_inversion_report.num_inverted == 0
    assert result.surface_inversion_report.num_inverted == 0
    assert result.surface_quality_report.degenerate_elements == 0
    assert result.elapsed_seconds > 0.0
    assert result.recorder is not None
    # The triangle wall carries no affine hourglass mode, so a positive
    # polygon-regularization weight is simply inapplicable here.
    assert result.surface_ngon_mode_count == 0
