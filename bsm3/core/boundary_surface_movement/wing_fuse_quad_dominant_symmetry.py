from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import os
from pathlib import Path
import sys

import numpy as np
import networkx as nx

try:
    import pyvista as pv  # type: ignore
except ImportError as exc:  # pragma: no cover - handled at runtime
    pv = None  # type: ignore[assignment]
    _PYVISTA_IMPORT_ERROR = exc
else:
    _PYVISTA_IMPORT_ERROR = None


def _require_pyvista():
    if pv is None:  # pragma: no cover
        message = "PyVista is required for visualization."
        if _PYVISTA_IMPORT_ERROR is not None:
            raise ImportError(message) from _PYVISTA_IMPORT_ERROR
        raise ImportError(message)
    return pv


def _empty_cells(nodes_per_cell: int) -> np.ndarray:
    return np.empty((0, nodes_per_cell), dtype=np.int64)


@dataclass(frozen=True)
class SurfaceMesh:
    points: np.ndarray
    triangles: np.ndarray
    quads: np.ndarray

    @property
    def num_vertices(self) -> int:
        return int(self.points.shape[0])

    @property
    def num_triangles(self) -> int:
        return int(self.triangles.shape[0])

    @property
    def num_quads(self) -> int:
        return int(self.quads.shape[0])


@dataclass(frozen=True)
class SymmetryClassification:
    is_full_mesh: bool
    selected_side: str
    positive_vertex_count: int
    negative_vertex_count: int
    symmetry_plane_vertex_count: int
    positive_triangle_count: int
    negative_triangle_count: int
    crossing_triangle_count: int


@dataclass(frozen=True)
class QuadDominantConversionStats:
    matching_method: str
    candidate_pair_count: int
    merged_pair_count: int
    leftover_triangle_count: int
    total_selected_score: float
    mean_selected_score: float
    premerge_accepted_flips: int
    cleanup_improved_patch_count: int
    cleanup_added_quad_count: int


@dataclass(frozen=True)
class QuadMergeCandidate:
    score: float
    weight: float
    triangle_index_a: int
    triangle_index_b: int
    quad: np.ndarray


@dataclass(frozen=True)
class QuadQualitySummary:
    count: int
    mean_abs_angle_deviation_degrees: float
    p95_abs_angle_deviation_degrees: float
    mean_aspect_ratio: float
    p95_aspect_ratio: float
    mean_planarity_ratio: float
    p95_planarity_ratio: float
    mean_min_scaled_jacobian: float
    p05_min_scaled_jacobian: float
    mean_merge_score: float


@dataclass(frozen=True)
class WorstElementSummary:
    count: int
    triangle_count: int
    quad_count: int
    min_angle_min_degrees: float
    min_angle_p05_degrees: float
    aspect_ratio_p95: float
    aspect_ratio_max: float
    min_scaled_jacobian_min: float
    min_scaled_jacobian_p05: float
    num_min_angle_below_20: int
    num_aspect_ratio_above_2: int
    num_scaled_jacobian_below_05: int


@dataclass(frozen=True)
class ProjectedSmoothingStats:
    attempted_iterations: int
    accepted_iterations: int
    protected_vertex_count: int
    active_vertex_count: int
    moved_vertex_count: int
    projection_attempt_count: int
    projection_converged_count: int
    mean_projection_distance: float
    max_projection_distance: float


@dataclass(frozen=True)
class GeometryCaseConfig:
    name: str
    mesh_filename: str
    step_filename: str
    output_filename: str
    component_patch_ranges: dict[str, tuple[int, int | None]]
    protected_intersection_pairs: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class GeometryProjectionBundle:
    combined_projection_model: object
    combined_coefficients: np.ndarray
    component_projection_models: dict[str, object]
    component_coefficients: dict[str, np.ndarray]
    recorder: object | None

    @property
    def wing_projection_model(self) -> object:
        return self.component_projection_models["wing"]

    @property
    def wing_coefficients(self) -> np.ndarray:
        return self.component_coefficients["wing"]

    @property
    def fuse_projection_model(self) -> object:
        return self.component_projection_models["fuse"]

    @property
    def fuse_coefficients(self) -> np.ndarray:
        return self.component_coefficients["fuse"]


@dataclass(frozen=True)
class MixedFaceQualityArrays:
    min_angles_degrees: np.ndarray
    aspect_ratios: np.ndarray
    min_scaled_jacobians: np.ndarray
    planarity_ratios: np.ndarray
    is_quad: np.ndarray


@dataclass(frozen=True)
class LocalQuadificationObjective:
    merged_pair_count: int
    total_score: float
    mean_score: float


GEOMETRY_CASE_CONFIGS: dict[str, GeometryCaseConfig] = {
    "wing_fuse": GeometryCaseConfig(
        name="wing_fuse",
        mesh_filename="wing_fuse_test.msh",
        step_filename="wing_fuse_test.stp",
        output_filename="wing_fuse_test_quad_dominant_symmetric.msh",
        component_patch_ranges={
            "wing": (0, 12),
            "fuse": (12, None),
        },
        protected_intersection_pairs=(("wing", "fuse"),),
    ),
    "wing_fuse_w_htail": GeometryCaseConfig(
        name="wing_fuse_w_htail",
        mesh_filename="wing_fuse_test_w_htail.msh",
        step_filename="wing_fuse_test_w_htail.stp",
        output_filename="wing_fuse_test_w_htail_quad_dominant_symmetric.msh",
        component_patch_ranges={
            "wing": (0, 12),
            "fuse": (12, 20),
            "htail": (20, None),
        },
        protected_intersection_pairs=(("wing", "fuse"), ("fuse", "htail")),
    ),
}

GEOMETRY_CASE_ALIASES = {
    "wing_fuse_htail": "wing_fuse_w_htail",
}


def _resolve_geometry_case(case_name: str) -> GeometryCaseConfig:
    canonical_case_name = GEOMETRY_CASE_ALIASES.get(case_name, case_name)
    try:
        return GEOMETRY_CASE_CONFIGS[canonical_case_name]
    except KeyError as exc:
        valid_case_names = sorted(
            set(GEOMETRY_CASE_CONFIGS) | set(GEOMETRY_CASE_ALIASES)
        )
        raise ValueError(
            f"Unsupported geometry case {case_name!r}. "
            f"Valid cases are: {', '.join(valid_case_names)}"
        ) from exc


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    valid_case_names = sorted(set(GEOMETRY_CASE_CONFIGS) | set(GEOMETRY_CASE_ALIASES))
    parser = argparse.ArgumentParser(
        description="Convert a symmetric wing/fuselage surface mesh to a quad-dominant mesh."
    )
    parser.add_argument(
        "--geometry-case",
        "--case",
        default=os.environ.get("BSM3_GEOMETRY_CASE", "wing_fuse"),
        choices=valid_case_names,
        help=(
            "Geometry preset to process. "
            "Can also be set with BSM3_GEOMETRY_CASE."
        ),
    )
    parser.add_argument(
        "--mesh-path",
        type=Path,
        default=None,
        help="Optional mesh path override for the selected geometry case.",
    )
    parser.add_argument(
        "--step-path",
        type=Path,
        default=None,
        help="Optional STEP path override for projected smoothing.",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help="Optional output mesh path override.",
    )
    args = parser.parse_args(argv)
    if args.geometry_case not in valid_case_names:
        parser.error(
            f"unsupported geometry case {args.geometry_case!r}; "
            f"choose from: {', '.join(valid_case_names)}"
        )
    return args


def read_gmsh22_surface_mesh(path: Path) -> SurfaceMesh:
    lines = path.read_text().splitlines()
    try:
        node_section_start = lines.index("$Nodes")
        element_section_start = lines.index("$Elements")
    except ValueError as exc:
        raise ValueError(f"{path} does not look like an ASCII Gmsh 2.2 file.") from exc

    num_nodes = int(lines[node_section_start + 1].strip())
    points = np.zeros((num_nodes, 3), dtype=float)
    node_id_to_index: dict[int, int] = {}
    for local_index in range(num_nodes):
        tokens = lines[node_section_start + 2 + local_index].split()
        node_id = int(tokens[0])
        node_id_to_index[node_id] = local_index
        points[local_index, :] = [float(tokens[1]), float(tokens[2]), float(tokens[3])]

    num_elements = int(lines[element_section_start + 1].strip())
    triangle_cells: list[list[int]] = []
    quad_cells: list[list[int]] = []
    for local_index in range(num_elements):
        tokens = lines[element_section_start + 2 + local_index].split()
        element_type = int(tokens[1])
        num_tags = int(tokens[2])
        connectivity = [node_id_to_index[int(value)] for value in tokens[3 + num_tags :]]
        if element_type == 2:
            triangle_cells.append(connectivity[:3])
        elif element_type == 3:
            quad_cells.append(connectivity[:4])

    triangles = (
        np.asarray(triangle_cells, dtype=np.int64)
        if triangle_cells
        else _empty_cells(3)
    )
    quads = np.asarray(quad_cells, dtype=np.int64) if quad_cells else _empty_cells(4)
    return SurfaceMesh(points=points, triangles=triangles, quads=quads)


def write_gmsh22_surface_mesh(path: Path, mesh: SurfaceMesh) -> None:
    total_cells = mesh.num_triangles + mesh.num_quads
    with path.open("w", encoding="utf-8") as stream:
        stream.write("$MeshFormat\n")
        stream.write("2.2 0 8\n")
        stream.write("$EndMeshFormat\n")
        stream.write("$Nodes\n")
        stream.write(f"{mesh.num_vertices}\n")
        for node_id, point in enumerate(mesh.points, start=1):
            stream.write(
                f"{node_id} {point[0]:.16g} {point[1]:.16g} {point[2]:.16g}\n"
            )
        stream.write("$EndNodes\n")
        stream.write("$Elements\n")
        stream.write(f"{total_cells}\n")
        element_id = 1
        for triangle in mesh.triangles:
            n0, n1, n2 = triangle + 1
            stream.write(f"{element_id} 2 0 {n0} {n1} {n2}\n")
            element_id += 1
        for quad in mesh.quads:
            n0, n1, n2, n3 = quad + 1
            stream.write(f"{element_id} 3 0 {n0} {n1} {n2} {n3}\n")
            element_id += 1
        stream.write("$EndElements\n")


def classify_symmetry(points: np.ndarray, triangles: np.ndarray, *, tol: float) -> SymmetryClassification:
    y_coordinates = np.asarray(points, dtype=float)[:, 1]
    positive_vertex_count = int(np.count_nonzero(y_coordinates > tol))
    negative_vertex_count = int(np.count_nonzero(y_coordinates < -tol))
    symmetry_plane_vertex_count = int(
        np.count_nonzero(np.abs(y_coordinates) <= tol)
    )

    if triangles.size == 0:
        positive_triangle_count = 0
        negative_triangle_count = 0
        crossing_triangle_count = 0
    else:
        triangle_y_coordinates = y_coordinates[np.asarray(triangles, dtype=np.int64)]
        positive_triangle_mask = np.all(triangle_y_coordinates >= -tol, axis=1)
        negative_triangle_mask = np.all(triangle_y_coordinates <= tol, axis=1)
        crossing_triangle_mask = ~(positive_triangle_mask | negative_triangle_mask)
        positive_triangle_count = int(np.count_nonzero(positive_triangle_mask))
        negative_triangle_count = int(np.count_nonzero(negative_triangle_mask))
        crossing_triangle_count = int(np.count_nonzero(crossing_triangle_mask))

    is_full_mesh = positive_vertex_count > 0 and negative_vertex_count > 0
    if positive_vertex_count > 0 and negative_vertex_count == 0:
        selected_side = "positive"
    elif negative_vertex_count > 0 and positive_vertex_count == 0:
        selected_side = "negative"
    else:
        selected_side = (
            "positive"
            if positive_triangle_count >= negative_triangle_count
            else "negative"
        )

    return SymmetryClassification(
        is_full_mesh=is_full_mesh,
        selected_side=selected_side,
        positive_vertex_count=positive_vertex_count,
        negative_vertex_count=negative_vertex_count,
        symmetry_plane_vertex_count=symmetry_plane_vertex_count,
        positive_triangle_count=positive_triangle_count,
        negative_triangle_count=negative_triangle_count,
        crossing_triangle_count=crossing_triangle_count,
    )


def _reindex_submesh(
    points: np.ndarray,
    triangles: np.ndarray,
    quads: np.ndarray,
) -> SurfaceMesh:
    used_vertex_indices_list: list[np.ndarray] = []
    if triangles.size > 0:
        used_vertex_indices_list.append(triangles.ravel())
    if quads.size > 0:
        used_vertex_indices_list.append(quads.ravel())
    if not used_vertex_indices_list:
        return SurfaceMesh(points=np.empty((0, 3), dtype=float), triangles=_empty_cells(3), quads=_empty_cells(4))

    used_vertex_indices = np.unique(np.concatenate(used_vertex_indices_list))
    old_to_new = -np.ones(points.shape[0], dtype=np.int64)
    old_to_new[used_vertex_indices] = np.arange(used_vertex_indices.size, dtype=np.int64)

    reindexed_triangles = old_to_new[triangles] if triangles.size > 0 else _empty_cells(3)
    reindexed_quads = old_to_new[quads] if quads.size > 0 else _empty_cells(4)
    return SurfaceMesh(
        points=np.asarray(points, dtype=float)[used_vertex_indices],
        triangles=reindexed_triangles,
        quads=reindexed_quads,
    )


def extract_half_mesh(mesh: SurfaceMesh, side: str, *, tol: float) -> SurfaceMesh:
    if side not in {"positive", "negative"}:
        raise ValueError(f"Unsupported side selection: {side}")

    y_coordinates = mesh.points[:, 1]
    if mesh.triangles.size > 0:
        triangle_y_coordinates = y_coordinates[mesh.triangles]
        if side == "positive":
            triangle_mask = np.all(triangle_y_coordinates >= -tol, axis=1)
            crossing_mask = np.any(triangle_y_coordinates < -tol, axis=1) & np.any(
                triangle_y_coordinates > tol, axis=1
            )
        else:
            triangle_mask = np.all(triangle_y_coordinates <= tol, axis=1)
            crossing_mask = np.any(triangle_y_coordinates < -tol, axis=1) & np.any(
                triangle_y_coordinates > tol, axis=1
            )
        if np.any(crossing_mask):
            raise ValueError(
                "Mesh contains triangles that cross the x-z symmetry plane; "
                "this script expects each triangle to lie on one side or on the plane."
            )
        selected_triangles = mesh.triangles[triangle_mask]
    else:
        selected_triangles = _empty_cells(3)

    if mesh.quads.size > 0:
        quad_y_coordinates = y_coordinates[mesh.quads]
        if side == "positive":
            quad_mask = np.all(quad_y_coordinates >= -tol, axis=1)
            crossing_mask = np.any(quad_y_coordinates < -tol, axis=1) & np.any(
                quad_y_coordinates > tol, axis=1
            )
        else:
            quad_mask = np.all(quad_y_coordinates <= tol, axis=1)
            crossing_mask = np.any(quad_y_coordinates < -tol, axis=1) & np.any(
                quad_y_coordinates > tol, axis=1
            )
        if np.any(crossing_mask):
            raise ValueError(
                "Mesh contains quads that cross the x-z symmetry plane; "
                "this script expects each quad to lie on one side or on the plane."
            )
        selected_quads = mesh.quads[quad_mask]
    else:
        selected_quads = _empty_cells(4)

    return _reindex_submesh(mesh.points, selected_triangles, selected_quads)


