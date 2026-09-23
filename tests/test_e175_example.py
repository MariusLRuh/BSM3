"""End-to-end and structural checks for the flagship E175 example."""

import ast
import sys
from pathlib import Path

import csdl_alpha as csdl
import numpy as np
import pytest

import bsm3.mesh_motion as mm

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
    assert result.initial_inversion_report.num_inverted == 0
    assert result.preprojection_inversion_report.num_inverted == 0
    assert result.surface_inversion_report.num_inverted == 0
    assert result.surface_quality_report.degenerate_elements == 0
    assert result.elapsed_seconds > 0.0
    assert result.recorder is not None
    # The triangle wall carries no affine hourglass mode, so a positive
    # polygon-regularization weight is simply inapplicable here.
    assert result.surface_ngon_mode_count == 0


# ---------------------------------------------------------------------------
# Recorder lifecycle: BSM3 never owns global CSDL state.
# ---------------------------------------------------------------------------


def _active_recorder():
    """Return the active CSDL recorder, or ``None`` when there is none."""
    try:
        return csdl.get_current_recorder()
    except Exception:
        return None


def test_geometry_model_construction_does_not_touch_recorder_state():
    """Constructing a model must not start or adopt a recorder."""
    before = _active_recorder()
    mm.GeometryModel()
    assert _active_recorder() is before


def test_design_variable_without_recorder_raises_clearly():
    """A design variable needs a caller-started recorder."""
    assert _active_recorder() is None
    geometry = mm.GeometryModel()
    with pytest.raises(RuntimeError, match="recorder must be active"):
        geometry.design_variable("x", 1.0)


def test_run_neither_starts_nor_stops_the_supplied_recorder():
    """``mm.run`` borrows the recorder; it never owns its lifecycle."""
    recorder = csdl.Recorder(inline=True)
    recorder.start()
    try:
        geometry = mm.GeometryModel()
        geometry.design_variable("x", 1.0)
        assert _active_recorder() is recorder
        # A failing run must leave ownership exactly as the caller left it.
        with pytest.raises(Exception):
            mm.run(
                inputs=mm.InputFiles(
                    geometry_file=Path("missing.stp"),
                    surface_mesh_file=Path("missing.msh"),
                ),
                geometry=geometry,
                motion=mm.MeshMotion(),
                recorder=recorder,
            )
        assert _active_recorder() is recorder
    finally:
        recorder.stop()
    assert _active_recorder() is None


# ---------------------------------------------------------------------------
# External coefficients are a first-class entry point.
# ---------------------------------------------------------------------------


class _Patch:
    """Minimal stand-in for an LFS patch holding coefficients."""

    def __init__(self, rows):
        self.coefficients = csdl.Variable(value=np.zeros((rows, 3)))


class _Component:
    """Minimal stand-in for an imported LFS component."""

    def __init__(self, rows_by_patch):
        self.functions = {
            patch: _Patch(rows) for patch, rows in rows_by_patch.items()
        }


def _resolver():
    """Return the private external-coefficient resolver under test."""
    from bsm3.core.boundary_surface_movement.geometry_model import (
        _resolve_external_coefficients,
    )

    return _resolve_external_coefficients


def test_external_stacked_variable_is_accepted_and_preserved():
    """A stacked CSDL variable passes through without NumPy conversion."""
    recorder = csdl.Recorder(inline=True)
    recorder.start()
    try:
        component = _Component({0: 4, 5: 6})
        stacked = csdl.Variable(value=np.ones((10, 3)))
        resolved = _resolver()(component, stacked, "wing")
        assert isinstance(resolved, csdl.Variable)
        assert resolved.shape == (10, 3)
    finally:
        recorder.stop()


def test_external_per_patch_mapping_is_accepted():
    """A patch-ID mapping is stacked in sorted patch-ID order."""
    recorder = csdl.Recorder(inline=True)
    recorder.start()
    try:
        component = _Component({0: 4, 5: 6})
        mapping = {
            0: csdl.Variable(value=np.ones((4, 3))),
            5: csdl.Variable(value=np.full((6, 3), 2.0)),
        }
        resolved = _resolver()(component, mapping, "wing")
        assert isinstance(resolved, csdl.Variable)
        assert resolved.shape == (10, 3)
    finally:
        recorder.stop()


def test_external_coefficient_validation_rejects_bad_input():
    """Missing keys, extra keys, and wrong shapes fail with clear errors."""
    recorder = csdl.Recorder(inline=True)
    recorder.start()
    try:
        component = _Component({0: 4, 5: 6})
        resolve = _resolver()
        with pytest.raises(ValueError, match="wrong patch"):
            resolve(component, {0: np.ones((4, 3))}, "wing")
        with pytest.raises(ValueError, match="wrong patch"):
            resolve(
                component,
                {0: np.ones((4, 3)), 5: np.ones((6, 3)), 9: np.ones((2, 3))},
                "wing",
            )
        with pytest.raises(ValueError, match="coefficient rows"):
            resolve(
                component,
                {0: np.ones((3, 3)), 5: np.ones((6, 3))},
                "wing",
            )
        with pytest.raises(ValueError, match="trailing dimension of 3"):
            resolve(
                component,
                {0: np.ones((4, 2)), 5: np.ones((6, 2))},
                "wing",
            )
        with pytest.raises(ValueError, match=r"shape \(N, 3\)"):
            resolve(component, np.ones((10, 2)), "wing")
        with pytest.raises(ValueError, match="10 rows"):
            resolve(component, np.ones((9, 3)), "wing")
    finally:
        recorder.stop()


