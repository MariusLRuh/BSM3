"""Reusable, configuration-driven E175 surface and volume mesh-motion pipeline.

The user-facing deformation and DAFoam drivers instantiate CSDL design
variables and configuration dataclasses explicitly, then call the builder in
this module. No run configuration is read from command-line arguments or
environment variables.
"""

from __future__ import annotations

from pathlib import Path
import time
from typing import Callable, Mapping

import csdl_alpha as csdl
import lsdo_function_spaces as lfs
import numpy as np

import bsm3
from bsm3.component_parameters import (
    FuselageParameters,
    TailParameters,
    WingParameters,
)
from bsm3.core.projections.function_set_closest_distance_custom_op import (
    FunctionSetProjectionModel,
)
from .e175_mesh_motion_config import (
    E175GeometryVariables,
    E175MeshMotionResult,
    E175ModelFiles,
    E175PipelineConfig,
    MeshQualityOutputConfig,
    VolumeMotionConfig,
)


def _load_polygon_surface_pickle(path):
    import pickle
    with open(path, "rb") as stream:
        data = pickle.load(stream)
    points = np.asarray(data["points"], dtype=float)
    connectivity = [np.asarray(face, dtype=np.int64).reshape(-1) for face in data["connectivity"]]
    return points, connectivity


def _cfd_mesh_from_pickle(path):
    """Build a MeshData from the polygonal CFD surface pickle *without*
    triangulating.  The mesh is hex-dominant; fan-triangulating an n-gon invents
    sliver cells that report spurious inversions and hands the elastic solve the
    wrong (diagonal) edges.  Instead group faces by vertex count into uniform
    blocks (``triangle``/``quad``/``polygonN``): the elasticity assembler and the
    quality/inversion check both iterate ``cell_blocks`` and are n-gon general."""
    from bsm3.preprocessing import MeshData
    points, connectivity = _load_polygon_surface_pickle(path)
    sizes = np.array([face.size for face in connectivity], dtype=np.int64)

    cell_blocks = {}
    for k in np.unique(sizes):
        key = {3: "triangle", 4: "quad"}.get(int(k), f"polygon{int(k)}")
        cell_blocks[key] = np.asarray(
            [face for face in connectivity if face.size == k], dtype=np.int64
        )
    mesh = MeshData(
        vertices=points,
        connectivity=np.empty(0, dtype=np.int64),
        cell_types=np.array([], dtype=object),
        cell_blocks=cell_blocks,
    )
    return mesh, connectivity


def _cfd_surface_cells(mesh):
    """Same cell ordering the quality report uses (tri, quad, then polygonN), so
    inverted-element ids from ``check_element_inversion`` map to the right cell."""
    ordered = ["triangle", "quad"] + [
        t for t in mesh.cell_blocks if t not in ("triangle", "quad")
    ]
    cells = []
    for cell_type in ordered:
        block = mesh.cell_blocks.get(cell_type)
        if block is None:
            continue
        for cell in np.asarray(block, dtype=np.int64):
            cells.append(cell)
    return cells


def _polygon_normals(vertices, connectivity):
    """Area-weighted (Newell) normal per polygon; used for a fold check that is
    meaningful on the original polygonal cells rather than the fan triangles.

    Vectorized over all directed edges of all polygons (scatter-add by polygon
    id) so it is O(total-edges) in NumPy rather than a Python loop per cell.
    """
    poly_ids = np.concatenate(
        [np.full(face.size, pid, dtype=np.int64) for pid, face in enumerate(connectivity)]
    )
    a_idx = np.concatenate([face for face in connectivity])
    b_idx = np.concatenate([np.roll(face, -1) for face in connectivity])
    a = vertices[a_idx]
    b = vertices[b_idx]
    contrib = np.empty_like(a)
    contrib[:, 0] = (a[:, 1] - b[:, 1]) * (a[:, 2] + b[:, 2])
    contrib[:, 1] = (a[:, 2] - b[:, 2]) * (a[:, 0] + b[:, 0])
    contrib[:, 2] = (a[:, 0] - b[:, 0]) * (a[:, 1] + b[:, 1])
    normals = np.zeros((len(connectivity), 3), dtype=float)
    np.add.at(normals, poly_ids, contrib)
    return normals


def _count_polygon_folds(initial_vertices, final_vertices, connectivity):
    """A polygon has folded if its area-weighted normal flipped direction from
    the undeformed to the deformed mesh (dot < 0)."""
    n0 = _polygon_normals(initial_vertices, connectivity)
    n1 = _polygon_normals(final_vertices, connectivity)
    dots = np.einsum("ij,ij->i", n0, n1)
    return int(np.sum(dots < 0.0)), dots


def _setup_code_signature(extra_params):
    """Fingerprint of the code + parameters that determine the cached setup
    (baseline projection ownership + seams).  Hashing the *contents* of every
    module the setup depends on means the cache is invalidated whenever any of
    that logic changes -- otherwise a cache written by an older/broken code
    version is silently reused and produces garbage (folded mesh) from a benign
    deformation, which is impossible to diagnose from the run alone."""
    import hashlib
    import importlib

    digest = hashlib.sha1()
    module_names = [
        "bsm3.preprocessing.movement",
        "bsm3.preprocessing.intersections",
        "bsm3.core.projections.warm_start_candidate_projection_numpy",
        "bsm3.core.projections.orthogonality_projection_numpy",
        "bsm3.core.projections.function_set_closest_distance_custom_op",
        "bsm3.core.boundary_surface_movement.intersections",
    ]
    for name in module_names:
        try:
            module = importlib.import_module(name)
            digest.update(Path(module.__file__).read_bytes())
        except Exception:
            digest.update(name.encode())
    digest.update(repr(extra_params).encode())
    return digest.hexdigest()


