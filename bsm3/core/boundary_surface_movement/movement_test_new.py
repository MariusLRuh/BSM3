from heapq import heappop, heappush
from pathlib import Path

import meshio
import numpy as np
import pyvista as pv

import csdl_alpha as csdl
import lsdo_function_spaces as lfs

import bsm3


def _make_faces(mesh: meshio.Mesh) -> np.ndarray:
    triangle_cells = mesh.cells_dict.get("triangle")
    if triangle_cells is None or triangle_cells.size == 0:
        raise ValueError("Expected at least one triangle cell block in the mesh.")

    faces = np.empty((triangle_cells.shape[0], 4), dtype=np.int64)
    faces[:, 0] = 3
    faces[:, 1:] = triangle_cells
    return faces.ravel()


def _build_rbf_polynomial_terms(points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=float)
    return np.column_stack(
        [
            np.ones(points.shape[0], dtype=float),
            points,
        ]
    )


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


def _fit_vector_rbf(
    training_points: np.ndarray,
    training_displacements: np.ndarray,
    *,
    fit_mode: str,
    kernel: str,
    kernel_scale: float,
    regularization: float,
    polynomial_regularization: float = 0.0,
    sample_weights = None,
) -> tuple[np.ndarray, np.ndarray]:
    training_points = np.asarray(training_points, dtype=float)
    training_displacements = np.asarray(training_displacements, dtype=float)

    num_points = training_points.shape[0]
    pairwise_distances = np.linalg.norm(
        training_points[:, None, :] - training_points[None, :, :],
        axis=2,
    )
    kernel_matrix = _evaluate_rbf_kernel(
        pairwise_distances,
        kernel=kernel,
        kernel_scale=kernel_scale,
    )
    polynomial_terms = _build_rbf_polynomial_terms(training_points)

    if fit_mode == "exact_interpolation":
        kernel_matrix = kernel_matrix + regularization * np.eye(num_points)

        system_matrix = np.zeros((num_points + 4, num_points + 4), dtype=float)
        system_matrix[:num_points, :num_points] = kernel_matrix
        system_matrix[:num_points, num_points:] = polynomial_terms
        system_matrix[num_points:, :num_points] = polynomial_terms.T

        rhs = np.zeros((num_points + 4, training_displacements.shape[1]), dtype=float)
        rhs[:num_points, :] = training_displacements

        try:
            solution = np.linalg.solve(system_matrix, rhs)
        except np.linalg.LinAlgError:
            solution, *_ = np.linalg.lstsq(system_matrix, rhs, rcond=None)
    elif fit_mode == "weighted_least_squares":
        if sample_weights is None:
            sample_weights = np.ones((num_points,), dtype=float)
        else:
            sample_weights = np.asarray(sample_weights, dtype=float).reshape((num_points,))
        sqrt_sample_weights = np.sqrt(np.maximum(sample_weights, 0.0))

        weighted_kernel_matrix = sqrt_sample_weights[:, None] * kernel_matrix
        weighted_polynomial_terms = sqrt_sample_weights[:, None] * polynomial_terms
        weighted_targets = sqrt_sample_weights[:, None] * training_displacements

        design_matrix_blocks = [
            np.hstack([weighted_kernel_matrix, weighted_polynomial_terms]),
        ]
        rhs_blocks = [weighted_targets]

        if regularization > 0.0:
            design_matrix_blocks.append(
                np.hstack(
                    [
                        np.sqrt(regularization) * np.eye(num_points),
                        np.zeros((num_points, 4), dtype=float),
                    ]
                )
            )
            rhs_blocks.append(np.zeros((num_points, training_displacements.shape[1]), dtype=float))

        if polynomial_regularization > 0.0:
            design_matrix_blocks.append(
                np.hstack(
                    [
                        np.zeros((4, num_points), dtype=float),
                        np.sqrt(polynomial_regularization) * np.eye(4),
                    ]
                )
            )
            rhs_blocks.append(np.zeros((4, training_displacements.shape[1]), dtype=float))

        design_matrix = np.vstack(design_matrix_blocks)
        rhs = np.vstack(rhs_blocks)
        solution, *_ = np.linalg.lstsq(design_matrix, rhs, rcond=None)
    else:
        raise ValueError(f"Unsupported RBF fit mode: {fit_mode}")

    weights = solution[:num_points, :]
    polynomial_coefficients = solution[num_points:, :]
    return weights, polynomial_coefficients


def _evaluate_vector_rbf(
    query_points: np.ndarray,
    training_points: np.ndarray,
    weights: np.ndarray,
    polynomial_coefficients: np.ndarray,
    *,
    kernel: str,
    kernel_scale: float,
) -> np.ndarray:
    query_points = np.asarray(query_points, dtype=float)
    training_points = np.asarray(training_points, dtype=float)

    query_distances = np.linalg.norm(
        query_points[:, None, :] - training_points[None, :, :],
        axis=2,
    )
    kernel_values = _evaluate_rbf_kernel(
        query_distances,
        kernel=kernel,
        kernel_scale=kernel_scale,
    )
    polynomial_terms = _build_rbf_polynomial_terms(query_points)
    return kernel_values @ weights + polynomial_terms @ polynomial_coefficients


def _triangle_areas(points: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    tri_points = np.asarray(points, dtype=float)[triangles]
    edge_1 = tri_points[:, 1, :] - tri_points[:, 0, :]
    edge_2 = tri_points[:, 2, :] - tri_points[:, 0, :]
    return 0.5 * np.linalg.norm(np.cross(edge_1, edge_2), axis=1)


def _build_vertex_neighbors(num_vertices: int, triangles: np.ndarray) -> list[np.ndarray]:
    neighbor_sets = [set() for _ in range(num_vertices)]
    for triangle in np.asarray(triangles, dtype=int):
        i, j, k = int(triangle[0]), int(triangle[1]), int(triangle[2])
        neighbor_sets[i].update((j, k))
        neighbor_sets[j].update((i, k))
        neighbor_sets[k].update((i, j))
    return [np.asarray(sorted(neighbors), dtype=int) for neighbors in neighbor_sets]


def _surface_laplacian_displacement(points: np.ndarray, adjacency: list[np.ndarray]) -> np.ndarray:
    points = np.asarray(points, dtype=float)
    displacement = np.zeros_like(points)
    for vertex_index, neighbors in enumerate(adjacency):
        if neighbors.size == 0:
            continue
        displacement[vertex_index] = points[neighbors].mean(axis=0) - points[vertex_index]
    return displacement


def _triangle_unit_normals(
    points: np.ndarray,
    triangles: np.ndarray,
    *,
    eps: float = 1e-14,
) -> np.ndarray:
    tri_points = np.asarray(points, dtype=float)[np.asarray(triangles, dtype=int)]
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
    include_boundary: bool = True,
) -> np.ndarray:
    triangles = np.asarray(triangles, dtype=int)
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


def _normalize_weights(weights: np.ndarray, *, eps: float = 1e-15) -> np.ndarray:
    weights = np.asarray(weights, dtype=float)
    normalization = np.sum(weights, axis=1, keepdims=True)
    return weights / np.maximum(normalization, eps)


def _interaction_indicator(component_sdf: np.ndarray, *, num_active_components: int = 2) -> np.ndarray:
    component_sdf = np.abs(np.asarray(component_sdf, dtype=float))
    if component_sdf.ndim != 2:
        raise ValueError("Expected component SDF array with shape (num_points, num_components).")
    if component_sdf.shape[1] == 0:
        return np.zeros((component_sdf.shape[0],), dtype=float)

    num_active_components = max(1, min(int(num_active_components), component_sdf.shape[1]))
    if num_active_components == component_sdf.shape[1]:
        closest_component_sdf = component_sdf
    else:
        closest_component_sdf = np.partition(
            component_sdf,
            kth=num_active_components - 1,
            axis=1,
        )[:, :num_active_components]
    return np.sqrt(np.sum(closest_component_sdf**2, axis=1))


def _gaussian_support(indicator: np.ndarray, sigma: float, *, eps: float = 1e-12) -> np.ndarray:
    indicator = np.asarray(indicator, dtype=float)
    sigma_safe = max(float(sigma), eps)
    return np.exp(-(indicator**2) / (sigma_safe**2))


def _estimate_wing_root_quarter_chord(
    wing_points: np.ndarray,
    *,
    root_span_fraction: float = 0.05,
    quarter_chord_x_fraction: float = 0.25,
    quarter_chord_window_fraction: float = 0.1,
) -> np.ndarray:
    wing_points = np.asarray(wing_points, dtype=float)
    if wing_points.ndim != 2 or wing_points.shape[1] != 3:
        raise ValueError("Expected wing_points with shape (num_points, 3).")

    y_min = np.min(wing_points[:, 1])
    y_max = np.max(wing_points[:, 1])
    y_root = 0.5 * (y_min + y_max)
    span = max(y_max - y_min, 1e-12)
    root_half_width = max(root_span_fraction * span, 1e-12)

    root_mask = np.abs(wing_points[:, 1] - y_root) <= root_half_width
    if not np.any(root_mask):
        root_mask[np.argmin(np.abs(wing_points[:, 1] - y_root))] = True
    root_points = wing_points[root_mask]

    leading_edge_x = np.min(root_points[:, 0])
    trailing_edge_x = np.max(root_points[:, 0])
    chord = max(trailing_edge_x - leading_edge_x, 1e-12)
    quarter_chord_x = leading_edge_x + quarter_chord_x_fraction * chord

    quarter_chord_window = max(quarter_chord_window_fraction * chord, 1e-12)
    quarter_chord_mask = np.abs(root_points[:, 0] - quarter_chord_x) <= quarter_chord_window
    if not np.any(quarter_chord_mask):
        quarter_chord_mask[np.argmin(np.abs(root_points[:, 0] - quarter_chord_x))] = True
    quarter_chord_points = root_points[quarter_chord_mask]
    quarter_chord_z = np.mean(quarter_chord_points[:, 2])

    return np.array([quarter_chord_x, y_root, quarter_chord_z], dtype=float)


