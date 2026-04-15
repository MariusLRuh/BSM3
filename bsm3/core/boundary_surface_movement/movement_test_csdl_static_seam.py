from __future__ import annotations

import argparse
from pathlib import Path

import meshio
import numpy as np

try:
    import pyvista as pv
except ImportError:  # pragma: no cover
    pv = None

import csdl_alpha as csdl
import lsdo_function_spaces as lfs

import bsm3


def _make_faces(mesh: meshio.Mesh) -> np.ndarray:
    face_blocks: list[np.ndarray] = []

    triangle_cells = mesh.cells_dict.get("triangle")
    if triangle_cells is not None and triangle_cells.size > 0:
        triangle_faces = np.empty((triangle_cells.shape[0], 4), dtype=np.int64)
        triangle_faces[:, 0] = 3
        triangle_faces[:, 1:] = triangle_cells
        face_blocks.append(triangle_faces)

    quad_cells = mesh.cells_dict.get("quad")
    if quad_cells is not None and quad_cells.size > 0:
        quad_faces = np.empty((quad_cells.shape[0], 5), dtype=np.int64)
        quad_faces[:, 0] = 4
        quad_faces[:, 1:] = quad_cells
        face_blocks.append(quad_faces)

    if not face_blocks:
        raise ValueError("Expected at least one triangle or quad cell block in the mesh.")

    return np.concatenate([block.ravel() for block in face_blocks])


def _triangulate_surface_cells(mesh: meshio.Mesh) -> np.ndarray:
    triangles = mesh.cells_dict.get("triangle")
    quads = mesh.cells_dict.get("quad")

    tri_blocks: list[np.ndarray] = []
    if triangles is not None and triangles.size > 0:
        tri_blocks.append(np.asarray(triangles, dtype=np.int64))
    if quads is not None and quads.size > 0:
        quads = np.asarray(quads, dtype=np.int64)
        tri_blocks.append(quads[:, [0, 1, 2]])
        tri_blocks.append(quads[:, [0, 2, 3]])

    if not tri_blocks:
        raise ValueError("Expected at least one triangle or quad cell block in the mesh.")

    return np.vstack(tri_blocks)


def _build_vertex_neighbors(num_vertices: int, triangles: np.ndarray) -> list[np.ndarray]:
    neighbor_sets = [set() for _ in range(num_vertices)]
    for triangle in np.asarray(triangles, dtype=np.int64):
        i, j, k = int(triangle[0]), int(triangle[1]), int(triangle[2])
        neighbor_sets[i].update((j, k))
        neighbor_sets[j].update((i, k))
        neighbor_sets[k].update((i, j))
    return [np.asarray(sorted(neighbors), dtype=np.int64) for neighbors in neighbor_sets]


def _build_uniform_laplacian_matrix(num_vertices: int, adjacency: list[np.ndarray]) -> np.ndarray:
    laplacian = np.zeros((num_vertices, num_vertices), dtype=float)
    for vertex_index, neighbors in enumerate(adjacency):
        if neighbors.size == 0:
            continue
        laplacian[vertex_index, vertex_index] = -1.0
        laplacian[vertex_index, neighbors] = 1.0 / neighbors.size
    return laplacian


def _triangle_unit_normals(
    points: np.ndarray,
    triangles: np.ndarray,
    *,
    eps: float = 1e-14,
) -> np.ndarray:
    tri_points = np.asarray(points, dtype=float)[np.asarray(triangles, dtype=np.int64)]
    normals = np.cross(
        tri_points[:, 1, :] - tri_points[:, 0, :],
        tri_points[:, 2, :] - tri_points[:, 0, :],
    )
    norm = np.linalg.norm(normals, axis=1)
    valid = norm > eps
    normals[valid] /= norm[valid, None]
    normals[~valid] = 0.0
    return normals


def _sharp_feature_vertex_mask(
    points: np.ndarray,
    triangles: np.ndarray,
    *,
    feature_angle_degrees: float,
    include_boundary: bool = False,
) -> np.ndarray:
    triangles = np.asarray(triangles, dtype=np.int64)
    feature_mask = np.zeros(np.asarray(points, dtype=float).shape[0], dtype=bool)
    face_normals = _triangle_unit_normals(points, triangles)
    cos_threshold = np.cos(np.radians(float(feature_angle_degrees)))

    edge_to_faces: dict[tuple[int, int], list[int]] = {}
    for face_index, triangle in enumerate(triangles):
        i, j, k = (int(triangle[0]), int(triangle[1]), int(triangle[2]))
        for edge in ((i, j), (j, k), (k, i)):
            key = tuple(sorted(edge))
            edge_to_faces.setdefault(key, []).append(face_index)

    for (vertex_i, vertex_j), face_indices in edge_to_faces.items():
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


def _compute_graph_distances(
    points: np.ndarray,
    neighbors: list[np.ndarray],
    source_indices: np.ndarray,
) -> np.ndarray:
    from heapq import heappop, heappush

    points = np.asarray(points, dtype=float)
    source_indices = np.asarray(source_indices, dtype=np.int64)

    distances = np.full(points.shape[0], np.inf, dtype=float)
    heap: list[tuple[float, int]] = []
    for source_index in np.unique(source_indices):
        source_index = int(source_index)
        distances[source_index] = 0.0
        heappush(heap, (0.0, source_index))

    while heap:
        current_distance, vertex_index = heappop(heap)
        if current_distance > distances[vertex_index]:
            continue

        vertex_point = points[vertex_index]
        for neighbor_index in neighbors[vertex_index]:
            neighbor_index = int(neighbor_index)
            edge_length = np.linalg.norm(points[neighbor_index] - vertex_point)
            candidate_distance = current_distance + edge_length
            if candidate_distance < distances[neighbor_index]:
                distances[neighbor_index] = candidate_distance
                heappush(heap, (candidate_distance, neighbor_index))

    return distances


def _select_farthest_point_indices(points: np.ndarray, num_samples: int) -> np.ndarray:
    points = np.asarray(points, dtype=float)
    num_points = points.shape[0]
    if num_samples <= 0:
        return np.empty((0,), dtype=np.int64)
    if num_samples >= num_points:
        return np.arange(num_points, dtype=np.int64)

    centroid = np.mean(points, axis=0)
    first_index = int(np.argmax(np.linalg.norm(points - centroid, axis=1)))

    selected_indices = np.empty(num_samples, dtype=np.int64)
    selected_indices[0] = first_index
    min_distance_squared = np.sum((points - points[first_index]) ** 2, axis=1)
    min_distance_squared[first_index] = -1.0

    for selection_index in range(1, num_samples):
        next_index = int(np.argmax(min_distance_squared))
        selected_indices[selection_index] = next_index
        candidate_distance_squared = np.sum((points - points[next_index]) ** 2, axis=1)
        min_distance_squared = np.minimum(min_distance_squared, candidate_distance_squared)
        min_distance_squared[selected_indices[: selection_index + 1]] = -1.0

    return np.sort(selected_indices)


def _make_coordinate_key(point: np.ndarray, tolerance: float) -> tuple[int, ...]:
    point = np.asarray(point, dtype=float)
    tolerance = max(float(tolerance), 1e-14)
    return tuple(np.rint(point / tolerance).astype(np.int64))