def _run_volume_motion(
    volume_mesh,
    final_wall_positions,
    wall_position_history,
    load_fractions,
    *,
    volume_config: VolumeMotionConfig,
    quality_config: MeshQualityOutputConfig,
    output_directory: Path,
    surface_mesh_file: Path,
    surface_distortion_weight: float,
):
    """Run and write the requested volume propagators.

    ``VolumeMotionConfig.load_mode`` selects the volume path independently of the number
    of surface load steps:

    * ``final`` -- one differentiable reference-stiffness ``evaluate`` solve
      driven by the final wall, factored once on the baseline volume mesh.  This
      is the default and stays in the CSDL graph even for multi-step surfaces.
    * ``synchronized`` -- reassemble/refactor from every intermediate deformed
      volume state along the wall history in NumPy; forward-only, deferred
      derivatives.

    The exact wall history and per-step wall meshes are always written so the
    volume-only replay tool can reproduce either path.
    """
    volume_load_mode = volume_config.load_mode
    volume_methods = volume_config.methods
    graph_stiffening = volume_config.graph_stiffening_exponent
    elasticity_poisson_ratio = volume_config.elasticity_poisson_ratio
    elasticity_stiffening = volume_config.elasticity_stiffening_exponent
    evaluate_gmsh_quality = quality_config.gmsh_volume_metrics
    output_directory = Path(output_directory).expanduser()

    fractions = tuple(float(value) for value in load_fractions)
    if not fractions:
        raise ValueError("Volume motion requires at least one load fraction.")
    targets = [
        np.asarray(
            item.value if hasattr(item, "value") else item,
            dtype=float,
        )
        for item in wall_position_history
    ]
    targets[-1] = np.asarray(final_wall_positions.value, dtype=float)
    history_path = (
        output_directory
        / f"e175_surface_wall_history_load{len(fractions)}.npz"
    )
    bsm3.core.boundary_surface_movement.write_wall_position_history(
        history_path,
        volume_mesh,
        targets,
        fractions,
    )
    print(
        f"[volume] exact surface history written to {history_path.resolve()}",
        flush=True,
    )
    wall_mesh_paths = []
    for step, target in enumerate(targets, start=1):
        wall_mesh_path = (
            output_directory
            / (
                f"e175_surface_wall_load{len(fractions)}"
                f"_step{step:02d}.msh"
            )
        )
        bsm3.core.boundary_surface_movement.write_aircraft_wall_gmsh22(
            volume_mesh,
            target,
            wall_mesh_path,
        )
        wall_mesh_paths.append(str(wall_mesh_path.resolve()))
    baseline_quality = (
        bsm3.core.boundary_surface_movement.evaluate_volume_quality(
            volume_mesh.vertices,
            volume_mesh.vertices,
            volume_mesh.tetrahedra,
        )
    )
    summary = {
        "volume_mesh": str(volume_mesh.source_path),
        "surface_mesh": str(surface_mesh_file.resolve()),
        "surface_load_steps": len(fractions),
        "volume_load_mode": volume_load_mode,
        "load_steps": len(fractions),
        "load_fractions": list(fractions),
        "surface_wall_history": str(history_path.resolve()),
        "surface_wall_meshes": wall_mesh_paths,
        "surface_distortion_lambda": surface_distortion_weight,
        "methods_requested": list(volume_methods),
        "baseline_quality": baseline_quality.as_dict(),
        "methods": {},
    }
    if evaluate_gmsh_quality:
        quality_started = time.perf_counter()
        summary["baseline_gmsh_quality"] = (
            bsm3.core.boundary_surface_movement.evaluate_gmsh_tetra_quality(
                volume_mesh.source_path
            )
        )
        summary["baseline_gmsh_quality_seconds"] = (
            time.perf_counter() - quality_started
        )

    volume_outputs = {}
    for method in volume_methods:
        method_started = time.perf_counter()
        if volume_load_mode == "final":
            # One differentiable reference-stiffness solve driven by the final
            # wall, regardless of the number of *surface* load steps.  The
            # operator is assembled/factored once on the baseline volume mesh.
            if method == "graph":
                system = (
                    bsm3.core.boundary_surface_movement
                    .assemble_graph_volume_system(
                        volume_mesh,
                        stiffening_exponent=graph_stiffening,
                    )
                )
            else:
                system = (
                    bsm3.core.boundary_surface_movement
                    .assemble_elastic_volume_system(
                        volume_mesh,
                        poisson_ratio=elasticity_poisson_ratio,
                        stiffening_exponent=elasticity_stiffening,
                    )
                )
            solve_started = time.perf_counter()
            volume_variable = system.evaluate(final_wall_positions)
            solve_seconds = time.perf_counter() - solve_started
            final_vertices = np.asarray(volume_variable.value, dtype=float)
            volume_outputs[method] = volume_variable
            method_summary = {
                "mode": "differentiable_reference_stiffness",
                "differentiable": True,
                "assembly_seconds": system.assembly_seconds,
                "factorization_seconds": system.factorization_seconds,
                "solve_seconds": solve_seconds,
                "factor_backend": (
                    system.factor._backend
                    if method == "elasticity"
                    else {
                        "xz": system.factor_xz._backend,
                        "y": system.factor_y._backend,
                    }
                ),
            }
            if method == "elasticity":
                method_summary["stiffness_nnz"] = system.stiffness_nnz
        else:
            load_result = (
                bsm3.core.boundary_surface_movement
                .run_forward_volume_load_steps(
                    volume_mesh,
                    targets,
                    fractions,
                    method=method,
                    graph_stiffening_exponent=graph_stiffening,
                    elasticity_poisson_ratio=elasticity_poisson_ratio,
                    elasticity_stiffening_exponent=elasticity_stiffening,
                )
            )
            final_vertices = load_result.vertices
            method_summary = {
                "mode": "forward_load_stepping_with_refactorization",
                "differentiable": False,
                "steps": [record.as_dict() for record in load_result.records],
                "total_assembly_seconds": sum(
                    record.assembly_seconds for record in load_result.records
                ),
                "total_factorization_seconds": sum(
                    record.factorization_seconds
                    for record in load_result.records
                ),
                "total_solve_seconds": sum(
                    record.solve_seconds for record in load_result.records
                ),
            }

        final_quality = (
            bsm3.core.boundary_surface_movement.evaluate_volume_quality(
                volume_mesh.vertices,
                final_vertices,
                volume_mesh.tetrahedra,
            )
        )
        method_summary["final_quality"] = final_quality.as_dict()
        output_path = (
            output_directory
            / (
                f"e175_volume_{method}_{volume_load_mode}"
                f"_load{len(fractions)}.msh"
            )
        )
        bsm3.core.boundary_surface_movement.write_deformed_gmsh22(
            volume_mesh,
            final_vertices,
            output_path,
        )
        method_summary["output_mesh"] = str(output_path.resolve())
        if evaluate_gmsh_quality:
            quality_started = time.perf_counter()
            method_summary["gmsh_quality"] = (
                bsm3.core.boundary_surface_movement
                .evaluate_gmsh_tetra_quality(output_path)
            )
            method_summary["gmsh_quality_seconds"] = (
                time.perf_counter() - quality_started
            )
        method_summary["wall_maximum_error"] = float(
            np.max(
                np.abs(
                    final_vertices[volume_mesh.aircraft_nodes]
                    - np.asarray(final_wall_positions.value, dtype=float)
                )
            )
        )
        method_summary["total_wall_seconds"] = (
            time.perf_counter() - method_started
        )
        summary["methods"][method] = method_summary

        gmsh_metrics = method_summary.get("gmsh_quality", {})
        min_sicn = gmsh_metrics.get("minSICN", {}).get("minimum")
        min_sige = gmsh_metrics.get("minSIGE", {}).get("minimum")
        print(
            f"[volume:{method}] inverted={final_quality.inverted_tetrahedra} "
            f"relative-J min/p001={final_quality.minimum_relative_jacobian:.4g}/"
            f"{final_quality.relative_jacobian_p001:.4g} "
            f"mean-ratio min/p001={final_quality.minimum_mean_ratio:.4g}/"
            f"{final_quality.mean_ratio_p001:.4g} "
            f"minSICN={min_sicn} minSIGE={min_sige} "
            f"time={method_summary['total_wall_seconds']:.2f}s",
            flush=True,
        )

    summary_path = (
        output_directory
        / (
            f"e175_volume_comparison_{volume_load_mode}"
            f"_load{len(fractions)}.json"
        )
    )
    bsm3.core.boundary_surface_movement.write_comparison_summary(
        summary_path, summary
    )
    print(f"[volume] comparison written to {summary_path.resolve()}", flush=True)
    return volume_outputs, summary


reference_wing_area = 70.0
reference_wing_aspect_ratio = 8.4

intersection_tolerance = 2e-3
bisection_tolerance = 1e-10
bisection_max_iter = 80