def test_add_component_interpolates_and_reaches_the_target_exactly():
    """Load fraction 1 hands the exact external target to the solve chain."""
    recorder = csdl.Recorder(inline=True)
    recorder.start()
    try:
        component = _Component({0: 4, 5: 6})
        target = np.arange(30, dtype=float).reshape((10, 3))
        geometry = mm.GeometryModel()
        geometry.add_component(
            name="wing",
            search_name="wing",
            deformed_coefficients=target,
        )
        build = geometry.component_records[0].coefficient_builder
        full = np.asarray(build(component, 1.0, {}), dtype=float)
        half = np.asarray(build(component, 0.5, {}), dtype=float)
        baseline = np.zeros((10, 3))
        np.testing.assert_allclose(full, target)
        np.testing.assert_allclose(half, baseline + 0.5 * (target - baseline))
    finally:
        recorder.stop()


def test_validate_does_not_require_a_model_owned_design_variable():
    """External parameterizations own their variables; none is required."""
    recorder = csdl.Recorder(inline=True)
    recorder.start()
    try:
        geometry = mm.GeometryModel()
        geometry.add_component(
            name="wing",
            search_name="wing",
            deformed_coefficients=np.zeros((4, 3)),
        )
        geometry.validate()
    finally:
        recorder.stop()


@pytest.mark.integration
@pytest.mark.timeout(900)
@requires_assets
def test_quad_panel_introduces_no_new_inverted_elements(tmp_path):
    """The quad asset's pre-existing inversions must not grow."""
    example = _load_example()
    result = example.main(
        surface_mesh_file=QUAD_SURFACE_FILE,
        cache_directory=tmp_path / "quad-cache",
    )

    initial = set(
        int(i) for i in result.initial_inversion_report.inverted_element_ids
    )
    preprojection = set(
        int(i)
        for i in result.preprojection_inversion_report.inverted_element_ids
    )
    final = set(
        int(i) for i in result.surface_inversion_report.inverted_element_ids
    )

    # The unchanged tracked asset's own input reference.
    assert len(initial) == 114
    assert result.surface_quality_report.degenerate_elements == 0
    # Compare ID sets, not only counts: the deformation must introduce no
    # inverted element that the input did not already have.
    assert not preprojection - initial
    assert not final - initial
    assert result.surface_fold_count == 0
    # Real quad cells activate the affine model.
    assert result.surface_ngon_mode_count > 0


@pytest.mark.integration
@pytest.mark.timeout(900)
@requires_assets
def test_external_coefficients_drive_the_real_pipeline(tmp_path):
    """An externally produced coefficient set reaches the full solve chain.

    This mirrors how another package drives BSM3: it imports the same STEP
    body, deforms the coefficients with its own differentiable
    parameterization, and hands the result to ``add_component``. BSM3 supplies
    no transformation here.
    """
    import lsdo_function_spaces as lfs

    import bsm3
    from bsm3.core.boundary_surface_movement import (
        stack_component_coefficients,
    )

    recorder = csdl.Recorder(inline=True)
    recorder.start()
    try:
        cache = tmp_path / "external-cache"
        cache.mkdir(parents=True, exist_ok=True)
        imported = lfs.import_file_patched(STEP_FILE, parallelize=False)
        wing, tail, fuselage = bsm3.preprocessing.create_components(
            geometry=imported,
            search_names=["wing", "HT", "fuselage"],
        )

        geometry = mm.GeometryModel()
        shift = geometry.design_variable("external_shift", 0.004)
        free_regions = {
            "wing": {"y": (None, 0.3, "abs")},
            "tail": {"y": (None, 0.3, "abs")},
            "fuselage": {"x": (0.05, 0.97, "extent")},
        }
        for name, search, component in (
            ("wing", "wing", wing),
            ("tail", "HT", tail),
            ("fuselage", "fuselage", fuselage),
        ):
            baseline = stack_component_coefficients(component)
            # An external, differentiable target built outside BSM3: a rigid
            # chordwise shift applied to every control point.
            direction = np.zeros(baseline.shape)
            direction[:, 0] = 1.0
            geometry.add_component(
                name=name,
                search_name=search,
                deformed_coefficients=baseline + shift * direction,
                free_region=free_regions[name],
            )
        geometry.connect(
            name="wing_root",
            driving_component="wing",
            query_component="fuselage",
        )
        geometry.connect(
            name="tail_root",
            driving_component="tail",
            query_component="fuselage",
        )
        result = mm.run(
            inputs=mm.InputFiles(
                geometry_file=STEP_FILE,
                surface_mesh_file=TRIANGLE_SURFACE_FILE,
                cache_directory=cache,
            ),
            geometry=geometry,
            motion=mm.MeshMotion(
                surface=mm.SurfaceMotion(load_steps=1),
                quality=mm.QualityChecks(surface=True),
                symmetry=True,
            ),
            recorder=recorder,
        )
        objective = csdl.sum(result.surface_coordinates)
        derivative = csdl.derivative(objective, shift)
    finally:
        recorder.stop()

    assert result.surface_fold_count == 0
    assert result.surface_inversion_report.num_inverted == 0
    # The external variable must stay analytically differentiable through
    # intersections, the graph solve, and OML reprojection.
    assert abs(float(np.asarray(derivative.value).reshape(-1)[0])) > 1.0e-6


@pytest.mark.skip(
    reason="Blocked on bsm3/preprocessing/movement.py:305, outside the "
    "Turn-34 allowlist. free_region=None on every component leaves no "
    "reevaluation vertices, and np.asarray([]) yields float64 so the "
    "'local_mask &= ~assigned' bitwise-and raises TypeError. One-line fix: "
    "pass dtype=bool. Reported to Codex for an allowlist ruling."
)
@pytest.mark.integration
@requires_assets
def test_external_coefficients_with_whole_component_free_regions(tmp_path):
    """``free_region=None`` should mean the whole imported component is free."""
    raise AssertionError("Enable once the movement.py dependency is approved.")