def _triangle_unit_normals(points: np.ndarray, triangles: np.ndarray, *, eps: float = 1e-14) -> np.ndarray:
    if triangles.size == 0:
        return np.empty((0, 3), dtype=float)
    triangle_points = np.asarray(points, dtype=float)[triangles]
    normals = np.cross(
        triangle_points[:, 1, :] - triangle_points[:, 0, :],
        triangle_points[:, 2, :] - triangle_points[:, 0, :],
    )
    normal_norm = np.linalg.norm(normals, axis=1)
    valid_mask = normal_norm > eps
    normals[valid_mask] /= normal_norm[valid_mask, None]
    normals[~valid_mask] = 0.0
    return normals


def _triangle_corner_angles(points: np.ndarray, triangle: np.ndarray) -> np.ndarray:
    triangle_points = np.asarray(points, dtype=float)[np.asarray(triangle, dtype=np.int64)]
    angles = np.zeros(3, dtype=float)
    for local_index in range(3):
        current_point = triangle_points[local_index]
        previous_edge = triangle_points[(local_index - 1) % 3] - current_point
        next_edge = triangle_points[(local_index + 1) % 3] - current_point
        previous_norm = np.linalg.norm(previous_edge)
        next_norm = np.linalg.norm(next_edge)
        if previous_norm <= 1e-14 or next_norm <= 1e-14:
            angles[local_index] = 180.0
            continue
        cosine = np.clip(
            np.dot(previous_edge, next_edge) / (previous_norm * next_norm),
            -1.0,
            1.0,
        )
        angles[local_index] = np.degrees(np.arccos(cosine))
    return angles


def _triangle_min_angle(points: np.ndarray, triangle: np.ndarray) -> float:
    return float(np.min(_triangle_corner_angles(points, triangle)))


def _triangle_aspect_ratio(points: np.ndarray, triangle: np.ndarray) -> float:
    triangle_points = np.asarray(points, dtype=float)[np.asarray(triangle, dtype=np.int64)]
    edge_lengths = np.linalg.norm(
        triangle_points[np.arange(3)] - triangle_points[np.roll(np.arange(3), -1)],
        axis=1,
    )
    return float(np.max(edge_lengths) / max(float(np.min(edge_lengths)), 1e-14))


def _triangle_area_magnitude(points: np.ndarray, triangle: np.ndarray) -> float:
    triangle_points = np.asarray(points, dtype=float)[np.asarray(triangle, dtype=np.int64)]
    return 0.5 * float(
        np.linalg.norm(
            np.cross(
                triangle_points[1] - triangle_points[0],
                triangle_points[2] - triangle_points[0],
            )
        )
    )


def _polygon_corner_scaled_jacobians(polygon_points: np.ndarray) -> np.ndarray:
    polygon_points = np.asarray(polygon_points, dtype=float)
    corner_scaled_jacobians = np.zeros(polygon_points.shape[0], dtype=float)
    for local_index in range(polygon_points.shape[0]):
        current_point = polygon_points[local_index]
        previous_edge = polygon_points[(local_index - 1) % polygon_points.shape[0]] - current_point
        next_edge = polygon_points[(local_index + 1) % polygon_points.shape[0]] - current_point
        denominator = np.linalg.norm(previous_edge) * np.linalg.norm(next_edge)
        if denominator <= 1e-14:
            corner_scaled_jacobians[local_index] = 0.0
            continue
        corner_scaled_jacobians[local_index] = float(
            np.linalg.norm(np.cross(previous_edge, next_edge)) / denominator
        )
    return corner_scaled_jacobians


def _triangle_min_scaled_jacobian(points: np.ndarray, triangle: np.ndarray) -> float:
    triangle_points = np.asarray(points, dtype=float)[np.asarray(triangle, dtype=np.int64)]
    return float(np.min(_polygon_corner_scaled_jacobians(triangle_points)))


def _build_vertex_neighbors_from_surface_mesh(mesh: SurfaceMesh) -> list[np.ndarray]:
    neighbor_sets = [set() for _ in range(mesh.num_vertices)]
    for triangle in np.asarray(mesh.triangles, dtype=np.int64):
        for edge_start, edge_end in _cycle_edges(triangle):
            neighbor_sets[edge_start].add(edge_end)
            neighbor_sets[edge_end].add(edge_start)
    for quad in np.asarray(mesh.quads, dtype=np.int64):
        for edge_start, edge_end in _cycle_edges(quad):
            neighbor_sets[edge_start].add(edge_end)
            neighbor_sets[edge_end].add(edge_start)
    return [np.asarray(sorted(neighbors), dtype=np.int64) for neighbors in neighbor_sets]


def _surface_laplacian_displacement(
    points: np.ndarray,
    adjacency: list[np.ndarray],
) -> np.ndarray:
    points = np.asarray(points, dtype=float)
    displacement = np.zeros_like(points)
    for vertex_index, neighbors in enumerate(adjacency):
        if neighbors.size == 0:
            continue
        displacement[vertex_index] = points[neighbors].mean(axis=0) - points[vertex_index]
    return displacement


def _vertex_mean_edge_lengths(
    points: np.ndarray,
    adjacency: list[np.ndarray],
) -> np.ndarray:
    points = np.asarray(points, dtype=float)
    mean_edge_lengths = np.zeros((points.shape[0],), dtype=float)
    for vertex_index, neighbors in enumerate(adjacency):
        if neighbors.size == 0:
            continue
        mean_edge_lengths[vertex_index] = float(
            np.mean(np.linalg.norm(points[neighbors] - points[vertex_index], axis=1))
        )
    return mean_edge_lengths


def _lazy_geometry_projection_imports():
    import importlib.util
    import types

    packages_root = Path(__file__).resolve().parents[4]
    candidate_roots = [
        Path(__file__).resolve().parents[3],
        packages_root / "CSDL_alpha",
        packages_root / "lsdo_function_spaces",
        packages_root / "FunSpace",
    ]
    for candidate_root in reversed(candidate_roots):
        candidate_root_str = str(candidate_root)
        if candidate_root.exists() and candidate_root_str not in sys.path:
            sys.path.insert(0, candidate_root_str)

    if importlib.util.find_spec("joblib") is None and "joblib" not in sys.modules:
        joblib_stub = types.ModuleType("joblib")

        def _delayed(function):
            def _wrapper(*args, **kwargs):
                return lambda: function(*args, **kwargs)

            return _wrapper

        class _Parallel:
            def __init__(self, *args, **kwargs):
                del args, kwargs

            def __call__(self, tasks):
                return [task() for task in tasks]

        joblib_stub.delayed = _delayed
        joblib_stub.Parallel = _Parallel
        sys.modules["joblib"] = joblib_stub

    try:
        import csdl_alpha as csdl  # type: ignore
        import lsdo_function_spaces as lfs  # type: ignore
        import bsm3 as bsm3_module  # type: ignore
    except ImportError as exc:  # pragma: no cover - dependency availability is environment-specific
        raise ImportError(
            "Projected smoothing requires csdl_alpha, lsdo_function_spaces, and bsm3."
        ) from exc
    return csdl, lfs, bsm3_module


def _ensure_inline_csdl_recorder(csdl_module):
    try:
        csdl_module.get_current_recorder()
    except ValueError:
        recorder = csdl_module.Recorder(inline=True)
        recorder.start()
        return recorder
    return None


def _stack_function_set_coefficients(function_set) -> np.ndarray:
    coefficient_blocks: list[np.ndarray] = []
    for patch_id in sorted(function_set.functions.keys()):
        coefficients = np.asarray(function_set.functions[int(patch_id)].coefficients.value, dtype=float)
        coefficient_blocks.append(coefficients.reshape(-1, coefficients.shape[-1]))
    if not coefficient_blocks:
        return np.empty((0, 3), dtype=float)
    return np.vstack(coefficient_blocks)


def _make_projection_model(bsm3_module, function_set):
    return bsm3_module.FunctionSetProjectionModel(
        function_set,
        warm_start_nu=40,
        warm_start_nv=40,
        edge_map_num_samples=25,
        output_mode="distance",
        debug=False,
    )


def _resolve_component_patch_keys(
    component_patch_ranges: dict[str, tuple[int, int | None]],
    *,
    num_functions: int,
) -> dict[str, np.ndarray]:
    component_patch_keys: dict[str, np.ndarray] = {}
    for component_name, (start_index, stop_index) in component_patch_ranges.items():
        start_index = int(start_index)
        resolved_stop_index = num_functions if stop_index is None else int(stop_index)
        if start_index < 0 or resolved_stop_index < start_index:
            raise ValueError(
                f"Invalid patch range for component {component_name!r}: "
                f"{start_index}:{resolved_stop_index}"
            )
        if resolved_stop_index > num_functions:
            raise ValueError(
                f"Patch range for component {component_name!r} ends at "
                f"{resolved_stop_index}, but the STEP import only has "
                f"{num_functions} functions."
            )
        if resolved_stop_index == start_index:
            raise ValueError(
                f"Component {component_name!r} has no patches in range "
                f"{start_index}:{resolved_stop_index}."
            )
        component_patch_keys[component_name] = np.arange(
            start_index,
            resolved_stop_index,
            dtype=int,
        )
    return component_patch_keys


def _load_geometry_projection_bundle(
    step_path: Path,
    *,
    component_patch_ranges: dict[str, tuple[int, int | None]],
) -> GeometryProjectionBundle:
    csdl, lfs, bsm3_module = _lazy_geometry_projection_imports()
    recorder = _ensure_inline_csdl_recorder(csdl)
    geometry = lfs.import_file_patched(step_path, parallelize=False)
    combined_coefficients = _stack_function_set_coefficients(geometry)
    combined_projection_model = _make_projection_model(bsm3_module, geometry)

    component_patch_keys = _resolve_component_patch_keys(
        component_patch_ranges,
        num_functions=len(geometry.functions),
    )
    available_function_keys = {int(key) for key in geometry.functions.keys()}
    component_projection_models: dict[str, object] = {}
    component_coefficients: dict[str, np.ndarray] = {}
    for component_name, patch_keys in component_patch_keys.items():
        missing_keys = [
            int(key)
            for key in patch_keys
            if int(key) not in available_function_keys
        ]
        if missing_keys:
            raise ValueError(
                f"Component {component_name!r} references missing STEP "
                f"function keys: {missing_keys}"
            )
        component_function_set = lfs.FunctionSet(
            functions={
                int(key): geometry.functions[int(key)]
                for key in patch_keys
            }
        )
        component_coefficients[component_name] = _stack_function_set_coefficients(
            component_function_set
        )
        component_projection_models[component_name] = _make_projection_model(
            bsm3_module,
            component_function_set,
        )

    return GeometryProjectionBundle(
        combined_projection_model=combined_projection_model,
        combined_coefficients=combined_coefficients,
        component_projection_models=component_projection_models,
        component_coefficients=component_coefficients,
        recorder=recorder,
    )


def _load_wing_fuse_projection_bundle(
    step_path: Path,
    *,
    wing_patch_count: int = 12,
) -> GeometryProjectionBundle:
    return _load_geometry_projection_bundle(
        step_path,
        component_patch_ranges={
            "wing": (0, wing_patch_count),
            "fuse": (wing_patch_count, None),
        },
    )


def _load_wing_fuse_projection_model(step_path: Path):
    bundle = _load_wing_fuse_projection_bundle(step_path)
    return (
        bundle.combined_projection_model,
        bundle.combined_coefficients,
        bundle.recorder,
    )


def _component_pair_intersection_vertex_masks(
    points: np.ndarray,
    projection_bundle: GeometryProjectionBundle,
    component_pairs: tuple[tuple[str, str], ...],
    *,
    intersection_tolerance: float = 1e-4,
) -> dict[tuple[str, str], np.ndarray]:
    points = np.asarray(points, dtype=float)
    component_names = sorted({name for pair in component_pairs for name in pair})
    component_close_masks: dict[str, np.ndarray] = {}
    for component_name in component_names:
        try:
            projection_model = projection_bundle.component_projection_models[component_name]
            coefficients = projection_bundle.component_coefficients[component_name]
        except KeyError as exc:
            available_components = ", ".join(
                sorted(projection_bundle.component_projection_models)
            )
            raise ValueError(
                f"Component {component_name!r} is not available in the "
                f"projection bundle. Available components: {available_components}"
            ) from exc
        distance, _ = projection_model.project(coefficients, points)
        component_close_masks[component_name] = (
            np.abs(np.asarray(distance, dtype=float)) < intersection_tolerance
        )

    return {
        pair: component_close_masks[pair[0]] & component_close_masks[pair[1]]
        for pair in component_pairs
    }


def _wing_fuse_intersection_vertex_mask(
    points: np.ndarray,
    projection_bundle: GeometryProjectionBundle,
    *,
    intersection_tolerance: float = 1e-4,
) -> np.ndarray:
    pair_masks = _component_pair_intersection_vertex_masks(
        points,
        projection_bundle,
        (("wing", "fuse"),),
        intersection_tolerance=intersection_tolerance,
    )
    return pair_masks[("wing", "fuse")]


def _parametric_boundary_vertex_mask(
    points: np.ndarray,
    projection_bundle: GeometryProjectionBundle,
    *,
    eps: float = 1e-10,
) -> np.ndarray:
    points = np.asarray(points, dtype=float)
    _, projection_state = projection_bundle.combined_projection_model.project(
        projection_bundle.combined_coefficients,
        points,
    )
    uv = np.asarray(projection_state["uv"], dtype=float)
    converged_mask = np.asarray(projection_state["converged"], dtype=bool)
    on_lower_edge = uv <= eps
    on_upper_edge = uv >= (1.0 - eps)
    on_parametric_boundary = np.any(on_lower_edge | on_upper_edge, axis=1)
    return converged_mask & on_parametric_boundary


def _build_triangle_edge_to_indices(
    triangles: np.ndarray,
) -> dict[tuple[int, int], list[int]]:
    edge_to_triangle_indices: dict[tuple[int, int], list[int]] = defaultdict(list)
    for triangle_index, triangle in enumerate(np.asarray(triangles, dtype=np.int64)):
        for edge in _cycle_edges(triangle):
            edge_to_triangle_indices[tuple(sorted(edge))].append(triangle_index)
    return edge_to_triangle_indices