def build_e175_mesh_motion_model(
    *,
    recorder: csdl.Recorder,
    model_files: E175ModelFiles,
    geometry_variables: E175GeometryVariables,
    config: E175PipelineConfig,
    aerodynamic_analysis: Callable[
        [csdl.Variable], Mapping[str, csdl.Variable]
    ]
    | None = None,
    aerodynamic_volume_method: str = "elasticity",
) -> E175MeshMotionResult:
    """Build and evaluate the differentiable E175 mesh-motion pipeline.

    ``aerodynamic_analysis`` is an optional downstream CSDL builder. It receives
    the selected final volume-coordinate variable before the recorder is
    stopped and returns named aerodynamic outputs. This keeps the established
    mesh-motion regression driver reusable while allowing a clean DAFoam
    analysis driver to append ``volume mesh -> flow -> CL/CD`` to the same graph.
    """

    # The active recorder owns the variables passed to this builder. Keeping it
    # in the public signature makes recorder ownership explicit to both drivers.
    _ = recorder

    surface = config.surface_motion
    smoothing = surface.tangential_smoothing
    distance = surface.graph_distance_weighting
    distortion = surface.distortion
    final_quality = surface.final_quality
    volume = config.volume_motion

    # Local aliases keep the established numerical implementation readable
    # without dynamic module globals. Every value originates in the explicit
    # dataclasses passed by the public drivers.
    STIFFENING_EXPONENT = surface.stiffening_exponent
    ELASTIC_STRATEGY = surface.mode
    GRAPH_LOAD_STEPS = surface.load_steps
    DISTORTION_LAMBDA = distortion.weight
    DISTORTION_MODE = distortion.mode
    DISTORTION_K_AREA = distortion.area
    DISTORTION_K_DEVIATORIC = distortion.deviatoric
    DISTORTION_K_SHEAR = distortion.shear
    DISTORTION_K_ROTATION = distortion.rotation
    DISTORTION_K_NORMAL = distortion.normal
    TANGENTIAL_SMOOTHING = smoothing.enabled
    TANGENTIAL_SMOOTHING_LAYERS = smoothing.layers
    TANGENTIAL_SMOOTHING_ITERATIONS = smoothing.iterations
    TANGENTIAL_SMOOTHING_RELAXATION = smoothing.relaxation
    TANGENTIAL_SMOOTHING_PRESERVE_REFERENCE = smoothing.preserve_reference
    TANGENTIAL_SMOOTHING_REPROJECTION = smoothing.reprojection
    GRAPH_DISTANCE_WEIGHT = distance.enabled
    GRAPH_DISTANCE_BETA = distance.beta
    GRAPH_DISTANCE_LENGTH = distance.length_scale
    GRAPH_DISTANCE_CAP = distance.cap
    GRAPH_DISTANCE_DECAY = distance.decay
    GRAPH_DISTANCE_POWER = distance.power
    GRAPH_DISTANCE_SEEDS = distance.seeds
    POISSON_RATIO = surface.membrane_poisson_ratio
    MEMBRANE_AREA_STIFFENING = surface.membrane_area_stiffening
    MEMBRANE_NORMAL_STABILIZATION = surface.membrane_normal_stabilization
    MEMBRANE_BARRIER = surface.membrane_barrier
    MEMBRANE_BARRIER_ACTIVATION = surface.membrane_barrier_activation
    MEMBRANE_BARRIER_TARGET = surface.membrane_barrier_target
    MEMBRANE_BARRIER_MAX_ITER = surface.membrane_barrier_maximum_iterations
    FINAL_QUALITY_STRATEGY = final_quality.mode
    OML_QUALITY_LAYERS = final_quality.layers
    OML_QUALITY_BARRIER_FLOOR = final_quality.barrier_floor
    OML_QUALITY_FEASIBILITY_TARGET = final_quality.feasibility_target
    OML_QUALITY_BARRIER_ACTIVATION = final_quality.barrier_activation
    OML_QUALITY_BARRIER_WEIGHT = final_quality.barrier_weight
    OML_QUALITY_MAX_ITER = final_quality.maximum_iterations
    OML_QUALITY_SOLVER = final_quality.solver
    VOLUME_METHODS = volume.methods
    VOLUME_LOAD_MODE = volume.load_mode
    WING_FREE_SPAN_FRACTION = surface.wing_free_span_fraction
    TAIL_FREE_SPAN_FRACTION = surface.tail_free_span_fraction
    FUSELAGE_FREE_X_RANGE = surface.fuselage_free_x_range
    SHOW_PLOT = config.visualization.enabled
    SYMMETRY = config.symmetry
    SYMMETRY_PLANE_TOLERANCE = config.symmetry_plane_tolerance

    setup_projection_options = {
        "warm_start_nu": config.setup_projection_resolution,
        "warm_start_nv": config.setup_projection_resolution,
    }
    projection_options = {
        "warm_start_nu": config.projection_warm_start_resolution,
        "warm_start_nv": config.projection_warm_start_resolution,
    }

    geometry_file = model_files.geometry_step_file.resolve()
    mesh_file = model_files.surface_mesh_file.resolve()
    volume_mesh_file = model_files.volume_mesh_file.resolve()
    volume_wall_map_file = model_files.volume_wall_map_file.resolve()
    setup_cache_directory = (
        model_files.setup_cache_directory.resolve()
        if model_files.setup_cache_directory is not None
        else geometry_file.parent
    )
    volume_output_directory = (
        Path(volume.output_directory).expanduser().resolve()
        if volume.output_directory is not None
        else volume_mesh_file.parent / "deformation_results"
    )

    if not geometry_file.is_file():
        raise FileNotFoundError(f"STEP geometry not found: {geometry_file}")
    if not volume_mesh_file.is_file():
        raise FileNotFoundError(f"Volume mesh not found: {volume_mesh_file}")
    surface_exists = mesh_file.is_file()
    wall_map_exists = volume_wall_map_file.is_file()
    if surface_exists != wall_map_exists:
        raise FileNotFoundError(
            "The surface mesh and volume-wall map are a matched pair and must "
            "either both exist or both be absent so they can be extracted from "
            f"the selected volume mesh. Surface: {mesh_file}; "
            f"wall map: {volume_wall_map_file}"
        )
    setup_cache_directory.mkdir(parents=True, exist_ok=True)
    volume_output_directory.mkdir(parents=True, exist_ok=True)
    print(
        "[inputs] "
        f"STEP={geometry_file} "
        f"surface={mesh_file} "
        f"volume={volume_mesh_file} "
        f"wall_map={volume_wall_map_file}",
        flush=True,
    )
    setup_start = time.perf_counter()

    # -------------------------------------------------------------------------
    # 1. Import the OML and mesh, then identify the aircraft components.
    # -------------------------------------------------------------------------
    geometry = lfs.import_file_patched(geometry_file, parallelize=False)
    wing, tail, fuselage = bsm3.preprocessing.create_components(
        search_names=["wing", "HT", "fuselage"],
        geometry=geometry,
    )

    volume_mesh = None
    if not surface_exists:
        volume_mesh = (
            bsm3.core.boundary_surface_movement.read_gmsh22_volume(
                volume_mesh_file
            )
        )
        bsm3.core.boundary_surface_movement.extract_aircraft_wall_mesh(
            volume_mesh,
            mesh_file,
            volume_wall_map_file,
        )
        print(
            f"[volume] extracted exact aircraft wall from {volume_mesh_file.name}",
            flush=True,
        )
    mesh = bsm3.preprocessing.import_mesh(mesh_file)
    cfd_polygon_connectivity = _cfd_surface_cells(mesh)

    # plot mesh
    # bsm3.plotting.plot_mesh(mesh, show=True)
    # exit()
    # mesh, cfd_polygon_connectivity = _cfd_mesh_from_pickle(mesh_file)
    _block_summary = ", ".join(
        f"{key}:{np.asarray(block).shape[0]}" for key, block in mesh.cell_blocks.items()
    )
    print(
        f"[cfd] loaded {mesh.vertices.shape[0]} vertices, "
        f"{len(cfd_polygon_connectivity)} polygons (no triangulation) [{_block_summary}]"
    )
    if VOLUME_METHODS:
        if volume_mesh is None:
            volume_mesh = (
                bsm3.core.boundary_surface_movement.read_gmsh22_volume(
                    volume_mesh_file
                )
            )
        wall_to_volume = (
            bsm3.core.boundary_surface_movement.load_wall_to_volume_map(
                volume_wall_map_file,
                volume_mesh,
                wall_vertices=np.asarray(mesh.vertices, dtype=float),
            )
        )
        print(
            f"[volume] exact wall map validated: {wall_to_volume.size} wall "
            f"nodes -> {volume_mesh.vertices.shape[0]} volume nodes, "
            f"{volume_mesh.tetrahedra.shape[0]} tetrahedra",
            flush=True,
        )
    _setup_after_load = time.perf_counter()

    # Symmetry: solve on one half and mirror.  The whole pipeline (steps 2-7)
    # then runs on ``mesh`` = the half; ``full_mesh`` is kept for the final
    # reconstruction, quality report, and plot.  The CFD mesh is already a
    # half-mesh (y>=0), so use ``config.symmetry=False`` to skip the split.
    full_mesh = mesh
    initial_full_vertices = np.asarray(full_mesh.vertices, dtype=float).copy()
    symmetry_split = None
    if SYMMETRY and bsm3.preprocessing.detect_symmetry(mesh):
        symmetry_split = bsm3.preprocessing.split_symmetric_mesh(mesh)
        mesh = symmetry_split.half_mesh
        print(
            f"[symmetry] half-mesh solve: {symmetry_split.half_to_full.size} of "
            f"{full_mesh.vertices.shape[0]} vertices, "
            f"{symmetry_split.plane_local_ids.size} on the y=0 plane"
        )
    initial_vertices = np.asarray(mesh.vertices, dtype=float)
    num_mesh_vertices = initial_vertices.shape[0]
    symmetry_plane_vertex_ids = (
        symmetry_split.plane_local_ids
        if symmetry_split is not None
        else bsm3.core.boundary_surface_movement
        .identify_symmetry_plane_vertices(
            initial_vertices,
            axis=1,
            tolerance=SYMMETRY_PLANE_TOLERANCE,
        )
    )
    print(
        f"[symmetry] hard y=0 constraint on "
        f"{symmetry_plane_vertex_ids.size} baseline plane vertices",
        flush=True,
    )

    # -------------------------------------------------------------------------
    # 2 + 3. Baseline projection/ownership and seam identification.  These are the
    #    expensive one-time setup (all vertices projected onto every component)
    #    and they depend ONLY on the fixed baseline mesh and OML -- not on the
    #    design variables -- so cache them to a sidecar .npz and reuse across
    #    every deformation run. Use ``config.rebuild_setup_cache=True`` to rebuild.
    # -------------------------------------------------------------------------
    setup_cache_path = setup_cache_directory / (
        f"_setup_cache_{mesh_file.stem}_{geometry_file.stem}"
        f"_nu{setup_projection_options['warm_start_nu']}_sym{int(SYMMETRY)}.npz"
    )
    _mesh_mtime = mesh_file.stat().st_mtime
    _geom_mtime = geometry_file.stat().st_mtime
    _code_sig = _setup_code_signature((
        sorted(setup_projection_options.items()),
        float(intersection_tolerance),
        float(bisection_tolerance),
        int(bisection_max_iter),
    ))
    _setup_keys = (
        "initial_parametric_coordinates", "wing_ids", "tail_ids", "fuselage_ids",
        "wing_fuse_parametric", "wing_fuse_vertices", "wing_fuse_ids",
        "tail_fuse_parametric", "tail_fuse_vertices", "tail_fuse_ids",
    )
    _setup = None
    if setup_cache_path.exists() and not config.rebuild_setup_cache:
        _c = np.load(setup_cache_path)
        if (
            float(_c["_mesh_mtime"]) == _mesh_mtime
            and float(_c["_geom_mtime"]) == _geom_mtime
            and int(_c["_num_vertices"]) == num_mesh_vertices
            and "_code_sig" in _c
            and str(_c["_code_sig"]) == _code_sig
        ):
            _setup = {k: _c[k] for k in _setup_keys}
            print(
                f"[cache] loaded setup projections from {setup_cache_path.name} "
                f"({time.perf_counter()-setup_start:.1f}s, skipped ~{'?'})",
                flush=True,
            )
        else:
            print("[cache] setup cache stale (mesh/geom changed); rebuilding", flush=True)

    if _setup is None:
        projection_cache = {}
        component_projection_data = bsm3.preprocessing.project_mesh_onto_components(
            mesh_vertices=initial_vertices,
            components=[wing, tail, fuselage],
            projection_cache=projection_cache,
            projection_options=setup_projection_options,
        )
        print(f"[time] after step2 setup-projection: {time.perf_counter()-setup_start:.1f}s", flush=True)
        component_distances = np.column_stack(
            [np.abs(item.distances) for item in component_projection_data]
        )
        component_ownership = np.argmin(component_distances, axis=1)
        initial_parametric_coordinates = np.empty((num_mesh_vertices, 3))
        for component_index, component_projection in enumerate(component_projection_data):
            owned = component_ownership == component_index
            initial_parametric_coordinates[owned] = (
                component_projection.parametric_coordinates[owned]
            )
        initial_patch_ids = np.rint(initial_parametric_coordinates[:, 0]).astype(np.int64)
        wing_ids = np.where(np.isin(initial_patch_ids, list(wing.functions)))[0].astype(np.int64)
        tail_ids = np.where(np.isin(initial_patch_ids, list(tail.functions)))[0].astype(np.int64)
        fuselage_ids = np.where(np.isin(initial_patch_ids, list(fuselage.functions)))[0].astype(np.int64)

        (wing_fuse_parametric, wing_fuse_vertices, wing_fuse_ids) = (
            bsm3.preprocessing.identify_intersection_vertices(
                components=[wing, fuselage],
                driving_component=wing,
                mesh=mesh,
                intersection_tolerance=intersection_tolerance,
                projection_cache=projection_cache,
                projection_options=setup_projection_options,
            )
        )
        (tail_fuse_parametric, tail_fuse_vertices, tail_fuse_ids) = (
            bsm3.preprocessing.identify_intersection_vertices(
                components=[tail, fuselage],
                driving_component=tail,
                mesh=mesh,
                intersection_tolerance=intersection_tolerance,
                projection_cache=projection_cache,
                projection_options=setup_projection_options,
            )
        )
        _setup = {
            "initial_parametric_coordinates": initial_parametric_coordinates,
            "wing_ids": wing_ids, "tail_ids": tail_ids, "fuselage_ids": fuselage_ids,
            "wing_fuse_parametric": wing_fuse_parametric,
            "wing_fuse_vertices": wing_fuse_vertices, "wing_fuse_ids": wing_fuse_ids,
            "tail_fuse_parametric": tail_fuse_parametric,
            "tail_fuse_vertices": tail_fuse_vertices, "tail_fuse_ids": tail_fuse_ids,
        }
        np.savez(
            setup_cache_path,
            _mesh_mtime=_mesh_mtime, _geom_mtime=_geom_mtime,
            _num_vertices=num_mesh_vertices, _code_sig=_code_sig, **_setup,
        )
        print(f"[cache] saved setup projections to {setup_cache_path.name}", flush=True)

    initial_parametric_coordinates = _setup["initial_parametric_coordinates"]
    wing_ids = _setup["wing_ids"]; tail_ids = _setup["tail_ids"]; fuselage_ids = _setup["fuselage_ids"]
    wing_fuse_parametric = _setup["wing_fuse_parametric"]
    wing_fuse_vertices = _setup["wing_fuse_vertices"]; wing_fuse_ids = _setup["wing_fuse_ids"]
    tail_fuse_parametric = _setup["tail_fuse_parametric"]
    tail_fuse_vertices = _setup["tail_fuse_vertices"]; tail_fuse_ids = _setup["tail_fuse_ids"]

    # -------------------------------------------------------------------------
    # 4. Define the geometry variables and deform the component coefficients.
    # -------------------------------------------------------------------------
    wing_translation_x = geometry_variables.wing_translation_x
    wing_rotation_degrees = geometry_variables.wing_rotation_degrees
    tail_rotation_degrees = geometry_variables.tail_rotation_degrees
    wing_area = geometry_variables.wing_area
    wing_aspect_ratio = geometry_variables.wing_aspect_ratio
    # Fuselage cross-section scaling.  This is the design variable that makes the
    # query component of both intersections *move*, exercising the query-side
    # seam reference in the corotational solve.  Scaling about a pivot on y=0
    # keeps the symmetry plane at y=0.
    fuselage_diameter_scale = geometry_variables.fuselage_diameter_scale

    wing_leading = wing_fuse_vertices[
        int(np.argmin(wing_fuse_vertices[:, 0]))
    ]
    wing_trailing = wing_fuse_vertices[
        int(np.argmax(wing_fuse_vertices[:, 0]))
    ]
    wing_pivot = wing_leading + 0.25 * (wing_trailing - wing_leading)
    wing_pivot[1] = 0.0
    tail_leading = tail_fuse_vertices[
        int(np.argmin(tail_fuse_vertices[:, 0]))
    ]
    tail_trailing = tail_fuse_vertices[
        int(np.argmax(tail_fuse_vertices[:, 0]))
    ]
    tail_pivot = tail_leading + 0.25 * (tail_trailing - tail_leading)
    tail_pivot[1] = 0.0

    # Scale the fuselage cross-section about a pivot on the symmetry plane so
    # y=0 stays at y=0 (keeps the mesh symmetry and the plane condition exact).
    fuselage_control_points = np.vstack(
        [
            np.asarray(
                fuselage.functions[key].coefficients.value, dtype=float
            ).reshape((-1, 3))
            for key in sorted(fuselage.functions)
        ]
    )
    fuselage_pivot = 0.5 * (
        fuselage_control_points.min(axis=0) + fuselage_control_points.max(axis=0)
    )
    fuselage_pivot[1] = 0.0
    load_fractions = (
        bsm3.core.boundary_surface_movement.linear_load_fractions(
            GRAPH_LOAD_STEPS if ELASTIC_STRATEGY == "graph" else 1
        )
    )
    component_coefficient_steps = []
    for load_fraction in load_fractions:
        wing_coefficients_at_step = (
            bsm3.core.boundary_surface_movement.deform_geometry(
                component=wing,
                parameters=WingParameters(
                    translation_x=load_fraction * wing_translation_x,
                    rotation_y_degrees=load_fraction * wing_rotation_degrees,
                    area=reference_wing_area
                    + load_fraction * (wing_area - reference_wing_area),
                    aspect_ratio=reference_wing_aspect_ratio
                    + load_fraction
                    * (wing_aspect_ratio - reference_wing_aspect_ratio),
                    reference_area=reference_wing_area,
                    reference_aspect_ratio=reference_wing_aspect_ratio,
                    pivot=wing_pivot.reshape((1, 3)),
                    # Scale span only outboard of the physical fuselage junction.
                    # Uniform scaling about y=0 would drag the root through the
                    # fixed fuselage before the intersection is recomputed.
                    spanwise_scaling_root=float(
                        np.median(np.abs(wing_fuse_vertices[:, 1]))
                    ),
                ),
            )
        )
        tail_coefficients_at_step = (
            bsm3.core.boundary_surface_movement.deform_geometry(
                component=tail,
                parameters=TailParameters(
                    rotation_y_degrees=load_fraction * tail_rotation_degrees,
                    pivot=tail_pivot.reshape((1, 3)),
                ),
            )
        )
        fuselage_coefficients_at_step = (
            bsm3.core.boundary_surface_movement.deform_geometry(
                component=fuselage,
                parameters=FuselageParameters(
                    diameter_scale=1.0
                    + load_fraction * (fuselage_diameter_scale - 1.0),
                    pivot=fuselage_pivot.reshape((1, 3)),
                ),
            )
        )
        component_coefficient_steps.append(
            {
                id(wing): wing_coefficients_at_step,
                id(tail): tail_coefficients_at_step,
                id(fuselage): fuselage_coefficients_at_step,
            }
        )
    coefficient_map = component_coefficient_steps[-1]
    wing_coefficients = coefficient_map[id(wing)]
    tail_coefficients = coefficient_map[id(tail)]
    fuselage_coefficients = coefficient_map[id(fuselage)]

    # -------------------------------------------------------------------------
    # 5. Recompute the exact wing/fuselage and tail/fuselage intersections with
    #    bracketed SDF solves; their exact seam displacements drive the elastic
    #    propagator (step 6).
    # -------------------------------------------------------------------------
    wing_intersection = (
        bsm3.core.boundary_surface_movement.IntersectionParameters(
            name="wing_fuselage",
            parametric_coords=wing_fuse_parametric,
            vertex_ids=wing_fuse_ids,
            driving_component=wing,
            sdf_query_component=fuselage,
            bisection_search_direction="u",
            bisection_tolerance=bisection_tolerance,
            bisection_max_iter=bisection_max_iter,
            projection_options=projection_options,
        )
    )
    tail_intersection = (
        bsm3.core.boundary_surface_movement.IntersectionParameters(
            name="tail_fuselage",
            parametric_coords=tail_fuse_parametric,
            vertex_ids=tail_fuse_ids,
            driving_component=tail,
            sdf_query_component=fuselage,
            bisection_search_direction="u",
            bisection_tolerance=bisection_tolerance,
            bisection_max_iter=bisection_max_iter,
            projection_options=projection_options,
        )
    )
    # -------------------------------------------------------------------------
    # 6. Select the free (elastically solved) vertices, build the corotational
    #    elastic propagator, and evaluate the preprojected mesh vertices.
    # -------------------------------------------------------------------------
    # Free vertices per component.  The band spans the lifting surfaces: the
    # inboard wing/tail is free so it blends between the moving seam and the
    # rigid outboard, which keeps near-root rows off the fuselage under planform
    # changes instead of penetrating it with a fixed parametric reevaluation.
    # Seam vertices are always prescribed.
    seam_ids = np.concatenate((wing_fuse_ids, tail_fuse_ids)).astype(np.int64)
    free_regions = [
        bsm3.core.boundary_surface_movement.ComponentFreeRegion(
            component=wing,
            y=bsm3.core.boundary_surface_movement.AxisRange(
                upper=WING_FREE_SPAN_FRACTION, mode="abs"
            ),
        ),
        bsm3.core.boundary_surface_movement.ComponentFreeRegion(
            component=tail,
            y=bsm3.core.boundary_surface_movement.AxisRange(
                upper=TAIL_FREE_SPAN_FRACTION, mode="abs"
            ),
        ),
        bsm3.core.boundary_surface_movement.ComponentFreeRegion(
            component=fuselage,
            x=bsm3.core.boundary_surface_movement.AxisRange(
                lower=FUSELAGE_FREE_X_RANGE[0],
                upper=FUSELAGE_FREE_X_RANGE[1],
                mode="extent",
            ),
        ),
    ]
    free_ids = bsm3.core.boundary_surface_movement.select_free_vertices(
        free_regions=free_regions,
        component_vertex_ids={
            id(wing): wing_ids,
            id(tail): tail_ids,
            id(fuselage): fuselage_ids,
        },
        mesh_vertices=initial_vertices,
        exclude_ids=seam_ids,
    )
    # Projection groups partition the deformation set (free vertices + seam) by
    # component: wing/tail keep the parent-patch restriction, the fuselage
    # projects to all of its patches.  Everything else on the mesh is
    # reevaluated at fixed parametric coordinates (step 7).
    wing_free_ids = np.intersect1d(free_ids, wing_ids)
    tail_free_ids = np.intersect1d(free_ids, tail_ids)
    fuselage_free_ids = np.intersect1d(free_ids, fuselage_ids)
    wing_projection_ids = np.unique(
        np.concatenate((wing_free_ids, wing_fuse_ids))
    )
    tail_projection_ids = np.setdiff1d(
        np.unique(np.concatenate((tail_free_ids, tail_fuse_ids))),
        wing_projection_ids,
    )
    fuselage_projection_ids = np.setdiff1d(
        fuselage_free_ids,
        np.concatenate((wing_projection_ids, tail_projection_ids)),
    )
    deformation_vertex_ids = np.concatenate(
        (wing_projection_ids, tail_projection_ids, fuselage_projection_ids)
    ).astype(np.int64)

    # Optional fixed reference-geodesic distance weighting.  Seed from the
    # enabled moving seams and restrict the shortest-path graph to the elastic
    # band (free + its graph ring) so paths cannot shortcut through unrelated
    # components.  Built once on the reference mesh; beta=0/off is a pure no-op.
    distance_weighting = None
    if GRAPH_DISTANCE_WEIGHT:
        distance_seed_blocks = []
        if GRAPH_DISTANCE_SEEDS in ("wing", "both"):
            distance_seed_blocks.append(wing_fuse_ids)
        if GRAPH_DISTANCE_SEEDS in ("tail", "both"):
            distance_seed_blocks.append(tail_fuse_ids)
        distance_seed_ids = np.unique(
            np.concatenate(distance_seed_blocks)
        ).astype(np.int64)
        distance_band_ids = np.union1d(
            free_ids,
            bsm3.core.boundary_surface_movement.graph_neighbors(mesh, free_ids),
        )
        distance_weighting = (
            bsm3.core.boundary_surface_movement.build_graph_distance_weighting(
                mesh,
                distance_seed_ids,
                beta=GRAPH_DISTANCE_BETA,
                length=GRAPH_DISTANCE_LENGTH,
                cap=GRAPH_DISTANCE_CAP,
                decay=GRAPH_DISTANCE_DECAY,
                rational_power=GRAPH_DISTANCE_POWER,
                restrict_vertex_ids=distance_band_ids,
            )
        )
        _band_edges = set()
        for _block in mesh.cell_blocks.values():
            for _cell in np.asarray(_block, dtype=np.int64):
                for _a, _b in zip(_cell, np.roll(_cell, -1)):
                    _a, _b = int(_a), int(_b)
                    if _a != _b:
                        _band_edges.add((min(_a, _b), max(_a, _b)))
        _distance_summary = distance_weighting.summary(
            np.asarray(sorted(_band_edges), dtype=np.int64)
        )
        print(
            "[graph-distance] "
            f"seeds={GRAPH_DISTANCE_SEEDS}({distance_seed_ids.size}) "
            f"beta={GRAPH_DISTANCE_BETA:g} length={GRAPH_DISTANCE_LENGTH:g} "
            f"cap={GRAPH_DISTANCE_CAP:g} decay={GRAPH_DISTANCE_DECAY} "
            f"reachable={_distance_summary['num_reachable_vertices']} "
            f"max_dist={_distance_summary['max_finite_distance']:.3g} "
            f"mult[min/med/max]="
            f"{_distance_summary['multiplier_min']:.3g}/"
            f"{_distance_summary['multiplier_median']:.3g}/"
            f"{_distance_summary['multiplier_max']:.3g}",
            flush=True,
        )
    motion_common = dict(
        mesh=mesh,
        free_ids=free_ids,
        intersection_params=[wing_intersection, tail_intersection],
        parametric_coordinates=initial_parametric_coordinates,
        components=[wing, tail, fuselage],
        component_reevaluations=(),
        use_query_seam_reference=config.query_seam_reference,
        symmetry_plane_ids=symmetry_plane_vertex_ids,
    )
    if ELASTIC_STRATEGY == "membrane":
        motion = (
            bsm3.core.boundary_surface_movement.CorotationalMembraneMotionSolver(
                **motion_common,
                poisson_ratio=POISSON_RATIO,
                area_stiffening_exponent=MEMBRANE_AREA_STIFFENING,
                normal_stabilization=MEMBRANE_NORMAL_STABILIZATION,
                use_inversion_barrier=MEMBRANE_BARRIER,
                graph_fallback_stiffening_exponent=STIFFENING_EXPONENT,
                barrier_activation_margin=MEMBRANE_BARRIER_ACTIVATION,
                barrier_target_margin=MEMBRANE_BARRIER_TARGET,
                barrier_max_iterations=MEMBRANE_BARRIER_MAX_ITER,
            )
        )
    else:
        graph_prescribed_ids = None
        if DISTORTION_LAMBDA > 0.0:
            graph_prescribed_ids = (
                bsm3.core.boundary_surface_movement.element_neighbors(
                    mesh, free_ids
                )
            )
        motion = bsm3.core.boundary_surface_movement.ElasticityMotionSolver(
            **motion_common,
            stiffening_exponent=STIFFENING_EXPONENT,
            use_corotational_reference=True,
            prescribed_ids=graph_prescribed_ids,
            distance_weighting=distance_weighting,
        )

    # -------------------------------------------------------------------------
    # 7. Put every mesh node on the deformed OML.
    #
    #    - selected wing/tail rows: project to their original parent patch;
    #    - selected fuselage rows: project to all fuselage patches;
    #    - all remaining rows: reevaluate their fixed baseline (patch,u,v).
    #
    # There is deliberately no projection bypass for CAD patch-edge nodes.
    # -------------------------------------------------------------------------
    wing_parent_coordinates = initial_parametric_coordinates.copy()
    wing_parent_coordinates[wing_fuse_ids] = wing_fuse_parametric
    tail_parent_coordinates = initial_parametric_coordinates.copy()
    tail_parent_coordinates[tail_fuse_ids] = tail_fuse_parametric
    # Lifting-surface projection restriction.  Measured on the extreme combined
    # corner (tx-3, rot-5, tail+8, area 0.85, fuselage 1.15):
    #
    #   parent : 34 inverted, minSJ -0.94 -- clamps a node that slid spanwise
    #            across the Yehudi-break patch boundary onto that edge.
    #   side   :  2 inverted, minSJ -0.03 -- same-skin restriction; the node may
    #            slide spanwise between the patches of its own skin but can never
    #            jump to the opposite skin.
    #   any    :  2 inverted, minSJ -0.03 -- unrestricted.
    #
    # "side" and "any" agree to <1 mm here (they differ on 292 nodes), so the
    # same-skin restriction is essentially free while structurally ruling out the
    # cross-skin jump that an unrestricted projection permits on a thin surface.
    # It is therefore the default.  The 2 remaining inversions are marginal
    # tail-cone cells that are already near-degenerate before projection
    # (pre-projection scaled Jacobian ~ +0.001), not a projection failure.
    _lifting_surface_mode = config.lifting_surface_patch_mode

    def _lifting_surface_metadata(component, projection_ids, parent_coordinates, name):
        if projection_ids.size == 0:
            return []
        if _lifting_surface_mode == "parent":
            return [
                bsm3.preprocessing.get_projection_metadata(
                    component=component,
                    vertices=initial_vertices[projection_ids],
                    vertex_ids=projection_ids,
                    para_coords=parent_coordinates,
                    name=name,
                )
            ]
        if _lifting_surface_mode == "any":
            return [
                bsm3.preprocessing.get_projection_metadata(
                    component=component,
                    vertices=initial_vertices[projection_ids],
                    vertex_ids=projection_ids,
                    para_coords=None,
                    name=name,
                )
            ]
        # Same-skin restriction: a node may slide spanwise across the Yehudi
        # break (parent-patch cannot) but never onto the opposite skin (any-patch
        # can).  End caps are classified 0 and excluded -- they are reevaluated
        # from parametric space, never projected onto.
        sides = bsm3.core.boundary_surface_movement.classify_patch_sides(component)
        node_patch = np.rint(parent_coordinates[projection_ids, 0]).astype(np.int64)
        node_side = np.array([sides.get(int(p), 0) for p in node_patch])
        groups = []
        for side in sorted(set(node_side.tolist())):
            selected = projection_ids[node_side == side]
            if selected.size == 0:
                continue
            if side == 0:
                # Unclassified parent (cap/degenerate): fall back to all patches.
                side_patches = None
            else:
                side_patches = [p for p, value in sides.items() if value == side]
            groups.append(
                bsm3.preprocessing.get_projection_metadata(
                    component=component,
                    vertices=initial_vertices[selected],
                    vertex_ids=selected,
                    para_coords=None,
                    allowed_patch_ids=side_patches,
                    name=f"{name}_side{side:+d}",
                )
            )
        return groups

    projection_metadata = [
        *_lifting_surface_metadata(
            wing, wing_projection_ids, wing_parent_coordinates, "wing"
        ),
        *_lifting_surface_metadata(
            tail, tail_projection_ids, tail_parent_coordinates, "horizontal_tail"
        ),
        bsm3.preprocessing.get_projection_metadata(
            component=fuselage,
            vertices=initial_vertices[fuselage_projection_ids],
            vertex_ids=fuselage_projection_ids,
            para_coords=None,
            name="fuselage",
        ),
    ]
    tangential_smoothing_ids = np.empty(0, dtype=np.int64)
    tangential_smoother = None
    if TANGENTIAL_SMOOTHING:
        smoothing_excluded = np.unique(
            np.concatenate((seam_ids, symmetry_plane_vertex_ids))
        )
        tangential_smoothing_ids = (
            bsm3.core.boundary_surface_movement.select_fixed_vertex_band(
                mesh,
                seed_ids=wing_fuse_ids,
                allowed_ids=fuselage_projection_ids,
                excluded_ids=smoothing_excluded,
                element_layers=TANGENTIAL_SMOOTHING_LAYERS,
            )
        )
        smoothing_projection_metadata = [
            bsm3.preprocessing.get_projection_metadata(
                component=fuselage,
                vertices=initial_vertices[tangential_smoothing_ids],
                vertex_ids=tangential_smoothing_ids,
                para_coords=None,
                name="fixed_tangential_smoothing_fuselage",
            )
        ]
        tangential_smoother = (
            bsm3.core.boundary_surface_movement
            .assemble_fixed_projected_tangential_smoother(
                mesh,
                active_ids=tangential_smoothing_ids,
                projection_metadata=smoothing_projection_metadata,
                iterations=TANGENTIAL_SMOOTHING_ITERATIONS,
                relaxation=TANGENTIAL_SMOOTHING_RELAXATION,
                preserve_reference=(
                    TANGENTIAL_SMOOTHING_PRESERVE_REFERENCE
                ),
                projection_mode=TANGENTIAL_SMOOTHING_REPROJECTION,
            )
        )
        print(
            "[tangential-smoothing] "
            f"active={tangential_smoothing_ids.size} "
            f"fixed_neighbors={tangential_smoother.fixed_neighbor_ids.size} "
            f"layers={TANGENTIAL_SMOOTHING_LAYERS} "
            f"iterations={TANGENTIAL_SMOOTHING_ITERATIONS} "
            f"relaxation={TANGENTIAL_SMOOTHING_RELAXATION:g} "
            "weighting=inverse_edge_length "
            f"reprojection={TANGENTIAL_SMOOTHING_REPROJECTION} "
            f"preserve_reference={int(TANGENTIAL_SMOOTHING_PRESERVE_REFERENCE)}",
            flush=True,
        )
    reevaluation_metadata = (
        bsm3.preprocessing.identify_reevaluated_vertices(
            mesh=mesh,
            vertex_ids=deformation_vertex_ids,
            parametric_coords=initial_parametric_coordinates,
            components=[wing, tail, fuselage],
            names=["wing", "horizontal_tail", "fuselage"],
        )
    )
    parameterized_projection = None
    deformation_vertices = initial_vertices[deformation_vertex_ids]
    if ELASTIC_STRATEGY == "graph":
        load_step_result = (
            bsm3.core.boundary_surface_movement.run_graph_load_steps(
                motion=motion,
                mesh=mesh,
                initial_deformation_vertices=csdl.Variable(
                    name="deformation_vertices",
                    value=deformation_vertices,
                ),
                deformation_vertex_ids=deformation_vertex_ids,
                component_coefficient_steps=component_coefficient_steps,
                projection_metadata=projection_metadata,
                reevaluation_metadata=reevaluation_metadata,
                projection_options=projection_options,
                load_fractions=load_fractions,
                parameterize_final_projection=(
                    FINAL_QUALITY_STRATEGY == "oml"
                ),
                distortion_config=(
                    None
                    if DISTORTION_LAMBDA == 0.0
                    else bsm3.core.boundary_surface_movement.QuadraticDistortionConfig(
                        lambda_dist=DISTORTION_LAMBDA,
                        mode=DISTORTION_MODE,
                        coefficients=(
                            bsm3.core.boundary_surface_movement.DistortionModeCoefficients(
                                area=DISTORTION_K_AREA,
                                deviatoric=DISTORTION_K_DEVIATORIC,
                                shear=DISTORTION_K_SHEAR,
                                rotation=DISTORTION_K_ROTATION,
                                normal=DISTORTION_K_NORMAL,
                            )
                        ),
                    )
                ),
                tangential_smoother=tangential_smoother,
                symmetry_plane_vertex_ids=symmetry_plane_vertex_ids,
                symmetry_plane_axis=1,
            )
        )
        preprojected_mesh_vertices = (
            load_step_result.final_preprojected_mesh_vertices
        )
        projected_mesh_vertices = load_step_result.final_mesh_vertices
        parameterized_projection = (
            load_step_result.final_parameterized_projection
        )
    else:
        motion_field = motion.train(
            component_coeffs=[wing_coefficients, tail_coefficients],
            query_component_coeffs={id(fuselage): fuselage_coefficients},
        )
        preprojected_vertices = motion_field.evaluate(
            vertices=csdl.Variable(
                name="deformation_vertices",
                value=deformation_vertices,
            ),
            vertex_ids=deformation_vertex_ids,
        )
        if FINAL_QUALITY_STRATEGY == "oml":
            parameterized_projection = (
                bsm3.core.boundary_surface_movement.project_onto_oml_parameterized(
                    deformed_mesh_vertices=preprojected_vertices,
                    deformed_mesh_vertex_ids=deformation_vertex_ids,
                    projection_metadata=projection_metadata,
                    component_coefficients=coefficient_map,
                    projection_options=projection_options,
                )
            )
            projected_vertices = parameterized_projection.vertices
        else:
            projected_vertices = (
                bsm3.core.boundary_surface_movement.project_onto_oml(
                    deformed_mesh_vertices=preprojected_vertices,
                    deformed_mesh_vertex_ids=deformation_vertex_ids,
                    projection_metadata=projection_metadata,
                    component_coefficients=coefficient_map,
                    projection_options=projection_options,
                )
            )
        reevaluated_vertices = (
            bsm3.core.boundary_surface_movement.reevaluate_vertices(
                mesh=mesh,
                metadata=reevaluation_metadata,
                component_coefficients=coefficient_map,
            )
        )
        # The complete pre-projection surface consists of the elastically moved
        # deformation rows *and* the surrounding rows already moved by
        # parametric reevaluation.
        preprojected_mesh_vertices = (
            bsm3.core.boundary_surface_movement.combine_vertices(
                oml_projected_vertices=
                bsm3.core.boundary_surface_movement.VertexBatch(
                    values=preprojected_vertices,
                    vertex_ids=deformation_vertex_ids,
                    num_mesh_vertices=initial_vertices.shape[0],
                ),
                reevaluated_mesh_vertices=reevaluated_vertices,
            )
        )
        projected_mesh_vertices = (
            bsm3.core.boundary_surface_movement.combine_vertices(
                oml_projected_vertices=projected_vertices,
                reevaluated_mesh_vertices=reevaluated_vertices,
            )
        )
    # Projection is only guaranteed to satisfy the CAD surface.  Impose the
    # essential half-domain condition explicitly afterward for every motion
    # strategy, including the no-smoother path.
    preprojected_mesh_vertices = (
        bsm3.core.boundary_surface_movement.enforce_symmetry_plane(
            preprojected_mesh_vertices,
            vertex_ids=symmetry_plane_vertex_ids,
            axis=1,
        )
    )
    projected_mesh_vertices = (
        bsm3.core.boundary_surface_movement.enforce_symmetry_plane(
            projected_mesh_vertices,
            vertex_ids=symmetry_plane_vertex_ids,
            axis=1,
        )
    )
    if FINAL_QUALITY_STRATEGY == "oml":
        quality_excluded = np.unique(
            np.concatenate((seam_ids, symmetry_plane_vertex_ids))
        )
        quality_vertex_ids = (
            bsm3.core.boundary_surface_movement.select_fixed_vertex_band(
                mesh,
                seed_ids=seam_ids,
                allowed_ids=deformation_vertex_ids,
                excluded_ids=quality_excluded,
                element_layers=OML_QUALITY_LAYERS,
            )
        )
        final_mesh_vertices = (
            bsm3.core.boundary_surface_movement.optimize_mesh_on_oml(
                mesh=mesh,
                candidate_mesh_vertices=projected_mesh_vertices,
                quality_vertex_ids=quality_vertex_ids,
                parameter_groups=parameterized_projection.groups,
                barrier_floor=OML_QUALITY_BARRIER_FLOOR,
                feasibility_target=OML_QUALITY_FEASIBILITY_TARGET,
                barrier_activation=OML_QUALITY_BARRIER_ACTIVATION,
                barrier_weight=OML_QUALITY_BARRIER_WEIGHT,
                max_feasibility_iterations=OML_QUALITY_MAX_ITER,
                max_quality_iterations=OML_QUALITY_MAX_ITER,
                quality_solver=OML_QUALITY_SOLVER,
                verbose=True,
            )
        )
    else:
        final_mesh_vertices = projected_mesh_vertices
    final_mesh_vertices = (
        bsm3.core.boundary_surface_movement.enforce_symmetry_plane(
            final_mesh_vertices,
            vertex_ids=symmetry_plane_vertex_ids,
            axis=1,
        )
    )
    print(f"[time] after step7 project-onto-OML: {time.perf_counter()-setup_start:.1f}s", flush=True)

    # Reconstruct the full mesh from the half solve (identity without symmetry).
    if symmetry_split is not None:
        preprojected_mesh_vertices = (
            bsm3.preprocessing.reconstruct_full_from_half(
                preprojected_mesh_vertices, symmetry_split
            )
        )
        final_mesh_vertices = bsm3.preprocessing.reconstruct_full_from_half(
            final_mesh_vertices, symmetry_split
        )

    # -------------------------------------------------------------------------
    # 8. Extend the final OpenVSP aircraft-wall motion into the tetrahedral
    #    Euler mesh.  One step stays differentiable with a reference stiffness;
    #    multiple surface steps are replayed with volume reassembly/refactoring.
    # -------------------------------------------------------------------------
    volume_outputs = {}
    volume_summary = None
    if volume_mesh is not None:
        if GRAPH_LOAD_STEPS == 1:
            wall_position_history = (final_mesh_vertices,)
        else:
            wall_position_history = (
                load_step_result.projected_mesh_history
            )
            if symmetry_split is not None:
                wall_position_history = tuple(
                    bsm3.preprocessing.reconstruct_full_from_half(
                        item, symmetry_split
                    )
                    for item in wall_position_history
                )
        volume_outputs, volume_summary = _run_volume_motion(
            volume_mesh,
            final_mesh_vertices,
            wall_position_history,
            load_fractions,
            volume_config=volume,
            quality_config=config.quality,
            output_directory=volume_output_directory,
            surface_mesh_file=mesh_file,
            surface_distortion_weight=DISTORTION_LAMBDA,
        )

    # -------------------------------------------------------------------------
    # Diagnostics: inversion / quality on the full mesh, and where inversions
    # sit relative to the wing and tail seams.
    # -------------------------------------------------------------------------
    pre_inversion_report = (
        bsm3.core.boundary_surface_movement.check_element_inversion(
            mesh=full_mesh, final_mesh_vertices=preprojected_mesh_vertices
        )
    )
    pre_quality_report = bsm3.core.boundary_surface_movement.evaluate_mesh_quality(
        mesh=full_mesh, vertices=preprojected_mesh_vertices
    )
    inversion_report = bsm3.core.boundary_surface_movement.check_element_inversion(
        mesh=full_mesh, final_mesh_vertices=final_mesh_vertices
    )
    quality_report = bsm3.core.boundary_surface_movement.evaluate_mesh_quality(
        mesh=full_mesh, vertices=final_mesh_vertices
    )
    final_np = np.asarray(final_mesh_vertices.value, dtype=float)
    preprojected_np = np.asarray(
        preprojected_mesh_vertices.value,
        dtype=float,
    )
    full_symmetry_plane_ids = (
        symmetry_plane_vertex_ids
        if symmetry_split is None
        else symmetry_split.half_to_full[symmetry_plane_vertex_ids]
    )
    pre_plane_error = float(
        np.max(np.abs(preprojected_np[full_symmetry_plane_ids, 1]))
    ) if full_symmetry_plane_ids.size else 0.0
    final_plane_error = float(
        np.max(np.abs(final_np[full_symmetry_plane_ids, 1]))
    ) if full_symmetry_plane_ids.size else 0.0
    surface_cells = _cfd_surface_cells(full_mesh)
    seam_all = np.vstack((wing_fuse_vertices, tail_fuse_vertices))
    if symmetry_split is not None:
        seam_mirror = seam_all.copy()
        seam_mirror[:, symmetry_split.axis] *= -1.0
        seam_all = np.vstack((seam_all, seam_mirror))
    near_seam = 0
    for element_id in inversion_report.inverted_element_ids:
        centroid = final_np[surface_cells[int(element_id)]].mean(axis=0)
        if float(np.min(np.linalg.norm(seam_all - centroid, axis=1))) < 1.0:
            near_seam += 1
    if ELASTIC_STRATEGY == "membrane":
        print(
            "[diagnostics] elasticity=membrane "
            f"nu={POISSON_RATIO} area_chi={MEMBRANE_AREA_STIFFENING} "
            f"normal_stabilization={MEMBRANE_NORMAL_STABILIZATION} "
            f"barrier={int(MEMBRANE_BARRIER)}"
        )
    else:
        print(
            f"[diagnostics] elasticity=graph chi={STIFFENING_EXPONENT} "
            f"surface_load_steps={GRAPH_LOAD_STEPS} "
            f"volume_load_mode={VOLUME_LOAD_MODE} "
            f"distortion_lambda={DISTORTION_LAMBDA:g} "
            f"distortion_mode={DISTORTION_MODE}"
        )
        if load_step_result.distortion_normalization_scale is not None:
            print(
                "[diagnostics] distortion "
                f"normalization={load_step_result.distortion_normalization_scale:.6g} "
                f"redundancy={load_step_result.distortion_redundancy:.6f} "
                f"ear_clipped={load_step_result.distortion_num_ear_clipped} "
                f"max_warp={load_step_result.distortion_maximum_warp_ratio:.6g}"
            )
        print(
            "[diagnostics] tangential_smoothing="
            f"{int(TANGENTIAL_SMOOTHING)} "
            f"active={tangential_smoothing_ids.size} "
            f"layers={TANGENTIAL_SMOOTHING_LAYERS} "
            f"iterations={TANGENTIAL_SMOOTHING_ITERATIONS} "
            f"relaxation={TANGENTIAL_SMOOTHING_RELAXATION:g}"
        )
    print(f"[diagnostics] final_quality={FINAL_QUALITY_STRATEGY}")
    print(
        "[diagnostics] symmetry-plane max |y| "
        f"PRE/POST: {pre_plane_error:.3e}/{final_plane_error:.3e}"
    )
    print(
        f"[diagnostics] PRE inverted elements: "
        f"{pre_inversion_report.num_inverted}; min scaled Jacobian: "
        f"{pre_quality_report.minimum_scaled_jacobian:.4f}"
    )
    print(f"[diagnostics] POST inverted elements: {inversion_report.num_inverted} "
          f"(within 1 m of a seam: {near_seam})")
    print(f"[diagnostics] POST inverted corners: {quality_report.inverted_corners}")
    print(f"[diagnostics] POST min scaled Jacobian: {quality_report.minimum_scaled_jacobian:.4f}")
    print(f"[diagnostics] p05 scaled Jacobian: {quality_report.scaled_jacobian_p05:.4f}")
    print(f"[diagnostics] max aspect ratio: {quality_report.maximum_aspect_ratio:.2f} "
          f"(p95 {quality_report.aspect_ratio_p95:.2f})")
    print(f"[diagnostics] area ratio range: [{quality_report.minimum_area_ratio:.3f}, "
          f"{quality_report.maximum_area_ratio:.3f}]")

    _dump_path = config.diagnostic_dump
    if _dump_path:
        if symmetry_split is None:
            _ids_to_full = lambda ids: np.asarray(ids, dtype=np.int64)
            _para_full = initial_parametric_coordinates
        else:
            _ids_to_full = lambda ids: symmetry_split.half_to_full[
                np.asarray(ids, dtype=np.int64)
            ]
            _para_full = initial_parametric_coordinates[symmetry_split.gather_index]
        np.savez(
            _dump_path,
            preprojected_vertices=np.asarray(
                preprojected_mesh_vertices.value, dtype=float
            ),
            final_vertices=final_np,
            initial_vertices=np.asarray(full_mesh.vertices, dtype=float),
            triangles=np.asarray(
                full_mesh.cell_blocks.get("triangle", np.empty((0, 3))), dtype=np.int64
            ),
            quads=np.asarray(
                full_mesh.cell_blocks.get("quad", np.empty((0, 4))), dtype=np.int64
            ),
            inverted_element_ids=inversion_report.inverted_element_ids,
            wing_fuse_vertices=wing_fuse_vertices,
            tail_fuse_vertices=tail_fuse_vertices,
            wing_fuse_ids=_ids_to_full(wing_fuse_ids),
            tail_fuse_ids=_ids_to_full(tail_fuse_ids),
            initial_parametric_coordinates=_para_full,
            wing_ids=_ids_to_full(wing_ids),
            tail_ids=_ids_to_full(tail_ids),
            fuselage_ids=_ids_to_full(fuselage_ids),
            deformation_vertex_ids=_ids_to_full(deformation_vertex_ids),
            tangential_smoothing_ids=_ids_to_full(
                tangential_smoothing_ids
            ),
            symmetry_plane_vertex_ids=_ids_to_full(
                symmetry_plane_vertex_ids
            ),
        )
        print(f"[diagnostics] dumped arrays to {_dump_path}")

    # Where the inverted cells are, so they are easy to find in the plot.
    if inversion_report.num_inverted:
        print("[diagnostics] inverted element centroids (deformed):")
        for element_id in inversion_report.inverted_element_ids[:20]:
            centroid = final_np[surface_cells[int(element_id)]].mean(axis=0)
            print(
                f"    cell {int(element_id):6d}  "
                f"({centroid[0]:8.3f}, {centroid[1]:8.3f}, {centroid[2]:8.3f})"
            )
        if inversion_report.num_inverted > 20:
            print(f"    ... {inversion_report.num_inverted - 20} more")

    # CFD robustness: a fold check on the ORIGINAL polygons.  Fan-triangulating a
    # hexagon can report sliver "inversions" that are not real cell folds, so the
    # meaningful CFD metric is whether a polygon's area-weighted normal flipped.
    cfd_folds, _fold_dots = _count_polygon_folds(
        np.asarray(full_mesh.vertices, dtype=float),
        final_np,
        cfd_polygon_connectivity,
    )
    print(
        f"[cfd] polygon folds (normal-flip): {cfd_folds} of "
        f"{len(cfd_polygon_connectivity)} polygons"
    )

    if (
        config.quality.fail_on_surface_inversion
        and inversion_report.num_inverted
    ):
        raise RuntimeError(
            "DAFoam/deformation continuation blocked: the final surface mesh "
            f"contains {inversion_report.num_inverted} inverted elements."
        )
    if config.quality.fail_on_volume_inversion and volume_summary is not None:
        inverted_by_method = {
            name: int(data["final_quality"]["inverted_tetrahedra"])
            for name, data in volume_summary["methods"].items()
            if int(data["final_quality"]["inverted_tetrahedra"]) != 0
        }
        if inverted_by_method:
            raise RuntimeError(
                "DAFoam/deformation continuation blocked: inverted volume "
                f"tetrahedra were found: {inverted_by_method}."
            )

    # Run downstream CFD only after all requested mesh-quality diagnostics and
    # inversion gates have completed.
    aerodynamic_outputs: dict[str, csdl.Variable] = {}
    if aerodynamic_analysis is not None:
        if aerodynamic_volume_method not in volume_outputs:
            raise ValueError(
                "The requested aerodynamic volume method "
                f"{aerodynamic_volume_method!r} is unavailable. Enable that "
                "method in VolumeMotionConfig before adding CFD."
            )
        aerodynamic_outputs = dict(
            aerodynamic_analysis(volume_outputs[aerodynamic_volume_method])
        )

    _pipeline_seconds = time.perf_counter() - setup_start
    print(
        f"[cfd] END-TO-END pipeline time: {_pipeline_seconds:.1f}s for "
        f"{mesh.vertices.shape[0]} vertices "
        f"(load {_setup_after_load - setup_start:.1f}s)"
    )

    full_mesh.nodes = final_mesh_vertices.value
    if SHOW_PLOT:
        # Inverted cells are drawn in red on top of the surface.
        bsm3.plotting.plot_mesh(
            mesh=full_mesh,
            plotting_elements=None,
            opacity=config.visualization.opacity,
            show=True,
            inverted_elements=inversion_report,
        )

    return E175MeshMotionResult(
        model_files=model_files,
        geometry_variables=geometry_variables,
        initial_surface_coordinates=initial_full_vertices,
        preprojected_surface_coordinates=preprojected_mesh_vertices,
        surface_coordinates=final_mesh_vertices,
        volume_coordinates=volume_outputs,
        aerodynamic_outputs=aerodynamic_outputs,
        surface_inversion_report=inversion_report,
        surface_quality_report=quality_report,
        volume_quality_summary=volume_summary,
        volume_mesh=volume_mesh,
        surface_mesh=full_mesh,
    )