def _select_farthest_point_indices_symmetric(
    points: np.ndarray,
    num_samples: int,
    *,
    symmetry_axis: int = 1,
    symmetry_plane_tolerance: float = 1e-10,
    mirror_tolerance: float = 1e-10,
) -> np.ndarray:
    points = np.asarray(points, dtype=float)
    num_points = points.shape[0]
    if num_samples <= 0:
        return np.empty((0,), dtype=np.int64)
    if num_samples >= num_points:
        return np.arange(num_points, dtype=np.int64)

    key_to_indices: dict[tuple[int, ...], list[int]] = {}
    for local_index, point in enumerate(points):
        key_to_indices.setdefault(_make_coordinate_key(point, mirror_tolerance), []).append(local_index)

    visited = np.zeros(num_points, dtype=bool)
    groups: list[np.ndarray] = []
    representative_points: list[np.ndarray] = []
    for local_index, point in enumerate(points):
        if visited[local_index]:
            continue
        if abs(point[symmetry_axis]) <= symmetry_plane_tolerance:
            visited[local_index] = True
            groups.append(np.array([local_index], dtype=np.int64))
            representative_points.append(point.copy())
            continue

        mirrored_point = point.copy()
        mirrored_point[symmetry_axis] *= -1.0
        partner = None
        for candidate_index in key_to_indices.get(
            _make_coordinate_key(mirrored_point, mirror_tolerance),
            [],
        ):
            if candidate_index == local_index or visited[candidate_index]:
                continue
            if np.linalg.norm(points[candidate_index] - mirrored_point) <= mirror_tolerance:
                partner = candidate_index
                break

        if partner is None:
            visited[local_index] = True
            groups.append(np.array([local_index], dtype=np.int64))
            representative_points.append(point.copy())
            continue

        visited[local_index] = True
        visited[partner] = True
        group = np.array(sorted((local_index, partner)), dtype=np.int64)
        groups.append(group)
        positive_index = local_index if points[local_index, symmetry_axis] >= 0.0 else partner
        representative_point = points[positive_index].copy()
        representative_point[symmetry_axis] = abs(representative_point[symmetry_axis])
        representative_points.append(representative_point)

    group_sizes = np.asarray([group.size for group in groups], dtype=np.int64)
    representative_points = np.asarray(representative_points, dtype=float)

    feasible_group_mask = group_sizes <= num_samples
    if not np.any(feasible_group_mask):
        return _select_farthest_point_indices(points, num_samples)

    selected_group_mask = np.zeros(len(groups), dtype=bool)
    selected_group_indices: list[int] = []
    remaining_slots = int(num_samples)

    centroid = np.mean(representative_points, axis=0)
    centroid_distance_squared = np.sum((representative_points - centroid) ** 2, axis=1)
    centroid_distance_squared[~feasible_group_mask] = -np.inf
    first_group_index = int(np.argmax(centroid_distance_squared))
    selected_group_mask[first_group_index] = True
    selected_group_indices.append(first_group_index)
    remaining_slots -= int(group_sizes[first_group_index])

    min_distance_squared = np.sum(
        (representative_points - representative_points[first_group_index]) ** 2,
        axis=1,
    )
    min_distance_squared[selected_group_mask] = -1.0

    while True:
        feasible_group_mask = (~selected_group_mask) & (group_sizes <= remaining_slots)
        if not np.any(feasible_group_mask):
            break
        candidate_scores = np.where(feasible_group_mask, min_distance_squared, -np.inf)
        next_group_index = int(np.argmax(candidate_scores))
        if not np.isfinite(candidate_scores[next_group_index]):
            break
        selected_group_mask[next_group_index] = True
        selected_group_indices.append(next_group_index)
        remaining_slots -= int(group_sizes[next_group_index])
        candidate_distance_squared = np.sum(
            (representative_points - representative_points[next_group_index]) ** 2,
            axis=1,
        )
        min_distance_squared = np.minimum(min_distance_squared, candidate_distance_squared)
        min_distance_squared[selected_group_mask] = -1.0

    selected_local_indices = np.concatenate([groups[group_index] for group_index in selected_group_indices])
    return np.sort(selected_local_indices.astype(np.int64, copy=False))


def _normalize_weights(weights: np.ndarray, *, eps: float = 1e-15) -> np.ndarray:
    weights = np.asarray(weights, dtype=float)
    normalization = np.sum(weights, axis=1, keepdims=True)
    return weights / np.maximum(normalization, eps)


def _gaussian_support(indicator: np.ndarray, sigma: float, *, eps: float = 1e-12) -> np.ndarray:
    indicator = np.asarray(indicator, dtype=float)
    sigma_safe = max(float(sigma), eps)
    return np.exp(-(indicator**2) / (sigma_safe**2))


def _interaction_indicator_two_components(component_sdf: np.ndarray) -> np.ndarray:
    component_sdf = np.asarray(component_sdf, dtype=float)
    if component_sdf.ndim != 2 or component_sdf.shape[1] != 2:
        raise ValueError("Expected a two-component SDF array with shape (num_points, 2).")
    return np.sqrt(np.sum(component_sdf**2, axis=1))


def _evaluate_rbf_kernel(
    distances: np.ndarray,
    *,
    kernel: str,
    kernel_scale: float,
) -> np.ndarray:
    distances = np.asarray(distances, dtype=float)
    scale_safe = max(float(kernel_scale), 1e-12)
    scaled_distances = distances / scale_safe

    if kernel == "cubic":
        return distances**3
    if kernel == "gaussian":
        return np.exp(-(scaled_distances**2))
    if kernel == "multiquadric":
        return np.sqrt(1.0 + scaled_distances**2)
    raise ValueError(f"Unsupported RBF kernel: {kernel}")


def _pairwise_distance_matrix(points_a: np.ndarray, points_b: np.ndarray) -> np.ndarray:
    points_a = np.asarray(points_a, dtype=float)
    points_b = np.asarray(points_b, dtype=float)
    difference = points_a[:, None, :] - points_b[None, :, :]
    return np.linalg.norm(difference, axis=2)


def _build_rbf_polynomial_terms(points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=float)
    return np.column_stack([np.ones(points.shape[0], dtype=float), points])