def _cycle_edges(cell: np.ndarray) -> list[tuple[int, int]]:
    return [
        (int(cell[i]), int(cell[(i + 1) % cell.shape[0]]))
        for i in range(cell.shape[0])
    ]


def _newell_polygon_normal(points: np.ndarray) -> np.ndarray:
    polygon_normal = np.zeros(3, dtype=float)
    for index in range(points.shape[0]):
        polygon_normal += np.cross(points[index], points[(index + 1) % points.shape[0]])
    return polygon_normal


def _shared_edge(triangle_a: np.ndarray, triangle_b: np.ndarray) -> tuple[int, int] | None:
    shared_vertices = sorted(set(map(int, triangle_a)) & set(map(int, triangle_b)))
    if len(shared_vertices) != 2:
        return None
    return shared_vertices[0], shared_vertices[1]


def _order_quad_vertices(
    points: np.ndarray,
    triangle_a: np.ndarray,
    triangle_b: np.ndarray,
    normal_a: np.ndarray,
    normal_b: np.ndarray,
) -> np.ndarray | None:
    shared_edge = _shared_edge(triangle_a, triangle_b)
    if shared_edge is None:
        return None

    boundary_graph: dict[int, list[int]] = defaultdict(list)
    for edge in _cycle_edges(triangle_a):
        edge_key = tuple(sorted(edge))
        if edge_key == shared_edge:
            continue
        boundary_graph[edge[0]].append(edge[1])
        boundary_graph[edge[1]].append(edge[0])
    for edge in _cycle_edges(triangle_b):
        edge_key = tuple(sorted(edge))
        if edge_key == shared_edge:
            continue
        boundary_graph[edge[0]].append(edge[1])
        boundary_graph[edge[1]].append(edge[0])

    if len(boundary_graph) != 4 or any(len(neighbors) != 2 for neighbors in boundary_graph.values()):
        return None

    opposite_vertex_candidates = [vertex for vertex in triangle_a if vertex not in shared_edge]
    if len(opposite_vertex_candidates) != 1:
        return None
    start_vertex = int(opposite_vertex_candidates[0])

    ordered_vertices = [start_vertex]
    previous_vertex = None
    current_vertex = start_vertex
    while len(ordered_vertices) < 4:
        neighbors = boundary_graph[current_vertex]
        next_vertex = neighbors[0]
        if previous_vertex is not None and next_vertex == previous_vertex:
            next_vertex = neighbors[1]
        ordered_vertices.append(next_vertex)
        previous_vertex = current_vertex
        current_vertex = next_vertex

    if len(set(ordered_vertices)) != 4:
        return None

    ordered_vertices_array = np.asarray(ordered_vertices, dtype=np.int64)
    quad_normal = _newell_polygon_normal(points[ordered_vertices_array])
    reference_normal = normal_a + normal_b
    if np.dot(quad_normal, reference_normal) < 0.0:
        ordered_vertices_array = ordered_vertices_array[::-1]
    return ordered_vertices_array


def _quad_interior_angles(points: np.ndarray, quad: np.ndarray) -> np.ndarray:
    quad_points = points[quad]
    angles = np.zeros(4, dtype=float)
    for local_index in range(4):
        current_point = quad_points[local_index]
        previous_edge = quad_points[(local_index - 1) % 4] - current_point
        next_edge = quad_points[(local_index + 1) % 4] - current_point
        previous_norm = np.linalg.norm(previous_edge)
        next_norm = np.linalg.norm(next_edge)
        if previous_norm <= 1e-14 or next_norm <= 1e-14:
            angles[local_index] = 180.0
            continue
        cosine = np.clip(
            np.dot(previous_edge, next_edge) / (previous_norm * next_norm),
            -1.0,
            1.0,
        )
        angles[local_index] = np.degrees(np.arccos(cosine))
    return angles


def _quad_min_angle(points: np.ndarray, quad: np.ndarray) -> float:
    return float(np.min(_quad_interior_angles(points, quad)))


def _quad_aspect_ratio(points: np.ndarray, quad: np.ndarray) -> float:
    quad_points = np.asarray(points, dtype=float)[np.asarray(quad, dtype=np.int64)]
    edge_lengths = np.linalg.norm(
        quad_points[np.arange(4)] - quad_points[np.roll(np.arange(4), -1)],
        axis=1,
    )
    return float(np.max(edge_lengths) / max(float(np.min(edge_lengths)), 1e-14))


def _quad_planarity_ratio(points: np.ndarray, quad: np.ndarray) -> float:
    quad_points = points[quad]
    first_triangle_normal = np.cross(
        quad_points[1] - quad_points[0],
        quad_points[2] - quad_points[0],
    )
    normal_norm = np.linalg.norm(first_triangle_normal)
    edge_lengths = np.linalg.norm(
        quad_points[np.arange(4)] - quad_points[np.roll(np.arange(4), -1)],
        axis=1,
    )
    characteristic_length = max(float(edge_lengths.mean()), 1e-14)
    if normal_norm <= 1e-14:
        return np.inf
    unit_normal = first_triangle_normal / normal_norm
    signed_distances = np.abs((quad_points - quad_points[0]) @ unit_normal)
    return float(np.max(signed_distances) / characteristic_length)


def _quad_min_scaled_jacobian(points: np.ndarray, quad: np.ndarray) -> float:
    quad_points = np.asarray(points, dtype=float)[np.asarray(quad, dtype=np.int64)]
    return float(np.min(_polygon_corner_scaled_jacobians(quad_points)))


def _quad_unit_normal(points: np.ndarray, quad: np.ndarray, *, eps: float = 1e-14) -> np.ndarray:
    quad_points = np.asarray(points, dtype=float)[np.asarray(quad, dtype=np.int64)]
    normal = _newell_polygon_normal(quad_points)
    normal_norm = np.linalg.norm(normal)
    if normal_norm <= eps:
        return np.zeros((3,), dtype=float)
    return normal / normal_norm


def _build_vertex_to_face_indices(mesh: SurfaceMesh) -> list[np.ndarray]:
    vertex_to_face_indices: list[list[int]] = [[] for _ in range(mesh.num_vertices)]
    face_index = 0
    for triangle in np.asarray(mesh.triangles, dtype=np.int64):
        for vertex_index in triangle:
            vertex_to_face_indices[int(vertex_index)].append(face_index)
        face_index += 1
    for quad in np.asarray(mesh.quads, dtype=np.int64):
        for vertex_index in quad:
            vertex_to_face_indices[int(vertex_index)].append(face_index)
        face_index += 1
    return [np.asarray(indices, dtype=np.int64) for indices in vertex_to_face_indices]


def _mixed_face_quality_arrays(mesh: SurfaceMesh) -> MixedFaceQualityArrays:
    total_faces = mesh.num_triangles + mesh.num_quads
    min_angles = np.zeros((total_faces,), dtype=float)
    aspect_ratios = np.zeros((total_faces,), dtype=float)
    min_scaled_jacobians = np.zeros((total_faces,), dtype=float)
    planarity_ratios = np.zeros((total_faces,), dtype=float)
    is_quad = np.zeros((total_faces,), dtype=bool)

    face_index = 0
    for triangle in np.asarray(mesh.triangles, dtype=np.int64):
        min_angles[face_index] = _triangle_min_angle(mesh.points, triangle)
        aspect_ratios[face_index] = _triangle_aspect_ratio(mesh.points, triangle)
        min_scaled_jacobians[face_index] = _triangle_min_scaled_jacobian(mesh.points, triangle)
        planarity_ratios[face_index] = 0.0
        face_index += 1

    for quad in np.asarray(mesh.quads, dtype=np.int64):
        min_angles[face_index] = _quad_min_angle(mesh.points, quad)
        aspect_ratios[face_index] = _quad_aspect_ratio(mesh.points, quad)
        min_scaled_jacobians[face_index] = _quad_min_scaled_jacobian(mesh.points, quad)
        planarity_ratios[face_index] = _quad_planarity_ratio(mesh.points, quad)
        is_quad[face_index] = True
        face_index += 1

    return MixedFaceQualityArrays(
        min_angles_degrees=min_angles,
        aspect_ratios=aspect_ratios,
        min_scaled_jacobians=min_scaled_jacobians,
        planarity_ratios=planarity_ratios,
        is_quad=is_quad,
    )


def _mixed_face_unit_normals(mesh: SurfaceMesh) -> np.ndarray:
    total_faces = mesh.num_triangles + mesh.num_quads
    normals = np.zeros((total_faces, 3), dtype=float)
    face_index = 0
    if mesh.triangles.size > 0:
        triangle_normals = _triangle_unit_normals(mesh.points, mesh.triangles)
        normals[face_index : face_index + mesh.num_triangles] = triangle_normals
        face_index += mesh.num_triangles
    for quad in np.asarray(mesh.quads, dtype=np.int64):
        normals[face_index] = _quad_unit_normal(mesh.points, quad)
        face_index += 1
    return normals


def _build_mixed_edge_to_face_indices(mesh: SurfaceMesh) -> dict[tuple[int, int], list[int]]:
    edge_to_face_indices: dict[tuple[int, int], list[int]] = defaultdict(list)
    face_index = 0
    for triangle in np.asarray(mesh.triangles, dtype=np.int64):
        for edge in _cycle_edges(triangle):
            edge_to_face_indices[tuple(sorted(edge))].append(face_index)
        face_index += 1
    for quad in np.asarray(mesh.quads, dtype=np.int64):
        for edge in _cycle_edges(quad):
            edge_to_face_indices[tuple(sorted(edge))].append(face_index)
        face_index += 1
    return edge_to_face_indices


def _sharp_feature_vertex_mask_mixed(
    mesh: SurfaceMesh,
    *,
    feature_angle_degrees: float,
    include_boundary: bool = True,
) -> np.ndarray:
    feature_mask = np.zeros((mesh.num_vertices,), dtype=bool)
    face_normals = _mixed_face_unit_normals(mesh)
    cos_threshold = np.cos(np.radians(float(feature_angle_degrees)))

    for edge, face_indices in _build_mixed_edge_to_face_indices(mesh).items():
        vertex_i, vertex_j = edge
        if len(face_indices) == 1:
            if include_boundary:
                feature_mask[vertex_i] = True
                feature_mask[vertex_j] = True
            continue
        if len(face_indices) != 2:
            feature_mask[vertex_i] = True
            feature_mask[vertex_j] = True
            continue

        normal_a = face_normals[face_indices[0]]
        normal_b = face_normals[face_indices[1]]
        if np.dot(normal_a, normal_b) <= cos_threshold:
            feature_mask[vertex_i] = True
            feature_mask[vertex_j] = True
    return feature_mask


def _vertex_mask_from_face_mask(
    mesh: SurfaceMesh,
    face_mask: np.ndarray,
) -> np.ndarray:
    face_mask = np.asarray(face_mask, dtype=bool)
    vertex_mask = np.zeros((mesh.num_vertices,), dtype=bool)
    triangle_mask = face_mask[: mesh.num_triangles]
    quad_mask = face_mask[mesh.num_triangles :]
    if np.any(triangle_mask):
        vertex_mask[np.unique(mesh.triangles[triangle_mask])] = True
    if np.any(quad_mask):
        vertex_mask[np.unique(mesh.quads[quad_mask])] = True
    return vertex_mask


def _face_mask_from_vertex_mask(
    vertex_to_face_indices: list[np.ndarray],
    vertex_mask: np.ndarray,
    *,
    num_faces: int,
) -> np.ndarray:
    face_mask = np.zeros((num_faces,), dtype=bool)
    for vertex_index in np.flatnonzero(np.asarray(vertex_mask, dtype=bool)):
        face_mask[vertex_to_face_indices[int(vertex_index)]] = True
    return face_mask


def _expand_vertex_mask(
    seed_mask: np.ndarray,
    adjacency: list[np.ndarray],
    *,
    num_rings: int,
) -> np.ndarray:
    expanded_mask = np.asarray(seed_mask, dtype=bool).copy()
    frontier = np.flatnonzero(expanded_mask)
    for _ in range(max(0, num_rings)):
        next_frontier: list[int] = []
        for vertex_index in frontier:
            for neighbor_index in adjacency[int(vertex_index)]:
                if expanded_mask[int(neighbor_index)]:
                    continue
                expanded_mask[int(neighbor_index)] = True
                next_frontier.append(int(neighbor_index))
        if not next_frontier:
            break
        frontier = np.asarray(next_frontier, dtype=np.int64)
    return expanded_mask


def _local_quality_objective_key(
    quality: MixedFaceQualityArrays,
    face_indices: np.ndarray,
    *,
    bad_min_angle_degrees: float,
    bad_aspect_ratio: float,
    bad_min_scaled_jacobian: float,
    bad_quad_planarity_ratio: float,
) -> tuple[float, ...]:
    face_indices = np.asarray(face_indices, dtype=np.int64)
    if face_indices.size == 0:
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    min_angles = quality.min_angles_degrees[face_indices]
    aspect_ratios = quality.aspect_ratios[face_indices]
    min_scaled_jacobians = quality.min_scaled_jacobians[face_indices]
    planarity_ratios = quality.planarity_ratios[face_indices]
    is_quad = quality.is_quad[face_indices]

    low_angle_count = int(np.count_nonzero(min_angles < bad_min_angle_degrees))
    high_aspect_ratio_count = int(np.count_nonzero(aspect_ratios > bad_aspect_ratio))
    low_scaled_jacobian_count = int(
        np.count_nonzero(min_scaled_jacobians < bad_min_scaled_jacobian)
    )
    bad_planarity_count = int(
        np.count_nonzero(is_quad & (planarity_ratios > bad_quad_planarity_ratio))
    )

    penalty = float(
        3.5 * np.sum(np.maximum(0.0, bad_min_scaled_jacobian - min_scaled_jacobians))
        + 2.0 * np.sum(np.maximum(0.0, aspect_ratios - bad_aspect_ratio))
        + 1.5
        * np.sum(
            np.maximum(0.0, bad_min_angle_degrees - min_angles)
            / max(bad_min_angle_degrees, 1e-14)
        )
        + 0.5
        * np.sum(
            np.maximum(0.0, planarity_ratios - bad_quad_planarity_ratio)
            / max(bad_quad_planarity_ratio, 1e-14)
        )
    )
    return (
        float(low_scaled_jacobian_count),
        float(high_aspect_ratio_count),
        float(low_angle_count),
        float(bad_planarity_count),
        penalty,
        -float(np.min(min_scaled_jacobians)),
        float(np.max(aspect_ratios)),
        -float(np.min(min_angles)),
        float(np.max(planarity_ratios)),
    )