def select_fd_objective(
    result: E175MeshMotionResult,
    objective_name: str,
) -> csdl.Variable:
    """Select a scalar objective used by the optional driver-level FD sweep."""

    if objective_name == "surface_coordinates":
        objective = csdl.sum(result.surface_coordinates)
    elif objective_name.startswith("volume_"):
        method = objective_name.removeprefix("volume_")
        if method not in result.volume_coordinates:
            raise ValueError(
                f"FD objective {objective_name!r} requires volume method "
                f"{method!r} to be enabled."
            )
        objective = csdl.sum(result.volume_coordinates[method])
    elif objective_name in result.aerodynamic_outputs:
        objective = result.aerodynamic_outputs[objective_name]
    else:
        choices = [
            "surface_coordinates",
            *(
                f"volume_{name}"
                for name in result.volume_coordinates
            ),
            *result.aerodynamic_outputs,
        ]
        raise ValueError(
            f"Unknown FD objective {objective_name!r}; choose one of {choices}."
        )
    objective.name = f"fd_objective_{objective_name}"
    objective.set_as_objective()
    return objective


def run_fd_sweep(
    recorder: csdl.Recorder,
    step_sizes: tuple[float, ...],
) -> dict[str, dict[float, float]]:
    """Run and print a finite-difference convergence sweep."""

    simulator = csdl.experimental.JaxSimulator(recorder=recorder, gpu=False)
    sweep: dict[str, dict[float, float]] = {}
    for step in step_sizes:
        results = simulator.check_optimization_derivatives(
            step_size=step,
            print_results=False,
            raise_on_error=False,
        )
        for key, entry in results.items():
            name = str(entry.get("wrt_name", key[1]))
            sweep.setdefault(name, {})[step] = float(entry["rel_error"])

    names = sorted(sweep)
    print("\n=== FD derivative convergence sweep (relative error) ===")
    print("  step      " + "".join(f"{name[:20]:>22s}" for name in names))
    for step in step_sizes:
        print(
            f"  {step:<9.0e}"
            + "".join(f"{sweep[name][step]:>22.3e}" for name in names)
        )
    print()
    for name in names:
        errors = [sweep[name][step] for step in step_sizes]
        best = int(np.argmin(errors))
        converging = errors[best] < errors[0]
        print(
            f"  {name}: min rel error {errors[best]:.3e} at step "
            f"{step_sizes[best]:.0e}  "
            f"({'converges' if converging else 'NO CONVERGENCE'})"
        )
    return sweep


__all__ = [
    "build_e175_mesh_motion_model",
    "run_fd_sweep",
    "select_fd_objective",
]
