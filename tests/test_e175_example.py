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
        build = geometry._component_records[0].coefficient_builder
        full = np.asarray(build(component, 1.0, {}), dtype=float)
        half = np.asarray(build(component, 0.5, {}), dtype=float)
        baseline = np.zeros((10, 3))
        np.testing.assert_allclose(full, target)
        np.testing.assert_allclose(half, baseline + 0.5 * (target - baseline))
    finally:
        recorder.stop()


def test_compiled_records_are_not_public():
    """The facade promised to hide compiled records and their callbacks."""
    geometry = mm.GeometryModel()
    assert not hasattr(geometry, "component_records")
    assert not hasattr(geometry, "intersection_records")
    # The design-variable mapping stays public.
    assert hasattr(geometry, "design_variables")


def test_unbounded_design_variable_is_registered_with_the_recorder():
    """``design_variable`` must register even without bounds or a scaler."""
    recorder = csdl.Recorder(inline=True)
    recorder.start()
    try:
        geometry = mm.GeometryModel()
        variable = geometry.design_variable("unbounded", 1.25)
        assert variable in recorder.design_variables
    finally:
        recorder.stop()


def test_example_stops_the_recorder_when_an_early_stage_fails(monkeypatch):
    """A failure in stage 2 or 3 must not leave an active recorder."""
    example = _load_example()

    def _boom(*args, **kwargs):
        raise RuntimeError("stage 2 failure")

    monkeypatch.setattr(mm.GeometryModel, "add_lifting_surface", _boom)
    assert _active_recorder() is None
    with pytest.raises(RuntimeError, match="stage 2 failure"):
        example.main()
    assert _active_recorder() is None


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

    # Pin all three unchanged-input facts, evaluated on the result's own
    # initial coordinates rather than read from the final report.
    from bsm3.core.boundary_surface_movement import evaluate_mesh_quality

    initial_quality = evaluate_mesh_quality(
        mesh=result.surface_mesh,
        vertices=np.asarray(result.initial_surface_coordinates, dtype=float),
    )
    assert len(initial) == 114
    assert initial_quality.inverted_corners == 114
    assert initial_quality.degenerate_elements == 0
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
    """A substantial relative external wing deformation, verified against FD.

    This mirrors how another package drives BSM3: it imports the same STEP
    body, deforms the coefficients with its own differentiable
    parameterization, and hands the result to ``add_component``. BSM3 supplies
    no transformation. Only the wing moves, so the intersection and motion
    chain is genuinely exercised rather than a global rigid translation.
    """
    import os

    import lsdo_function_spaces as lfs

    import bsm3
    from bsm3.core.boundary_surface_movement import (
        stack_component_coefficients,
    )

    wing_shift_metres = 0.35

    recorder = csdl.Recorder(inline=True)
    recorder.start()
    try:
        cache = tmp_path / "external-cache"
        cache.mkdir(parents=True, exist_ok=True)
        # lsdo_function_spaces writes its STEP-import cache relative to the
        # process working directory. The library contains that side effect
        # internally; a direct import here must contain it too.
        previous_directory = Path.cwd()
        try:
            os.chdir(cache)
            imported = lfs.import_file_patched(STEP_FILE, parallelize=False)
        finally:
            os.chdir(previous_directory)
        wing, tail, fuselage = bsm3.preprocessing.create_components(
            geometry=imported,
            search_names=["wing", "HT", "fuselage"],
        )

        geometry = mm.GeometryModel()
        shift = geometry.design_variable("external_wing_shift", 1.0)
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
            if name == "wing":
                # Only the wing moves: a substantial chordwise shift built
                # entirely outside BSM3.
                direction = np.zeros(baseline.shape)
                direction[:, 0] = wing_shift_metres
                target = baseline + shift * direction
            else:
                target = baseline
            geometry.add_component(
                name=name,
                search_name=search,
                deformed_coefficients=target,
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
                surface=mm.SurfaceMotion(load_steps=2),
                quality=mm.QualityChecks(surface=True),
                symmetry=True,
            ),
            recorder=recorder,
        )
        # A well-scaled scalar built from the FINAL REPROJECTED coordinates:
        # mean nodal displacement relative to the initial mesh.
        initial = np.asarray(result.initial_surface_coordinates, dtype=float)
        displacement = result.surface_coordinates - initial
        objective = csdl.average(displacement * displacement)
        objective.add_name("mean_squared_nodal_displacement")
        objective.set_as_objective()
        analytic = csdl.derivative(objective, shift)
    finally:
        recorder.stop()

    final = np.asarray(result.surface_coordinates.value, dtype=float)
    assert np.all(np.isfinite(final))
    assert result.surface_fold_count == 0
    assert result.surface_inversion_report.num_inverted == 0
    assert not (
        set(int(i) for i in result.surface_inversion_report.inverted_element_ids)
        - set(
            int(i)
            for i in result.initial_inversion_report.inverted_element_ids
        )
    )
    max_displacement = float(
        np.max(np.linalg.norm(final - initial, axis=1))
    )
    assert max_displacement > 0.05, max_displacement

    analytic_value = float(np.asarray(analytic.value).reshape(-1)[0])
    assert abs(analytic_value) > 1.0e-6

    # Centered finite difference, best step, matching the derivative gate.
    simulator = csdl.experimental.JaxSimulator(recorder=recorder, gpu=False)
    baseline_value = np.asarray(shift.value).copy()
    best_error = float("inf")
    best_step = None
    best_fd = None
    for step in (1.0e-4, 1.0e-5, 1.0e-6):
        simulator[shift] = baseline_value + step
        simulator.run()
        plus = float(np.asarray(simulator[objective]).reshape(-1)[0])
        simulator[shift] = baseline_value - step
        simulator.run()
        minus = float(np.asarray(simulator[objective]).reshape(-1)[0])
        centered = (plus - minus) / (2.0 * step)
        error = abs(analytic_value - centered) / max(
            abs(analytic_value), abs(centered), 1.0e-14
        )
        if error < best_error:
            best_error, best_step, best_fd = error, step, centered
    simulator[shift] = baseline_value
    print(
        f"[external-fd] wing_shift={wing_shift_metres} "
        f"analytic={analytic_value:.10e} fd={best_fd:.10e} "
        f"step={best_step:.0e} rel_error={best_error:.3e} "
        f"max_disp={max_displacement:.4f}"
    )
    assert best_error < 1.0e-5, best_error