def smooth_surface_mesh_with_hard_projection(
    mesh: SurfaceMesh,
    projection_model,
    stacked_coefficients: np.ndarray,
    *,
    symmetry_tolerance: float,
    additional_protected_vertex_mask: np.ndarray | None = None,
    feature_angle_degrees: float = 105.0,
    num_iterations: int = 20,
    laplacian_step: float = 0.5,
    bad_min_angle_degrees: float = 20.0,
    bad_aspect_ratio: float = 2.0,
    bad_min_scaled_jacobian: float = 0.5,
    bad_quad_planarity_ratio: float = 0.1,
    bad_vertex_ring_count: int = 2,
    max_step_fraction_of_mean_edge: float = 0.35,
    max_line_search_trials: int = 30,
    min_projected_motion_norm: float = 1e-10,
) -> tuple[SurfaceMesh, ProjectedSmoothingStats]:
    if mesh.num_vertices == 0 or (mesh.num_triangles + mesh.num_quads) == 0:
        return (
            mesh,
            ProjectedSmoothingStats(
                attempted_iterations=0,
                accepted_iterations=0,
                protected_vertex_count=0,
                active_vertex_count=0,
                moved_vertex_count=0,
                projection_attempt_count=0,
                projection_converged_count=0,
                mean_projection_distance=np.nan,
                max_projection_distance=np.nan,
            ),
        )

    adjacency = _build_vertex_neighbors_from_surface_mesh(mesh)
    vertex_to_face_indices = _build_vertex_to_face_indices(mesh)
    current_points = mesh.points.copy()
    symmetry_plane_vertex_mask = np.abs(current_points[:, 1]) <= symmetry_tolerance
    if additional_protected_vertex_mask is None:
        extra_protected_vertex_mask = np.zeros((mesh.num_vertices,), dtype=bool)
    else:
        extra_protected_vertex_mask = np.asarray(
            additional_protected_vertex_mask,
            dtype=bool,
        ).reshape((mesh.num_vertices,))

    protected_vertex_mask = symmetry_plane_vertex_mask | extra_protected_vertex_mask
    active_vertex_union_mask = np.zeros((mesh.num_vertices,), dtype=bool)
    moved_vertex_union_mask = np.zeros((mesh.num_vertices,), dtype=bool)
    projection_distance_samples: list[np.ndarray] = []
    projection_attempt_count = 0
    projection_converged_count = 0
    attempted_iterations = 0
    accepted_iterations = 0

    for _ in range(max(0, num_iterations)):
        print("Iteration", attempted_iterations + 1)
        current_mesh = SurfaceMesh(
            points=current_points,
            triangles=mesh.triangles,
            quads=mesh.quads,
        )
        current_quality = _mixed_face_quality_arrays(current_mesh)
        current_feature_mask = _sharp_feature_vertex_mask_mixed(
            current_mesh,
            feature_angle_degrees=feature_angle_degrees,
            include_boundary=True,
        )
        protected_vertex_mask = (
            symmetry_plane_vertex_mask
            | extra_protected_vertex_mask
            | current_feature_mask
        )

        bad_face_mask = (
            (current_quality.min_angles_degrees < bad_min_angle_degrees)
            | (current_quality.aspect_ratios > bad_aspect_ratio)
            | (current_quality.min_scaled_jacobians < bad_min_scaled_jacobian)
            | (
                current_quality.is_quad
                & (current_quality.planarity_ratios > bad_quad_planarity_ratio)
            )
        )
        if not np.any(bad_face_mask):
            break

        seed_vertex_mask = _vertex_mask_from_face_mask(current_mesh, bad_face_mask)
        active_vertex_mask = _expand_vertex_mask(
            seed_vertex_mask,
            adjacency,
            num_rings=bad_vertex_ring_count,
        )
        movable_vertex_mask = active_vertex_mask & ~protected_vertex_mask
        if not np.any(movable_vertex_mask):
            break

        attempted_iterations += 1
        active_vertex_union_mask |= active_vertex_mask
        affected_face_mask = _face_mask_from_vertex_mask(
            vertex_to_face_indices,
            active_vertex_mask,
            num_faces=mesh.num_triangles + mesh.num_quads,
        )
        affected_face_indices = np.flatnonzero(affected_face_mask)
        baseline_key = _local_quality_objective_key(
            current_quality,
            affected_face_indices,
            bad_min_angle_degrees=bad_min_angle_degrees,
            bad_aspect_ratio=bad_aspect_ratio,
            bad_min_scaled_jacobian=bad_min_scaled_jacobian,
            bad_quad_planarity_ratio=bad_quad_planarity_ratio,
        )

        laplacian = _surface_laplacian_displacement(current_points, adjacency)
        mean_edge_lengths = _vertex_mean_edge_lengths(current_points, adjacency)
        movable_vertex_indices = np.flatnonzero(movable_vertex_mask)
        accepted_iteration = False
        trial_step = laplacian_step
        for _ in range(max(1, max_line_search_trials)):
            proposed_displacements = trial_step * laplacian[movable_vertex_indices]
            clip_limits = max_step_fraction_of_mean_edge * mean_edge_lengths[movable_vertex_indices]
            displacement_norms = np.linalg.norm(proposed_displacements, axis=1)
            nonzero_mask = displacement_norms > 1e-14
            if np.any(nonzero_mask):
                scaling = np.ones_like(displacement_norms)
                scaling[nonzero_mask] = np.minimum(
                    1.0,
                    clip_limits[nonzero_mask] / displacement_norms[nonzero_mask],
                )
                proposed_displacements *= scaling[:, None]

            predicted_points = current_points[movable_vertex_indices] + proposed_displacements
            projection_distances, projection_state = projection_model.project(
                stacked_coefficients,
                predicted_points,
            )
            projection_attempt_count += int(movable_vertex_indices.size)
            projection_converged_mask = np.asarray(projection_state["converged"], dtype=bool)
            projection_converged_count += int(np.count_nonzero(projection_converged_mask))
            projection_distance_samples.append(np.abs(np.asarray(projection_distances, dtype=float)))

            if not np.any(projection_converged_mask):
                trial_step *= 0.5
                continue

            projected_points = np.asarray(projection_state["projected_points"], dtype=float)
            projected_motion_norms = np.linalg.norm(
                projected_points - current_points[movable_vertex_indices],
                axis=1,
            )
            accepted_projection_mask = projection_converged_mask & (
                projected_motion_norms > min_projected_motion_norm
            )
            if not np.any(accepted_projection_mask):
                trial_step *= 0.5
                continue

            candidate_points = current_points.copy()
            candidate_points[movable_vertex_indices[accepted_projection_mask]] = projected_points[
                accepted_projection_mask
            ]
            candidate_mesh = SurfaceMesh(
                points=candidate_points,
                triangles=mesh.triangles,
                quads=mesh.quads,
            )
            candidate_quality = _mixed_face_quality_arrays(candidate_mesh)
            candidate_key = _local_quality_objective_key(
                candidate_quality,
                affected_face_indices,
                bad_min_angle_degrees=bad_min_angle_degrees,
                bad_aspect_ratio=bad_aspect_ratio,
                bad_min_scaled_jacobian=bad_min_scaled_jacobian,
                bad_quad_planarity_ratio=bad_quad_planarity_ratio,
            )
            if candidate_key < baseline_key:
                current_points = candidate_points
                moved_vertex_union_mask[
                    movable_vertex_indices[accepted_projection_mask]
                ] = True
                accepted_iterations += 1
                accepted_iteration = True
                break

            trial_step *= 0.5

        if not accepted_iteration:
            break

    if projection_distance_samples:
        all_projection_distances = np.concatenate(projection_distance_samples)
        mean_projection_distance = float(np.mean(all_projection_distances))
        max_projection_distance = float(np.max(all_projection_distances))
    else:
        mean_projection_distance = np.nan
        max_projection_distance = np.nan

    return (
        SurfaceMesh(
            points=current_points,
            triangles=mesh.triangles.copy(),
            quads=mesh.quads.copy(),
        ),
        ProjectedSmoothingStats(
            attempted_iterations=attempted_iterations,
            accepted_iterations=accepted_iterations,
            protected_vertex_count=int(np.count_nonzero(protected_vertex_mask)),
            active_vertex_count=int(np.count_nonzero(active_vertex_union_mask)),
            moved_vertex_count=int(np.count_nonzero(moved_vertex_union_mask)),
            projection_attempt_count=projection_attempt_count,
            projection_converged_count=projection_converged_count,
            mean_projection_distance=mean_projection_distance,
            max_projection_distance=max_projection_distance,
        ),
    )


def _quad_candidate_score(
    points: np.ndarray,
    quad: np.ndarray,
    normal_a: np.ndarray,
    normal_b: np.ndarray,
) -> float:
    quad_points = points[quad]
    edge_lengths = np.linalg.norm(
        quad_points[np.arange(4)] - quad_points[np.roll(np.arange(4), -1)],
        axis=1,
    )
    mean_edge_length = max(float(edge_lengths.mean()), 1e-14)
    diagonal_lengths = np.array(
        [
            np.linalg.norm(quad_points[2] - quad_points[0]),
            np.linalg.norm(quad_points[3] - quad_points[1]),
        ],
        dtype=float,
    )
    angle_penalty = float(np.mean(np.abs(_quad_interior_angles(points, quad) - 90.0)) / 90.0)
    edge_balance_penalty = float(np.std(edge_lengths) / mean_edge_length)
    diagonal_balance_penalty = float(
        np.abs(diagonal_lengths[0] - diagonal_lengths[1]) / max(float(diagonal_lengths.mean()), 1e-14)
    )
    normal_alignment_penalty = float(1.0 - np.clip(np.dot(normal_a, normal_b), -1.0, 1.0))
    planarity_penalty = _quad_planarity_ratio(points, quad)
    return (
        0.45 * angle_penalty
        + 0.2 * edge_balance_penalty
        + 0.1 * diagonal_balance_penalty
        + 0.15 * normal_alignment_penalty
        + 0.1 * planarity_penalty
    )


def _evaluate_triangle_pair_quad_candidate(
    points: np.ndarray,
    triangle_a: np.ndarray,
    triangle_b: np.ndarray,
    normal_a: np.ndarray,
    normal_b: np.ndarray,
    *,
    max_normal_deviation_cosine: float,
    min_interior_angle_degrees: float,
    max_interior_angle_degrees: float,
    max_planarity_ratio: float,
    max_candidate_score: float | None,
) -> tuple[float, np.ndarray] | None:
    normal_alignment = float(np.dot(normal_a, normal_b))
    if normal_alignment < max_normal_deviation_cosine:
        return None

    quad = _order_quad_vertices(
        points,
        triangle_a,
        triangle_b,
        normal_a,
        normal_b,
    )
    if quad is None:
        return None

    interior_angles = _quad_interior_angles(points, quad)
    if np.min(interior_angles) < min_interior_angle_degrees:
        return None
    if np.max(interior_angles) > max_interior_angle_degrees:
        return None

    planarity_ratio = _quad_planarity_ratio(points, quad)
    if planarity_ratio > max_planarity_ratio:
        return None

    score = _quad_candidate_score(points, quad, normal_a, normal_b)
    if max_candidate_score is not None and score > max_candidate_score:
        return None
    return score, quad


def _build_quad_merge_candidates(
    mesh: SurfaceMesh,
    *,
    max_normal_deviation_degrees: float,
    min_interior_angle_degrees: float,
    max_interior_angle_degrees: float,
    max_planarity_ratio: float,
    max_candidate_score: float | None = None,
) -> list[QuadMergeCandidate]:
    triangles = np.asarray(mesh.triangles, dtype=np.int64)
    if triangles.size == 0:
        return []

    normals = _triangle_unit_normals(mesh.points, triangles)
    edge_to_triangle_indices = _build_triangle_edge_to_indices(triangles)
    max_normal_deviation_cosine = np.cos(np.radians(max_normal_deviation_degrees))
    raw_candidates: list[tuple[float, int, int, np.ndarray]] = []
    for incident_triangle_indices in edge_to_triangle_indices.values():
        if len(incident_triangle_indices) != 2:
            continue
        triangle_index_a, triangle_index_b = incident_triangle_indices
        evaluated_pair = _evaluate_triangle_pair_quad_candidate(
            mesh.points,
            triangles[triangle_index_a],
            triangles[triangle_index_b],
            normals[triangle_index_a],
            normals[triangle_index_b],
            max_normal_deviation_cosine=max_normal_deviation_cosine,
            min_interior_angle_degrees=min_interior_angle_degrees,
            max_interior_angle_degrees=max_interior_angle_degrees,
            max_planarity_ratio=max_planarity_ratio,
            max_candidate_score=max_candidate_score,
        )
        if evaluated_pair is None:
            continue

        score, quad = evaluated_pair
        raw_candidates.append((score, triangle_index_a, triangle_index_b, quad))

    if not raw_candidates:
        return []

    scores = np.asarray([candidate[0] for candidate in raw_candidates], dtype=float)
    score_min = float(np.min(scores))
    score_max = float(np.max(scores))
    score_span = max(score_max - score_min, 1e-12)

    candidates: list[QuadMergeCandidate] = []
    for score, triangle_index_a, triangle_index_b, quad in raw_candidates:
        normalized_quality = (score_max - score) / score_span
        candidates.append(
            QuadMergeCandidate(
                score=score,
                weight=1.0 + normalized_quality,
                triangle_index_a=triangle_index_a,
                triangle_index_b=triangle_index_b,
                quad=quad,
            )
        )
    return candidates


def _select_greedy_merge_candidates(
    candidates: list[QuadMergeCandidate],
    *,
    num_triangles: int,
) -> list[QuadMergeCandidate]:
    sorted_candidates = sorted(candidates, key=lambda candidate: candidate.score)
    used_triangle_mask = np.zeros(num_triangles, dtype=bool)
    selected_candidates: list[QuadMergeCandidate] = []
    for candidate in sorted_candidates:
        if (
            used_triangle_mask[candidate.triangle_index_a]
            or used_triangle_mask[candidate.triangle_index_b]
        ):
            continue
        used_triangle_mask[candidate.triangle_index_a] = True
        used_triangle_mask[candidate.triangle_index_b] = True
        selected_candidates.append(candidate)
    return selected_candidates


def _select_exact_merge_candidates(
    candidates: list[QuadMergeCandidate],
) -> list[QuadMergeCandidate]:
    if not candidates:
        return []

    graph = nx.Graph()
    for candidate_index, candidate in enumerate(candidates):
        graph.add_edge(
            candidate.triangle_index_a,
            candidate.triangle_index_b,
            weight=candidate.weight,
            score=candidate.score,
            candidate_index=candidate_index,
        )

    selected_candidates: list[QuadMergeCandidate] = []
    for component_nodes in nx.connected_components(graph):
        component_graph = graph.subgraph(component_nodes)
        component_matching = nx.algorithms.matching.max_weight_matching(
            component_graph,
            maxcardinality=True,
            weight="weight",
        )
        for triangle_index_a, triangle_index_b in component_matching:
            edge_data = graph.get_edge_data(triangle_index_a, triangle_index_b)
            selected_candidates.append(candidates[edge_data["candidate_index"]])

    selected_candidates.sort(key=lambda candidate: candidate.score)
    return selected_candidates