def _rotate_points_about_y_axis(
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


def _quintic_smoothstep(values: np.ndarray) -> np.ndarray:
    values = np.clip(np.asarray(values, dtype=float), 0.0, 1.0)
    return values**3 * (10.0 - 15.0 * values + 6.0 * values**2)


def _compute_graph_distances(
    points: np.ndarray,
    neighbors: list[np.ndarray],
    source_indices: np.ndarray,
) -> np.ndarray:
    points = np.asarray(points, dtype=float)
    source_indices = np.asarray(source_indices, dtype=int)

    distances = np.full(points.shape[0], np.inf, dtype=float)
    heap: list[tuple[float, int]] = []
    for source_index in np.unique(source_indices):
        distances[int(source_index)] = 0.0
        heappush(heap, (0.0, int(source_index)))

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
        return np.empty((0,), dtype=int)
    if num_samples >= num_points:
        return np.arange(num_points, dtype=int)

    centroid = np.mean(points, axis=0)
    first_index = int(np.argmax(np.linalg.norm(points - centroid, axis=1)))

    selected_indices = np.empty(num_samples, dtype=int)
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


def _evaluate_signed_distance_and_gradient(
    model: bsm3.FunctionSetProjectionModel,
    coefficients: np.ndarray,
    points: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(points, dtype=float)
    signed_distance, state = model.project(coefficients, points)
    point_gradients, _ = model.compute_vjp(
        coefficients,
        points,
        np.ones(points.shape[0], dtype=float),
        state,
    )
    return np.asarray(signed_distance, dtype=float), np.asarray(point_gradients, dtype=float)


def _smooth_minimum_signed_distance(
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


def _project_points_to_smooth_union_oml(
    points: np.ndarray,
    *,
    component_models: tuple[bsm3.FunctionSetProjectionModel, ...],
    component_coefficients: tuple[np.ndarray, ...],
    rho_schedule: np.ndarray,
    tolerance: float,
    gradient_norm_epsilon: float = 1e-14,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    projected_points = np.asarray(points, dtype=float).copy()
    rho_schedule = np.asarray(rho_schedule, dtype=float).reshape((-1,))
    if rho_schedule.size == 0:
        raise ValueError("rho_schedule must contain at least one value.")

    first_union_sdf = np.zeros(projected_points.shape[0], dtype=float)
    final_union_sdf = np.zeros(projected_points.shape[0], dtype=float)
    final_component_weights = np.zeros(
        (projected_points.shape[0], len(component_models)),
        dtype=float,
    )

    for iteration_index, ks_rho in enumerate(rho_schedule):
        component_sdf_values = []
        component_sdf_gradients = []
        for model, coefficients in zip(component_models, component_coefficients):
            sdf_values, sdf_gradients = _evaluate_signed_distance_and_gradient(
                model,
                coefficients,
                projected_points,
            )
            component_sdf_values.append(sdf_values)
            component_sdf_gradients.append(sdf_gradients)

        component_sdf_values = np.column_stack(component_sdf_values)
        component_sdf_gradients = np.stack(component_sdf_gradients, axis=1)
        union_sdf, component_weights = _smooth_minimum_signed_distance(
            component_sdf_values,
            ks_rho=ks_rho,
        )
        if iteration_index == 0:
            first_union_sdf = union_sdf.copy()
        union_sdf_gradient = np.sum(
            component_weights[:, :, None] * component_sdf_gradients,
            axis=1,
        )
        gradient_norm_squared = np.einsum(
            "ij,ij->i",
            union_sdf_gradient,
            union_sdf_gradient,
        )
        active_mask = np.abs(union_sdf) > tolerance
        step_mask = active_mask & (gradient_norm_squared > gradient_norm_epsilon)
        projected_points[step_mask] = (
            projected_points[step_mask]
            - (
                union_sdf[step_mask] / gradient_norm_squared[step_mask]
            )[:, None]
            * union_sdf_gradient[step_mask]
        )

    component_sdf_values = []
    for model, coefficients in zip(component_models, component_coefficients):
        sdf_values, _ = _evaluate_signed_distance_and_gradient(
            model,
            coefficients,
            projected_points,
        )
        component_sdf_values.append(sdf_values)
    component_sdf_values = np.column_stack(component_sdf_values)
    final_union_sdf, final_component_weights = _smooth_minimum_signed_distance(
        component_sdf_values,
        ks_rho=rho_schedule[-1],
    )
    iterations_used = np.full(projected_points.shape[0], rho_schedule.size, dtype=float)
    converged = np.abs(final_union_sdf) <= tolerance
    return (
        projected_points,
        first_union_sdf,
        final_union_sdf,
        final_component_weights,
        iterations_used,
        converged,
    )


def _format_stats(values: np.ndarray) -> str:
    values = np.asarray(values, dtype=float)
    return (
        f"min={np.min(values):.6e}, "
        f"mean={np.mean(values):.6e}, "
        f"max={np.max(values):.6e}"
    )


if __name__ == "__main__":
    plot = True
    plot_step8_prediction = False
    debug_projections = False
    alpha = 1.0
    sigma_phi = 0.1
    participation_mode = "hard"
    participation_sharpening = 1.0
    rbf_fit_mode ="weighted_least_squares" #  "exact_interpolation" #   
    rbf_kernel = "multiquadric" # "cubic" #    "gaussian" #  
    rbf_kernel_scale_factor = 0.01
    rbf_regularization_factor = 1e-6
    rbf_polynomial_regularization_factor = 1e-15
    use_anchor_vertices = False
    global_anchor_sample_weight = 10.0
    global_symmetry_plane_anchor_sample_weight = 10.0
    global_transition_sample_weight = 3.0
    global_interpolation_sample_weight = 1.0
    local_support_sample_weight_factor = 1.0
    local_seam_sample_weight = 10.0
    seam_master_mode = "largest_component_motion"
    seam_master_component = 0
    wing_root_rotation_degrees = 7.5
    wing_root_quarter_chord_span_fraction = 0.05
    symmetry_plane_anchor_mode = "soft_constraint"
    num_symmetry_plane_anchor_points = 0.
    symmetry_plane_y = 0.0
    symmetry_plane_tolerance = 1e-8
    local_symmetry_plane_sample_weight = 1.0
    seam_support_sigma_factor = 0.15
    seam_training_support_cutoff = 0.05
    step9_projection_mode = "smooth_union_ks" #"combined_function_set" # 
    step9_smooth_union_ks_rho_start = 8.
    step9_smooth_union_ks_rho_end = 8.
    step9_smooth_union_num_iterations = 5
    step9_smooth_union_tolerance = 1e-10
    step9_pre_projection_laplacian_step = 0.25
    sharp_feature_protection = True
    sharp_feature_angle_degrees = 110.0
    sharp_feature_include_boundary = False
    max_local_training_points = 900
    max_wing_anchor_training_points = 400
    max_fuse_anchor_training_points = 100
    max_transition_training_points = 900
    transition_bandwidth_factor = 0.08
    transition_beta_min = 0.2
    transition_beta_max = 0.8
    random_seed = 7
    rng = np.random.default_rng(random_seed)

    recorder = csdl.Recorder(inline=True)
    recorder.start()

    wing_fuse = lfs.import_file_patched(
        Path(__file__).with_name("wing_fuse_test.stp"),
        parallelize=False,
    )
    reshaped_total_coeffs = []
    for fun_ind, fun in wing_fuse.functions.items():
        coeffs = fun.coefficients
        reshaped_total_coeffs.append(csdl.reshape(coeffs, (-1, 3)))
    reshaped_total_coeffs_stacked = csdl.vstack(reshaped_total_coeffs)

    wing_keys = np.arange(0, 12)
    fuse_keys = np.arange(12, len(wing_fuse.functions))
    wing_fun_set = {key: wing_fuse.functions[key] for key in wing_keys}
    fuse_fun_set = {key: wing_fuse.functions[key] for key in fuse_keys}
    wing = lfs.FunctionSet(functions=wing_fun_set)
    fuse = lfs.FunctionSet(functions=fuse_fun_set)

    reshaped_wing_coeffs = []
    for fun_ind, fun in wing.functions.items():
        coeffs = fun.coefficients
        reshaped_wing_coeffs.append(csdl.reshape(coeffs, (-1, 3)))
    reshaped_wing_coeffs_stacked = csdl.vstack(reshaped_wing_coeffs)

    reshaped_fuse_coeffs = []
    for fun_ind, fun in fuse.functions.items():
        coeffs = fun.coefficients
        reshaped_fuse_coeffs.append(csdl.reshape(coeffs, (-1, 3)))
    reshaped_fuse_coeffs_stacked = csdl.vstack(reshaped_fuse_coeffs)

    mesh_path = Path(__file__).with_name("wing_fuse_test.msh")
    mesh = meshio.read(mesh_path)
    
    vertices = mesh.points
    triangles = mesh.cells_dict["triangle"]

    # fixed mesh nodes:
    # x direction: 
    #   0 ---> 0.1 * x_max 
    #   0.9 * x_max ---> x_max
    # y direction:
    #   0.5 * y_max ---> y_max
    #   0.5 * y_min ---> y_min

    # Identify the indices of the vertices that are within the fixed regions
    x_min = np.min(vertices[:, 0])
    x_max = np.max(vertices[:, 0])
    y_min = np.min(vertices[:, 1])
    y_max = np.max(vertices[:, 1])

    dx = x_max - x_min
    dy = y_max - y_min
    y_mid = 0.5 * (y_min + y_max)

    nose_mask = vertices[:, 0] <= x_min + 0.05 * dx
    tail_mask = vertices[:, 0] >= x_max - 0.2 * dx

    # Outer 50% of each half-span:
    left_tip_mask = vertices[:, 1] <= y_mid - 0.25 * dy
    right_tip_mask = vertices[:, 1] >= y_mid + 0.25 * dy

    symmetry_plane_anchor_mask = np.zeros(vertices.shape[0], dtype=bool)
    if use_anchor_vertices:
        wing_anchor_mask = left_tip_mask | right_tip_mask
        fuse_anchor_mask = (nose_mask | tail_mask) & ~wing_anchor_mask
        base_fixed_mask = nose_mask | tail_mask | left_tip_mask | right_tip_mask
        variable_region_mask = ~base_fixed_mask
        if num_symmetry_plane_anchor_points > 0:
            symmetry_plane_candidate_indices = np.where(
                variable_region_mask
                & (np.abs(vertices[:, 1] - symmetry_plane_y) <= symmetry_plane_tolerance)
            )[0]
            if symmetry_plane_candidate_indices.shape[0] > 0:
                selected_symmetry_anchor_local = _select_farthest_point_indices(
                    vertices[symmetry_plane_candidate_indices],
                    min(num_symmetry_plane_anchor_points, symmetry_plane_candidate_indices.shape[0]),
                )
                symmetry_plane_anchor_indices = symmetry_plane_candidate_indices[
                    selected_symmetry_anchor_local
                ]
                symmetry_plane_anchor_mask[symmetry_plane_anchor_indices] = True

        if (
            symmetry_plane_anchor_mode == "soft_constraint"
            and num_symmetry_plane_anchor_points > 0
            and rbf_fit_mode != "weighted_least_squares"
        ):
            raise ValueError(
                "Soft symmetry-plane anchors require rbf_fit_mode='weighted_least_squares'."
            )

        if symmetry_plane_anchor_mode == "hard_fixed":
            fixed_indices = np.where(base_fixed_mask | symmetry_plane_anchor_mask)[0]
        elif symmetry_plane_anchor_mode == "soft_constraint":
            fixed_indices = np.where(base_fixed_mask)[0]
        else:
            raise ValueError(
                f"Unsupported symmetry_plane_anchor_mode: {symmetry_plane_anchor_mode}"
            )
    else:
        wing_anchor_mask = np.zeros(vertices.shape[0], dtype=bool)
        fuse_anchor_mask = np.zeros(vertices.shape[0], dtype=bool)
        base_fixed_mask = np.zeros(vertices.shape[0], dtype=bool)
        variable_region_mask = np.ones(vertices.shape[0], dtype=bool)
        fixed_indices = np.empty((0,), dtype=int)

    wing_anchor_indices = np.where(wing_anchor_mask)[0]
    fuse_anchor_indices = np.where(fuse_anchor_mask)[0]
    symmetry_plane_anchor_indices = np.where(symmetry_plane_anchor_mask)[0]
    wing_anchor_vertices = vertices[wing_anchor_indices]
    fuse_anchor_vertices = vertices[fuse_anchor_indices]
    symmetry_plane_anchor_vertices = vertices[symmetry_plane_anchor_indices]

    # The rest of the vertices are free to move
    variable_indices = np.setdiff1d(np.arange(vertices.shape[0]), fixed_indices)
    variable_local_indices = -np.ones(vertices.shape[0], dtype=int)
    variable_local_indices[variable_indices] = np.arange(variable_indices.size)
    vertex_neighbors = _build_vertex_neighbors(vertices.shape[0], triangles)
    bounding_box_diagonal = np.linalg.norm(
        np.max(vertices, axis=0) - np.min(vertices, axis=0)
    )
    seam_support_sigma = seam_support_sigma_factor * bounding_box_diagonal

    # project variable vertices onto wing and fuse and compute distance to each component
    variable_vertices = vertices[variable_indices]
    variable_vertices_csdl = csdl.Variable(name="variable_vertices", value=variable_vertices)
    wing_projection_model = bsm3.FunctionSetProjectionModel(
        wing,
        warm_start_nu=40,
        warm_start_nv=40,
        edge_map_num_samples=25,
        debug=debug_projections,
    )
    wing_projection_op = bsm3.FunctionSetProjectionOperation(model=wing_projection_model)
    para_coords_wing = wing_projection_op.evaluate(
        coefficients=reshaped_wing_coeffs_stacked,
        points=variable_vertices_csdl,
    )
    wing_eval_model = bsm3.FunctionSetEvaluationModel(wing)
    wing_eval_op = bsm3.FunctionSetEvaluationOperation(model=wing_eval_model)
    projected_variable_verts_wing = wing_eval_op.evaluate(
        coefficients=reshaped_wing_coeffs_stacked,
        parametric_coordinates=para_coords_wing,
    )

    # repeat for fuse
    fuse_projection_model = bsm3.FunctionSetProjectionModel(
        fuse,
        warm_start_nu=40,
        warm_start_nv=40,
        edge_map_num_samples=25,
        debug=debug_projections,
    )  
    fuse_projection_op = bsm3.FunctionSetProjectionOperation(model=fuse_projection_model)
    para_coords_fuse = fuse_projection_op.evaluate(
        coefficients=reshaped_fuse_coeffs_stacked,
        points=variable_vertices_csdl,
    )
    fuse_eval_model = bsm3.FunctionSetEvaluationModel(fuse)
    fuse_eval_op = bsm3.FunctionSetEvaluationOperation(model=fuse_eval_model)
    projected_variable_verts_fuse = fuse_eval_op.evaluate(
        coefficients=reshaped_fuse_coeffs_stacked,
        parametric_coordinates=para_coords_fuse,
    )
    variable_verts_distance_to_wing = csdl.norm(variable_vertices_csdl - projected_variable_verts_wing, axes=(1, ))
    variable_verts_distance_to_fuse = csdl.norm(variable_vertices_csdl - projected_variable_verts_fuse, axes=(1, ))

    # get indices where both distances are close to zero; these are the vertices that lie near the intersection and should be included as interpolation vertices
    intersection_indices = np.where(
        (variable_verts_distance_to_wing.value < 1e-4) & (variable_verts_distance_to_fuse.value < 1e-4)
    )[0]

    print("intersection vertices", intersection_indices)

    # global indices of the intersection vertices in the original vertex array
    intersection_global_indices = variable_indices[intersection_indices]
    print("intersection vertices (global)", intersection_global_indices)
    
    # make sure local and global vertices are identical for the intersection vertices
    assert np.allclose(
        vertices[intersection_global_indices],
        variable_vertices[intersection_indices],
    )
    
    # plot intersection vertices
    if False:
        intersection_vertices = variable_vertices[intersection_indices]
        intersection_plot = lfs.plot_points(intersection_vertices, color="red", show=False)
        wing_fuse.plot(additional_plotting_elements=[intersection_plot], show=True)


    # Out of the variable vertices, we select a subset of "interpolation vertices",
    # that will be used to fit displacement field using RBFs; 
    # generally, we want to include the vertices that lie on intersections;
    # these can be found by projecting all vertices onto all components (wing and fuse in this case) 
    # and checking which projections lie on the same point on both components
    # num_interpolation_vertices = 250
    # interpolation_indices = np.sort(
    #     rng.choice(variable_indices, size=num_interpolation_vertices, replace=False)
    # )
    # interpolation_vertices = vertices[interpolation_indices]
    interpolation_indices = intersection_global_indices.copy()
    remaining_variable_indices = np.setdiff1d(variable_indices, interpolation_indices)
    num_additional_interp_vertices = 2000
    selected_additional_interp_local = _select_farthest_point_indices(
        vertices[remaining_variable_indices],
        min(num_additional_interp_vertices, remaining_variable_indices.size),
    )
    additional_variable_indices = remaining_variable_indices[selected_additional_interp_local]
    additional_variable_vertices = vertices[additional_variable_indices]
    interpolation_vertices_intersection = vertices[interpolation_indices]
    interpolation_vertices = np.vstack([interpolation_vertices_intersection, additional_variable_vertices])
    interpolation_indices = np.concatenate([interpolation_indices, additional_variable_indices])
    seam_interpolation_mask = np.isin(interpolation_indices, intersection_global_indices)
    
    if interpolation_vertices.shape[0] == 0:
        raise ValueError("No interpolation vertices were identified from the component intersection.")
    interpolation_vertices_csdl = csdl.Variable(name="interpolation_vertices", value=interpolation_vertices)


    #################### Step 0 ####################
    # project interpolation nodes onto wing and fuse and compute distance
    # wing
    wing_projection_model = bsm3.FunctionSetProjectionModel(
        wing,
        warm_start_nu=40,
        warm_start_nv=40,
        edge_map_num_samples=25,
        debug=debug_projections,
    )

    wing_eval_model = bsm3.FunctionSetEvaluationModel(wing)

    projection_op_wing_interp = bsm3.FunctionSetProjectionOperation(model=wing_projection_model)
    para_coords_wing_interp = projection_op_wing_interp.evaluate(
        coefficients=reshaped_wing_coeffs_stacked,
        points=interpolation_vertices_csdl,
    )
    eval_op_wing_interp = bsm3.FunctionSetEvaluationOperation(model=wing_eval_model)
    projected_interp_verts_wing = eval_op_wing_interp.evaluate(
        coefficients=reshaped_wing_coeffs_stacked,
        parametric_coordinates=para_coords_wing_interp,
    )
    interp_verts_distance_to_wing = csdl.norm(interpolation_vertices_csdl - projected_interp_verts_wing, axes=(1, ))
    
    # fuse
    fuse_projection_model = bsm3.FunctionSetProjectionModel(
        fuse,
        warm_start_nu=40,
        warm_start_nv=40,
        edge_map_num_samples=25,
        debug=debug_projections,
    )

    fuse_eval_model = bsm3.FunctionSetEvaluationModel(fuse)

    projection_op_fuse_interp = bsm3.FunctionSetProjectionOperation(model=fuse_projection_model)
    para_coords_fuse_interp = projection_op_fuse_interp.evaluate(
        coefficients=reshaped_fuse_coeffs_stacked,
        points=interpolation_vertices_csdl,
    )
    eval_op_fuse_interp = bsm3.FunctionSetEvaluationOperation(model=fuse_eval_model)
    projected_interp_verts_fuse = eval_op_fuse_interp.evaluate(
        coefficients=reshaped_fuse_coeffs_stacked,
        parametric_coordinates=para_coords_fuse_interp,
    )
    interp_verts_distance_to_fuse = csdl.norm(interpolation_vertices_csdl - projected_interp_verts_fuse, axes=(1, ))

    initial_wing_coeffs = np.asarray(reshaped_wing_coeffs_stacked.value, dtype=float).copy()
    initial_fuse_coeffs = np.asarray(reshaped_fuse_coeffs_stacked.value, dtype=float).copy()

    wing_anchor_parametric_coordinates = None
    wing_anchor_projected_initial = None
    if wing_anchor_vertices.size > 0:
        _, wing_anchor_projection_state = wing_projection_model.project(
            initial_wing_coeffs,
            wing_anchor_vertices,
        )
        wing_anchor_parametric_coordinates = np.column_stack(
            [
                wing_anchor_projection_state["patch_id"],
                wing_anchor_projection_state["uv"],
            ]
        )
        wing_anchor_projected_initial = wing_eval_model.evaluate(
            initial_wing_coeffs,
            wing_anchor_parametric_coordinates,
        )

    #################### Step 1 ####################
    # Update geometry coefficients of wing and fusealge;
    # In an actual optimization this would be done via FFD;
    # For this test case, we directly move the coefficients;
    # We apply a wing translation along the fuselage (x-direction), then
    # rotate the translated wing about the y-axis through the root quarter-chord.
    translation_amount = -2.
    initial_root_quarter_chord = _estimate_wing_root_quarter_chord(
        initial_wing_coeffs,
        root_span_fraction=wing_root_quarter_chord_span_fraction,
    )
    translation_vector = np.array([translation_amount, 0.0, 0.0], dtype=float)
    moved_wing_coeffs = initial_wing_coeffs + translation_vector[None, :]
    translated_root_quarter_chord = initial_root_quarter_chord + translation_vector
    moved_wing_coeffs = _rotate_points_about_y_axis(
        moved_wing_coeffs,
        wing_root_rotation_degrees,
        translated_root_quarter_chord,
    )
    reshaped_wing_coeffs_stacked = csdl.Variable(
        name="moved_wing_coeffs",
        value=moved_wing_coeffs,
    )
    moved_total_coeffs = np.vstack([moved_wing_coeffs, initial_fuse_coeffs])
    wing_fuse_projection_model = bsm3.FunctionSetProjectionModel(
        wing_fuse,
        warm_start_nu=40,
        warm_start_nv=40,
        edge_map_num_samples=25,
        output_mode="distance",
        debug=debug_projections,
    )

    #################### Step 2 ####################
    # Re-evaluate the parametric coordinates of the projected interpolation vertices
    eval_op_wing_interp_post_mvmt = bsm3.FunctionSetEvaluationOperation(model=wing_eval_model)
    projected_interp_verts_wing_post_mvmt = eval_op_wing_interp_post_mvmt.evaluate(
        coefficients=reshaped_wing_coeffs_stacked,
        parametric_coordinates=para_coords_wing_interp,
    )

    # for consistency we also re-evaluate the fuse projections, even though the fuse didn't move
    eval_op_fuse_interp_post_mvmt = bsm3.FunctionSetEvaluationOperation(model=fuse_eval_model)
    projected_interp_verts_fuse_post_mvmt = eval_op_fuse_interp_post_mvmt.evaluate(
        coefficients=reshaped_fuse_coeffs_stacked,
        parametric_coordinates=para_coords_fuse_interp,
    )

    #################### Step 3 ####################
    # Generate training data for RBF fit of displacement field based 
    # on how the projected interpolation vertices moved
    interp_verts_displacement_wing = projected_interp_verts_wing_post_mvmt - projected_interp_verts_wing
    interp_verts_displacement_fuse = projected_interp_verts_fuse_post_mvmt - projected_interp_verts_fuse
    # weights are normalized exponential distance weights so that points closer
    # to the wing are more influenced by the wing displacement and points closer
    # to the fuse are more influenced by the fuse displacement
    interp_component_distances = np.column_stack(
        [
            np.asarray(interp_verts_distance_to_wing.value, dtype=float),
            np.asarray(interp_verts_distance_to_fuse.value, dtype=float),
        ]
    )
    interp_component_displacements = np.stack(
        [
            np.asarray(interp_verts_displacement_wing.value, dtype=float),
            np.asarray(interp_verts_displacement_fuse.value, dtype=float),
        ],
        axis=1,
    )
    global_component_weights = _normalize_weights(np.exp(-alpha * interp_component_distances))
    interpolation_displacements = np.sum(
        global_component_weights[:, :, None] * interp_component_displacements,
        axis=1,
    )

    moved_wing_anchor_vertices = np.empty((0, 3), dtype=float)
    if wing_anchor_vertices.size > 0:
        moved_wing_anchor_vertices = wing_eval_model.evaluate(
            moved_wing_coeffs,
            wing_anchor_parametric_coordinates,
        )
    wing_anchor_displacements = np.empty((0, 3), dtype=float)
    if wing_anchor_vertices.size > 0:
        wing_anchor_displacements = moved_wing_anchor_vertices - wing_anchor_vertices
    fuse_anchor_displacements = np.zeros_like(fuse_anchor_vertices)
    symmetry_plane_anchor_displacements = np.zeros_like(symmetry_plane_anchor_vertices)

    #################### Step 4 ####################
    # Build an anchor-satisfying baseline displacement field, then fit
    # residuals so the interpolation region transitions smoothly into the
    # anchor regions instead of being stitched to them afterward.
    selected_wing_anchor_local = np.empty((0,), dtype=int)
    wing_anchor_training_points = np.empty((0, 3), dtype=float)
    wing_anchor_training_displacements = np.empty((0, 3), dtype=float)
    if wing_anchor_vertices.shape[0] > 0:
        selected_wing_anchor_local = _select_farthest_point_indices(
            wing_anchor_vertices,
            min(max_wing_anchor_training_points, wing_anchor_vertices.shape[0]),
        )
        wing_anchor_training_points = wing_anchor_vertices[selected_wing_anchor_local]
        wing_anchor_training_displacements = wing_anchor_displacements[selected_wing_anchor_local]

    selected_fuse_anchor_local = np.empty((0,), dtype=int)
    fuse_anchor_training_points = np.empty((0, 3), dtype=float)
    fuse_anchor_training_displacements = np.empty((0, 3), dtype=float)
    if fuse_anchor_vertices.shape[0] > 0:
        selected_fuse_anchor_local = _select_farthest_point_indices(
            fuse_anchor_vertices,
            min(max_fuse_anchor_training_points, fuse_anchor_vertices.shape[0]),
        )
        fuse_anchor_training_points = fuse_anchor_vertices[selected_fuse_anchor_local]
        fuse_anchor_training_displacements = fuse_anchor_displacements[selected_fuse_anchor_local]

    symmetry_plane_anchor_training_points = symmetry_plane_anchor_vertices.copy()
    symmetry_plane_anchor_training_displacements = symmetry_plane_anchor_displacements.copy()

    baseline_training_points_list = []
    baseline_training_displacements_list = []
    baseline_training_weights_list = []
    if wing_anchor_training_points.shape[0] > 0:
        baseline_training_points_list.append(wing_anchor_training_points)
        baseline_training_displacements_list.append(wing_anchor_training_displacements)
        baseline_training_weights_list.append(
            np.full(
                wing_anchor_training_points.shape[0],
                global_anchor_sample_weight,
                dtype=float,
            )
        )
    if fuse_anchor_training_points.shape[0] > 0:
        baseline_training_points_list.append(fuse_anchor_training_points)
        baseline_training_displacements_list.append(fuse_anchor_training_displacements)
        baseline_training_weights_list.append(
            np.full(
                fuse_anchor_training_points.shape[0],
                global_anchor_sample_weight,
                dtype=float,
            )
        )
    if symmetry_plane_anchor_training_points.shape[0] > 0:
        baseline_training_points_list.append(symmetry_plane_anchor_training_points)
        baseline_training_displacements_list.append(
            symmetry_plane_anchor_training_displacements
        )
        baseline_training_weights_list.append(
            np.full(
                symmetry_plane_anchor_training_points.shape[0],
                global_symmetry_plane_anchor_sample_weight,
                dtype=float,
            )
        )

    if baseline_training_points_list:
        baseline_training_points = np.vstack(baseline_training_points_list)
        baseline_training_displacements = np.vstack(baseline_training_displacements_list)
        baseline_sample_weights = np.concatenate(baseline_training_weights_list)
    else:
        baseline_training_points = np.empty((0, 3), dtype=float)
        baseline_training_displacements = np.empty((0, 3), dtype=float)
        baseline_sample_weights = np.empty((0,), dtype=float)

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

    if baseline_training_points.shape[0] > 0:
        anchor_rbf_weights, anchor_rbf_polynomial_coefficients = _fit_vector_rbf(
            baseline_training_points,
            baseline_training_displacements,
            fit_mode=rbf_fit_mode,
            kernel=rbf_kernel,
            kernel_scale=rbf_kernel_scale,
            regularization=rbf_regularization,
            polynomial_regularization=rbf_polynomial_regularization,
            sample_weights=baseline_sample_weights,
        )
    else:
        anchor_rbf_weights = np.empty((0, 3), dtype=float)
        anchor_rbf_polynomial_coefficients = np.zeros((4, 3), dtype=float)

    def evaluate_anchor_baseline(query_points: np.ndarray) -> np.ndarray:
        query_points = np.asarray(query_points, dtype=float)
        if baseline_training_points.shape[0] == 0:
            return np.zeros((query_points.shape[0], 3), dtype=float)
        return _evaluate_vector_rbf(
            query_points,
            baseline_training_points,
            anchor_rbf_weights,
            anchor_rbf_polynomial_coefficients,
            kernel=rbf_kernel,
            kernel_scale=rbf_kernel_scale,
        )

    anchor_baseline_interp_displacements = evaluate_anchor_baseline(interpolation_vertices)
    anchor_baseline_variable_displacements = evaluate_anchor_baseline(variable_vertices)
    anchor_baseline_symmetry_plane_displacements = evaluate_anchor_baseline(
        symmetry_plane_anchor_vertices
    )

    provisional_global_residual_targets = (
        interpolation_displacements - anchor_baseline_interp_displacements
    )
    provisional_global_weights, provisional_global_polynomial_coefficients = _fit_vector_rbf(
        interpolation_vertices,
        provisional_global_residual_targets,
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
    provisional_global_interp_displacements = (
        anchor_baseline_interp_displacements
        + _evaluate_vector_rbf(
            interpolation_vertices,
            interpolation_vertices,
            provisional_global_weights,
            provisional_global_polynomial_coefficients,
            kernel=rbf_kernel,
            kernel_scale=rbf_kernel_scale,
        )
    )
    provisional_global_variable_displacements = (
        anchor_baseline_variable_displacements
        + _evaluate_vector_rbf(
            variable_vertices,
            interpolation_vertices,
            provisional_global_weights,
            provisional_global_polynomial_coefficients,
            kernel=rbf_kernel,
            kernel_scale=rbf_kernel_scale,
        )
    )

    interpolation_graph_distances = _compute_graph_distances(
        vertices,
        vertex_neighbors,
        interpolation_indices,
    )
    anchor_graph_distances = np.full(vertices.shape[0], np.inf, dtype=float)
    variable_anchor_graph_distances = anchor_graph_distances[variable_indices]
    variable_interpolation_graph_distances = interpolation_graph_distances[variable_indices]
    transition_bandwidth = transition_bandwidth_factor * bounding_box_diagonal

    interpolation_membership_mask = np.zeros(vertices.shape[0], dtype=bool)
    interpolation_membership_mask[interpolation_indices] = True
    transition_beta_variable = np.zeros(variable_indices.shape[0], dtype=float)
    transition_global_indices = np.empty((0,), dtype=int)
    if fixed_indices.size > 0:
        anchor_graph_distances = _compute_graph_distances(
            vertices,
            vertex_neighbors,
            fixed_indices,
        )
        variable_anchor_graph_distances = anchor_graph_distances[variable_indices]
        transition_blend_ratio = variable_anchor_graph_distances / np.maximum(
            variable_anchor_graph_distances + variable_interpolation_graph_distances,
            1e-15,
        )
        transition_beta_variable = _quintic_smoothstep(transition_blend_ratio)
        transition_candidate_mask = (
            np.isfinite(variable_anchor_graph_distances)
            & np.isfinite(variable_interpolation_graph_distances)
            & (variable_anchor_graph_distances > 0.0)
            & (variable_anchor_graph_distances <= transition_bandwidth)
            & ~interpolation_membership_mask[variable_indices]
            & (transition_beta_variable > transition_beta_min)
            & (transition_beta_variable < transition_beta_max)
        )
        transition_candidate_global_indices = variable_indices[transition_candidate_mask]
        if transition_candidate_global_indices.shape[0] > max_transition_training_points:
            selected_transition_local = _select_farthest_point_indices(
                vertices[transition_candidate_global_indices],
                max_transition_training_points,
            )
            transition_global_indices = transition_candidate_global_indices[
                selected_transition_local
            ]
        else:
            transition_global_indices = transition_candidate_global_indices

    transition_local_indices = variable_local_indices[transition_global_indices]
    transition_vertices = vertices[transition_global_indices]
    transition_anchor_baseline_displacements = anchor_baseline_variable_displacements[
        transition_local_indices
    ]
    transition_provisional_displacements = provisional_global_variable_displacements[
        transition_local_indices
    ]
    transition_beta = transition_beta_variable[transition_local_indices]
    transition_target_displacements = (
        (1.0 - transition_beta)[:, None] * transition_anchor_baseline_displacements
        + transition_beta[:, None] * transition_provisional_displacements
    )

    global_residual_training_points_list = []
    global_residual_training_displacements_list = []
    global_residual_training_weights_list = []
    if baseline_training_points.shape[0] > 0:
        global_residual_training_points_list.append(baseline_training_points)
        global_residual_training_displacements_list.append(
            np.zeros_like(baseline_training_displacements)
        )
        global_residual_training_weights_list.append(baseline_sample_weights)
    if transition_vertices.shape[0] > 0:
        global_residual_training_points_list.append(transition_vertices)
        global_residual_training_displacements_list.append(
            transition_target_displacements - transition_anchor_baseline_displacements
        )
        global_residual_training_weights_list.append(
            np.full(
                transition_vertices.shape[0],
                global_transition_sample_weight,
                dtype=float,
            )
        )
    global_residual_training_points_list.append(interpolation_vertices)
    global_residual_training_displacements_list.append(
        interpolation_displacements - anchor_baseline_interp_displacements
    )
    global_residual_training_weights_list.append(
        np.full(
            interpolation_vertices.shape[0],
            global_interpolation_sample_weight,
            dtype=float,
        )
    )

    rbf_training_points = np.vstack(global_residual_training_points_list)
    rbf_training_displacements = np.vstack(global_residual_training_displacements_list)
    rbf_training_sample_weights = np.concatenate(global_residual_training_weights_list)
    rbf_weights, rbf_polynomial_coefficients = _fit_vector_rbf(
        rbf_training_points,
        rbf_training_displacements,
        fit_mode=rbf_fit_mode,
        kernel=rbf_kernel,
        kernel_scale=rbf_kernel_scale,
        regularization=rbf_regularization,
        polynomial_regularization=rbf_polynomial_regularization,
        sample_weights=rbf_training_sample_weights,
    )

    predicted_global_interp_displacements = (
        anchor_baseline_interp_displacements
        + _evaluate_vector_rbf(
            interpolation_vertices,
            rbf_training_points,
            rbf_weights,
            rbf_polynomial_coefficients,
            kernel=rbf_kernel,
            kernel_scale=rbf_kernel_scale,
        )
    )
    predicted_global_symmetry_plane_displacements = evaluate_anchor_baseline(
        symmetry_plane_anchor_vertices
    )
    if symmetry_plane_anchor_vertices.shape[0] > 0:
        predicted_global_symmetry_plane_displacements = (
            anchor_baseline_symmetry_plane_displacements
            + _evaluate_vector_rbf(
                symmetry_plane_anchor_vertices,
                rbf_training_points,
                rbf_weights,
                rbf_polynomial_coefficients,
                kernel=rbf_kernel,
                kernel_scale=rbf_kernel_scale,
            )
        )

    #################### Step 5 ####################
    predicted_interpolation_vertices = (
        interpolation_vertices + predicted_global_interp_displacements
    )

    wing_sdf_model = bsm3.FunctionSetProjectionModel(
        wing,
        warm_start_nu=40,
        warm_start_nv=40,
        edge_map_num_samples=25,
        output_mode="distance",
        sdf=True,
        debug=debug_projections,
    )
    fuse_sdf_model = bsm3.FunctionSetProjectionModel(
        fuse,
        warm_start_nu=40,
        warm_start_nv=40,
        edge_map_num_samples=25,
        output_mode="distance",
        sdf=True,
        debug=debug_projections,
    )
    interp_sdf_wing, _ = wing_sdf_model.project(
        moved_wing_coeffs,
        predicted_interpolation_vertices,
    )
    interp_sdf_fuse, _ = fuse_sdf_model.project(
        initial_fuse_coeffs,
        predicted_interpolation_vertices,
    )
    interp_component_sdf = np.column_stack([interp_sdf_wing, interp_sdf_fuse])
    sigma_phi_safe = max(float(sigma_phi), 1e-12)
    participation_scores = np.exp(-(interp_component_sdf**2) / (sigma_phi_safe**2))
    if participation_sharpening != 1.0:
        participation_scores = participation_scores**participation_sharpening
    smooth_master_weights = _normalize_weights(participation_scores)
    hard_master_indices = np.argmax(participation_scores, axis=1)
    hard_master_weights = np.zeros_like(smooth_master_weights)
    hard_master_weights[
        np.arange(interpolation_vertices.shape[0]),
        hard_master_indices,
    ] = 1.0
    interp_interaction_indicator = _interaction_indicator(interp_component_sdf)
    seam_support_interp = _gaussian_support(interp_interaction_indicator, seam_support_sigma)
    seam_support_interp[seam_interpolation_mask] = 1.0
    if participation_mode == "smooth":
        participation_weights = smooth_master_weights
    elif participation_mode == "hard":
        participation_weights = hard_master_weights
    elif participation_mode == "hybrid":
        participation_weights = (
            seam_support_interp[:, None] * smooth_master_weights
            + (1.0 - seam_support_interp)[:, None] * hard_master_weights
        )
    else:
        raise ValueError(f"Unsupported participation_mode: {participation_mode}")

    #################### Step 6 ####################
    soft_interpolation_target_displacements = np.sum(
        participation_weights[:, :, None] * interp_component_displacements,
        axis=1,
    )
    if seam_master_mode == "fixed":
        if not (0 <= int(seam_master_component) < interp_component_displacements.shape[1]):
            raise ValueError("seam_master_component is out of bounds for the available components.")
        master_component_indices = np.full(
            interpolation_vertices.shape[0],
            int(seam_master_component),
            dtype=int,
        )
    elif seam_master_mode == "largest_component_motion":
        component_motion_magnitudes = np.linalg.norm(interp_component_displacements, axis=2)
        master_component_indices = np.argmax(component_motion_magnitudes, axis=1)
    else:
        raise ValueError(f"Unsupported seam_master_mode: {seam_master_mode}")

    master_interpolation_target_displacements = interp_component_displacements[
        np.arange(interpolation_vertices.shape[0]),
        master_component_indices,
    ]
    interpolation_target_displacements = (
        (1.0 - seam_support_interp)[:, None] * soft_interpolation_target_displacements
        + seam_support_interp[:, None] * master_interpolation_target_displacements
    )
    interpolation_local_residuals = (
        interpolation_target_displacements - predicted_global_interp_displacements
    )
    local_activation = 1.0 - np.sum(smooth_master_weights**2, axis=1)
    activated_local_residuals = local_activation[:, None] * interpolation_local_residuals

    symmetry_plane_local_constraint_points = np.empty((0, 3), dtype=float)
    symmetry_plane_local_target_displacements = np.empty((0, 3), dtype=float)
    symmetry_plane_local_support = np.empty((0,), dtype=float)
    if (
        symmetry_plane_anchor_mode == "soft_constraint"
        and symmetry_plane_anchor_vertices.shape[0] > 0
    ):
        predicted_global_symmetry_plane_vertices = (
            symmetry_plane_anchor_vertices + predicted_global_symmetry_plane_displacements
        )
        symmetry_plane_sdf_wing, _ = wing_sdf_model.project(
            moved_wing_coeffs,
            predicted_global_symmetry_plane_vertices,
        )
        symmetry_plane_sdf_fuse, _ = fuse_sdf_model.project(
            initial_fuse_coeffs,
            predicted_global_symmetry_plane_vertices,
        )
        symmetry_plane_component_sdf = np.column_stack(
            [symmetry_plane_sdf_wing, symmetry_plane_sdf_fuse]
        )
        symmetry_plane_interaction_indicator = _interaction_indicator(
            symmetry_plane_component_sdf
        )
        symmetry_plane_local_support_full = _gaussian_support(
            symmetry_plane_interaction_indicator,
            seam_support_sigma,
        )
        symmetry_plane_local_constraint_mask = (
            symmetry_plane_local_support_full > seam_training_support_cutoff
        )
        symmetry_plane_local_constraint_points = symmetry_plane_anchor_vertices[
            symmetry_plane_local_constraint_mask
        ]
        symmetry_plane_local_support = symmetry_plane_local_support_full[
            symmetry_plane_local_constraint_mask
        ]
        symmetry_plane_local_target_displacements = (
            -predicted_global_symmetry_plane_displacements[
                symmetry_plane_local_constraint_mask
            ]
        )

    #################### Step 7 ####################
    local_training_candidate_mask = seam_interpolation_mask | (
        seam_support_interp > seam_training_support_cutoff
    )
    local_training_candidate_indices = np.where(local_training_candidate_mask)[0]
    if local_training_candidate_indices.shape[0] > max_local_training_points:
        selected_local_training = _select_farthest_point_indices(
            interpolation_vertices[local_training_candidate_indices],
            max_local_training_points,
        )
        local_training_indices = local_training_candidate_indices[selected_local_training]
    else:
        local_training_indices = local_training_candidate_indices

    interpolation_local_training_points = interpolation_vertices[local_training_indices]
    interpolation_local_training_support = seam_support_interp[local_training_indices]
    interpolation_local_training_raw_residuals = np.empty((0, 3), dtype=float)
    interpolation_local_training_sample_weights = np.empty((0,), dtype=float)
    if interpolation_local_training_points.shape[0] > 0:
        interpolation_local_training_raw_residuals = interpolation_local_residuals[
            local_training_indices
        ] / np.maximum(interpolation_local_training_support[:, None], 1e-12)
        interpolation_local_training_sample_weights = (
            local_support_sample_weight_factor
            * np.maximum(interpolation_local_training_support, 1e-12)
        )
        interpolation_local_training_sample_weights[
            seam_interpolation_mask[local_training_indices]
        ] *= local_seam_sample_weight

    local_training_points_list = []
    local_training_raw_residuals_list = []
    local_training_sample_weights_list = []
    if interpolation_local_training_points.shape[0] > 0:
        local_training_points_list.append(interpolation_local_training_points)
        local_training_raw_residuals_list.append(interpolation_local_training_raw_residuals)
        local_training_sample_weights_list.append(interpolation_local_training_sample_weights)
    if symmetry_plane_local_constraint_points.shape[0] > 0:
        local_training_points_list.append(symmetry_plane_local_constraint_points)
        local_training_raw_residuals_list.append(
            symmetry_plane_local_target_displacements
            / np.maximum(symmetry_plane_local_support[:, None], 1e-12)
        )
        local_training_sample_weights_list.append(
            local_symmetry_plane_sample_weight
            * np.maximum(symmetry_plane_local_support, 1e-12)
        )

    local_training_points = np.empty((0, 3), dtype=float)
    local_training_raw_residuals = np.empty((0, 3), dtype=float)
    local_training_sample_weights = np.empty((0,), dtype=float)
    if local_training_points_list:
        local_training_points = np.vstack(local_training_points_list)
        local_training_raw_residuals = np.vstack(local_training_raw_residuals_list)
        local_training_sample_weights = np.concatenate(local_training_sample_weights_list)

    if local_training_points.shape[0] > 0:
        local_rbf_weights, local_rbf_polynomial_coefficients = _fit_vector_rbf(
            local_training_points,
            local_training_raw_residuals,
            fit_mode=rbf_fit_mode,
            kernel=rbf_kernel,
            kernel_scale=rbf_kernel_scale,
            regularization=rbf_regularization,
            polynomial_regularization=rbf_polynomial_regularization,
            sample_weights=local_training_sample_weights,
        )
    else:
        local_rbf_weights = np.empty((0, 3), dtype=float)
        local_rbf_polynomial_coefficients = np.zeros((4, 3), dtype=float)
        local_training_sample_weights = np.empty((0,), dtype=float)

    def evaluate_local_residual(query_points: np.ndarray) -> np.ndarray:
        query_points = np.asarray(query_points, dtype=float)
        if local_training_points.shape[0] == 0:
            return np.zeros((query_points.shape[0], 3), dtype=float)
        return _evaluate_vector_rbf(
            query_points,
            local_training_points,
            local_rbf_weights,
            local_rbf_polynomial_coefficients,
            kernel=rbf_kernel,
            kernel_scale=rbf_kernel_scale,
        )

    #################### Step 8 ####################
    predicted_variable_global_displacements = (
        anchor_baseline_variable_displacements
        + _evaluate_vector_rbf(
            variable_vertices,
            rbf_training_points,
            rbf_weights,
            rbf_polynomial_coefficients,
            kernel=rbf_kernel,
            kernel_scale=rbf_kernel_scale,
        )
    )
    predicted_global_variable_vertices = variable_vertices + predicted_variable_global_displacements
    variable_sdf_wing, _ = wing_sdf_model.project(
        moved_wing_coeffs,
        predicted_global_variable_vertices,
    )
    variable_sdf_fuse, _ = fuse_sdf_model.project(
        initial_fuse_coeffs,
        predicted_global_variable_vertices,
    )
    variable_component_sdf = np.column_stack([variable_sdf_wing, variable_sdf_fuse])
    variable_interaction_indicator = _interaction_indicator(variable_component_sdf)
    variable_local_support = _gaussian_support(variable_interaction_indicator, seam_support_sigma)
    if intersection_indices.size > 0:
        # Preserve the full seam correction on the original intersection set
        # even if the global prediction moves them slightly off the interaction band.
        variable_local_support[intersection_indices] = 1.0
    raw_predicted_variable_local_displacements = evaluate_local_residual(variable_vertices)
    predicted_variable_local_displacements = (
        variable_local_support[:, None] * raw_predicted_variable_local_displacements
    )
    predicted_variable_displacements = (
        predicted_variable_global_displacements + predicted_variable_local_displacements
    )
    predicted_variable_vertices = variable_vertices + predicted_variable_displacements
    symmetry_plane_step8_displacements = np.empty((0, 3), dtype=float)
    if symmetry_plane_anchor_indices.shape[0] > 0:
        symmetry_plane_variable_local_indices = variable_local_indices[symmetry_plane_anchor_indices]
        valid_symmetry_plane_variable_mask = symmetry_plane_variable_local_indices >= 0
        if np.any(valid_symmetry_plane_variable_mask):
            symmetry_plane_step8_displacements = predicted_variable_displacements[
                symmetry_plane_variable_local_indices[valid_symmetry_plane_variable_mask]
            ]

    predicted_transition_displacements = np.empty((0, 3), dtype=float)
    if transition_vertices.shape[0] > 0:
        predicted_transition_displacements = predicted_variable_displacements[transition_local_indices]

    if plot_step8_prediction:
        step8_vertices = vertices.copy()
        step8_vertices[variable_indices] = predicted_variable_vertices
        if wing_anchor_indices.size > 0:
            step8_vertices[wing_anchor_indices] = moved_wing_anchor_vertices
        if fuse_anchor_indices.size > 0:
            step8_vertices[fuse_anchor_indices] = fuse_anchor_vertices
        
        step_8_intersection_vertices = step8_vertices[intersection_global_indices]
        print("Step 8 intersection vertices", step_8_intersection_vertices)
        print("Step 8 intersection vertices movement", step_8_intersection_vertices - vertices[intersection_global_indices])

        step8_mesh_plot = pv.PolyData(step8_vertices, _make_faces(mesh))
        plotter = pv.Plotter()
        plotter.add_mesh(step8_mesh_plot, opacity=1.0, show_edges=True, label="Step 8 Prediction")
        plotter.show()

    #################### Step 9 ####################
    step9_projection_residual_before = np.empty((0,), dtype=float)
    step9_projection_residual_after = np.empty((0,), dtype=float)
    step9_smooth_union_rho_schedule = np.empty((0,), dtype=float)
    step9_sharp_feature_vertex_mask = np.zeros(vertices.shape[0], dtype=bool)
    step9_sharp_feature_variable_mask = np.zeros(variable_indices.shape[0], dtype=bool)
    step9_smoothed_variable_vertices = predicted_variable_vertices.copy()
    if step9_pre_projection_laplacian_step > 0.0 and variable_indices.size > 0:
        step9_predicted_vertices = vertices.copy()
        step9_predicted_vertices[variable_indices] = predicted_variable_vertices
        if wing_anchor_indices.size > 0:
            step9_predicted_vertices[wing_anchor_indices] = moved_wing_anchor_vertices
        if fuse_anchor_indices.size > 0:
            step9_predicted_vertices[fuse_anchor_indices] = fuse_anchor_vertices
        if sharp_feature_protection:
            step9_sharp_feature_vertex_mask = _sharp_feature_vertex_mask(
                step9_predicted_vertices,
                triangles,
                feature_angle_degrees=sharp_feature_angle_degrees,
                include_boundary=sharp_feature_include_boundary,
            )
            step9_sharp_feature_variable_mask = step9_sharp_feature_vertex_mask[variable_indices]

        step9_laplacian = _surface_laplacian_displacement(
            step9_predicted_vertices,
            vertex_neighbors,
        )
        step9_unprotected_variable_indices = variable_indices[~step9_sharp_feature_variable_mask]
        step9_predicted_vertices[step9_unprotected_variable_indices] = (
            step9_predicted_vertices[step9_unprotected_variable_indices]
            + step9_pre_projection_laplacian_step * step9_laplacian[step9_unprotected_variable_indices]
        )
        step9_smoothed_variable_vertices = step9_predicted_vertices[variable_indices]

    if step9_projection_mode == "combined_function_set":
        projected_variable_surface_distance, projected_variable_projection_state = (
            wing_fuse_projection_model.project(
                moved_total_coeffs,
                step9_smoothed_variable_vertices,
            )
        )
        projected_variable_vertices = np.asarray(
            projected_variable_projection_state["projected_points"],
            dtype=float,
        )
        projected_variable_projection_iterations = np.asarray(
            projected_variable_projection_state["iterations"],
            dtype=float,
        )
        projected_variable_projection_converged = np.asarray(
            projected_variable_projection_state["converged"],
            dtype=bool,
        )
        step9_projection_residual_before = np.abs(
            np.asarray(projected_variable_surface_distance, dtype=float)
        )
    elif step9_projection_mode == "smooth_union_ks":
        step9_smooth_union_rho_schedule = _make_ks_rho_schedule(
            step9_smooth_union_ks_rho_start,
            step9_smooth_union_ks_rho_end,
            step9_smooth_union_num_iterations,
        )
        (
            projected_variable_vertices,
            projected_variable_union_sdf_before,
            projected_variable_union_sdf_after,
            _,
            projected_variable_projection_iterations,
            projected_variable_projection_converged,
        ) = _project_points_to_smooth_union_oml(
            step9_smoothed_variable_vertices,
            component_models=(wing_sdf_model, fuse_sdf_model),
            component_coefficients=(moved_wing_coeffs, initial_fuse_coeffs),
            rho_schedule=step9_smooth_union_rho_schedule,
            tolerance=step9_smooth_union_tolerance,
        )
        step9_projection_residual_before = np.abs(projected_variable_union_sdf_before)
        step9_projection_residual_after = np.abs(projected_variable_union_sdf_after)
    else:
        raise ValueError(f"Unsupported step9_projection_mode: {step9_projection_mode}")
    pre_projection_smoothing_correction = step9_smoothed_variable_vertices - predicted_variable_vertices
    projection_correction = projected_variable_vertices - step9_smoothed_variable_vertices

    updated_vertices = vertices.copy()
    updated_vertices[variable_indices] = projected_variable_vertices
    if wing_anchor_indices.size > 0:
        updated_vertices[wing_anchor_indices] = moved_wing_anchor_vertices
    if fuse_anchor_indices.size > 0:
        updated_vertices[fuse_anchor_indices] = fuse_anchor_vertices
    updated_interpolation_vertices = updated_vertices[interpolation_indices]


    #################### Step 10 ####################
    _, refreshed_wing_projection_state = wing_projection_model.project(
        moved_wing_coeffs,
        updated_interpolation_vertices,
    )
    refreshed_para_coords_wing_interp = np.column_stack(
        [
            refreshed_wing_projection_state["patch_id"],
            refreshed_wing_projection_state["uv"],
        ]
    )
    refreshed_projected_interp_verts_wing = wing_eval_model.evaluate(
        moved_wing_coeffs,
        refreshed_para_coords_wing_interp,
    )
    refreshed_interp_verts_distance_to_wing = np.linalg.norm(
        updated_interpolation_vertices - refreshed_projected_interp_verts_wing,
        axis=1,
    )

    _, refreshed_fuse_projection_state = fuse_projection_model.project(
        initial_fuse_coeffs,
        updated_interpolation_vertices,
    )
    refreshed_para_coords_fuse_interp = np.column_stack(
        [
            refreshed_fuse_projection_state["patch_id"],
            refreshed_fuse_projection_state["uv"],
        ]
    )
    refreshed_projected_interp_verts_fuse = fuse_eval_model.evaluate(
        initial_fuse_coeffs,
        refreshed_para_coords_fuse_interp,
    )
    refreshed_interp_verts_distance_to_fuse = np.linalg.norm(
        updated_interpolation_vertices - refreshed_projected_interp_verts_fuse,
        axis=1,
    )
    refreshed_interp_verts_distance_to_oml = np.minimum(
        refreshed_interp_verts_distance_to_wing,
        refreshed_interp_verts_distance_to_fuse,
    )

    original_area_vectors = np.cross(
        vertices[triangles[:, 1]] - vertices[triangles[:, 0]],
        vertices[triangles[:, 2]] - vertices[triangles[:, 0]],
    )
    original_triangle_areas = _triangle_areas(vertices, triangles)
    updated_triangle_areas = _triangle_areas(updated_vertices, triangles)
    triangle_area_ratio = updated_triangle_areas / np.maximum(original_triangle_areas, 1e-12)
    updated_area_vectors = np.cross(
        updated_vertices[triangles[:, 1]] - updated_vertices[triangles[:, 0]],
        updated_vertices[triangles[:, 2]] - updated_vertices[triangles[:, 0]],
    )
    triangle_orientation_dot = np.einsum("ij,ij->i", original_area_vectors, updated_area_vectors)
    flipped_triangle_indices = np.where(triangle_orientation_dot < 0.0)[0]

    final_surface_distance, _ = wing_fuse_projection_model.project(
        moved_total_coeffs,
        updated_vertices,
    )

    wing_anchor_displacement = np.empty((0,), dtype=float)
    if wing_anchor_displacements.shape[0] > 0:
        wing_anchor_displacement = np.linalg.norm(wing_anchor_displacements, axis=1)

    print("")
    print("Surface mesh movement diagnostics")
    print("    Random seed:", random_seed)
    print("    Use anchor vertices:", use_anchor_vertices)
    print("    Interpolation vertices:", interpolation_vertices.shape[0])
    print("    Variable vertices:", variable_indices.shape[0])
    print("    Wing anchor training points:", wing_anchor_training_points.shape[0])
    print("    Fuse anchor training points:", fuse_anchor_training_points.shape[0])
    print(
        "    Symmetry-plane anchor points:",
        symmetry_plane_anchor_training_points.shape[0],
    )
    print(
        "    Symmetry-plane local constraint points:",
        symmetry_plane_local_constraint_points.shape[0],
    )
    print("    Transition training points:", transition_vertices.shape[0])
    print("    Local training points:", local_training_points.shape[0])
    print("    Alpha:", f"{alpha:.6e}")
    print("    Sigma phi:", f"{sigma_phi:.6e}")
    print("    Participation mode:", participation_mode)
    print("    Sharpening p:", f"{participation_sharpening:.6e}")
    print("    Wing translation:", f"{translation_amount:.6e}")
    print("    Wing-root rotation (deg):", f"{wing_root_rotation_degrees:.6e}")
    print(
        "    Wing-root quarter-chord:",
        np.array2string(translated_root_quarter_chord, precision=6, suppress_small=False),
    )
    print("    Symmetry-plane anchor mode:", symmetry_plane_anchor_mode)
    print("    Symmetry-plane y:", f"{symmetry_plane_y:.6e}")
    print("    Symmetry-plane tolerance:", f"{symmetry_plane_tolerance:.6e}")
    print("    RBF fit mode:", rbf_fit_mode)
    print("    RBF kernel:", rbf_kernel)
    print("    RBF kernel scale:", f"{rbf_kernel_scale:.6e}")
    print("    RBF regularization:", f"{rbf_regularization:.6e}")
    print("    RBF polynomial regularization:", f"{rbf_polynomial_regularization:.6e}")
    print("    Seam master mode:", seam_master_mode)
    if seam_master_mode == "fixed":
        print("    Seam master component:", int(seam_master_component))
    print("    Seam support sigma:", f"{seam_support_sigma:.6e}")
    print("    Global anchor sample weight:", f"{global_anchor_sample_weight:.6e}")
    print(
        "    Global symmetry-plane anchor sample weight:",
        f"{global_symmetry_plane_anchor_sample_weight:.6e}",
    )
    print(
        "    Local symmetry-plane sample weight:",
        f"{local_symmetry_plane_sample_weight:.6e}",
    )
    print("    Global transition sample weight:", f"{global_transition_sample_weight:.6e}")
    print("    Global interpolation sample weight:", f"{global_interpolation_sample_weight:.6e}")
    print("    Local seam sample weight:", f"{local_seam_sample_weight:.6e}")
    print("    Transition bandwidth:", f"{transition_bandwidth:.6e}")
    print("    Step 9 projection mode:", step9_projection_mode)
    print("    Sharp-feature protection:", sharp_feature_protection)
    print("    Sharp-feature angle (deg):", f"{sharp_feature_angle_degrees:.6e}")
    print(
        "    Step 9 pre-projection Laplacian step:",
        f"{step9_pre_projection_laplacian_step:.6e}",
    )
    if step9_smooth_union_rho_schedule.size > 0:
        print(
            "    Step 9 smooth-union rho schedule:",
            np.array2string(step9_smooth_union_rho_schedule, precision=6, suppress_small=False),
        )
    print(
        "    Step 9 projection iterations:",
        _format_stats(projected_variable_projection_iterations),
    )
    print(
        "    Step 9 converged points:",
        f"{int(np.sum(projected_variable_projection_converged))} / "
        f"{projected_variable_projection_converged.size}",
    )
    print(
        "    Global interpolation displacement:",
        _format_stats(np.linalg.norm(interpolation_displacements, axis=1)),
    )
    print(
        "    Anchor baseline displacement:",
        _format_stats(np.linalg.norm(anchor_baseline_variable_displacements, axis=1)),
    )
    if transition_vertices.shape[0] > 0:
        print("    Transition beta:", _format_stats(transition_beta))
        print(
            "    Transition target displacement:",
            _format_stats(np.linalg.norm(transition_target_displacements, axis=1)),
        )
        print(
            "    Transition predicted displacement:",
            _format_stats(np.linalg.norm(predicted_transition_displacements, axis=1)),
        )
    print(
        "    Global interpolation prediction:",
        _format_stats(np.linalg.norm(predicted_global_interp_displacements, axis=1)),
    )
    if predicted_global_symmetry_plane_displacements.shape[0] > 0:
        print(
            "    Global symmetry-plane displacement:",
            _format_stats(np.linalg.norm(predicted_global_symmetry_plane_displacements, axis=1)),
        )
    print(
        "    Local activation:",
        _format_stats(local_activation),
    )
    print(
        "    Seam support:",
        _format_stats(seam_support_interp),
    )
    print(
        "    Activated local residual:",
        _format_stats(np.linalg.norm(activated_local_residuals, axis=1)),
    )
    print(
        "    Local residual target:",
        _format_stats(np.linalg.norm(interpolation_local_residuals, axis=1)),
    )
    if local_training_raw_residuals.shape[0] > 0:
        print(
            "    Raw local training target:",
            _format_stats(np.linalg.norm(local_training_raw_residuals, axis=1)),
        )
        print(
            "    Local training sample weight:",
            _format_stats(local_training_sample_weights),
        )
    print(
        "    Predicted free-node displacement:",
        _format_stats(np.linalg.norm(predicted_variable_displacements, axis=1)),
    )
    print(
        "    Step 9 protected sharp-feature vertices:",
        f"{int(np.sum(step9_sharp_feature_variable_mask))} / {step9_sharp_feature_variable_mask.size}",
    )
    print(
        "    Step 9 Laplacian smoothing correction:",
        _format_stats(np.linalg.norm(pre_projection_smoothing_correction, axis=1)),
    )
    print(
        "    Projection correction:",
        _format_stats(np.linalg.norm(projection_correction, axis=1)),
    )
    if step9_projection_mode == "combined_function_set":
        print(
            "    Step 9 input distance to combined OML:",
            _format_stats(step9_projection_residual_before),
        )
    else:
        print(
            "    Step 9 smooth-union residual before projection:",
            _format_stats(step9_projection_residual_before),
        )
        print(
            "    Step 9 smooth-union residual after projection:",
            _format_stats(step9_projection_residual_after),
        )
    print("    Final OML distance:", _format_stats(final_surface_distance))
    print("    Updated triangle area:", _format_stats(updated_triangle_areas))
    print("    Triangle area ratio:", _format_stats(triangle_area_ratio))
    print("    Flipped triangles:", int(flipped_triangle_indices.size))
    if wing_anchor_displacement.size > 0:
        print("    Wing-anchor displacement:", _format_stats(wing_anchor_displacement))
    if symmetry_plane_step8_displacements.shape[0] > 0:
        print(
            "    Step 8 symmetry-plane displacement:",
            _format_stats(np.linalg.norm(symmetry_plane_step8_displacements, axis=1)),
        )
    if np.any(seam_interpolation_mask):
        print(
            "    Intersection wing participation:",
            _format_stats(participation_weights[seam_interpolation_mask, 0]),
        )
        print(
            "    Intersection Step-3 target x-displacement:",
            _format_stats(interpolation_displacements[seam_interpolation_mask, 0]),
        )
        print(
            "    Intersection seam support:",
            _format_stats(seam_support_interp[seam_interpolation_mask]),
        )
        print(
            "    Intersection Step-6 target x-displacement:",
            _format_stats(interpolation_target_displacements[seam_interpolation_mask, 0]),
        )
        print(
            "    Intersection global-prediction x-displacement:",
            _format_stats(predicted_global_interp_displacements[seam_interpolation_mask, 0]),
        )
        print(
            "    Intersection local residual x-target:",
            _format_stats(interpolation_local_residuals[seam_interpolation_mask, 0]),
        )
        print(
            "    Intersection local activation:",
            _format_stats(local_activation[seam_interpolation_mask]),
        )
        print(
            "    Step 8 intersection x-displacement:",
            _format_stats(predicted_variable_displacements[intersection_indices, 0]),
        )
    print(
        "    Refreshed interpolation distance to OML:",
        _format_stats(refreshed_interp_verts_distance_to_oml),
    )
    
    # Visualize the updated mesh and geometry
    if plot:
        initial_mesh_plot = pv.PolyData(vertices, _make_faces(mesh))
        updated_mesh_plot = pv.PolyData(updated_vertices, _make_faces(mesh))
        updated_interpolation_plot_vertices = updated_vertices[interpolation_indices]
        protected_feature_vertices = updated_vertices[step9_sharp_feature_vertex_mask]
        updated_rbf_training_vertices_list = [updated_interpolation_plot_vertices]
        if selected_wing_anchor_local.size > 0:
            updated_rbf_training_vertices_list.append(
                moved_wing_anchor_vertices[selected_wing_anchor_local]
            )
        if selected_fuse_anchor_local.size > 0:
            updated_rbf_training_vertices_list.append(
                fuse_anchor_vertices[selected_fuse_anchor_local]
            )
        if symmetry_plane_anchor_indices.size > 0:
            updated_rbf_training_vertices_list.append(
                updated_vertices[symmetry_plane_anchor_indices]
            )
        updated_rbf_training_vertices = np.vstack(updated_rbf_training_vertices_list)

        wing_anchor_non_training_vertices = np.empty((0, 3), dtype=float)
        if moved_wing_anchor_vertices.size > 0:
            wing_anchor_non_training_mask = np.ones(
                moved_wing_anchor_vertices.shape[0], dtype=bool
            )
            wing_anchor_non_training_mask[selected_wing_anchor_local] = False
            wing_anchor_non_training_vertices = moved_wing_anchor_vertices[
                wing_anchor_non_training_mask
            ]

        fuse_anchor_non_training_vertices = np.empty((0, 3), dtype=float)
        if fuse_anchor_vertices.size > 0:
            fuse_anchor_non_training_mask = np.ones(
                fuse_anchor_vertices.shape[0], dtype=bool
            )
            fuse_anchor_non_training_mask[selected_fuse_anchor_local] = False
            fuse_anchor_non_training_vertices = fuse_anchor_vertices[
                fuse_anchor_non_training_mask
            ]

        updated_anchor_plot_vertices_list = []
        if wing_anchor_non_training_vertices.size > 0:
            updated_anchor_plot_vertices_list.append(wing_anchor_non_training_vertices)
        if fuse_anchor_non_training_vertices.size > 0:
            updated_anchor_plot_vertices_list.append(fuse_anchor_non_training_vertices)
        if updated_anchor_plot_vertices_list:
            updated_anchor_plot_vertices = np.vstack(updated_anchor_plot_vertices_list)
        else:
            updated_anchor_plot_vertices = np.empty((0, 3), dtype=float)
        plotter = pv.Plotter()
        # plotter.add_mesh(initial_mesh_plot, color="lightgray", opacity=0.35, show_edges=False, label="Initial mesh")
        plotter.add_mesh(updated_mesh_plot, opacity=1., show_edges=True, label="Updated mesh")
        plotter.add_mesh(
            pv.PolyData(updated_rbf_training_vertices),
            color="orange",
            point_size=8,
            render_points_as_spheres=True,
            label="Updated interpolation / RBF-training points",
        )
        if protected_feature_vertices.size > 0:
            plotter.add_mesh(
                pv.PolyData(protected_feature_vertices),
                color="red",
                point_size=8,
                render_points_as_spheres=True,
                label="Sharp-feature-protected vertices",
            )
        if updated_anchor_plot_vertices.size > 0:
            plotter.add_mesh(
                pv.PolyData(updated_anchor_plot_vertices),
                color="royalblue",
                point_size=6,
                render_points_as_spheres=True,
                label="Wing / fuselage anchors",
            )
        plotter.add_legend()
        plotter.show()