def _precompute_rbf_evaluation_operator(
    training_points: np.ndarray,
    query_points: np.ndarray,
    *,
    fit_mode: str,
    kernel: str,
    kernel_scale: float,
    regularization: float,
    polynomial_regularization: float,
    sample_weights: np.ndarray,
) -> np.ndarray:
    training_points = np.asarray(training_points, dtype=float)
    query_points = np.asarray(query_points, dtype=float)
    sample_weights = np.asarray(sample_weights, dtype=float).reshape((-1,))

    num_points = training_points.shape[0]
    kernel_matrix = _evaluate_rbf_kernel(
        _pairwise_distance_matrix(training_points, training_points),
        kernel=kernel,
        kernel_scale=kernel_scale,
    )
    polynomial_terms = _build_rbf_polynomial_terms(training_points)
    query_kernel_matrix = _evaluate_rbf_kernel(
        _pairwise_distance_matrix(query_points, training_points),
        kernel=kernel,
        kernel_scale=kernel_scale,
    )
    query_polynomial_terms = _build_rbf_polynomial_terms(query_points)
    evaluation_matrix = np.hstack([query_kernel_matrix, query_polynomial_terms])

    if fit_mode == "exact_interpolation":
        system_matrix = np.zeros((num_points + 4, num_points + 4), dtype=float)
        system_matrix[:num_points, :num_points] = kernel_matrix + regularization * np.eye(num_points)
        system_matrix[:num_points, num_points:] = polynomial_terms
        system_matrix[num_points:, :num_points] = polynomial_terms.T

        rhs_map = np.zeros((num_points + 4, num_points), dtype=float)
        rhs_map[:num_points, :] = np.eye(num_points)
        try:
            fit_operator = np.linalg.solve(system_matrix, rhs_map)
        except np.linalg.LinAlgError:
            fit_operator, *_ = np.linalg.lstsq(system_matrix, rhs_map, rcond=None)
        return evaluation_matrix @ fit_operator

    if fit_mode == "weighted_least_squares":
        design_matrix = np.hstack([kernel_matrix, polynomial_terms])
        diagonal_weights = np.diag(np.maximum(sample_weights, 0.0))
        normal_matrix = design_matrix.T @ diagonal_weights @ design_matrix
        if regularization > 0.0:
            regularization_block = np.zeros_like(normal_matrix)
            regularization_block[:num_points, :num_points] = regularization * np.eye(num_points)
            normal_matrix = normal_matrix + regularization_block
        if polynomial_regularization > 0.0:
            polynomial_block = np.zeros_like(normal_matrix)
            polynomial_block[num_points:, num_points:] = polynomial_regularization * np.eye(4)
            normal_matrix = normal_matrix + polynomial_block

        rhs_operator = design_matrix.T @ diagonal_weights
        try:
            fit_operator = np.linalg.solve(normal_matrix, rhs_operator)
        except np.linalg.LinAlgError:
            fit_operator, *_ = np.linalg.lstsq(normal_matrix, rhs_operator, rcond=None)
        return evaluation_matrix @ fit_operator

    raise ValueError(f"Unsupported RBF fit mode: {fit_mode}")


def _stack_coefficients_csdl(function_set: lfs.FunctionSet) -> csdl.Variable:
    reshaped_total_coeffs = []
    for function in function_set.functions.values():
        reshaped_total_coeffs.append(csdl.reshape(function.coefficients, (-1, 3)))
    return csdl.vstack(reshaped_total_coeffs)


def _stack_coefficients_numpy(function_set: lfs.FunctionSet) -> np.ndarray:
    reshaped_total_coeffs = []
    for function in function_set.functions.values():
        reshaped_total_coeffs.append(np.asarray(function.coefficients.value, dtype=float).reshape((-1, 3)))
    return np.vstack(reshaped_total_coeffs)


def _rotate_points_about_y_axis_numpy(
    points: np.ndarray,
    angle_degrees: float,
    pivot_point: np.ndarray,
) -> np.ndarray:
    points = np.asarray(points, dtype=float)
    pivot_point = np.asarray(pivot_point, dtype=float).reshape((1, 3))
    angle_radians = np.deg2rad(float(angle_degrees))
    cosine = np.cos(angle_radians)
    sine = np.sin(angle_radians)
    rotation_matrix = np.array(
        [
            [cosine, 0.0, sine],
            [0.0, 1.0, 0.0],
            [-sine, 0.0, cosine],
        ],
        dtype=float,
    )
    centered_points = points - pivot_point
    rotated_centered_points = centered_points @ rotation_matrix.T
    return rotated_centered_points + pivot_point


def _expand_vector_to_columns(vector: csdl.Variable | np.ndarray, num_columns: int) -> csdl.Variable:
    vector = csdl.reshape(vector, (-1, 1))
    return csdl.matmat(vector, np.ones((1, num_columns), dtype=float))


def _rotate_points_about_y_axis_csdl(
    points: csdl.Variable,
    angle_degrees: float,
    pivot_point: csdl.Variable | np.ndarray,
) -> csdl.Variable:
    pivot_point = csdl.reshape(pivot_point, (1, 3))
    pivot_rows = csdl.matmat(np.ones((points.shape[0], 1), dtype=float), pivot_point)
    centered_points = points - pivot_rows

    x_coordinates = centered_points[csdl.slice[:, 0:1]]
    y_coordinates = centered_points[csdl.slice[:, 1:2]]
    z_coordinates = centered_points[csdl.slice[:, 2:3]]

    if isinstance(angle_degrees, csdl.Variable):
        angle_radians = angle_degrees * (np.pi / 180.0)
        cosine = csdl.cos(angle_radians)
        sine = csdl.sin(angle_radians)
    else:
        angle_radians = np.deg2rad(float(angle_degrees))
        cosine = np.cos(angle_radians)
        sine = np.sin(angle_radians)

    rotated_x = cosine * x_coordinates + sine * z_coordinates
    rotated_z = -sine * x_coordinates + cosine * z_coordinates
    rotated_points = csdl.concatenate((rotated_x, y_coordinates, rotated_z), axis=1)
    return rotated_points + pivot_rows


def _format_stats(values: np.ndarray) -> str:
    values = np.asarray(values, dtype=float)
    return (
        f"min={np.min(values):.6e}, "
        f"mean={np.mean(values):.6e}, "
        f"max={np.max(values):.6e}"
    )


def _make_ks_rho_schedule(
    rho_start: float,
    rho_end: float,
    num_iterations: int,
) -> np.ndarray:
    num_iterations = int(num_iterations)
    rho_start = float(rho_start)
    rho_end = float(rho_end)
    if num_iterations <= 0:
        raise ValueError("num_iterations must be positive.")
    if rho_start <= 0.0 or rho_end <= 0.0:
        raise ValueError("KS rho schedule values must be positive.")
    if num_iterations == 1:
        return np.array([rho_end], dtype=float)
    return np.geomspace(rho_start, rho_end, num_iterations)


def _smooth_minimum_signed_distance_numpy(
    component_sdf_values: np.ndarray,
    *,
    ks_rho: float,
) -> tuple[np.ndarray, np.ndarray]:
    component_sdf_values = np.asarray(component_sdf_values, dtype=float)
    ks_rho = float(ks_rho)
    if ks_rho <= 0.0:
        raise ValueError("ks_rho must be positive.")

    reference = np.min(component_sdf_values, axis=1, keepdims=True)
    shifted = component_sdf_values - reference
    exp_terms = np.exp(-ks_rho * shifted)
    normalized_weights = _normalize_weights(exp_terms)
    smooth_union_sdf = reference[:, 0] - np.log(np.sum(exp_terms, axis=1)) / ks_rho
    return smooth_union_sdf, normalized_weights