def _local_candidate_score_ceiling(
    points: np.ndarray,
    triangles: np.ndarray,
    *,
    base_max_candidate_score: float | None,
    relaxation_cap: float = 0.02,
) -> float | None:
    if base_max_candidate_score is None or relaxation_cap <= 0.0 or triangles.size == 0:
        return base_max_candidate_score

    normals = _triangle_unit_normals(points, triangles)
    valid_mask = np.linalg.norm(normals, axis=1) > 1e-14
    if not np.any(valid_mask):
        return base_max_candidate_score

    representative_normal = np.sum(normals[valid_mask], axis=0)
    representative_norm = np.linalg.norm(representative_normal)
    if representative_norm <= 1e-14:
        return base_max_candidate_score
    representative_normal /= representative_norm

    alignments = np.clip(
        np.abs(normals[valid_mask] @ representative_normal),
        0.0,
        1.0,
    )
    flatness = np.clip((float(np.mean(alignments)) - 0.97) / 0.03, 0.0, 1.0)
    return float(base_max_candidate_score + relaxation_cap * flatness)


def _triangle_pair_flip_is_reasonable(
    points: np.ndarray,
    current_triangle_pair: tuple[np.ndarray, np.ndarray],
    proposed_triangle_pair: tuple[np.ndarray, np.ndarray],
    *,
    absolute_min_angle_degrees: float = 12.0,
    max_aspect_ratio: float = 4.0,
) -> bool:
    proposed_min_angles = np.array(
        [
            _triangle_min_angle(points, proposed_triangle_pair[0]),
            _triangle_min_angle(points, proposed_triangle_pair[1]),
        ],
        dtype=float,
    )
    if float(np.min(proposed_min_angles)) < absolute_min_angle_degrees:
        return False

    proposed_aspect_ratios = np.array(
        [
            _triangle_aspect_ratio(points, proposed_triangle_pair[0]),
            _triangle_aspect_ratio(points, proposed_triangle_pair[1]),
        ],
        dtype=float,
    )
    if float(np.max(proposed_aspect_ratios)) > max_aspect_ratio:
        return False

    current_min_angles = np.array(
        [
            _triangle_min_angle(points, current_triangle_pair[0]),
            _triangle_min_angle(points, current_triangle_pair[1]),
        ],
        dtype=float,
    )
    if float(np.min(proposed_min_angles)) + 1.0 < float(np.min(current_min_angles)):
        return False
    return True


def _proposed_flipped_triangle_pair(
    points: np.ndarray,
    triangle_a: np.ndarray,
    triangle_b: np.ndarray,
    *,
    edge_to_triangle_indices: dict[tuple[int, int], list[int]],
) -> tuple[np.ndarray, np.ndarray] | None:
    normals = _triangle_unit_normals(
        points,
        np.vstack(
            [
                np.asarray(triangle_a, dtype=np.int64),
                np.asarray(triangle_b, dtype=np.int64),
            ]
        ),
    )
    quad_boundary = _order_quad_vertices(
        points,
        triangle_a,
        triangle_b,
        normals[0],
        normals[1],
    )
    if quad_boundary is None:
        return None

    proposed_diagonal = tuple(sorted((int(quad_boundary[0]), int(quad_boundary[2]))))
    if proposed_diagonal in edge_to_triangle_indices:
        return None

    reference_normal = normals[0] + normals[1]
    if np.linalg.norm(reference_normal) <= 1e-14:
        return None

    proposed_triangle_a = np.asarray(
        [quad_boundary[0], quad_boundary[1], quad_boundary[2]],
        dtype=np.int64,
    )
    proposed_triangle_b = np.asarray(
        [quad_boundary[0], quad_boundary[2], quad_boundary[3]],
        dtype=np.int64,
    )
    for proposed_triangle in (proposed_triangle_a, proposed_triangle_b):
        area_vector = np.cross(
            points[proposed_triangle[1]] - points[proposed_triangle[0]],
            points[proposed_triangle[2]] - points[proposed_triangle[0]],
        )
        if np.dot(area_vector, reference_normal) < 0.0:
            proposed_triangle[[1, 2]] = proposed_triangle[[2, 1]]
        if _triangle_area_magnitude(points, proposed_triangle) <= 1e-14:
            return None

    return proposed_triangle_a, proposed_triangle_b


def _local_patch_quadification_objective(
    points: np.ndarray,
    patch_triangles: np.ndarray,
    *,
    max_normal_deviation_degrees: float,
    min_interior_angle_degrees: float,
    max_interior_angle_degrees: float,
    max_planarity_ratio: float,
    max_candidate_score: float | None,
) -> LocalQuadificationObjective:
    patch_mesh = SurfaceMesh(
        points=np.asarray(points, dtype=float),
        triangles=np.asarray(patch_triangles, dtype=np.int64),
        quads=_empty_cells(4),
    )
    patch_candidates = _build_quad_merge_candidates(
        patch_mesh,
        max_normal_deviation_degrees=max_normal_deviation_degrees,
        min_interior_angle_degrees=min_interior_angle_degrees,
        max_interior_angle_degrees=max_interior_angle_degrees,
        max_planarity_ratio=max_planarity_ratio,
        max_candidate_score=max_candidate_score,
    )
    selected_candidates = _select_exact_merge_candidates(patch_candidates)
    if not selected_candidates:
        return LocalQuadificationObjective(
            merged_pair_count=0,
            total_score=0.0,
            mean_score=np.inf,
        )

    selected_scores = np.asarray(
        [candidate.score for candidate in selected_candidates],
        dtype=float,
    )
    return LocalQuadificationObjective(
        merged_pair_count=int(selected_scores.size),
        total_score=float(np.sum(selected_scores)),
        mean_score=float(np.mean(selected_scores)),
    )


def _local_quadification_objective_is_better(
    baseline: LocalQuadificationObjective,
    proposed: LocalQuadificationObjective,
) -> bool:
    if proposed.merged_pair_count != baseline.merged_pair_count:
        return proposed.merged_pair_count > baseline.merged_pair_count
    if proposed.total_score != baseline.total_score:
        return proposed.total_score < baseline.total_score - 1e-12
    return proposed.mean_score < baseline.mean_score - 1e-12


def _flip_patch_triangle_indices(
    triangles: np.ndarray,
    edge_to_triangle_indices: dict[tuple[int, int], list[int]],
    triangle_index_a: int,
    triangle_index_b: int,
) -> list[int]:
    patch_indices = {triangle_index_a, triangle_index_b}
    for triangle_index in (triangle_index_a, triangle_index_b):
        for edge in _cycle_edges(triangles[triangle_index]):
            patch_indices.update(edge_to_triangle_indices[tuple(sorted(edge))])
    return sorted(patch_indices)


def _apply_premerge_edge_flips(
    mesh: SurfaceMesh,
    *,
    max_normal_deviation_degrees: float,
    min_interior_angle_degrees: float,
    max_interior_angle_degrees: float,
    max_planarity_ratio: float,
    base_max_candidate_score: float | None,
    max_passes: int = 2,
    max_accepted_flips: int = 128,
    local_score_relaxation_cap: float = 0.02,
) -> tuple[SurfaceMesh, int]:
    triangles = np.asarray(mesh.triangles, dtype=np.int64).copy()
    if triangles.shape[0] < 2:
        return mesh, 0

    accepted_flip_count = 0
    for _ in range(max_passes):
        made_change = False
        edge_to_triangle_indices = _build_triangle_edge_to_indices(triangles)
        for edge_key, incident_triangle_indices in edge_to_triangle_indices.items():
            if len(incident_triangle_indices) != 2:
                continue
            triangle_index_a, triangle_index_b = incident_triangle_indices
            current_triangle_a = triangles[triangle_index_a].copy()
            current_triangle_b = triangles[triangle_index_b].copy()

            local_score_ceiling = _local_candidate_score_ceiling(
                mesh.points,
                np.vstack([current_triangle_a, current_triangle_b]),
                base_max_candidate_score=base_max_candidate_score,
                relaxation_cap=local_score_relaxation_cap,
            )
            current_normals = _triangle_unit_normals(
                mesh.points,
                np.vstack([current_triangle_a, current_triangle_b]),
            )
            current_pair_candidate = _evaluate_triangle_pair_quad_candidate(
                mesh.points,
                current_triangle_a,
                current_triangle_b,
                current_normals[0],
                current_normals[1],
                max_normal_deviation_cosine=np.cos(
                    np.radians(max_normal_deviation_degrees)
                ),
                min_interior_angle_degrees=min_interior_angle_degrees,
                max_interior_angle_degrees=max_interior_angle_degrees,
                max_planarity_ratio=max_planarity_ratio,
                max_candidate_score=local_score_ceiling,
            )
            if current_pair_candidate is not None:
                continue

            proposed_triangle_pair = _proposed_flipped_triangle_pair(
                mesh.points,
                current_triangle_a,
                current_triangle_b,
                edge_to_triangle_indices=edge_to_triangle_indices,
            )
            if proposed_triangle_pair is None:
                continue
            if not _triangle_pair_flip_is_reasonable(
                mesh.points,
                (current_triangle_a, current_triangle_b),
                proposed_triangle_pair,
            ):
                continue

            patch_triangle_indices = _flip_patch_triangle_indices(
                triangles,
                edge_to_triangle_indices,
                triangle_index_a,
                triangle_index_b,
            )
            patch_triangle_lookup = {
                triangle_index: local_index
                for local_index, triangle_index in enumerate(patch_triangle_indices)
            }
            current_patch_triangles = triangles[patch_triangle_indices].copy()
            proposed_patch_triangles = current_patch_triangles.copy()
            proposed_patch_triangles[patch_triangle_lookup[triangle_index_a]] = proposed_triangle_pair[0]
            proposed_patch_triangles[patch_triangle_lookup[triangle_index_b]] = proposed_triangle_pair[1]

            patch_score_ceiling = _local_candidate_score_ceiling(
                mesh.points,
                current_patch_triangles,
                base_max_candidate_score=base_max_candidate_score,
                relaxation_cap=local_score_relaxation_cap,
            )
            current_objective = _local_patch_quadification_objective(
                mesh.points,
                current_patch_triangles,
                max_normal_deviation_degrees=max_normal_deviation_degrees,
                min_interior_angle_degrees=min_interior_angle_degrees,
                max_interior_angle_degrees=max_interior_angle_degrees,
                max_planarity_ratio=max_planarity_ratio,
                max_candidate_score=patch_score_ceiling,
            )
            proposed_objective = _local_patch_quadification_objective(
                mesh.points,
                proposed_patch_triangles,
                max_normal_deviation_degrees=max_normal_deviation_degrees,
                min_interior_angle_degrees=min_interior_angle_degrees,
                max_interior_angle_degrees=max_interior_angle_degrees,
                max_planarity_ratio=max_planarity_ratio,
                max_candidate_score=patch_score_ceiling,
            )
            if not _local_quadification_objective_is_better(
                current_objective,
                proposed_objective,
            ):
                continue

            triangles[triangle_index_a] = proposed_triangle_pair[0]
            triangles[triangle_index_b] = proposed_triangle_pair[1]
            accepted_flip_count += 1
            made_change = True
            break
        if not made_change or accepted_flip_count >= max_accepted_flips:
            break

    return SurfaceMesh(
        points=mesh.points.copy(),
        triangles=triangles,
        quads=mesh.quads.copy(),
    ), accepted_flip_count


def _select_matching_refined_merge_candidates(
    candidates: list[QuadMergeCandidate],
    *,
    exact_component_node_threshold: int = 256,
    refinement_radius: int = 2,
    max_refinement_passes: int = 2,
) -> list[QuadMergeCandidate]:
    if not candidates:
        return []

    graph = nx.Graph()
    for candidate_index, candidate in enumerate(candidates):
        graph.add_edge(
            candidate.triangle_index_a,
            candidate.triangle_index_b,
            weight=candidate.weight,
            score=candidate.score,
            candidate_index=candidate_index,
        )

    selected_candidates: list[QuadMergeCandidate] = []
    for component_nodes in nx.connected_components(graph):
        component_graph = graph.subgraph(component_nodes)
        if component_graph.number_of_nodes() <= exact_component_node_threshold:
            component_matching = nx.algorithms.matching.max_weight_matching(
                component_graph,
                maxcardinality=True,
                weight="weight",
            )
        else:
            component_matching = _refine_component_matching(
                component_graph,
                refinement_radius=refinement_radius,
                max_refinement_passes=max_refinement_passes,
            )
        for triangle_index_a, triangle_index_b in component_matching:
            edge_data = graph.get_edge_data(triangle_index_a, triangle_index_b)
            selected_candidates.append(candidates[edge_data["candidate_index"]])
    selected_candidates.sort(key=lambda candidate: candidate.score)
    return selected_candidates


def _canonical_edge(node_a: int, node_b: int) -> tuple[int, int]:
    return (node_a, node_b) if node_a < node_b else (node_b, node_a)


def _matching_weight(
    graph: nx.Graph,
    matching_edges: list[tuple[int, int]] | set[tuple[int, int]],
) -> float:
    total_weight = 0.0
    for node_a, node_b in matching_edges:
        total_weight += float(graph.edges[node_a, node_b]["weight"])
    return total_weight


def _current_matching_edges(
    matched_partner: dict[int, int | None],
    node_subset: set[int] | None = None,
) -> list[tuple[int, int]]:
    matching_edges: list[tuple[int, int]] = []
    for node_a, node_b in matched_partner.items():
        if node_b is None or node_a >= node_b:
            continue
        if node_subset is not None and (
            node_a not in node_subset or node_b not in node_subset
        ):
            continue
        matching_edges.append((node_a, node_b))
    return matching_edges


def _window_nodes(
    graph: nx.Graph,
    seed_node: int,
    *,
    radius: int,
) -> set[int]:
    return set(
        nx.single_source_shortest_path_length(
            graph,
            seed_node,
            cutoff=radius,
        ).keys()
    )


def _matching_is_better(
    candidate_matching: list[tuple[int, int]] | set[tuple[int, int]],
    baseline_matching: list[tuple[int, int]] | set[tuple[int, int]],
    graph: nx.Graph,
) -> bool:
    candidate_cardinality = len(candidate_matching)
    baseline_cardinality = len(baseline_matching)
    if candidate_cardinality != baseline_cardinality:
        return candidate_cardinality > baseline_cardinality
    return _matching_weight(graph, candidate_matching) > _matching_weight(
        graph,
        baseline_matching,
    ) + 1e-12