@pytest.mark.integration
@pytest.mark.timeout(900)
@requires_assets
def test_external_coefficients_with_whole_component_free_regions(tmp_path):
    """``free_region=None`` means the whole imported component is free.

    With no reevaluation vertices at all, the preprocessing mask reduction
    used to raise ``TypeError``; this is the end-to-end regression for that
    fix.
    """
    import os

    import lsdo_function_spaces as lfs

    import bsm3
    from bsm3.core.boundary_surface_movement import (
        stack_component_coefficients,
    )

    recorder = csdl.Recorder(inline=True)
    recorder.start()
    try:
        cache = tmp_path / "whole-free-cache"
        cache.mkdir(parents=True, exist_ok=True)
        previous_directory = Path.cwd()
        try:
            os.chdir(cache)
            imported = lfs.import_file_patched(STEP_FILE, parallelize=False)
        finally:
            os.chdir(previous_directory)
        wing, tail, fuselage = bsm3.preprocessing.create_components(
            geometry=imported,
            search_names=["wing", "HT", "fuselage"],
        )

        geometry = mm.GeometryModel()
        shift = geometry.design_variable("whole_free_shift", 1.0)
        for name, search, component in (
            ("wing", "wing", wing),
            ("tail", "HT", tail),
            ("fuselage", "fuselage", fuselage),
        ):
            baseline = stack_component_coefficients(component)
            if name == "wing":
                direction = np.zeros(baseline.shape)
                direction[:, 0] = 0.05
                target = baseline + shift * direction
            else:
                target = baseline
            # No free region: the whole imported component is free.
            geometry.add_component(
                name=name,
                search_name=search,
                deformed_coefficients=target,
                free_region=None,
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
                surface=mm.SurfaceMotion(load_steps=2),
                quality=mm.QualityChecks(surface=True),
                symmetry=True,
            ),
            recorder=recorder,
        )
    finally:
        recorder.stop()

    final = np.asarray(result.surface_coordinates.value, dtype=float)
    assert final.shape == (16400, 3)
    assert np.all(np.isfinite(final))
    assert result.surface_fold_count == 0
    initial_ids = set(
        int(i) for i in result.initial_inversion_report.inverted_element_ids
    )
    assert not (
        set(
            int(i)
            for i in result.preprojection_inversion_report.inverted_element_ids
        )
        - initial_ids
    )
    assert not (
        set(
            int(i)
            for i in result.surface_inversion_report.inverted_element_ids
        )
        - initial_ids
    )


@pytest.mark.integration
@pytest.mark.timeout(900)
@requires_assets
def test_triangle_wall_at_full_deformation_scale(tmp_path):
    """Deliberate large-deformation coverage on the triangle wall.

    ``deformation_scale=1.0`` is the full Turn-32 design point: 0.35 m wing
    shift, 0.75 deg wing incidence, 71.5 m^2 wing area, 1.2 deg tail
    incidence, and a 1.02 fuselage width scale. The quad panel is
    sliver-sensitive and keeps its own smaller supported point.
    """
    example = _load_example()
    result = example.main(
        surface_mesh_file=TRIANGLE_SURFACE_FILE,
        cache_directory=tmp_path / "full-scale-cache",
        deformation_scale=1.0,
    )

    initial = np.asarray(result.initial_surface_coordinates, dtype=float)
    final = np.asarray(result.surface_coordinates.value, dtype=float)
    assert final.shape == (16400, 3)
    assert np.all(np.isfinite(final))

    initial_ids = set(
        int(i) for i in result.initial_inversion_report.inverted_element_ids
    )
    preprojection_ids = set(
        int(i)
        for i in result.preprojection_inversion_report.inverted_element_ids
    )
    final_ids = set(
        int(i) for i in result.surface_inversion_report.inverted_element_ids
    )
    assert not preprojection_ids - initial_ids
    assert not final_ids - initial_ids
    assert result.surface_fold_count == 0

    # Guard against the case silently collapsing to a near-null deformation.
    max_displacement = float(np.max(np.linalg.norm(final - initial, axis=1)))
    print(f"[full-scale-tri] max nodal displacement {max_displacement:.4f} m")
    assert max_displacement > 0.1, max_displacement