def _smooth_minimum_signed_distance_csdl(
    component_sdf_a: csdl.Variable,
    component_sdf_b: csdl.Variable,
    *,
    ks_rho: float,
    reference_rho: float = 60.0,
) -> tuple[csdl.Variable, csdl.Variable, csdl.Variable]:
    component_sdf_a = csdl.reshape(component_sdf_a, (-1, 1))
    component_sdf_b = csdl.reshape(component_sdf_b, (-1, 1))
    # reference = csdl.minimum(component_sdf_a, component_sdf_b, rho=max(reference_rho, ks_rho))
    reference = csdl.minimum(component_sdf_a, component_sdf_b, rho=ks_rho)
    shifted_a = component_sdf_a - reference
    shifted_b = component_sdf_b - reference
    exp_a = csdl.exp(-ks_rho * shifted_a)
    exp_b = csdl.exp(-ks_rho * shifted_b)
    normalization = exp_a + exp_b
    union_sdf = reference - csdl.log(normalization) / ks_rho
    return csdl.reshape(union_sdf, (-1,)), exp_a / normalization, exp_b / normalization


def _signed_distance_gradient_from_projection_csdl(
    signed_distance: csdl.Variable,
    query_points: csdl.Variable,
    projected_points: csdl.Variable,
    *,
    eps: float = 1e-12,
) -> csdl.Variable:
    residual = query_points - projected_points
    raw_distance = csdl.sqrt(csdl.sum(residual**2, axes=(1,)) + eps)
    smooth_sign = signed_distance / csdl.sqrt(signed_distance**2 + eps)
    gradient_scale = smooth_sign / raw_distance
    return _expand_vector_to_columns(gradient_scale, 3) * residual