def _refine_component_matching(
    component_graph: nx.Graph,
    *,
    refinement_radius: int,
    max_refinement_passes: int,
) -> set[tuple[int, int]]:
    component_candidates = [
        QuadMergeCandidate(
            score=float(component_graph.edges[node_a, node_b]["score"]),
            weight=float(component_graph.edges[node_a, node_b]["weight"]),
            triangle_index_a=int(node_a),
            triangle_index_b=int(node_b),
            quad=np.empty((0,), dtype=np.int64),
        )
        for node_a, node_b in component_graph.edges()
    ]
    greedy_candidates = _select_greedy_merge_candidates(
        component_candidates,
        num_triangles=max(component_graph.nodes) + 1,
    )

    matched_partner: dict[int, int | None] = {
        int(node): None for node in component_graph.nodes()
    }
    for candidate in greedy_candidates:
        matched_partner[candidate.triangle_index_a] = candidate.triangle_index_b
        matched_partner[candidate.triangle_index_b] = candidate.triangle_index_a

    component_nodes = sorted(component_graph.nodes())
    for _ in range(max_refinement_passes):
        improved = False
        for seed_node in component_nodes:
            local_nodes = _window_nodes(
                component_graph,
                seed_node,
                radius=refinement_radius,
            )
            blocked_nodes = {
                node
                for node in local_nodes
                if matched_partner[node] is not None
                and matched_partner[node] not in local_nodes
            }
            free_nodes = local_nodes - blocked_nodes
            if len(free_nodes) <= 1:
                continue

            local_subgraph = component_graph.subgraph(free_nodes)
            current_local_matching = _current_matching_edges(
                matched_partner,
                node_subset=free_nodes,
            )
            optimal_local_matching = list(
                nx.algorithms.matching.max_weight_matching(
                    local_subgraph,
                    maxcardinality=True,
                    weight="weight",
                )
            )
            if not _matching_is_better(
                optimal_local_matching,
                current_local_matching,
                component_graph,
            ):
                continue

            for node_a, node_b in current_local_matching:
                matched_partner[node_a] = None
                matched_partner[node_b] = None
            for node_a, node_b in optimal_local_matching:
                matched_partner[node_a] = node_b
                matched_partner[node_b] = node_a
            improved = True
        if not improved:
            break

    return set(_current_matching_edges(matched_partner))


def _mesh_from_selected_candidates(
    mesh: SurfaceMesh,
    selected_candidates: list[QuadMergeCandidate],
    *,
    matching_method: str,
) -> tuple[SurfaceMesh, QuadDominantConversionStats]:
    triangles = np.asarray(mesh.triangles, dtype=np.int64)
    used_triangle_mask = np.zeros(triangles.shape[0], dtype=bool)
    merged_quads: list[np.ndarray] = []
    selected_scores: list[float] = []
    for candidate in selected_candidates:
        used_triangle_mask[candidate.triangle_index_a] = True
        used_triangle_mask[candidate.triangle_index_b] = True
        merged_quads.append(candidate.quad)
        selected_scores.append(candidate.score)

    leftover_triangles = triangles[~used_triangle_mask]
    merged_quad_array = (
        np.asarray(merged_quads, dtype=np.int64) if merged_quads else _empty_cells(4)
    )
    output_mesh = SurfaceMesh(
        points=mesh.points.copy(),
        triangles=leftover_triangles,
        quads=np.vstack([mesh.quads, merged_quad_array])
        if mesh.quads.size > 0 and merged_quad_array.size > 0
        else mesh.quads.copy()
        if merged_quad_array.size == 0
        else merged_quad_array,
    )

    if selected_scores:
        total_selected_score = float(np.sum(selected_scores))
        mean_selected_score = float(np.mean(selected_scores))
    else:
        total_selected_score = 0.0
        mean_selected_score = 0.0

    stats = QuadDominantConversionStats(
        matching_method=matching_method,
        candidate_pair_count=0,
        merged_pair_count=int(len(merged_quads)),
        leftover_triangle_count=int(leftover_triangles.shape[0]),
        total_selected_score=total_selected_score,
        mean_selected_score=mean_selected_score,
        premerge_accepted_flips=0,
        cleanup_improved_patch_count=0,
        cleanup_added_quad_count=0,
    )
    return output_mesh, stats


def _triangle_patch_components(triangles: np.ndarray) -> list[list[int]]:
    triangles = np.asarray(triangles, dtype=np.int64)
    if triangles.size == 0:
        return []

    edge_to_triangle_indices = _build_triangle_edge_to_indices(triangles)
    adjacency: list[set[int]] = [set() for _ in range(triangles.shape[0])]
    for incident_triangle_indices in edge_to_triangle_indices.values():
        if len(incident_triangle_indices) != 2:
            continue
        triangle_index_a, triangle_index_b = incident_triangle_indices
        adjacency[triangle_index_a].add(triangle_index_b)
        adjacency[triangle_index_b].add(triangle_index_a)

    components: list[list[int]] = []
    unvisited = set(range(triangles.shape[0]))
    while unvisited:
        seed_triangle_index = unvisited.pop()
        component = [seed_triangle_index]
        stack = [seed_triangle_index]
        while stack:
            triangle_index = stack.pop()
            for neighbor_index in adjacency[triangle_index]:
                if neighbor_index not in unvisited:
                    continue
                unvisited.remove(neighbor_index)
                component.append(neighbor_index)
                stack.append(neighbor_index)
        components.append(sorted(component))
    return components


def _cleanup_leftover_triangle_patches(
    mesh: SurfaceMesh,
    *,
    max_normal_deviation_degrees: float,
    min_interior_angle_degrees: float,
    max_interior_angle_degrees: float,
    max_planarity_ratio: float,
    base_max_candidate_score: float | None,
    local_score_relaxation_cap: float = 0.02,
    max_patch_triangles: int = 24,
    patch_flip_max_passes: int = 2,
) -> tuple[SurfaceMesh, int, int]:
    if mesh.triangles.size == 0:
        return mesh, 0, 0

    kept_triangle_blocks: list[np.ndarray] = []
    added_quad_blocks: list[np.ndarray] = []
    improved_patch_count = 0
    added_quad_count = 0
    for component_triangle_indices in _triangle_patch_components(mesh.triangles):
        patch_triangles = mesh.triangles[component_triangle_indices]
        if patch_triangles.shape[0] < 2 or patch_triangles.shape[0] > max_patch_triangles:
            kept_triangle_blocks.append(patch_triangles)
            continue

        local_score_ceiling = _local_candidate_score_ceiling(
            mesh.points,
            patch_triangles,
            base_max_candidate_score=base_max_candidate_score,
            relaxation_cap=local_score_relaxation_cap,
        )
        patch_mesh = SurfaceMesh(
            points=mesh.points.copy(),
            triangles=patch_triangles.copy(),
            quads=_empty_cells(4),
        )
        optimized_patch_mesh, _ = _apply_premerge_edge_flips(
            patch_mesh,
            max_normal_deviation_degrees=max_normal_deviation_degrees,
            min_interior_angle_degrees=min_interior_angle_degrees,
            max_interior_angle_degrees=max_interior_angle_degrees,
            max_planarity_ratio=max_planarity_ratio,
            base_max_candidate_score=local_score_ceiling,
            max_passes=patch_flip_max_passes,
            max_accepted_flips=max_patch_triangles,
            local_score_relaxation_cap=local_score_relaxation_cap,
        )
        patch_candidates = _build_quad_merge_candidates(
            optimized_patch_mesh,
            max_normal_deviation_degrees=max_normal_deviation_degrees,
            min_interior_angle_degrees=min_interior_angle_degrees,
            max_interior_angle_degrees=max_interior_angle_degrees,
            max_planarity_ratio=max_planarity_ratio,
            max_candidate_score=local_score_ceiling,
        )
        selected_patch_candidates = _select_exact_merge_candidates(patch_candidates)
        if not selected_patch_candidates:
            kept_triangle_blocks.append(patch_triangles)
            continue

        improved_patch_result, improved_patch_stats = _mesh_from_selected_candidates(
            optimized_patch_mesh,
            selected_patch_candidates,
            matching_method="leftover_patch_cleanup",
        )
        if improved_patch_stats.leftover_triangle_count >= patch_triangles.shape[0]:
            kept_triangle_blocks.append(patch_triangles)
            continue

        improved_patch_count += 1
        added_quad_count += improved_patch_stats.merged_pair_count
        if improved_patch_result.triangles.size > 0:
            kept_triangle_blocks.append(improved_patch_result.triangles)
        if improved_patch_result.quads.size > 0:
            added_quad_blocks.append(improved_patch_result.quads)

    if kept_triangle_blocks:
        updated_triangles = np.vstack(kept_triangle_blocks)
    else:
        updated_triangles = _empty_cells(3)

    quad_blocks = [mesh.quads]
    quad_blocks.extend(quad_block for quad_block in added_quad_blocks if quad_block.size > 0)
    nonempty_quad_blocks = [quad_block for quad_block in quad_blocks if quad_block.size > 0]
    updated_quads = np.vstack(nonempty_quad_blocks) if nonempty_quad_blocks else _empty_cells(4)

    return (
        SurfaceMesh(
            points=mesh.points.copy(),
            triangles=updated_triangles,
            quads=updated_quads,
        ),
        improved_patch_count,
        added_quad_count,
    )


def convert_to_quad_dominant(
    mesh: SurfaceMesh,
    *,
    pairing_method: str = "matching_refined",
    max_normal_deviation_degrees: float = 55.0,
    min_interior_angle_degrees: float = 20.0,
    max_interior_angle_degrees: float = 160.0,
    max_planarity_ratio: float = 0.2,
    max_candidate_score: float | None = 0.20,
    precomputed_candidates: list[QuadMergeCandidate] | None = None,
    apply_premerge_edge_flips: bool = True,
    apply_leftover_patch_cleanup: bool = True,
    local_score_relaxation_cap: float = 0.02,
) -> tuple[SurfaceMesh, QuadDominantConversionStats]:
    triangles = np.asarray(mesh.triangles, dtype=np.int64)
    if triangles.size == 0:
        stats = QuadDominantConversionStats(
            matching_method=pairing_method,
            candidate_pair_count=0,
            merged_pair_count=0,
            leftover_triangle_count=0,
            total_selected_score=0.0,
            mean_selected_score=0.0,
            premerge_accepted_flips=0,
            cleanup_improved_patch_count=0,
            cleanup_added_quad_count=0,
        )
        return mesh, stats

    working_mesh = SurfaceMesh(
        points=mesh.points.copy(),
        triangles=triangles.copy(),
        quads=mesh.quads.copy(),
    )
    premerge_accepted_flips = 0
    if apply_premerge_edge_flips and working_mesh.triangles.size > 0:
        working_mesh, premerge_accepted_flips = _apply_premerge_edge_flips(
            working_mesh,
            max_normal_deviation_degrees=max_normal_deviation_degrees,
            min_interior_angle_degrees=min_interior_angle_degrees,
            max_interior_angle_degrees=max_interior_angle_degrees,
            max_planarity_ratio=max_planarity_ratio,
            base_max_candidate_score=max_candidate_score,
            local_score_relaxation_cap=local_score_relaxation_cap,
        )

    candidates = precomputed_candidates
    if candidates is None or apply_premerge_edge_flips:
        candidates = _build_quad_merge_candidates(
            working_mesh,
            max_normal_deviation_degrees=max_normal_deviation_degrees,
            min_interior_angle_degrees=min_interior_angle_degrees,
            max_interior_angle_degrees=max_interior_angle_degrees,
            max_planarity_ratio=max_planarity_ratio,
            max_candidate_score=max_candidate_score,
        )

    if pairing_method == "greedy":
        selected_candidates = _select_greedy_merge_candidates(
            candidates,
            num_triangles=triangles.shape[0],
        )
    elif pairing_method in {"matching_refined", "max_weight_matching"}:
        selected_candidates = _select_matching_refined_merge_candidates(candidates)
    else:
        raise ValueError(f"Unsupported pairing_method: {pairing_method}")

    output_mesh, stats = _mesh_from_selected_candidates(
        working_mesh,
        selected_candidates,
        matching_method=pairing_method,
    )
    cleanup_improved_patch_count = 0
    cleanup_added_quad_count = 0
    if apply_leftover_patch_cleanup and output_mesh.triangles.size > 1:
        output_mesh, cleanup_improved_patch_count, cleanup_added_quad_count = _cleanup_leftover_triangle_patches(
            output_mesh,
            max_normal_deviation_degrees=max_normal_deviation_degrees,
            min_interior_angle_degrees=min_interior_angle_degrees,
            max_interior_angle_degrees=max_interior_angle_degrees,
            max_planarity_ratio=max_planarity_ratio,
            base_max_candidate_score=max_candidate_score,
            local_score_relaxation_cap=local_score_relaxation_cap,
        )

    stats = QuadDominantConversionStats(
        matching_method=stats.matching_method,
        candidate_pair_count=len(candidates),
        merged_pair_count=int(output_mesh.quads.shape[0] - working_mesh.quads.shape[0]),
        leftover_triangle_count=int(output_mesh.triangles.shape[0]),
        total_selected_score=stats.total_selected_score,
        mean_selected_score=stats.mean_selected_score,
        premerge_accepted_flips=premerge_accepted_flips,
        cleanup_improved_patch_count=cleanup_improved_patch_count,
        cleanup_added_quad_count=cleanup_added_quad_count,
    )
    return output_mesh, stats


