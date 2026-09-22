"""Validation of the small E175 asset set retained for overhaul examples."""

from pathlib import Path

import numpy as np
import pytest

from bsm3.preprocessing import import_mesh, import_trusted_polygon_pickle


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIRECTORY = (
    REPOSITORY_ROOT / "bsm3" / "core" / "boundary_surface_movement"
)
STEP_FILE = ASSET_DIRECTORY / "embraer_175_no_winglets.stp"
R1_DIRECTORY = ASSET_DIRECTORY / "fluent_R1_tet_euler_volume_mesh"
R1_WALL_FILE = R1_DIRECTORY / "e175_fluent_R1_aircraft_wall_tri.msh"
R1_WALL_MAP_FILE = (
    R1_DIRECTORY / "e175_fluent_R1_aircraft_wall_tri.volume_map.npz"
)
QUAD_PANEL_FILE = (
    ASSET_DIRECTORY / "embraer_175_quad_dominant_symmetric_no_winglets.msh"
)
MIXED_NGON_FILE = ASSET_DIRECTORY / "wall_surface.pkl"
CURATED_ASSETS = (
    STEP_FILE,
    R1_WALL_FILE,
    R1_WALL_MAP_FILE,
    QUAD_PANEL_FILE,
    MIXED_NGON_FILE,
)
requires_curated_assets = pytest.mark.skipif(
    not all(path.is_file() for path in CURATED_ASSETS),
    reason="curated E175 assets are not available in this checkout",
)


def test_generic_mesh_import_does_not_dispatch_pickle():
    """Require callers to opt in explicitly before executing pickle data."""
    with pytest.raises(ValueError, match="Unsupported mesh format"):
        import_mesh(Path("untrusted.pkl"))


@pytest.mark.integration
@requires_curated_assets
def test_curated_e175_surface_assets_load_with_expected_topology():
    """Load each curated surface mesh and verify its distinguishing topology."""
    assert STEP_FILE.is_file()

    triangle_wall = import_mesh(R1_WALL_FILE)
    assert triangle_wall.vertices.shape == (16400, 3)
    assert triangle_wall.cell_blocks["triangle"].shape == (32522, 3)

    quad_panel = import_mesh(QUAD_PANEL_FILE)
    assert quad_panel.vertices.shape == (14411, 3)
    assert quad_panel.cell_blocks["quad"].shape == (13696, 4)

    mixed_ngon = import_trusted_polygon_pickle(MIXED_NGON_FILE)
    assert mixed_ngon.vertices.shape == (79207, 3)
    assert mixed_ngon.cell_blocks["polygon6"].shape == (28190, 6)
    assert {"quad", "polygon5", "polygon6", "polygon7"} <= set(
        mixed_ngon.cell_blocks
    )


@pytest.mark.integration
@requires_curated_assets
def test_curated_r1_wall_map_matches_the_triangle_wall():
    """Check the retained R1 wall-to-volume metadata against the wall mesh."""
    wall = import_mesh(R1_WALL_FILE)
    with np.load(R1_WALL_MAP_FILE) as mapping:
        wall_to_volume = np.asarray(mapping["wall_to_volume"], dtype=np.int64)
        baseline_wall = np.asarray(mapping["baseline_wall_vertices"], dtype=float)
        triangles = np.asarray(mapping["surface_triangles"], dtype=np.int64)

    assert wall_to_volume.shape == (wall.vertices.shape[0],)
    np.testing.assert_allclose(baseline_wall, wall.vertices, atol=0.0)
    np.testing.assert_array_equal(triangles, wall.cell_blocks["triangle"])