def _plot_surface_debug(
    surface_vertices: np.ndarray,
    *,
    mesh_faces: np.ndarray,
    interpolation_indices: np.ndarray,
    seam_seed_indices: np.ndarray,
    protected_feature_indices: np.ndarray,
    mesh_label: str,
) -> None:
    if pv is None:
        raise ImportError("PyVista is required for plotting.")

    surface_vertices = np.asarray(surface_vertices, dtype=float)
    plotter = pv.Plotter()
    plotter.add_mesh(
        pv.PolyData(surface_vertices, mesh_faces),
        opacity=1.0,
        show_edges=True,
        label=mesh_label,
    )
    plotter.add_mesh(
        pv.PolyData(surface_vertices[interpolation_indices]),
        color="orange",
        point_size=7,
        render_points_as_spheres=True,
        label="Interpolation vertices",
    )
    plotter.add_mesh(
        pv.PolyData(surface_vertices[seam_seed_indices]),
        color="red",
        point_size=9,
        render_points_as_spheres=True,
        label="Exact seam seeds",
    )
    if protected_feature_indices.size > 0:
        plotter.add_mesh(
            pv.PolyData(surface_vertices[protected_feature_indices]),
            color="royalblue",
            point_size=8,
            render_points_as_spheres=True,
            label="Protected wing features",
        )
    plotter.add_legend()
    plotter.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mesh",
        default="wing_fuse_test_quad_dominant_symmetric.msh",
        choices=("wing_fuse_test_quad_dominant_symmetric.msh", "wing_fuse_test.msh"),
        help="Surface mesh used for setup and runtime validation.",
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Display the final updated mesh with PyVista if available.",
    )
    parser.add_argument(
        "--plot-step8-prediction",
        action="store_true",
        help="Display the pre-projection mesh predicted by the RBF field.",
    )
    args = parser.parse_args()

    plot = True # args.plot
    plot_step8_prediction = True # args.plot_step8_prediction
    mesh_filename = args.mesh

    alpha = 1.0
    sigma_phi = 0.1
    rbf_fit_mode = "exact_interpolation" # "weighted_least_squares"
    rbf_kernel = "cubic" # "multiquadric"
    rbf_kernel_scale_factor = 0.01
    rbf_regularization_factor = 1e-6
    rbf_polynomial_regularization_factor = 1e-15
    global_interpolation_sample_weight = 1.0
    local_support_sample_weight_factor = 1.0
    local_seam_sample_weight = 10.0
    num_additional_interp_vertices = 2000
    max_local_training_points = 0

    intersection_tolerance = 1e-4
    wing_surface_projection_tolerance = 1e-4
    seam_support_sigma_factor = 0.15
    setup_seam_support_cutoff = 0.05
    local_support_floor = 0.05
    seam_graph_radius_factor = 0.08
    translation_envelope_mac = 2.0
    rotation_envelope_degrees = 8.0

    translation_amount = -1.5
    wing_root_rotation_degrees = 0.0
    local_master_band_mode = "exact_seeds_only"
    step9_projection_mode = "smooth_union_ks"
    step9_smooth_union_ks_rho_start = 8.0
    step9_smooth_union_ks_rho_end = 8.0
    step9_smooth_union_num_iterations = 5

    wing_feature_protection = True
    sharp_feature_angle_degrees = 110.0
    sharp_feature_include_boundary = False
    step9_pre_projection_laplacian_step = 0.15

    recorder = csdl.Recorder(inline=True)
    recorder.start()

    wing_fuse = lfs.import_file_patched(
        Path(__file__).with_name("wing_fuse_test.stp"),
        parallelize=False,
    )

    wing_keys = np.arange(0, 12)
    fuse_keys = np.arange(12, len(wing_fuse.functions))
    wing_function_set = lfs.FunctionSet(functions={key: wing_fuse.functions[key] for key in wing_keys})
    fuse_function_set = lfs.FunctionSet(functions={key: wing_fuse.functions[key] for key in fuse_keys})

    wing_coefficients_csdl = _stack_coefficients_csdl(wing_function_set)
    fuse_coefficients_csdl = _stack_coefficients_csdl(fuse_function_set)
    initial_wing_coefficients = _stack_coefficients_numpy(wing_function_set)
    initial_fuse_coefficients = _stack_coefficients_numpy(fuse_function_set)

    mesh = meshio.read(Path(__file__).with_name(mesh_filename))
    vertices = np.asarray(mesh.points, dtype=float)
    triangulated_surface_cells = _triangulate_surface_cells(mesh)
    mesh_faces = _make_faces(mesh)

    num_vertices = vertices.shape[0]
    variable_indices = np.arange(num_vertices, dtype=np.int64)
    vertex_neighbors = _build_vertex_neighbors(num_vertices, triangulated_surface_cells)
    laplacian_matrix = _build_uniform_laplacian_matrix(num_vertices, vertex_neighbors)
    bounding_box_diagonal = np.linalg.norm(np.max(vertices, axis=0) - np.min(vertices, axis=0))
    seam_support_sigma = seam_support_sigma_factor * max(bounding_box_diagonal, 1e-12)
    seam_graph_radius = seam_graph_radius_factor * max(bounding_box_diagonal, 1e-12)

    wing_projection_model = bsm3.FunctionSetProjectionModel(
        wing_function_set,
        warm_start_nu=40,
        warm_start_nv=40,
        edge_map_num_samples=25,
    )
    fuse_projection_model = bsm3.FunctionSetProjectionModel(
        fuse_function_set,
        warm_start_nu=40,
        warm_start_nv=40,
        edge_map_num_samples=25,
    )
    combined_projection_model = bsm3.FunctionSetProjectionModel(
        wing_fuse,
        warm_start_nu=40,
        warm_start_nv=40,
        edge_map_num_samples=25,
    )
    wing_sdf_model = bsm3.FunctionSetProjectionModel(
        wing_function_set,
        warm_start_nu=40,
        warm_start_nv=40,
        edge_map_num_samples=25,
        output_mode="distance",
        sdf=True,
    )
    fuse_sdf_model = bsm3.FunctionSetProjectionModel(
        fuse_function_set,
        warm_start_nu=40,
        warm_start_nv=40,
        edge_map_num_samples=25,
        output_mode="distance",
        sdf=True,
    )
    wing_evaluation_model = bsm3.FunctionSetEvaluationModel(wing_function_set)

    wing_projection_distances, wing_projection_state = wing_projection_model.project(
        initial_wing_coefficients,
        vertices,
    )
    fuse_projection_distances, _ = fuse_projection_model.project(
        initial_fuse_coefficients,
        vertices,
    )

    seam_seed_indices = np.where(
        (np.abs(wing_projection_distances) <= intersection_tolerance)
        & (np.abs(fuse_projection_distances) <= intersection_tolerance)
    )[0]
    if seam_seed_indices.size == 0:
        raise ValueError("No exact seam seed vertices were identified from the initial wing/fuselage intersection.")

    interpolation_indices = seam_seed_indices.copy()
    remaining_variable_indices = np.setdiff1d(variable_indices, interpolation_indices)
    additional_interp_local = _select_farthest_point_indices_symmetric(
        vertices[remaining_variable_indices],
        min(num_additional_interp_vertices, remaining_variable_indices.size),
    )
    if additional_interp_local.size > 0:
        interpolation_indices = np.concatenate(
            [interpolation_indices, remaining_variable_indices[additional_interp_local]]
        )
    interpolation_indices = np.unique(interpolation_indices)
    interpolation_vertices = vertices[interpolation_indices]
    seam_interpolation_mask = np.isin(interpolation_indices, seam_seed_indices)
    seam_interpolation_local_indices = np.where(seam_interpolation_mask)[0]

    seam_graph_distances = _compute_graph_distances(vertices, vertex_neighbors, seam_seed_indices)

    interpolation_wing_distances, interpolation_wing_state = wing_projection_model.project(
        initial_wing_coefficients,
        interpolation_vertices,
    )
    interpolation_fuse_distances, _ = fuse_projection_model.project(
        initial_fuse_coefficients,
        interpolation_vertices,
    )
    interpolation_wing_parametric_coordinates = np.column_stack(
        [
            interpolation_wing_state["patch_id"],
            interpolation_wing_state["uv"],
        ]
    )
    interpolation_initial_wing_points = wing_evaluation_model.evaluate(
        initial_wing_coefficients,
        interpolation_wing_parametric_coordinates,
    )
    interpolation_wing_weights = _normalize_weights(
        np.exp(
            -alpha
            * np.column_stack([interpolation_wing_distances, interpolation_fuse_distances])
        )
    )[:, 0]

    seam_seed_wing_parametric_coordinates = np.column_stack(
        [
            wing_projection_state["patch_id"][seam_seed_indices],
            wing_projection_state["uv"][seam_seed_indices],
        ]
    )
    seam_seed_wing_points = wing_evaluation_model.evaluate(
        initial_wing_coefficients,
        seam_seed_wing_parametric_coordinates,
    )
    seam_seed_leading_local = int(np.argmin(seam_seed_wing_points[:, 0]))
    seam_seed_trailing_local = int(np.argmax(seam_seed_wing_points[:, 0]))
    root_leading_parametric_coordinate = seam_seed_wing_parametric_coordinates[
        seam_seed_leading_local : seam_seed_leading_local + 1
    ]
    root_trailing_parametric_coordinate = seam_seed_wing_parametric_coordinates[
        seam_seed_trailing_local : seam_seed_trailing_local + 1
    ]
    root_leading_point = seam_seed_wing_points[seam_seed_leading_local : seam_seed_leading_local + 1]
    root_trailing_point = seam_seed_wing_points[
        seam_seed_trailing_local : seam_seed_trailing_local + 1
    ]
    root_chord_proxy = max(
        float(root_trailing_point[0, 0] - root_leading_point[0, 0]),
        1e-12,
    )
    root_quarter_chord = root_leading_point + 0.25 * (root_trailing_point - root_leading_point)

    def move_wing_coefficients_numpy(translation_x: float, rotation_degrees: float) -> np.ndarray:
        translated_coefficients = initial_wing_coefficients + np.array(
            [translation_x, 0.0, 0.0],
            dtype=float,
        )[None, :]
        translated_root_quarter_chord = root_quarter_chord + np.array(
            [translation_x, 0.0, 0.0],
            dtype=float,
        ).reshape((1, 3))
        return _rotate_points_about_y_axis_numpy(
            translated_coefficients,
            rotation_degrees,
            translated_root_quarter_chord,
        )

    envelope_translation_values = np.array(
        [
            -translation_envelope_mac * root_chord_proxy,
            0.0,
            translation_envelope_mac * root_chord_proxy,
        ],
        dtype=float,
    )
    envelope_rotation_values = np.array(
        # [0.0],
        [-rotation_envelope_degrees, rotation_envelope_degrees],
        dtype=float,
    )

    seam_support_envelope = np.zeros(num_vertices, dtype=float)
    swept_states = [(0.0, 0.0)]
    swept_states.extend(
        [
            (float(translation_x), float(rotation_degrees))
            for translation_x in (envelope_translation_values[0], envelope_translation_values[2])
            for rotation_degrees in envelope_rotation_values
        ]
    )
    for translation_x, rotation_degrees in swept_states:
        moved_wing_coefficients_setup = move_wing_coefficients_numpy(
            translation_x,
            rotation_degrees,
        )
        wing_sdf_values, _ = wing_sdf_model.project(moved_wing_coefficients_setup, vertices)
        fuse_sdf_values, _ = fuse_sdf_model.project(initial_fuse_coefficients, vertices)
        setup_indicator = _interaction_indicator_two_components(
            np.column_stack([wing_sdf_values, fuse_sdf_values])
        )
        seam_support_envelope = np.maximum(
            seam_support_envelope,
            _gaussian_support(setup_indicator, seam_support_sigma),
        )

    seam_graph_band_mask = seam_graph_distances <= seam_graph_radius
    seam_envelope_mask = seam_support_envelope >= setup_seam_support_cutoff
    seam_candidate_mask = seam_graph_band_mask & seam_envelope_mask
    seam_candidate_mask[seam_seed_indices] = True
    seam_candidate_indices = np.where(seam_candidate_mask)[0]

    local_training_candidate_interp_mask = seam_candidate_mask[interpolation_indices]
    local_training_candidate_interp_mask[seam_interpolation_mask] = True
    local_training_candidate_interp_local = np.where(local_training_candidate_interp_mask)[0]
    if local_training_candidate_interp_local.size > max_local_training_points:
        seed_mask = seam_interpolation_mask[local_training_candidate_interp_local]
        fixed_seed_interp_local = local_training_candidate_interp_local[seed_mask]
        non_seed_interp_local = local_training_candidate_interp_local[~seed_mask]
        num_remaining_slots = max(0, max_local_training_points - fixed_seed_interp_local.size)
        if num_remaining_slots > 0 and non_seed_interp_local.size > 0:
            selected_non_seed_local = _select_farthest_point_indices_symmetric(
                interpolation_vertices[non_seed_interp_local],
                min(num_remaining_slots, non_seed_interp_local.size),
            )
            non_seed_interp_local = non_seed_interp_local[selected_non_seed_local]
        else:
            non_seed_interp_local = np.empty((0,), dtype=np.int64)
        local_training_interp_local = np.unique(
            np.concatenate([fixed_seed_interp_local, non_seed_interp_local])
        )
    else:
        local_training_interp_local = local_training_candidate_interp_local
    local_training_indices = interpolation_indices[local_training_interp_local]
    local_training_vertices = interpolation_vertices[local_training_interp_local]
    local_training_interp_local_list = local_training_interp_local.tolist()
    local_training_setup_support = np.maximum(
        local_support_floor,
        seam_support_envelope[local_training_indices],
    )
    local_training_setup_support[seam_interpolation_mask[local_training_interp_local]] = 1.0
    local_training_sample_weights = (
        local_support_sample_weight_factor * local_training_setup_support
    )
    local_training_sample_weights[
        seam_interpolation_mask[local_training_interp_local]
    ] *= local_seam_sample_weight

    sharp_feature_vertex_mask = _sharp_feature_vertex_mask(
        vertices,
        triangulated_surface_cells,
        feature_angle_degrees=sharp_feature_angle_degrees,
        include_boundary=sharp_feature_include_boundary,
    )
    protected_feature_indices = np.empty((0,), dtype=np.int64)
    protected_feature_parametric_coordinates = np.empty((0, 3), dtype=float)
    if wing_feature_protection:
        protected_feature_mask = (
            sharp_feature_vertex_mask
            & (wing_projection_distances <= wing_surface_projection_tolerance)
            & ~seam_candidate_mask
        )
        protected_feature_indices = np.where(protected_feature_mask)[0]
        if protected_feature_indices.size > 0:
            protected_feature_parametric_coordinates = np.column_stack(
                [
                    wing_projection_state["patch_id"][protected_feature_indices],
                    wing_projection_state["uv"][protected_feature_indices],
                ]
            )

    unprotected_laplacian_scale = np.ones(num_vertices, dtype=float)
    unprotected_laplacian_scale[protected_feature_indices] = 0.0

    length_scale = np.linalg.norm(
        np.max(interpolation_vertices, axis=0) - np.min(interpolation_vertices, axis=0)
    )
    rbf_kernel_scale = rbf_kernel_scale_factor * max(length_scale, 1e-12)
    if rbf_kernel == "cubic":
        kernel_regularization_scale = max(length_scale**3, 1.0)
    else:
        kernel_regularization_scale = 1.0
    rbf_regularization = rbf_regularization_factor * kernel_regularization_scale
    rbf_polynomial_regularization = rbf_polynomial_regularization_factor

    global_variable_evaluation_operator = _precompute_rbf_evaluation_operator(
        interpolation_vertices,
        vertices,
        fit_mode=rbf_fit_mode,
        kernel=rbf_kernel,
        kernel_scale=rbf_kernel_scale,
        regularization=rbf_regularization,
        polynomial_regularization=rbf_polynomial_regularization,
        sample_weights=np.full(
            interpolation_vertices.shape[0],
            global_interpolation_sample_weight,
            dtype=float,
        ),
    )
    global_interpolation_evaluation_operator = _precompute_rbf_evaluation_operator(
        interpolation_vertices,
        interpolation_vertices,
        fit_mode=rbf_fit_mode,
        kernel=rbf_kernel,
        kernel_scale=rbf_kernel_scale,
        regularization=rbf_regularization,
        polynomial_regularization=rbf_polynomial_regularization,
        sample_weights=np.full(
            interpolation_vertices.shape[0],
            global_interpolation_sample_weight,
            dtype=float,
        ),
    )
    global_local_training_evaluation_operator = _precompute_rbf_evaluation_operator(
        interpolation_vertices,
        local_training_vertices,
        fit_mode=rbf_fit_mode,
        kernel=rbf_kernel,
        kernel_scale=rbf_kernel_scale,
        regularization=rbf_regularization,
        polynomial_regularization=rbf_polynomial_regularization,
        sample_weights=np.full(
            interpolation_vertices.shape[0],
            global_interpolation_sample_weight,
            dtype=float,
        ),
    )
    local_variable_evaluation_operator = _precompute_rbf_evaluation_operator(
        local_training_vertices,
        vertices,
        fit_mode=rbf_fit_mode,
        kernel=rbf_kernel,
        kernel_scale=rbf_kernel_scale,
        regularization=rbf_regularization,
        polynomial_regularization=rbf_polynomial_regularization,
        sample_weights=local_training_sample_weights,
    )
    local_interpolation_evaluation_operator = _precompute_rbf_evaluation_operator(
        local_training_vertices,
        interpolation_vertices,
        fit_mode=rbf_fit_mode,
        kernel=rbf_kernel,
        kernel_scale=rbf_kernel_scale,
        regularization=rbf_regularization,
        polynomial_regularization=rbf_polynomial_regularization,
        sample_weights=local_training_sample_weights,
    )
    local_training_self_evaluation_operator = _precompute_rbf_evaluation_operator(
        local_training_vertices,
        local_training_vertices,
        fit_mode=rbf_fit_mode,
        kernel=rbf_kernel,
        kernel_scale=rbf_kernel_scale,
        regularization=rbf_regularization,
        polynomial_regularization=rbf_polynomial_regularization,
        sample_weights=local_training_sample_weights,
    )

    vertices_csdl = csdl.Variable(name="surface_vertices", value=vertices)
    interpolation_vertices_csdl = csdl.Variable(
        name="interpolation_vertices",
        value=interpolation_vertices,
    )
    root_quarter_chord_csdl = csdl.Variable(name="root_quarter_chord", value=root_quarter_chord)

    wing_evaluation_interpolation_operation = bsm3.FunctionSetEvaluationOperation(
        model=wing_evaluation_model
    )
    wing_evaluation_feature_operation = bsm3.FunctionSetEvaluationOperation(
        model=wing_evaluation_model
    )
    interpolation_wing_closest_distance_operation = bsm3.FunctionSetClosestDistanceOperation(
        model=wing_sdf_model
    )
    interpolation_fuse_closest_distance_operation = bsm3.FunctionSetClosestDistanceOperation(
        model=fuse_sdf_model
    )
    variable_wing_closest_distance_operation = bsm3.FunctionSetClosestDistanceOperation(
        model=wing_sdf_model
    )
    variable_fuse_closest_distance_operation = bsm3.FunctionSetClosestDistanceOperation(
        model=fuse_sdf_model
    )

    translation_vector = np.array([translation_amount, 0.0, 0.0], dtype=float).reshape((1, 3))
    wing_translation_rows = csdl.matmat(
        np.ones((wing_coefficients_csdl.shape[0], 1), dtype=float),
        translation_vector,
    )
    translated_root_quarter_chord = root_quarter_chord_csdl + translation_vector
    moved_wing_coefficients = _rotate_points_about_y_axis_csdl(
        wing_coefficients_csdl + wing_translation_rows,
        wing_root_rotation_degrees,
        translated_root_quarter_chord,
    )
    moved_total_coefficients = csdl.concatenate(
        (moved_wing_coefficients, fuse_coefficients_csdl),
        axis=0,
    )

    moved_interpolation_wing_points = wing_evaluation_interpolation_operation.evaluate(
        moved_wing_coefficients,
        interpolation_wing_parametric_coordinates,
    )
    interpolation_wing_displacements = (
        moved_interpolation_wing_points - interpolation_initial_wing_points
    )
    provisional_interpolation_target_displacements = _expand_vector_to_columns(
        interpolation_wing_weights,
        3,
    ) * interpolation_wing_displacements

    predicted_global_interpolation_displacements = csdl.matmat(
        global_interpolation_evaluation_operator,
        provisional_interpolation_target_displacements,
    )
    predicted_global_variable_displacements = csdl.matmat(
        global_variable_evaluation_operator,
        provisional_interpolation_target_displacements,
    )
    predicted_global_local_training_displacements = csdl.matmat(
        global_local_training_evaluation_operator,
        provisional_interpolation_target_displacements,
    )
    predicted_global_interpolation_vertices = (
        interpolation_vertices_csdl + predicted_global_interpolation_displacements
    )
    predicted_global_variable_vertices = vertices_csdl + predicted_global_variable_displacements

    interpolation_sdf_to_wing = interpolation_wing_closest_distance_operation.evaluate(
        moved_wing_coefficients,
        predicted_global_interpolation_vertices,
    )
    interpolation_sdf_to_fuse = interpolation_fuse_closest_distance_operation.evaluate(
        fuse_coefficients_csdl,
        predicted_global_interpolation_vertices,
    )
    sigma_phi_safe = max(float(sigma_phi), 1e-12)
    interpolation_participation_wing = csdl.exp(
        -(interpolation_sdf_to_wing**2) / (sigma_phi_safe**2)
    )
    interpolation_participation_fuse = csdl.exp(
        -(interpolation_sdf_to_fuse**2) / (sigma_phi_safe**2)
    )
    interpolation_smooth_wing_weight = interpolation_participation_wing / (
        interpolation_participation_wing + interpolation_participation_fuse
    )
    interpolation_interaction_indicator = (
        interpolation_sdf_to_wing**2 + interpolation_sdf_to_fuse**2
    ) ** 0.5
    seam_support_interp = csdl.exp(
        -(
            interpolation_interaction_indicator / max(seam_support_sigma, 1e-12)
        )
        ** 2
    )
    if seam_interpolation_local_indices.size > 0:
        seam_support_interp = seam_support_interp.set(
            csdl.slice[seam_interpolation_local_indices.tolist()],
            1.0,
        )

    interpolation_target_scale = (
        (1.0 - seam_support_interp) * interpolation_smooth_wing_weight
        + seam_support_interp
    )
    interpolation_target_displacements = _expand_vector_to_columns(
        interpolation_target_scale,
        3,
    ) * interpolation_wing_displacements

    local_training_target_displacements = interpolation_target_displacements[
        csdl.slice[local_training_interp_local_list, :]
    ]
    local_training_runtime_support = seam_support_interp[
        csdl.slice[local_training_interp_local_list]
    ]
    local_training_runtime_support = csdl.maximum(
        local_training_runtime_support,
        np.full(local_training_indices.shape[0], local_support_floor, dtype=float),
        rho=60.0,
    )
    local_training_targets_raw = (
        local_training_target_displacements - predicted_global_local_training_displacements
    ) / _expand_vector_to_columns(local_training_runtime_support, 3)

    raw_predicted_local_variable_displacements = csdl.matmat(
        local_variable_evaluation_operator,
        local_training_targets_raw,
    )
    raw_predicted_local_interpolation_displacements = csdl.matmat(
        local_interpolation_evaluation_operator,
        local_training_targets_raw,
    )
    raw_predicted_local_training_displacements = csdl.matmat(
        local_training_self_evaluation_operator,
        local_training_targets_raw,
    )
    local_training_fit_error = (
        raw_predicted_local_training_displacements - local_training_targets_raw
    )

    variable_sdf_to_wing = variable_wing_closest_distance_operation.evaluate(
        moved_wing_coefficients,
        predicted_global_variable_vertices,
    )
    variable_sdf_to_fuse = variable_fuse_closest_distance_operation.evaluate(
        fuse_coefficients_csdl,
        predicted_global_variable_vertices,
    )
    variable_interaction_indicator = (
        variable_sdf_to_wing**2 + variable_sdf_to_fuse**2
    ) ** 0.5
    variable_local_support = csdl.exp(
        -(
            variable_interaction_indicator / max(seam_support_sigma, 1e-12)
        )
        ** 2
    )
    if seam_seed_indices.size > 0:
        variable_local_support = variable_local_support.set(
            csdl.slice[seam_seed_indices.tolist()],
            1.0,
        )

    predicted_local_variable_displacements = _expand_vector_to_columns(
        variable_local_support,
        3,
    ) * raw_predicted_local_variable_displacements
    predicted_local_interpolation_displacements = _expand_vector_to_columns(
        seam_support_interp,
        3,
    ) * raw_predicted_local_interpolation_displacements
    predicted_total_interpolation_displacements = (
        predicted_global_interpolation_displacements + predicted_local_interpolation_displacements
    )
    interpolation_target_error = (
        predicted_total_interpolation_displacements - interpolation_target_displacements
    )
    predicted_variable_displacements = (
        predicted_global_variable_displacements + predicted_local_variable_displacements
    )
    predicted_variable_vertices = vertices_csdl + predicted_variable_displacements

    moved_protected_feature_vertices = None
    if protected_feature_indices.size > 0:
        moved_protected_feature_vertices = wing_evaluation_feature_operation.evaluate(
            moved_wing_coefficients,
            protected_feature_parametric_coordinates,
        )
        predicted_variable_vertices = predicted_variable_vertices.set(
            csdl.slice[protected_feature_indices.tolist(), :],
            moved_protected_feature_vertices,
        )

    if plot_step8_prediction:
        predicted_plot_vertices = np.asarray(predicted_variable_vertices.value, dtype=float)
        _plot_surface_debug(
            predicted_plot_vertices,
            mesh_faces=mesh_faces,
            interpolation_indices=interpolation_indices,
            seam_seed_indices=seam_seed_indices,
            protected_feature_indices=protected_feature_indices,
            mesh_label="RBF-predicted mesh",
        )

    if step9_pre_projection_laplacian_step > 0.0:
        laplacian_displacement = csdl.matmat(laplacian_matrix, predicted_variable_vertices)
        step9_smoothed_variable_vertices = (
            predicted_variable_vertices
            + step9_pre_projection_laplacian_step
            * _expand_vector_to_columns(unprotected_laplacian_scale, 3)
            * laplacian_displacement
        )
        if moved_protected_feature_vertices is not None:
            step9_smoothed_variable_vertices = step9_smoothed_variable_vertices.set(
                csdl.slice[protected_feature_indices.tolist(), :],
                moved_protected_feature_vertices,
            )
    else:
        step9_smoothed_variable_vertices = predicted_variable_vertices

    if step9_projection_mode != "smooth_union_ks":
        raise ValueError(f"Unsupported step9_projection_mode: {step9_projection_mode}")

    step9_smooth_union_rho_schedule = _make_ks_rho_schedule(
        step9_smooth_union_ks_rho_start,
        step9_smooth_union_ks_rho_end,
        step9_smooth_union_num_iterations,
    )
    projected_variable_vertices = step9_smoothed_variable_vertices
    first_union_sdf_csdl = None
    last_union_sdf_csdl = None
    for iteration_index, ks_rho in enumerate(step9_smooth_union_rho_schedule):
        wing_projection_iteration_operation = bsm3.FunctionSetProjectionOperation(
            model=wing_projection_model,
            return_parametric=False,
        )
        fuse_projection_iteration_operation = bsm3.FunctionSetProjectionOperation(
            model=fuse_projection_model,
            return_parametric=False,
        )
        wing_sdf_iteration_operation = bsm3.FunctionSetClosestDistanceOperation(model=wing_sdf_model)
        fuse_sdf_iteration_operation = bsm3.FunctionSetClosestDistanceOperation(model=fuse_sdf_model)

        projected_to_wing = wing_projection_iteration_operation.evaluate(
            moved_wing_coefficients,
            projected_variable_vertices,
        )
        projected_to_fuse = fuse_projection_iteration_operation.evaluate(
            fuse_coefficients_csdl,
            projected_variable_vertices,
        )
        sdf_to_wing = wing_sdf_iteration_operation.evaluate(
            moved_wing_coefficients,
            projected_variable_vertices,
        )
        sdf_to_fuse = fuse_sdf_iteration_operation.evaluate(
            fuse_coefficients_csdl,
            projected_variable_vertices,
        )

        wing_sdf_gradient = _signed_distance_gradient_from_projection_csdl(
            sdf_to_wing,
            projected_variable_vertices,
            projected_to_wing,
        )
        fuse_sdf_gradient = _signed_distance_gradient_from_projection_csdl(
            sdf_to_fuse,
            projected_variable_vertices,
            projected_to_fuse,
        )
        union_sdf, wing_union_weight, fuse_union_weight = _smooth_minimum_signed_distance_csdl(
            sdf_to_wing,
            sdf_to_fuse,
            ks_rho=ks_rho,
        )
        if iteration_index == 0:
            first_union_sdf_csdl = union_sdf
        union_sdf_gradient = (
            _expand_vector_to_columns(csdl.reshape(wing_union_weight, (-1,)), 3) * wing_sdf_gradient
            + _expand_vector_to_columns(csdl.reshape(fuse_union_weight, (-1,)), 3) * fuse_sdf_gradient
        )
        union_gradient_norm_squared = csdl.sum(union_sdf_gradient**2, axes=(1,)) + 1e-12
        projected_variable_vertices = projected_variable_vertices - (
            _expand_vector_to_columns(union_sdf / union_gradient_norm_squared, 3)
            * union_sdf_gradient
        )
        last_union_sdf_csdl = union_sdf

    if moved_protected_feature_vertices is not None:
        projected_variable_vertices = projected_variable_vertices.set(
            csdl.slice[protected_feature_indices.tolist(), :],
            moved_protected_feature_vertices,
        )

    updated_vertices = np.asarray(projected_variable_vertices.value, dtype=float)
    final_combined_surface_distance, _ = combined_projection_model.project(
        np.asarray(moved_total_coefficients.value, dtype=float),
        updated_vertices,
    )
    final_wing_sdf, _ = wing_sdf_model.project(
        np.asarray(moved_wing_coefficients.value, dtype=float),
        updated_vertices,
    )
    final_fuse_sdf, _ = fuse_sdf_model.project(
        initial_fuse_coefficients,
        updated_vertices,
    )
    final_union_sdf, _ = _smooth_minimum_signed_distance_numpy(
        np.column_stack([final_wing_sdf, final_fuse_sdf]),
        ks_rho=step9_smooth_union_rho_schedule[-1],
    )

    print("")
    print("Static-seam native-CSDL movement test")
    print("    Mesh:", mesh_filename)
    print("    Vertices:", num_vertices)
    print("    Interpolation vertices:", interpolation_indices.size)
    print("    Exact seam seed vertices:", seam_seed_indices.size)
    print("    Seam candidate vertices:", seam_candidate_indices.size)
    print("    Local training interpolation vertices:", local_training_indices.size)
    print("    Protected wing feature vertices:", protected_feature_indices.size)
    print("    Root chord proxy:", f"{root_chord_proxy:.6e}")
    print(
        "    Envelope translation bounds:",
        f"{-translation_envelope_mac * root_chord_proxy:.6e} to "
        f"{translation_envelope_mac * root_chord_proxy:.6e}",
    )
    print(
        "    Envelope rotation bounds:",
        f"{-rotation_envelope_degrees:.6e} to {rotation_envelope_degrees:.6e}",
    )
    print("    Active translation:", f"{translation_amount:.6e}")
    print("    Active rotation (deg):", f"{wing_root_rotation_degrees:.6e}")
    print("    RBF fit mode:", rbf_fit_mode)
    print("    RBF kernel:", rbf_kernel)
    print("    RBF kernel scale:", f"{rbf_kernel_scale:.6e}")
    print("    RBF regularization:", f"{rbf_regularization:.6e}")
    print("    Step 9 projection mode:", step9_projection_mode)
    print(
        "    Step 9 smooth-union rho schedule:",
        np.array2string(step9_smooth_union_rho_schedule, precision=6, suppress_small=False),
    )
    print(
        "    Step 9 union residual before:",
        _format_stats(np.abs(first_union_sdf_csdl.value)),
    )
    print(
        "    Step 9 union residual after:",
        _format_stats(np.abs(final_union_sdf)),
    )
    print(
        "    Final combined-patch distance:",
        _format_stats(np.abs(final_combined_surface_distance)),
    )
    print(
        "    Global interpolation fit error:",
        _format_stats(
            np.linalg.norm(
                (
                    predicted_global_interpolation_displacements.value
                    - provisional_interpolation_target_displacements.value
                ),
                axis=1,
            )
        ),
    )
    print(
        "    Total interpolation target error:",
        _format_stats(np.linalg.norm(interpolation_target_error.value, axis=1)),
    )
    print(
        "    Local training self-fit error:",
        _format_stats(np.linalg.norm(local_training_fit_error.value, axis=1)),
    )
    print(
        "    Global displacement magnitude:",
        _format_stats(np.linalg.norm(predicted_global_variable_displacements.value, axis=1)),
    )
    print(
        "    Local support:",
        _format_stats(variable_local_support.value),
    )
    print(
        "    Local displacement magnitude:",
        _format_stats(np.linalg.norm(predicted_local_variable_displacements.value, axis=1)),
    )
    print(
        "    Total displacement magnitude:",
        _format_stats(np.linalg.norm(predicted_variable_displacements.value, axis=1)),
    )


    if plot:
        _plot_surface_debug(
            updated_vertices,
            mesh_faces=mesh_faces,
            interpolation_indices=interpolation_indices,
            seam_seed_indices=seam_seed_indices,
            protected_feature_indices=protected_feature_indices,
            mesh_label="Updated mesh",
        )