def summarize_quad_quality(
    mesh: SurfaceMesh,
    *,
    quad_scores: np.ndarray | None = None,
) -> QuadQualitySummary:
    if mesh.quads.size == 0:
        return QuadQualitySummary(
            count=0,
            mean_abs_angle_deviation_degrees=np.nan,
            p95_abs_angle_deviation_degrees=np.nan,
            mean_aspect_ratio=np.nan,
            p95_aspect_ratio=np.nan,
            mean_planarity_ratio=np.nan,
            p95_planarity_ratio=np.nan,
            mean_min_scaled_jacobian=np.nan,
            p05_min_scaled_jacobian=np.nan,
            mean_merge_score=np.nan,
        )

    abs_angle_deviations: list[float] = []
    aspect_ratios: list[float] = []
    planarity_ratios: list[float] = []
    min_scaled_jacobians: list[float] = []
    for quad in mesh.quads:
        quad_points = mesh.points[quad]
        angles = _quad_interior_angles(mesh.points, quad)
        abs_angle_deviations.append(float(np.mean(np.abs(angles - 90.0))))

        edge_lengths = np.linalg.norm(
            quad_points[np.arange(4)] - quad_points[np.roll(np.arange(4), -1)],
            axis=1,
        )
        aspect_ratios.append(
            float(np.max(edge_lengths) / max(float(np.min(edge_lengths)), 1e-14))
        )
        planarity_ratios.append(_quad_planarity_ratio(mesh.points, quad))

        corner_scaled_jacobians = []
        for local_index in range(4):
            current_point = quad_points[local_index]
            previous_edge = quad_points[(local_index - 1) % 4] - current_point
            next_edge = quad_points[(local_index + 1) % 4] - current_point
            denominator = np.linalg.norm(previous_edge) * np.linalg.norm(next_edge)
            if denominator <= 1e-14:
                corner_scaled_jacobians.append(0.0)
                continue
            corner_scaled_jacobians.append(
                float(np.linalg.norm(np.cross(previous_edge, next_edge)) / denominator)
            )
        min_scaled_jacobians.append(float(np.min(corner_scaled_jacobians)))

    abs_angle_deviation_array = np.asarray(abs_angle_deviations, dtype=float)
    aspect_ratio_array = np.asarray(aspect_ratios, dtype=float)
    planarity_ratio_array = np.asarray(planarity_ratios, dtype=float)
    min_scaled_jacobian_array = np.asarray(min_scaled_jacobians, dtype=float)

    mean_merge_score = (
        float(np.mean(quad_scores)) if quad_scores is not None and quad_scores.size > 0 else np.nan
    )
    return QuadQualitySummary(
        count=int(mesh.quads.shape[0]),
        mean_abs_angle_deviation_degrees=float(np.mean(abs_angle_deviation_array)),
        p95_abs_angle_deviation_degrees=float(np.percentile(abs_angle_deviation_array, 95.0)),
        mean_aspect_ratio=float(np.mean(aspect_ratio_array)),
        p95_aspect_ratio=float(np.percentile(aspect_ratio_array, 95.0)),
        mean_planarity_ratio=float(np.mean(planarity_ratio_array)),
        p95_planarity_ratio=float(np.percentile(planarity_ratio_array, 95.0)),
        mean_min_scaled_jacobian=float(np.mean(min_scaled_jacobian_array)),
        p05_min_scaled_jacobian=float(np.percentile(min_scaled_jacobian_array, 5.0)),
        mean_merge_score=mean_merge_score,
    )


def summarize_worst_elements(mesh: SurfaceMesh) -> WorstElementSummary:
    min_angles: list[float] = []
    aspect_ratios: list[float] = []
    min_scaled_jacobians: list[float] = []

    for triangle in mesh.triangles:
        min_angles.append(_triangle_min_angle(mesh.points, triangle))
        aspect_ratios.append(_triangle_aspect_ratio(mesh.points, triangle))
        min_scaled_jacobians.append(_triangle_min_scaled_jacobian(mesh.points, triangle))

    for quad in mesh.quads:
        min_angles.append(_quad_min_angle(mesh.points, quad))
        aspect_ratios.append(_quad_aspect_ratio(mesh.points, quad))
        min_scaled_jacobians.append(_quad_min_scaled_jacobian(mesh.points, quad))

    if not min_angles:
        return WorstElementSummary(
            count=0,
            triangle_count=0,
            quad_count=0,
            min_angle_min_degrees=np.nan,
            min_angle_p05_degrees=np.nan,
            aspect_ratio_p95=np.nan,
            aspect_ratio_max=np.nan,
            min_scaled_jacobian_min=np.nan,
            min_scaled_jacobian_p05=np.nan,
            num_min_angle_below_20=0,
            num_aspect_ratio_above_2=0,
            num_scaled_jacobian_below_05=0,
        )

    min_angle_array = np.asarray(min_angles, dtype=float)
    aspect_ratio_array = np.asarray(aspect_ratios, dtype=float)
    min_scaled_jacobian_array = np.asarray(min_scaled_jacobians, dtype=float)
    return WorstElementSummary(
        count=int(min_angle_array.size),
        triangle_count=int(mesh.triangles.shape[0]),
        quad_count=int(mesh.quads.shape[0]),
        min_angle_min_degrees=float(np.min(min_angle_array)),
        min_angle_p05_degrees=float(np.percentile(min_angle_array, 5.0)),
        aspect_ratio_p95=float(np.percentile(aspect_ratio_array, 95.0)),
        aspect_ratio_max=float(np.max(aspect_ratio_array)),
        min_scaled_jacobian_min=float(np.min(min_scaled_jacobian_array)),
        min_scaled_jacobian_p05=float(np.percentile(min_scaled_jacobian_array, 5.0)),
        num_min_angle_below_20=int(np.count_nonzero(min_angle_array < 20.0)),
        num_aspect_ratio_above_2=int(np.count_nonzero(aspect_ratio_array > 2.0)),
        num_scaled_jacobian_below_05=int(np.count_nonzero(min_scaled_jacobian_array < 0.5)),
    )


def mirror_half_mesh_across_xz_plane(mesh: SurfaceMesh, *, tol: float) -> SurfaceMesh:
    mirror_map = np.arange(mesh.num_vertices, dtype=np.int64)
    mirrored_points: list[np.ndarray] = [mesh.points.copy()]
    new_vertex_count = mesh.num_vertices
    for vertex_index, point in enumerate(mesh.points):
        if abs(point[1]) <= tol:
            continue
        mirrored_point = point.copy()
        mirrored_point[1] *= -1.0
        mirrored_points.append(mirrored_point[None, :])
        mirror_map[vertex_index] = new_vertex_count
        new_vertex_count += 1

    full_points = np.vstack(mirrored_points)

    mirrored_triangles = _empty_cells(3)
    if mesh.triangles.size > 0:
        mirrored_triangles = mirror_map[mesh.triangles][:, [0, 2, 1]]

    mirrored_quads = _empty_cells(4)
    if mesh.quads.size > 0:
        mirrored_quads = mirror_map[mesh.quads][:, [0, 3, 2, 1]]

    full_triangles = (
        np.vstack([mesh.triangles, mirrored_triangles])
        if mesh.triangles.size > 0
        else mirrored_triangles
    )
    full_quads = (
        np.vstack([mesh.quads, mirrored_quads])
        if mesh.quads.size > 0
        else mirrored_quads
    )
    return SurfaceMesh(points=full_points, triangles=full_triangles, quads=full_quads)


def _faces_from_cells(cells: np.ndarray, *, cell_size: int) -> np.ndarray:
    if cells.size == 0:
        return np.empty((0,), dtype=np.int64)
    faces = np.empty((cells.shape[0], cell_size + 1), dtype=np.int64)
    faces[:, 0] = cell_size
    faces[:, 1:] = cells
    return faces.ravel()


def _mixed_faces(mesh: SurfaceMesh) -> np.ndarray:
    face_blocks: list[np.ndarray] = []
    triangle_faces = _faces_from_cells(mesh.triangles, cell_size=3)
    quad_faces = _faces_from_cells(mesh.quads, cell_size=4)
    if triangle_faces.size > 0:
        face_blocks.append(triangle_faces)
    if quad_faces.size > 0:
        face_blocks.append(quad_faces)
    if not face_blocks:
        return np.empty((0,), dtype=np.int64)
    return np.concatenate(face_blocks)


def _polydata_from_mesh(mesh: SurfaceMesh):
    pv_mod = _require_pyvista()
    faces = _mixed_faces(mesh)
    if faces.size == 0:
        return pv_mod.PolyData(mesh.points)
    return pv_mod.PolyData(mesh.points, faces)


def _plot_pipeline(
    original_mesh: SurfaceMesh,
    quad_half_mesh: SurfaceMesh,
    full_quad_dominant_mesh: SurfaceMesh,
    *,
    selected_side: str,
) -> None:
    pv_mod = _require_pyvista()
    plotter = pv_mod.Plotter(shape=(1, 3), border=False)

    panels = [
        ("Original Full Triangle Mesh", original_mesh),
        (f"Selected {selected_side.capitalize()} Half After Quad Merge", quad_half_mesh),
        ("Mirrored Symmetric Full Quad-Dominant Mesh", full_quad_dominant_mesh),
    ]
    for subplot_index, (title, mesh) in enumerate(panels):
        plotter.subplot(0, subplot_index)
        plotter.add_text(title, font_size=10)
        if mesh.num_quads > 0:
            quad_polydata = _polydata_from_mesh(
                SurfaceMesh(points=mesh.points, triangles=_empty_cells(3), quads=mesh.quads)
            )
            plotter.add_mesh(
                quad_polydata,
                color="lightsteelblue",
                show_edges=True,
                line_width=1.0,
            )
        if mesh.num_triangles > 0:
            triangle_polydata = _polydata_from_mesh(
                SurfaceMesh(points=mesh.points, triangles=mesh.triangles, quads=_empty_cells(4))
            )
            plotter.add_mesh(
                triangle_polydata,
                color="lightsalmon",
                show_edges=True,
                line_width=1.0,
            )
        if mesh.num_triangles == 0 and mesh.num_quads == 0:
            plotter.add_mesh(_polydata_from_mesh(mesh), color="lightgray", point_size=4)
        plotter.show_axes()
        plotter.view_isometric()

    plotter.link_views()
    plotter.show()


def _print_mesh_summary(label: str, mesh: SurfaceMesh) -> None:
    print(
        f"{label}: vertices={mesh.num_vertices}, triangles={mesh.num_triangles}, quads={mesh.num_quads}"
    )


def _format_metric(value: float) -> str:
    if not np.isfinite(value):
        return "n/a"
    return f"{value:.6f}"


def _format_improvement(
    baseline_value: float,
    improved_value: float,
    *,
    lower_is_better: bool,
) -> str:
    if not np.isfinite(baseline_value) or not np.isfinite(improved_value):
        return "n/a"

    delta = improved_value - baseline_value
    if abs(delta) <= 1e-14:
        return "unchanged"

    if abs(baseline_value) > 1e-14:
        relative_change_percent = 100.0 * delta / baseline_value
        relative_change_text = f"{relative_change_percent:+.2f}%"
    else:
        relative_change_text = "absolute change only"

    improved = delta < 0.0 if lower_is_better else delta > 0.0
    verdict = "improved" if improved else "worsened"
    return f"{verdict} ({delta:+.6f}, {relative_change_text})"


def _format_count_improvement(baseline_value: int, improved_value: int, *, lower_is_better: bool) -> str:
    delta = improved_value - baseline_value
    if delta == 0:
        return "unchanged"

    if baseline_value != 0:
        relative_change_percent = 100.0 * delta / baseline_value
        relative_change_text = f"{relative_change_percent:+.2f}%"
    else:
        relative_change_text = "absolute change only"

    improved = delta < 0 if lower_is_better else delta > 0
    verdict = "improved" if improved else "worsened"
    return f"{verdict} ({delta:+d}, {relative_change_text})"


def _print_quad_quality_summary(label: str, summary: QuadQualitySummary) -> None:
    print(f"{label}:")
    print(f"    quads={summary.count}")
    print(
        "    mean |angle-90| [deg]=",
        _format_metric(summary.mean_abs_angle_deviation_degrees),
        "p95=",
        _format_metric(summary.p95_abs_angle_deviation_degrees),
    )
    print(
        "    mean aspect ratio=",
        _format_metric(summary.mean_aspect_ratio),
        "p95=",
        _format_metric(summary.p95_aspect_ratio),
    )
    print(
        "    mean planarity ratio=",
        _format_metric(summary.mean_planarity_ratio),
        "p95=",
        _format_metric(summary.p95_planarity_ratio),
    )
    print(
        "    mean min scaled Jacobian=",
        _format_metric(summary.mean_min_scaled_jacobian),
        "p05=",
        _format_metric(summary.p05_min_scaled_jacobian),
    )
    print("    mean merge score=", _format_metric(summary.mean_merge_score))


def _print_worst_element_summary(label: str, summary: WorstElementSummary) -> None:
    print(f"{label}:")
    print(
        f"    elements={summary.count}",
        f"(triangles={summary.triangle_count}, quads={summary.quad_count})",
    )
    print(
        "    min angle [deg]:",
        "min=",
        _format_metric(summary.min_angle_min_degrees),
        "p05=",
        _format_metric(summary.min_angle_p05_degrees),
    )
    print(
        "    aspect ratio:",
        "p95=",
        _format_metric(summary.aspect_ratio_p95),
        "max=",
        _format_metric(summary.aspect_ratio_max),
    )
    print(
        "    min scaled Jacobian:",
        "min=",
        _format_metric(summary.min_scaled_jacobian_min),
        "p05=",
        _format_metric(summary.min_scaled_jacobian_p05),
    )
    print(
        "    threshold counts:",
        f"min_angle<20={summary.num_min_angle_below_20},",
        f"aspect_ratio>2={summary.num_aspect_ratio_above_2},",
        f"min_scaled_jacobian<0.5={summary.num_scaled_jacobian_below_05}",
    )


def _print_projected_smoothing_summary(
    label: str,
    stats: ProjectedSmoothingStats,
) -> None:
    print(f"{label}:")
    print(
        f"    iterations={stats.accepted_iterations} accepted / {stats.attempted_iterations} attempted"
    )
    print(
        f"    protected_vertices={stats.protected_vertex_count},",
        f"active_vertices={stats.active_vertex_count},",
        f"moved_vertices={stats.moved_vertex_count}",
    )
    print(
        f"    projection_converged={stats.projection_converged_count} / {stats.projection_attempt_count}",
    )
    print(
        "    projection distance:",
        "mean=",
        _format_metric(stats.mean_projection_distance),
        "max=",
        _format_metric(stats.max_projection_distance),
    )


def _print_quality_improvement_report(
    baseline_label: str,
    baseline_summary: QuadQualitySummary,
    improved_label: str,
    improved_summary: QuadQualitySummary,
) -> None:
    print(f"Quality improvement report ({baseline_label} -> {improved_label}):")
    print(
        "    mean |angle-90| [deg]:",
        _format_metric(baseline_summary.mean_abs_angle_deviation_degrees),
        "->",
        _format_metric(improved_summary.mean_abs_angle_deviation_degrees),
        _format_improvement(
            baseline_summary.mean_abs_angle_deviation_degrees,
            improved_summary.mean_abs_angle_deviation_degrees,
            lower_is_better=True,
        ),
    )
    print(
        "    p95 |angle-90| [deg]:",
        _format_metric(baseline_summary.p95_abs_angle_deviation_degrees),
        "->",
        _format_metric(improved_summary.p95_abs_angle_deviation_degrees),
        _format_improvement(
            baseline_summary.p95_abs_angle_deviation_degrees,
            improved_summary.p95_abs_angle_deviation_degrees,
            lower_is_better=True,
        ),
    )
    print(
        "    mean aspect ratio:",
        _format_metric(baseline_summary.mean_aspect_ratio),
        "->",
        _format_metric(improved_summary.mean_aspect_ratio),
        _format_improvement(
            baseline_summary.mean_aspect_ratio,
            improved_summary.mean_aspect_ratio,
            lower_is_better=True,
        ),
    )
    print(
        "    p95 aspect ratio:",
        _format_metric(baseline_summary.p95_aspect_ratio),
        "->",
        _format_metric(improved_summary.p95_aspect_ratio),
        _format_improvement(
            baseline_summary.p95_aspect_ratio,
            improved_summary.p95_aspect_ratio,
            lower_is_better=True,
        ),
    )
    print(
        "    mean planarity ratio:",
        _format_metric(baseline_summary.mean_planarity_ratio),
        "->",
        _format_metric(improved_summary.mean_planarity_ratio),
        _format_improvement(
            baseline_summary.mean_planarity_ratio,
            improved_summary.mean_planarity_ratio,
            lower_is_better=True,
        ),
    )
    print(
        "    p05 min scaled Jacobian:",
        _format_metric(baseline_summary.p05_min_scaled_jacobian),
        "->",
        _format_metric(improved_summary.p05_min_scaled_jacobian),
        _format_improvement(
            baseline_summary.p05_min_scaled_jacobian,
            improved_summary.p05_min_scaled_jacobian,
            lower_is_better=False,
        ),
    )
    print(
        "    mean merge score:",
        _format_metric(baseline_summary.mean_merge_score),
        "->",
        _format_metric(improved_summary.mean_merge_score),
        _format_improvement(
            baseline_summary.mean_merge_score,
            improved_summary.mean_merge_score,
            lower_is_better=True,
        ),
    )


def _print_worst_element_improvement_report(
    baseline_label: str,
    baseline_summary: WorstElementSummary,
    improved_label: str,
    improved_summary: WorstElementSummary,
) -> None:
    print(f"Worst-element improvement report ({baseline_label} -> {improved_label}):")
    print(
        "    min angle [deg]:",
        _format_metric(baseline_summary.min_angle_min_degrees),
        "->",
        _format_metric(improved_summary.min_angle_min_degrees),
        _format_improvement(
            baseline_summary.min_angle_min_degrees,
            improved_summary.min_angle_min_degrees,
            lower_is_better=False,
        ),
    )
    print(
        "    p05 min angle [deg]:",
        _format_metric(baseline_summary.min_angle_p05_degrees),
        "->",
        _format_metric(improved_summary.min_angle_p05_degrees),
        _format_improvement(
            baseline_summary.min_angle_p05_degrees,
            improved_summary.min_angle_p05_degrees,
            lower_is_better=False,
        ),
    )
    print(
        "    p95 aspect ratio:",
        _format_metric(baseline_summary.aspect_ratio_p95),
        "->",
        _format_metric(improved_summary.aspect_ratio_p95),
        _format_improvement(
            baseline_summary.aspect_ratio_p95,
            improved_summary.aspect_ratio_p95,
            lower_is_better=True,
        ),
    )
    print(
        "    max aspect ratio:",
        _format_metric(baseline_summary.aspect_ratio_max),
        "->",
        _format_metric(improved_summary.aspect_ratio_max),
        _format_improvement(
            baseline_summary.aspect_ratio_max,
            improved_summary.aspect_ratio_max,
            lower_is_better=True,
        ),
    )
    print(
        "    min scaled Jacobian:",
        _format_metric(baseline_summary.min_scaled_jacobian_min),
        "->",
        _format_metric(improved_summary.min_scaled_jacobian_min),
        _format_improvement(
            baseline_summary.min_scaled_jacobian_min,
            improved_summary.min_scaled_jacobian_min,
            lower_is_better=False,
        ),
    )
    print(
        "    p05 min scaled Jacobian:",
        _format_metric(baseline_summary.min_scaled_jacobian_p05),
        "->",
        _format_metric(improved_summary.min_scaled_jacobian_p05),
        _format_improvement(
            baseline_summary.min_scaled_jacobian_p05,
            improved_summary.min_scaled_jacobian_p05,
            lower_is_better=False,
        ),
    )
    print(
        "    count(min angle < 20 deg):",
        baseline_summary.num_min_angle_below_20,
        "->",
        improved_summary.num_min_angle_below_20,
        _format_count_improvement(
            baseline_summary.num_min_angle_below_20,
            improved_summary.num_min_angle_below_20,
            lower_is_better=True,
        ),
    )
    print(
        "    count(aspect ratio > 2):",
        baseline_summary.num_aspect_ratio_above_2,
        "->",
        improved_summary.num_aspect_ratio_above_2,
        _format_count_improvement(
            baseline_summary.num_aspect_ratio_above_2,
            improved_summary.num_aspect_ratio_above_2,
            lower_is_better=True,
        ),
    )
    print(
        "    count(min scaled Jacobian < 0.5):",
        baseline_summary.num_scaled_jacobian_below_05,
        "->",
        improved_summary.num_scaled_jacobian_below_05,
        _format_count_improvement(
            baseline_summary.num_scaled_jacobian_below_05,
            improved_summary.num_scaled_jacobian_below_05,
            lower_is_better=True,
        ),
    )


if __name__ == "__main__":
    args = _parse_args()
    geometry_case = _resolve_geometry_case(args.geometry_case)
    script_directory = Path(__file__).resolve().parent
    symmetry_tolerance = 1e-8
    plot = os.environ.get("BSM3_PLOT_QUAD_MESH", "1") == "1"
    apply_projected_smoothing = os.environ.get("BSM3_PROJECTED_SMOOTHING", "1") == "1"
    max_candidate_score = 0.5
    mesh_path = (
        args.mesh_path
        if args.mesh_path is not None
        else script_directory / geometry_case.mesh_filename
    )
    step_path = (
        args.step_path
        if args.step_path is not None
        else script_directory / geometry_case.step_filename
    )
    output_path = (
        args.output_path
        if args.output_path is not None
        else script_directory / geometry_case.output_filename
    )
    plot_existing_output = os.environ.get("BSM3_PLOT_EXISTING_OUTPUT", "0") == "1"

    # load output mesh if it already exists to avoid re-running the pipeline during development
    if output_path.is_file() and plot_existing_output:
        print(f"Output mesh already exists at {output_path}, loading it instead of re-running the pipeline.")
        output_mesh = read_gmsh22_surface_mesh(output_path)
        _print_mesh_summary("Loaded output mesh", output_mesh)
        if plot:
            _plot_pipeline(
                original_mesh=output_mesh,
                quad_half_mesh=output_mesh,
                full_quad_dominant_mesh=output_mesh,
                selected_side="n/a",
            )
        exit(0)

    source_mesh = read_gmsh22_surface_mesh(mesh_path)
    classification = classify_symmetry(
        source_mesh.points,
        source_mesh.triangles,
        tol=symmetry_tolerance,
    )

    print(f"Geometry case: {geometry_case.name}")
    print(f"Input mesh: {mesh_path.name}")
    print(
        "Detected source type:",
        "full mesh" if classification.is_full_mesh else "half mesh",
    )
    print(
        "Vertex distribution relative to y=0:",
        f"positive={classification.positive_vertex_count},",
        f"negative={classification.negative_vertex_count},",
        f"on_plane={classification.symmetry_plane_vertex_count}",
    )
    print(
        "Triangle distribution relative to y=0:",
        f"positive={classification.positive_triangle_count},",
        f"negative={classification.negative_triangle_count},",
        f"crossing={classification.crossing_triangle_count}",
    )
    print(f"Selected half for processing: {classification.selected_side}")
    _print_mesh_summary("Original mesh", source_mesh)

    selected_half_mesh = extract_half_mesh(
        source_mesh,
        classification.selected_side,
        tol=symmetry_tolerance,
    )
    _print_mesh_summary("Selected half mesh", selected_half_mesh)

    greedy_quad_merge_candidates = _build_quad_merge_candidates(
        selected_half_mesh,
        max_normal_deviation_degrees=55.0,
        min_interior_angle_degrees=20.0,
        max_interior_angle_degrees=160.0,
        max_planarity_ratio=0.2,
        max_candidate_score=None,
    )
    greedy_half_mesh, greedy_stats = convert_to_quad_dominant(
        selected_half_mesh,
        pairing_method="greedy",
        max_candidate_score=None,
        precomputed_candidates=greedy_quad_merge_candidates,
        apply_premerge_edge_flips=False,
        apply_leftover_patch_cleanup=False,
    )
    quad_half_mesh_pre_smoothing, quad_stats = convert_to_quad_dominant(
        selected_half_mesh,
        pairing_method="matching_refined",
        max_candidate_score=max_candidate_score,
    )
    smoothing_stats = ProjectedSmoothingStats(
        attempted_iterations=0,
        accepted_iterations=0,
        protected_vertex_count=0,
        active_vertex_count=0,
        moved_vertex_count=0,
        projection_attempt_count=0,
        projection_converged_count=0,
        mean_projection_distance=np.nan,
        max_projection_distance=np.nan,
    )
    quad_half_mesh = quad_half_mesh_pre_smoothing
    component_intersection_vertex_mask = np.zeros(
        (quad_half_mesh_pre_smoothing.num_vertices,),
        dtype=bool,
    )
    parametric_boundary_vertex_mask = np.zeros(
        (quad_half_mesh_pre_smoothing.num_vertices,),
        dtype=bool,
    )
    if apply_projected_smoothing:
        projection_bundle = _load_geometry_projection_bundle(
            step_path,
            component_patch_ranges=geometry_case.component_patch_ranges,
        )
        component_pair_intersection_vertex_masks = _component_pair_intersection_vertex_masks(
            quad_half_mesh_pre_smoothing.points,
            projection_bundle,
            geometry_case.protected_intersection_pairs,
        )
        for pair, pair_mask in component_pair_intersection_vertex_masks.items():
            component_intersection_vertex_mask |= pair_mask
        parametric_boundary_vertex_mask = _parametric_boundary_vertex_mask(
            quad_half_mesh_pre_smoothing.points,
            projection_bundle,
            eps=1e-10,
        )
        additional_protected_vertex_mask = (
            component_intersection_vertex_mask | parametric_boundary_vertex_mask
        )
        for pair, pair_mask in component_pair_intersection_vertex_masks.items():
            print(
                f"{pair[0]}-{pair[1]} intersection vertices fixed during smoothing:",
                int(np.count_nonzero(pair_mask)),
            )
        print(
            "Component intersection vertices fixed during smoothing:",
            int(np.count_nonzero(component_intersection_vertex_mask)),
        )
        print(
            "Parametric boundary vertices fixed during smoothing:",
            int(np.count_nonzero(parametric_boundary_vertex_mask)),
        )
        print(
            "Total additional protected vertices during smoothing:",
            int(np.count_nonzero(additional_protected_vertex_mask)),
        )
        quad_half_mesh, smoothing_stats = smooth_surface_mesh_with_hard_projection(
            quad_half_mesh_pre_smoothing,
            projection_bundle.combined_projection_model,
            projection_bundle.combined_coefficients,
            symmetry_tolerance=symmetry_tolerance,
            additional_protected_vertex_mask=additional_protected_vertex_mask,
        )

    initial_worst_elements = summarize_worst_elements(selected_half_mesh)
    pre_smoothing_worst_elements = summarize_worst_elements(quad_half_mesh_pre_smoothing)
    final_worst_elements = summarize_worst_elements(quad_half_mesh)
    greedy_quality = summarize_quad_quality(
        greedy_half_mesh,
    )
    matching_quality_pre_smoothing = summarize_quad_quality(
        quad_half_mesh_pre_smoothing,
    )
    matching_quality = summarize_quad_quality(
        quad_half_mesh,
    )
    print(
        "Greedy baseline stats:",
        f"candidates={greedy_stats.candidate_pair_count},",
        f"merged_pairs={greedy_stats.merged_pair_count},",
        f"leftover_triangles={greedy_stats.leftover_triangle_count},",
        f"initial_mean_score={greedy_stats.mean_selected_score:.6f}",
    )
    _print_quad_quality_summary("Greedy baseline quad quality", greedy_quality)
    print(
        "Quality-preserving matching-refined stats:",
        f"candidates={quad_stats.candidate_pair_count},",
        f"merged_pairs={quad_stats.merged_pair_count},",
        f"leftover_triangles={quad_stats.leftover_triangle_count}",
        f"initial_mean_score={quad_stats.mean_selected_score:.6f}",
        f"score_ceiling={max_candidate_score:.2f}",
        f"premerge_flips={quad_stats.premerge_accepted_flips}",
        f"cleanup_patches={quad_stats.cleanup_improved_patch_count}",
        f"cleanup_added_quads={quad_stats.cleanup_added_quad_count}",
    )
    _print_quad_quality_summary(
        "Quality-preserving matching-refined quad quality",
        matching_quality_pre_smoothing,
    )
    _print_quality_improvement_report(
        "greedy",
        greedy_quality,
        "quality-preserving matching-refined",
        matching_quality_pre_smoothing,
    )
    if apply_projected_smoothing:
        _print_projected_smoothing_summary(
            "Projected smoothing stats",
            smoothing_stats,
        )
        _print_quad_quality_summary(
            "Projected-smoothed quad quality",
            matching_quality,
        )
        _print_quality_improvement_report(
            "matching-refined pre-smoothing",
            matching_quality_pre_smoothing,
            "projected-smoothed",
            matching_quality,
        )
    _print_worst_element_summary(
        "Initial selected-half triangulation worst elements",
        initial_worst_elements,
    )
    _print_worst_element_summary(
        "Post-quadification selected-half mixed-mesh worst elements",
        pre_smoothing_worst_elements,
    )
    if apply_projected_smoothing:
        _print_worst_element_summary(
            "Final selected-half projected-smoothed mixed-mesh worst elements",
            final_worst_elements,
        )
        _print_worst_element_improvement_report(
            "post-quadification mixed mesh",
            pre_smoothing_worst_elements,
            "projected-smoothed mixed mesh",
            final_worst_elements,
        )
    else:
        _print_worst_element_summary(
            "Final selected-half mixed-mesh worst elements",
            final_worst_elements,
        )
    _print_worst_element_improvement_report(
        "initial triangulation",
        initial_worst_elements,
        "final mixed mesh",
        final_worst_elements,
    )
    _print_mesh_summary("Quad-dominant half mesh", quad_half_mesh)

    symmetric_full_mesh = mirror_half_mesh_across_xz_plane(
        quad_half_mesh,
        tol=symmetry_tolerance,
    )
    _print_mesh_summary("Mirrored full mesh", symmetric_full_mesh)

    write_gmsh22_surface_mesh(output_path, symmetric_full_mesh)
    print(f"Wrote processed mesh to: {output_path.name}")

    if not plot:
        print(
            "Interactive visualization is disabled. "
            "Set BSM3_PLOT_QUAD_MESH=1 to open the PyVista view."
        )
    elif pv is None:
        print("PyVista is not installed in this environment; skipping visualization.")
    else:
        _plot_pipeline(
            source_mesh,
            quad_half_mesh,
            symmetric_full_mesh,
            selected_side=classification.selected_side,
        )
