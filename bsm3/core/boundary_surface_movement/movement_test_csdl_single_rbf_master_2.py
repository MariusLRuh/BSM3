from __future__ import annotations

import argparse
from pathlib import Path

import meshio
import numpy as np

import csdl_alpha as csdl
import lsdo_function_spaces as lfs

import bsm3
from bsm3.core.boundary_surface_movement.movement_test_csdl_static_seam import (
    _build_uniform_laplacian_matrix,
    _build_vertex_neighbors,
    _compute_graph_distances,
    _expand_vector_to_columns,
    _format_stats,
    _gaussian_support,
    _interaction_indicator_two_components,
    _make_faces,
    _make_ks_rho_schedule,
    _normalize_weights,
    _plot_surface_debug,
    _rotate_points_about_y_axis_csdl,
    _rotate_points_about_y_axis_numpy,
    _select_farthest_point_indices_symmetric,
    _sharp_feature_vertex_mask,
    _smooth_minimum_signed_distance_numpy,
    _stack_coefficients_csdl,
    _stack_coefficients_numpy,
    _triangulate_surface_cells,
)


def _pairwise_distance_matrix_csdl(
    points_a: csdl.Variable,
    points_b: csdl.Variable,
) -> csdl.Variable:
    points_a_squared = csdl.sum(points_a**2, axes=(1,))
    points_b_squared = csdl.sum(points_b**2, axes=(1,))
    points_a_squared_matrix = csdl.matmat(
        csdl.reshape(points_a_squared, (-1, 1)),
        np.ones((1, points_b.shape[0]), dtype=float),
    )
    points_b_squared_matrix = csdl.matmat(
        np.ones((points_a.shape[0], 1), dtype=float),
        csdl.reshape(points_b_squared, (1, -1)),
    )
    pairwise_dot_products = csdl.matmat(points_a, csdl.transpose(points_b))
    pairwise_distance_squared = (
        points_a_squared_matrix + points_b_squared_matrix - 2.0 * pairwise_dot_products
    )
    pairwise_distance_squared = csdl.maximum(
        pairwise_distance_squared,
        np.zeros((points_a.shape[0], points_b.shape[0]), dtype=float),
        rho=200.0,
    )
    return csdl.sqrt(pairwise_distance_squared + 1e-14)


def _evaluate_rbf_kernel_csdl(
    distances: csdl.Variable,
    *,
    kernel: str,
    kernel_scale: float,
) -> csdl.Variable:
    scale_safe = max(float(kernel_scale), 1e-12)
    scaled_distances = distances / scale_safe

    if kernel == "cubic":
        return distances**3
    if kernel == "gaussian":
        return csdl.exp(-(scaled_distances**2))
    if kernel == "multiquadric":
        return csdl.sqrt(1.0 + scaled_distances**2)
    raise ValueError(f"Unsupported RBF kernel: {kernel}")


def _build_rbf_polynomial_terms_csdl(points: csdl.Variable) -> csdl.Variable:
    return csdl.concatenate(
        (np.ones((points.shape[0], 1), dtype=float), points),
        axis=1,
    )


def _solve_multi_rhs_csdl(system_matrix: csdl.Variable, rhs_matrix: csdl.Variable) -> csdl.Variable:
    solution_columns = []
    for column_index in range(rhs_matrix.shape[1]):
        solution_column = csdl.solve_linear(
            system_matrix,
            rhs_matrix[csdl.slice[:, column_index : column_index + 1]],
        )
        solution_columns.append(solution_column)
    if len(solution_columns) == 1:
        return solution_columns[0]
    return csdl.concatenate(tuple(solution_columns), axis=1)


def _fit_vector_rbf_csdl(
    training_points: csdl.Variable,
    training_displacements: csdl.Variable,
    *,
    fit_mode: str,
    kernel: str,
    kernel_scale: float,
    regularization: float,
    polynomial_regularization: float = 0.0,
    sample_weights: np.ndarray | None = None,
) -> tuple[csdl.Variable, csdl.Variable]:
    num_points = training_points.shape[0]
    kernel_matrix = _evaluate_rbf_kernel_csdl(
        _pairwise_distance_matrix_csdl(training_points, training_points),
        kernel=kernel,
        kernel_scale=kernel_scale,
    )
    polynomial_terms = _build_rbf_polynomial_terms_csdl(training_points)

    if fit_mode == "exact_interpolation":
        regularized_kernel_matrix = kernel_matrix + regularization * np.eye(num_points, dtype=float)
        top_block = csdl.concatenate((regularized_kernel_matrix, polynomial_terms), axis=1)
        bottom_block = csdl.concatenate(
            (csdl.transpose(polynomial_terms), np.zeros((4, 4), dtype=float)),
            axis=1,
        )
        system_matrix = csdl.concatenate((top_block, bottom_block), axis=0)
        rhs_matrix = csdl.concatenate(
            (training_displacements, np.zeros((4, training_displacements.shape[1]), dtype=float)),
            axis=0,
        )
        solution = _solve_multi_rhs_csdl(system_matrix, rhs_matrix)
        return solution[csdl.slice[:num_points, :]], solution[csdl.slice[num_points:, :]]

    if fit_mode == "weighted_least_squares":
        if sample_weights is None:
            sample_weights = np.ones((num_points,), dtype=float)
        else:
            sample_weights = np.asarray(sample_weights, dtype=float).reshape((num_points,))

        sqrt_sample_weights = np.sqrt(np.maximum(sample_weights, 0.0)).reshape((num_points, 1))
        weighted_kernel_matrix = sqrt_sample_weights * kernel_matrix
        weighted_polynomial_terms = sqrt_sample_weights * polynomial_terms
        weighted_targets = sqrt_sample_weights * training_displacements

        design_matrix = csdl.concatenate(
            (weighted_kernel_matrix, weighted_polynomial_terms),
            axis=1,
        )
        rhs_matrix = weighted_targets

        if regularization > 0.0:
            regularization_rows = np.hstack(
                [
                    np.sqrt(regularization) * np.eye(num_points, dtype=float),
                    np.zeros((num_points, 4), dtype=float),
                ]
            )
            design_matrix = csdl.concatenate((design_matrix, regularization_rows), axis=0)
            rhs_matrix = csdl.concatenate(
                (rhs_matrix, np.zeros((num_points, training_displacements.shape[1]), dtype=float)),
                axis=0,
            )

        if polynomial_regularization > 0.0:
            polynomial_rows = np.hstack(
                [
                    np.zeros((4, num_points), dtype=float),
                    np.sqrt(polynomial_regularization) * np.eye(4, dtype=float),
                ]
            )
            design_matrix = csdl.concatenate((design_matrix, polynomial_rows), axis=0)
            rhs_matrix = csdl.concatenate(
                (rhs_matrix, np.zeros((4, training_displacements.shape[1]), dtype=float)),
                axis=0,
            )

        normal_matrix = csdl.matmat(csdl.transpose(design_matrix), design_matrix)
        normal_rhs = csdl.matmat(csdl.transpose(design_matrix), rhs_matrix)
        solution = _solve_multi_rhs_csdl(normal_matrix, normal_rhs)
        return solution[csdl.slice[:num_points, :]], solution[csdl.slice[num_points:, :]]

    raise ValueError(f"Unsupported RBF fit mode: {fit_mode}")


def _evaluate_vector_rbf_csdl(
    query_points: csdl.Variable,
    training_points: csdl.Variable,
    weights: csdl.Variable,
    polynomial_coefficients: csdl.Variable,
    *,
    kernel: str,
    kernel_scale: float,
) -> csdl.Variable:
    kernel_values = _evaluate_rbf_kernel_csdl(
        _pairwise_distance_matrix_csdl(query_points, training_points),
        kernel=kernel,
        kernel_scale=kernel_scale,
    )
    polynomial_terms = _build_rbf_polynomial_terms_csdl(query_points)
    return csdl.matmat(kernel_values, weights) + csdl.matmat(
        polynomial_terms,
        polynomial_coefficients,
    )


def _signed_distance_gradient_from_ad_csdl(
    signed_distance: csdl.Variable,
    query_points: csdl.Variable,
) -> csdl.Variable:
    gradient_flat = csdl.derivative(csdl.sum(signed_distance), query_points)
    return csdl.reshape(gradient_flat, query_points.shape)


def _smooth_minimum_signed_distance_three_components_csdl(
    component_sdf_a: csdl.Variable,
    component_sdf_b: csdl.Variable,
    component_sdf_c: csdl.Variable,
    *,
    ks_rho: float,
) -> tuple[csdl.Variable, csdl.Variable, csdl.Variable, csdl.Variable]:
    component_sdf_a = csdl.reshape(component_sdf_a, (-1, 1))
    component_sdf_b = csdl.reshape(component_sdf_b, (-1, 1))
    component_sdf_c = csdl.reshape(component_sdf_c, (-1, 1))

    reference_ab = csdl.minimum(component_sdf_a, component_sdf_b, rho=ks_rho)
    reference = csdl.minimum(reference_ab, component_sdf_c, rho=ks_rho)
    shifted_a = component_sdf_a - reference
    shifted_b = component_sdf_b - reference
    shifted_c = component_sdf_c - reference
    exp_a = csdl.exp(-ks_rho * shifted_a)
    exp_b = csdl.exp(-ks_rho * shifted_b)
    exp_c = csdl.exp(-ks_rho * shifted_c)
    normalization = exp_a + exp_b + exp_c
    union_sdf = reference - csdl.log(normalization) / ks_rho
    return (
        csdl.reshape(union_sdf, (-1,)),
        exp_a / normalization,
        exp_b / normalization,
        exp_c / normalization,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mesh",
        default="wing_fuse_test_w_htail_quad_dominant_symmetric.msh",
        choices=(
            "wing_fuse_test_w_htail.msh",
            "wing_fuse_test_quad_dominant_symmetric.msh",
            "wing_fuse_test.msh",
            "wing_fuse_test_w_htail_quad_dominant_symmetric.msh",
        ),
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
        help="Display the pre-projection mesh predicted by the single RBF field.",
    )
    args = parser.parse_args()

    recorder = csdl.Recorder(inline=True)
    recorder.start()

    plot = False # args.plot
    plot_step8_prediction = False #args.plot_step8_prediction
    mesh_filename = args.mesh

    alpha = 1.0
    sigma_phi = 0.1
    master_component_name = "wing+horizontal_tail"
    rbf_fit_mode = "exact_interpolation"
    rbf_kernel = "cubic"
    rbf_kernel_scale_factor = 0.01
    rbf_regularization_factor = 1e-6
    rbf_polynomial_regularization_factor = 1e-15
    global_interpolation_sample_weight = 1.0
    seam_training_sample_weight = 1.0
    aft_fuse_symmetry_anchor_training_sample_weight = 1.0
    num_additional_interp_vertices = 1500

    intersection_tolerance = 1e-4
    wing_surface_projection_tolerance = 1e-4
    aft_fuse_symmetry_anchors = True
    aft_fuse_symmetry_anchor_x_fraction = 0.05
    aft_fuse_symmetry_anchor_y_tolerance = 1e-10
    aft_fuse_symmetry_anchor_hard_enforcement = True
    seam_support_sigma_factor = 0.15
    setup_seam_support_cutoff = 0.05
    seam_graph_radius_factor = 0.08
    translation_envelope_mac = 2.0
    rotation_envelope_degrees = 8.0

    wing_translation_amount = 0.
    htail_translation_amount = 0.
    wing_root_rotation_degrees = csdl.Variable(name="wing_root_rotation_degrees", value=0.0)
    wing_root_rotation_degrees.set_as_design_variable(lower=-7, upper=7, scaler=1/6)
    htail_root_rotation_degrees = csdl.Variable(name="htail_root_rotation_degrees", value=0.0)
    htail_root_rotation_degrees.set_as_design_variable(lower=-7, upper=7, scaler=1/6)
    step9_projection_mode = "smooth_union_ks"
    step9_smooth_union_ks_rho_start = 25.
    step9_smooth_union_ks_rho_end = 25.
    step9_smooth_union_num_iterations = 3 # 4

    wing_feature_protection = True
    htail_feature_protection = True
    sharp_feature_angle_degrees = 110.0
    sharp_feature_include_boundary = True
    step9_pre_projection_laplacian_step = 0.25

    
    wing_fuse_htail = lfs.import_file_patched(
        Path(__file__).with_name("wing_fuse_test_w_htail.stp"),
        parallelize=False,
    )

    wing_keys = np.arange(0, 12)
    fuse_keys = np.arange(12, 20)
    htail_keys = np.arange(20, len(wing_fuse_htail.functions))
    wing_function_set = lfs.FunctionSet(functions={key: wing_fuse_htail.functions[key] for key in wing_keys})
    fuse_function_set = lfs.FunctionSet(functions={key: wing_fuse_htail.functions[key] for key in fuse_keys})
    htail_function_set = lfs.FunctionSet(functions={key: wing_fuse_htail.functions[key] for key in htail_keys})

    wing_coefficients_csdl = _stack_coefficients_csdl(wing_function_set)
    fuse_coefficients_csdl = _stack_coefficients_csdl(fuse_function_set)
    htail_coefficients_csdl = _stack_coefficients_csdl(htail_function_set)
    initial_wing_coefficients = _stack_coefficients_numpy(wing_function_set)
    initial_fuse_coefficients = _stack_coefficients_numpy(fuse_function_set)
    initial_htail_coefficients = _stack_coefficients_numpy(htail_function_set)

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
    htail_projection_model = bsm3.FunctionSetProjectionModel(
        htail_function_set,
        warm_start_nu=40,
        warm_start_nv=40,
        edge_map_num_samples=25,
    )
    combined_projection_model = bsm3.FunctionSetProjectionModel(
        wing_fuse_htail,
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
    htail_sdf_model = bsm3.FunctionSetProjectionModel(
        htail_function_set,
        warm_start_nu=40,
        warm_start_nv=40,
        edge_map_num_samples=25,
        output_mode="distance",
        sdf=True,
    )
    wing_evaluation_model = bsm3.FunctionSetEvaluationModel(wing_function_set)
    htail_evaluation_model = bsm3.FunctionSetEvaluationModel(htail_function_set)

    wing_projection_distances, wing_projection_state = wing_projection_model.project(
        initial_wing_coefficients,
        vertices,
    )
    fuse_projection_distances, _ = fuse_projection_model.project(
        initial_fuse_coefficients,
        vertices,
    )
    htail_projection_distances, htail_projection_state = htail_projection_model.project(
        initial_htail_coefficients,
        vertices,
    )
    initial_component_distances = np.column_stack(
        [
            np.abs(wing_projection_distances),
            np.abs(fuse_projection_distances),
            np.abs(htail_projection_distances),
        ]
    )
    initial_component_ownership = np.argmin(initial_component_distances, axis=1)
    fuse_owned_vertex_mask = initial_component_ownership == 1

    wing_fuse_seam_seed_indices = np.where(
        (np.abs(wing_projection_distances) <= intersection_tolerance)
        & (np.abs(fuse_projection_distances) <= intersection_tolerance)
    )[0]
    if wing_fuse_seam_seed_indices.size == 0:
        raise ValueError("No exact seam seed vertices were identified from the initial wing/fuselage intersection.")

    htail_fuse_seam_seed_indices = np.where(
        (np.abs(htail_projection_distances) <= intersection_tolerance)
        & (np.abs(fuse_projection_distances) <= intersection_tolerance)
    )[0]
    if htail_fuse_seam_seed_indices.size == 0:
        raise ValueError(
            "No exact seam seed vertices were identified from the initial horizontal-tail/fuselage intersection."
        )

    seam_seed_indices = np.unique(
        np.concatenate([wing_fuse_seam_seed_indices, htail_fuse_seam_seed_indices])
    )

    aft_fuse_symmetry_anchor_indices = np.empty((0,), dtype=np.int64)
    if aft_fuse_symmetry_anchors:
        x_extent = max(float(np.max(vertices[:, 0]) - np.min(vertices[:, 0])), 1e-12)
        aft_fuse_symmetry_anchor_x_min = (
            float(np.max(vertices[:, 0])) - aft_fuse_symmetry_anchor_x_fraction * x_extent
        )
        aft_fuse_symmetry_anchor_mask = (
            fuse_owned_vertex_mask
            & (vertices[:, 0] >= aft_fuse_symmetry_anchor_x_min)
            & (np.abs(vertices[:, 1]) <= aft_fuse_symmetry_anchor_y_tolerance)
        )
        aft_fuse_symmetry_anchor_mask[seam_seed_indices] = False
        aft_fuse_symmetry_anchor_indices = np.where(aft_fuse_symmetry_anchor_mask)[0]

    interpolation_indices = np.unique(
        np.concatenate([seam_seed_indices, aft_fuse_symmetry_anchor_indices])
    )
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
    wing_fuse_seam_interpolation_mask = np.isin(
        interpolation_indices,
        wing_fuse_seam_seed_indices,
    )
    htail_fuse_seam_interpolation_mask = np.isin(
        interpolation_indices,
        htail_fuse_seam_seed_indices,
    )
    aft_fuse_symmetry_anchor_interpolation_mask = np.isin(
        interpolation_indices,
        aft_fuse_symmetry_anchor_indices,
    )
    wing_fuse_seam_interpolation_local_indices = np.where(wing_fuse_seam_interpolation_mask)[0]
    htail_fuse_seam_interpolation_local_indices = np.where(htail_fuse_seam_interpolation_mask)[0]
    aft_fuse_symmetry_anchor_local_indices = np.where(
        aft_fuse_symmetry_anchor_interpolation_mask
    )[0]

    seam_graph_distances = _compute_graph_distances(vertices, vertex_neighbors, seam_seed_indices)

    interpolation_wing_distances, interpolation_wing_state = wing_projection_model.project(
        initial_wing_coefficients,
        interpolation_vertices,
    )
    interpolation_fuse_distances, _ = fuse_projection_model.project(
        initial_fuse_coefficients,
        interpolation_vertices,
    )
    interpolation_htail_distances, interpolation_htail_state = htail_projection_model.project(
        initial_htail_coefficients,
        interpolation_vertices,
    )
    interpolation_wing_parametric_coordinates = np.column_stack(
        [
            interpolation_wing_state["patch_id"],
            interpolation_wing_state["uv"],
        ]
    )
    interpolation_htail_parametric_coordinates = np.column_stack(
        [
            interpolation_htail_state["patch_id"],
            interpolation_htail_state["uv"],
        ]
    )
    interpolation_initial_wing_points = wing_evaluation_model.evaluate(
        initial_wing_coefficients,
        interpolation_wing_parametric_coordinates,
    )
    interpolation_initial_htail_points = htail_evaluation_model.evaluate(
        initial_htail_coefficients,
        interpolation_htail_parametric_coordinates,
    )
    interpolation_component_weights = _normalize_weights(
        np.exp(
            -alpha
            * np.column_stack(
                [
                    interpolation_wing_distances,
                    interpolation_fuse_distances,
                    interpolation_htail_distances,
                ]
            )
        )
    )
    interpolation_wing_weights = interpolation_component_weights[:, 0]
    interpolation_htail_weights = interpolation_component_weights[:, 2]

    closest_initial_component = np.argmin(
        np.column_stack(
            [
                interpolation_wing_distances,
                interpolation_fuse_distances,
                interpolation_htail_distances,
            ]
        ),
        axis=1,
    )
    wing_owned_interpolation_mask = closest_initial_component == 0
    htail_owned_interpolation_mask = closest_initial_component == 2
    wing_owned_interpolation_mask[wing_fuse_seam_interpolation_mask] = True
    htail_owned_interpolation_mask[htail_fuse_seam_interpolation_mask] = True
    wing_owned_interpolation_local_indices = np.where(wing_owned_interpolation_mask)[0]
    htail_owned_interpolation_local_indices = np.where(htail_owned_interpolation_mask)[0]

    seam_seed_wing_parametric_coordinates = np.column_stack(
        [
            wing_projection_state["patch_id"][wing_fuse_seam_seed_indices],
            wing_projection_state["uv"][wing_fuse_seam_seed_indices],
        ]
    )
    seam_seed_wing_points = wing_evaluation_model.evaluate(
        initial_wing_coefficients,
        seam_seed_wing_parametric_coordinates,
    )
    seam_seed_leading_local = int(np.argmin(seam_seed_wing_points[:, 0]))
    seam_seed_trailing_local = int(np.argmax(seam_seed_wing_points[:, 0]))
    root_leading_point = seam_seed_wing_points[seam_seed_leading_local : seam_seed_leading_local + 1]
    root_trailing_point = seam_seed_wing_points[
        seam_seed_trailing_local : seam_seed_trailing_local + 1
    ]
    root_chord_proxy = max(
        float(root_trailing_point[0, 0] - root_leading_point[0, 0]),
        1e-12,
    )
    root_quarter_chord = root_leading_point + 0.25 * (root_trailing_point - root_leading_point)

    seam_seed_htail_parametric_coordinates = np.column_stack(
        [
            htail_projection_state["patch_id"][htail_fuse_seam_seed_indices],
            htail_projection_state["uv"][htail_fuse_seam_seed_indices],
        ]
    )
    seam_seed_htail_points = htail_evaluation_model.evaluate(
        initial_htail_coefficients,
        seam_seed_htail_parametric_coordinates,
    )
    htail_root_leading_local = int(np.argmin(seam_seed_htail_points[:, 0]))
    htail_root_trailing_local = int(np.argmax(seam_seed_htail_points[:, 0]))
    htail_root_leading_point = seam_seed_htail_points[
        htail_root_leading_local : htail_root_leading_local + 1
    ]
    htail_root_trailing_point = seam_seed_htail_points[
        htail_root_trailing_local : htail_root_trailing_local + 1
    ]
    htail_root_chord_proxy = max(
        float(htail_root_trailing_point[0, 0] - htail_root_leading_point[0, 0]),
        1e-12,
    )
    htail_root_quarter_chord = htail_root_leading_point + 0.25 * (
        htail_root_trailing_point - htail_root_leading_point
    )

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

    def move_htail_coefficients_numpy(translation_x: float, rotation_degrees: float) -> np.ndarray:
        translated_coefficients = initial_htail_coefficients + np.array(
            [translation_x, 0.0, 0.0],
            dtype=float,
        )[None, :]
        translated_root_quarter_chord = htail_root_quarter_chord + np.array(
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
    htail_envelope_translation_values = np.array(
        [
            -translation_envelope_mac * htail_root_chord_proxy,
            0.0,
            translation_envelope_mac * htail_root_chord_proxy,
        ],
        dtype=float,
    )
    envelope_rotation_values = np.array(
        [-rotation_envelope_degrees, rotation_envelope_degrees],
        dtype=float,
    )

    seam_support_envelope = np.zeros(num_vertices, dtype=float)
    swept_states = [(0.0, 0.0, 0.0, 0.0)]
    # swept_states.extend(
    #     [
    #         (
    #             float(wing_translation_x),
    #             float(wing_rotation_degrees),
    #             float(htail_translation_x),
    #             float(htail_rotation_degrees),
    #         )
    #         for wing_translation_x in (envelope_translation_values[0], envelope_translation_values[2])
    #         for wing_rotation_degrees in envelope_rotation_values
    #         for htail_translation_x in (
    #             htail_envelope_translation_values[0],
    #             htail_envelope_translation_values[2],
    #         )
    #         for htail_rotation_degrees in envelope_rotation_values
    #     ]
    # )
    for (
        wing_translation_x,
        wing_rotation_degrees,
        htail_translation_x,
        htail_rotation_degrees,
    ) in swept_states:
        moved_wing_coefficients_setup = move_wing_coefficients_numpy(
            wing_translation_x,
            wing_rotation_degrees,
        )
        moved_htail_coefficients_setup = move_htail_coefficients_numpy(
            htail_translation_x,
            htail_rotation_degrees,
        )
        wing_sdf_values, _ = wing_sdf_model.project(moved_wing_coefficients_setup, vertices)
        fuse_sdf_values, _ = fuse_sdf_model.project(initial_fuse_coefficients, vertices)
        htail_sdf_values, _ = htail_sdf_model.project(moved_htail_coefficients_setup, vertices)
        setup_wing_fuse_indicator = _interaction_indicator_two_components(
            np.column_stack([wing_sdf_values, fuse_sdf_values])
        )
        setup_htail_fuse_indicator = _interaction_indicator_two_components(
            np.column_stack([htail_sdf_values, fuse_sdf_values])
        )
        seam_support_envelope = np.maximum(
            seam_support_envelope,
            _gaussian_support(setup_wing_fuse_indicator, seam_support_sigma),
        )
        seam_support_envelope = np.maximum(
            seam_support_envelope,
            _gaussian_support(setup_htail_fuse_indicator, seam_support_sigma),
        )

    seam_graph_band_mask = seam_graph_distances <= seam_graph_radius
    seam_envelope_mask = seam_support_envelope >= setup_seam_support_cutoff
    seam_candidate_mask = seam_graph_band_mask & seam_envelope_mask
    seam_candidate_mask[seam_seed_indices] = True
    seam_candidate_indices = np.where(seam_candidate_mask)[0]

    sharp_feature_vertex_mask = _sharp_feature_vertex_mask(
        vertices,
        triangulated_surface_cells,
        feature_angle_degrees=sharp_feature_angle_degrees,
        include_boundary=sharp_feature_include_boundary,
    )
    protected_wing_feature_indices = np.empty((0,), dtype=np.int64)
    protected_wing_feature_parametric_coordinates = np.empty((0, 3), dtype=float)
    if wing_feature_protection:
        protected_wing_feature_mask = (
            sharp_feature_vertex_mask
            & (wing_projection_distances <= wing_surface_projection_tolerance)
            # & ~seam_candidate_mask
        )
        protected_wing_feature_indices = np.where(protected_wing_feature_mask)[0]
        if protected_wing_feature_indices.size > 0:
            protected_wing_feature_parametric_coordinates = np.column_stack(
                [
                    wing_projection_state["patch_id"][protected_wing_feature_indices],
                    wing_projection_state["uv"][protected_wing_feature_indices],
                ]
            )

    protected_htail_feature_indices = np.empty((0,), dtype=np.int64)
    protected_htail_feature_parametric_coordinates = np.empty((0, 3), dtype=float)
    if htail_feature_protection:
        protected_htail_feature_mask = (
            sharp_feature_vertex_mask
            & (htail_projection_distances <= wing_surface_projection_tolerance)
            # & ~seam_candidate_mask
        )
        protected_htail_feature_indices = np.where(protected_htail_feature_mask)[0]
        if protected_htail_feature_indices.size > 0:
            protected_htail_feature_parametric_coordinates = np.column_stack(
                [
                    htail_projection_state["patch_id"][protected_htail_feature_indices],
                    htail_projection_state["uv"][protected_htail_feature_indices],
                ]
            )

    protected_feature_indices = np.unique(
        np.concatenate([protected_wing_feature_indices, protected_htail_feature_indices])
    )
    constrained_stationary_indices = np.unique(
        np.concatenate([protected_feature_indices, aft_fuse_symmetry_anchor_indices])
    )
    unprotected_laplacian_scale = np.ones(num_vertices, dtype=float)
    unprotected_laplacian_scale[constrained_stationary_indices] = 0.0

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

    training_sample_weights = np.full(
        interpolation_vertices.shape[0],
        global_interpolation_sample_weight,
        dtype=float,
    )
    training_sample_weights[seam_interpolation_mask] *= seam_training_sample_weight
    training_sample_weights[
        aft_fuse_symmetry_anchor_interpolation_mask
    ] *= aft_fuse_symmetry_anchor_training_sample_weight

    vertices_csdl = csdl.Variable(name="surface_vertices", value=vertices)
    interpolation_vertices_csdl = csdl.Variable(
        name="interpolation_vertices",
        value=interpolation_vertices,
    )
    root_quarter_chord_csdl = csdl.Variable(name="root_quarter_chord", value=root_quarter_chord)
    htail_root_quarter_chord_csdl = csdl.Variable(
        name="htail_root_quarter_chord",
        value=htail_root_quarter_chord,
    )

    wing_evaluation_interpolation_operation = bsm3.FunctionSetEvaluationOperation(
        model=wing_evaluation_model
    )
    htail_evaluation_interpolation_operation = bsm3.FunctionSetEvaluationOperation(
        model=htail_evaluation_model
    )
    wing_evaluation_feature_operation = bsm3.FunctionSetEvaluationOperation(
        model=wing_evaluation_model
    )
    htail_evaluation_feature_operation = bsm3.FunctionSetEvaluationOperation(
        model=htail_evaluation_model
    )
    interpolation_wing_closest_distance_operation = bsm3.FunctionSetClosestDistanceOperation(
        model=wing_sdf_model
    )
    interpolation_fuse_closest_distance_operation = bsm3.FunctionSetClosestDistanceOperation(
        model=fuse_sdf_model
    )
    interpolation_htail_closest_distance_operation = bsm3.FunctionSetClosestDistanceOperation(
        model=htail_sdf_model
    )

    wing_translation_vector = np.array([wing_translation_amount, 0.0, 0.0], dtype=float).reshape((1, 3))
    htail_translation_vector = np.array([htail_translation_amount, 0.0, 0.0], dtype=float).reshape((1, 3))
    wing_translation_rows = csdl.matmat(
        np.ones((wing_coefficients_csdl.shape[0], 1), dtype=float),
        wing_translation_vector,
    )
    htail_translation_rows = csdl.matmat(
        np.ones((htail_coefficients_csdl.shape[0], 1), dtype=float),
        htail_translation_vector,
    )
    translated_root_quarter_chord = root_quarter_chord_csdl + wing_translation_vector
    translated_htail_root_quarter_chord = htail_root_quarter_chord_csdl + htail_translation_vector
    moved_wing_coefficients = _rotate_points_about_y_axis_csdl(
        wing_coefficients_csdl + wing_translation_rows,
        wing_root_rotation_degrees,
        translated_root_quarter_chord,
    )
    moved_htail_coefficients = _rotate_points_about_y_axis_csdl(
        htail_coefficients_csdl + htail_translation_rows,
        htail_root_rotation_degrees,
        translated_htail_root_quarter_chord,
    )
    moved_total_coefficients = csdl.concatenate(
        (moved_wing_coefficients, fuse_coefficients_csdl, moved_htail_coefficients),
        axis=0,
    )

    moved_interpolation_wing_points = wing_evaluation_interpolation_operation.evaluate(
        moved_wing_coefficients,
        interpolation_wing_parametric_coordinates,
    )
    interpolation_wing_displacements = (
        moved_interpolation_wing_points - interpolation_initial_wing_points
    )
    moved_interpolation_htail_points = htail_evaluation_interpolation_operation.evaluate(
        moved_htail_coefficients,
        interpolation_htail_parametric_coordinates,
    )
    interpolation_htail_displacements = (
        moved_interpolation_htail_points - interpolation_initial_htail_points
    )

    provisional_interpolation_target_displacements = _expand_vector_to_columns(
        interpolation_wing_weights,
        3,
    ) * interpolation_wing_displacements + _expand_vector_to_columns(
        interpolation_htail_weights,
        3,
    ) * interpolation_htail_displacements
    provisional_interpolation_vertices = (
        interpolation_vertices_csdl + provisional_interpolation_target_displacements
    )

    interpolation_sdf_to_wing = interpolation_wing_closest_distance_operation.evaluate(
        moved_wing_coefficients,
        provisional_interpolation_vertices,
    )
    interpolation_sdf_to_fuse = interpolation_fuse_closest_distance_operation.evaluate(
        fuse_coefficients_csdl,
        provisional_interpolation_vertices,
    )
    interpolation_sdf_to_htail = interpolation_htail_closest_distance_operation.evaluate(
        moved_htail_coefficients,
        provisional_interpolation_vertices,
    )
    sigma_phi_safe = max(float(sigma_phi), 1e-12)
    interpolation_participation_wing = csdl.exp(
        -(interpolation_sdf_to_wing**2) / (sigma_phi_safe**2)
    )
    interpolation_participation_fuse = csdl.exp(
        -(interpolation_sdf_to_fuse**2) / (sigma_phi_safe**2)
    )
    interpolation_participation_htail = csdl.exp(
        -(interpolation_sdf_to_htail**2) / (sigma_phi_safe**2)
    )
    interpolation_participation_sum = (
        interpolation_participation_wing
        + interpolation_participation_fuse
        + interpolation_participation_htail
    )
    interpolation_smooth_wing_weight = interpolation_participation_wing / (
        interpolation_participation_sum
    )
    interpolation_smooth_htail_weight = interpolation_participation_htail / (
        interpolation_participation_sum
    )
    interpolation_wing_fuse_interaction_indicator = (
        interpolation_sdf_to_wing**2 + interpolation_sdf_to_fuse**2
    ) ** 0.5
    interpolation_htail_fuse_interaction_indicator = (
        interpolation_sdf_to_htail**2 + interpolation_sdf_to_fuse**2
    ) ** 0.5
    wing_fuse_seam_support_interp = csdl.exp(
        -(
            interpolation_wing_fuse_interaction_indicator / max(seam_support_sigma, 1e-12)
        )
        ** 2
    )
    htail_fuse_seam_support_interp = csdl.exp(
        -(
            interpolation_htail_fuse_interaction_indicator / max(seam_support_sigma, 1e-12)
        )
        ** 2
    )
    if wing_fuse_seam_interpolation_local_indices.size > 0:
        wing_fuse_seam_support_interp = wing_fuse_seam_support_interp.set(
            csdl.slice[wing_fuse_seam_interpolation_local_indices.tolist()],
            1.0,
        )
    if htail_fuse_seam_interpolation_local_indices.size > 0:
        htail_fuse_seam_support_interp = htail_fuse_seam_support_interp.set(
            csdl.slice[htail_fuse_seam_interpolation_local_indices.tolist()],
            1.0,
        )

    soft_interpolation_target_displacements = (
        _expand_vector_to_columns(interpolation_smooth_wing_weight, 3)
        * interpolation_wing_displacements
        + _expand_vector_to_columns(interpolation_smooth_htail_weight, 3)
        * interpolation_htail_displacements
    )
    corrected_interpolation_target_displacements = (
        _expand_vector_to_columns(1.0 - wing_fuse_seam_support_interp, 3)
        * soft_interpolation_target_displacements
        + _expand_vector_to_columns(wing_fuse_seam_support_interp, 3)
        * interpolation_wing_displacements
    )
    corrected_interpolation_target_displacements = (
        _expand_vector_to_columns(1.0 - htail_fuse_seam_support_interp, 3)
        * corrected_interpolation_target_displacements
        + _expand_vector_to_columns(htail_fuse_seam_support_interp, 3)
        * interpolation_htail_displacements
    )
    if wing_owned_interpolation_local_indices.size > 0:
        corrected_interpolation_target_displacements = corrected_interpolation_target_displacements.set(
            csdl.slice[wing_owned_interpolation_local_indices.tolist(), :],
            interpolation_wing_displacements[csdl.slice[wing_owned_interpolation_local_indices.tolist(), :]],
        )
    if htail_owned_interpolation_local_indices.size > 0:
        corrected_interpolation_target_displacements = corrected_interpolation_target_displacements.set(
            csdl.slice[htail_owned_interpolation_local_indices.tolist(), :],
            interpolation_htail_displacements[csdl.slice[htail_owned_interpolation_local_indices.tolist(), :]],
        )
    if aft_fuse_symmetry_anchor_local_indices.size > 0:
        corrected_interpolation_target_displacements = corrected_interpolation_target_displacements.set(
            csdl.slice[aft_fuse_symmetry_anchor_local_indices.tolist(), :],
            np.zeros((aft_fuse_symmetry_anchor_local_indices.size, 3), dtype=float),
        )

    rbf_weights, rbf_polynomial_coefficients = _fit_vector_rbf_csdl(
        interpolation_vertices_csdl,
        corrected_interpolation_target_displacements,
        fit_mode=rbf_fit_mode,
        kernel=rbf_kernel,
        kernel_scale=rbf_kernel_scale,
        regularization=rbf_regularization,
        polynomial_regularization=rbf_polynomial_regularization,
        sample_weights=training_sample_weights,
    )

    predicted_interpolation_displacements = _evaluate_vector_rbf_csdl(
        interpolation_vertices_csdl,
        interpolation_vertices_csdl,
        rbf_weights,
        rbf_polynomial_coefficients,
        kernel=rbf_kernel,
        kernel_scale=rbf_kernel_scale,
    )
    interpolation_target_error = (
        predicted_interpolation_displacements - corrected_interpolation_target_displacements
    )

    predicted_variable_displacements = _evaluate_vector_rbf_csdl(
        vertices_csdl,
        interpolation_vertices_csdl,
        rbf_weights,
        rbf_polynomial_coefficients,
        kernel=rbf_kernel,
        kernel_scale=rbf_kernel_scale,
    )
    predicted_variable_vertices = vertices_csdl + predicted_variable_displacements

    stationary_aft_fuse_symmetry_anchor_vertices = None
    if (
        aft_fuse_symmetry_anchor_hard_enforcement
        and aft_fuse_symmetry_anchor_indices.size > 0
    ):
        stationary_aft_fuse_symmetry_anchor_vertices = vertices[
            aft_fuse_symmetry_anchor_indices
        ]
        predicted_variable_vertices = predicted_variable_vertices.set(
            csdl.slice[aft_fuse_symmetry_anchor_indices.tolist(), :],
            stationary_aft_fuse_symmetry_anchor_vertices,
        )

    moved_protected_wing_feature_vertices = None
    moved_protected_htail_feature_vertices = None
    if protected_wing_feature_indices.size > 0:
        moved_protected_wing_feature_vertices = wing_evaluation_feature_operation.evaluate(
            moved_wing_coefficients,
            protected_wing_feature_parametric_coordinates,
        )
        predicted_variable_vertices = predicted_variable_vertices.set(
            csdl.slice[protected_wing_feature_indices.tolist(), :],
            moved_protected_wing_feature_vertices,
        )
    if protected_htail_feature_indices.size > 0:
        moved_protected_htail_feature_vertices = htail_evaluation_feature_operation.evaluate(
            moved_htail_coefficients,
            protected_htail_feature_parametric_coordinates,
        )
        predicted_variable_vertices = predicted_variable_vertices.set(
            csdl.slice[protected_htail_feature_indices.tolist(), :],
            moved_protected_htail_feature_vertices,
        )

    if plot_step8_prediction:
        predicted_plot_vertices = np.asarray(predicted_variable_vertices.value, dtype=float)
        _plot_surface_debug(
            predicted_plot_vertices,
            mesh_faces=mesh_faces,
            interpolation_indices=interpolation_indices,
            seam_seed_indices=seam_seed_indices,
            protected_feature_indices=protected_feature_indices,
            mesh_label="Single-RBF predicted mesh",
        )
        # exit()

    if step9_pre_projection_laplacian_step > 0.0:
        laplacian_displacement = csdl.matmat(laplacian_matrix, predicted_variable_vertices)
        step9_smoothed_variable_vertices = (
            predicted_variable_vertices
            + step9_pre_projection_laplacian_step
            * _expand_vector_to_columns(unprotected_laplacian_scale, 3)
            * laplacian_displacement
        )
        if moved_protected_wing_feature_vertices is not None:
            step9_smoothed_variable_vertices = step9_smoothed_variable_vertices.set(
                csdl.slice[protected_wing_feature_indices.tolist(), :],
                moved_protected_wing_feature_vertices,
            )
        if moved_protected_htail_feature_vertices is not None:
            step9_smoothed_variable_vertices = step9_smoothed_variable_vertices.set(
                csdl.slice[protected_htail_feature_indices.tolist(), :],
                moved_protected_htail_feature_vertices,
            )
        if stationary_aft_fuse_symmetry_anchor_vertices is not None:
            step9_smoothed_variable_vertices = step9_smoothed_variable_vertices.set(
                csdl.slice[aft_fuse_symmetry_anchor_indices.tolist(), :],
                stationary_aft_fuse_symmetry_anchor_vertices,
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
    for iteration_index, ks_rho in enumerate(step9_smooth_union_rho_schedule):
        wing_sdf_iteration_operation = bsm3.FunctionSetClosestDistanceOperation(model=wing_sdf_model)
        fuse_sdf_iteration_operation = bsm3.FunctionSetClosestDistanceOperation(model=fuse_sdf_model)
        htail_sdf_iteration_operation = bsm3.FunctionSetClosestDistanceOperation(model=htail_sdf_model)

        sdf_to_wing = wing_sdf_iteration_operation.evaluate(
            moved_wing_coefficients,
            projected_variable_vertices,
        )
        sdf_to_fuse = fuse_sdf_iteration_operation.evaluate(
            fuse_coefficients_csdl,
            projected_variable_vertices,
        )
        sdf_to_htail = htail_sdf_iteration_operation.evaluate(
            moved_htail_coefficients,
            projected_variable_vertices,
        )

        wing_sdf_gradient = _signed_distance_gradient_from_ad_csdl(
            sdf_to_wing,
            projected_variable_vertices,
        )
        fuse_sdf_gradient = _signed_distance_gradient_from_ad_csdl(
            sdf_to_fuse,
            projected_variable_vertices,
        )
        htail_sdf_gradient = _signed_distance_gradient_from_ad_csdl(
            sdf_to_htail,
            projected_variable_vertices,
        )
        union_sdf, wing_union_weight, fuse_union_weight, htail_union_weight = (
            _smooth_minimum_signed_distance_three_components_csdl(
                sdf_to_wing,
                sdf_to_fuse,
                sdf_to_htail,
                ks_rho=ks_rho,
            )
        )
        if iteration_index == 0:
            first_union_sdf_csdl = union_sdf
        union_sdf_gradient = (
            _expand_vector_to_columns(csdl.reshape(wing_union_weight, (-1,)), 3) * wing_sdf_gradient
            + _expand_vector_to_columns(csdl.reshape(fuse_union_weight, (-1,)), 3) * fuse_sdf_gradient
            + _expand_vector_to_columns(csdl.reshape(htail_union_weight, (-1,)), 3) * htail_sdf_gradient
        )
        union_gradient_norm_squared = csdl.sum(union_sdf_gradient**2, axes=(1,)) + 1e-12
        projected_variable_vertices = projected_variable_vertices - (
            _expand_vector_to_columns(union_sdf / union_gradient_norm_squared, 3)
            * union_sdf_gradient
        )
        union_sdf_value = union_sdf.value
        print("max union sdf after iteration", iteration_index, ":", np.max(union_sdf_value))
        print("mean union sdf after iteration", iteration_index, ":", np.mean(union_sdf_value))

    if moved_protected_wing_feature_vertices is not None:
        projected_variable_vertices = projected_variable_vertices.set(
            csdl.slice[protected_wing_feature_indices.tolist(), :],
            moved_protected_wing_feature_vertices,
        )
    if moved_protected_htail_feature_vertices is not None:
        projected_variable_vertices = projected_variable_vertices.set(
            csdl.slice[protected_htail_feature_indices.tolist(), :],
            moved_protected_htail_feature_vertices,
        )
    if stationary_aft_fuse_symmetry_anchor_vertices is not None:
        projected_variable_vertices = projected_variable_vertices.set(
            csdl.slice[aft_fuse_symmetry_anchor_indices.tolist(), :],
            stationary_aft_fuse_symmetry_anchor_vertices,
        )
    projected_variable_vertices.add_name("surface_mesh_vertices")

    # _plot_surface_debug(
    #     projected_variable_vertices.value,
    #     mesh_faces=mesh_faces,
    #     interpolation_indices=interpolation_indices,
    #     seam_seed_indices=seam_seed_indices,
    #     protected_feature_indices=protected_feature_indices,
    #     mesh_label="Updated mesh",
    # )
    # exit("hi")

    recorder.inline = False

    if False:
        mean_verts = csdl.average(projected_variable_vertices)
        mean_verts.set_as_objective()

        sim = csdl.experimental.JaxSimulator(
            recorder=recorder,
            # additional_inputs=inputs,
            # additional_outputs = outputs,
            gpu=False
        )
        sim.check_optimization_derivatives()
        exit()

    from VortexAD import PanelMethod, find_cell_adjacency, TE_detection

    points_orig = mesh.points
    cells = mesh.cells
    cells_dict = mesh.cells_dict

    cell_adjacency_data = find_cell_adjacency(points=points_orig, cells=cells_dict)

    points_orig = cell_adjacency_data[0] 
    cells_dict = cell_adjacency_data[1] 
    cell_adjacency = cell_adjacency_data[2] 
    edges2cells = cell_adjacency_data[3]
    points2cells = cell_adjacency_data[4]

    # TE_nodes_to_ignore = [[5136-1, 5138-1], [16-1, 18-1]] # ignoring 1st element
    # TE_nodes_to_ignore = [[5136-1, 5138-1], [5206-1, 5138-1], [16-1, 18-1], [18-1, 86-1]] # ignoring 2nd element
    TE_nodes_to_ignore = [[5646-1, 5648-1], [16-1, 18-1], [4433-1, 5138-1], [10458-1, 9856-1]] # ignoring 3rd element

    TE_properties = TE_detection(
        points=points_orig,
        cells=cells_dict,
        edges2cells=edges2cells,
        points2cells=points2cells,
        threshold_theta=125.,
        edges2ignore=TE_nodes_to_ignore
    )

    # TE_properties = TE_detection(
    #     points=points_orig,
    #     cells=cells_dict,
    #     edges2cells=edges2cells,
    #     points2cells=points2cells,
    #     threshold_theta=125.
    # )

    # upper_TE_cells = TE_properties[0] 
    # lower_TE_cells = TE_properties[1] 
    # TE_edges = TE_properties[2] 
    # TE_node_indices = TE_properties[3]\

    pitch = csdl.Variable(value=np.array([0.]))
    BC = 'Dirichlet'
    # input dict
    input_dict = {
        'Mach': 0.25,
        'alpha': pitch,
        'Cp cutoff': -5.,
        # 'mesh_path': mesh_file_path, # can alternatively load mesh in with connectivity/TE data
        'ref_area': 58., 
        'BC': BC,
    }

    panel_method = PanelMethod(
        solver_input_dict=input_dict,
        skip_geometry=True # not running geometry
    )
    # inserting grid data from above
    panel_method.insert_grid_data(
        # mesh=panel_mesh[0,:],
        mesh=projected_variable_vertices,
        cell_adjacency_data=cell_adjacency_data,
        TE_properties=TE_properties
    )

    pm_outputs = [
        'CL',
        'CDi',
        'Cp',
        'mu',
        'L',
        'Di',
        'M',

    ]
    panel_method.declare_outputs(pm_outputs)

    # panel_method.setup_grid_properties(threshold_angle=125, plot=True) # optional for debugging

    # run the panel method
    outputs = panel_method.evaluate()

    # read outputs
    CL = outputs['CL']
    CL.add_name("CL")
    CDi = outputs['CDi']
    CDi.add_name("CDi")
    CP = outputs['Cp']
    CP.add_name("Cp")
    mu = outputs['mu']
    mu.add_name("mu")
    L = outputs['L']
    L.add_name("L")
    M = outputs['M']
    M.add_name("M")

    My = M[0, 1]
    My.add_name("My")
    My.set_as_constraint(equals=0.0, scaler=1e-3)

    W0 = 80000
    L_minus_L0 = L - W0
    objective = L_minus_L0**2
    objective.add_name("L_equals_W0_objective")
    objective.set_as_objective(scaler=1e-3)

    Di = outputs['Di']
    Di.add_name("Di")

    # csdl-jax stuff
    inputs = [pitch]
    outputs = [CL, CDi, CP, mu, L, Di, M, projected_variable_vertices]

    CL.save()
    CDi.save()
    L.save()
    CP.save()
    mu.save()
    Di.save()
    M.save()
    projected_variable_vertices.save()
    csdl.save_optimization_variables()

    sim = csdl.experimental.JaxSimulator(
        recorder=recorder,
        additional_inputs=inputs,
        additional_outputs=outputs,
        gpu=False,
        save_on_update=True,
        filename='wing_and_tail_rotation_defomration',
        output_saved=True,
    )   
    
    # sim.check_optimization_derivatives()
    # sim.run()

    from modopt import PySLSQP, CSDLAlphaProblem

    prob = CSDLAlphaProblem(problem_name='wing_and_tail_rotation_defomration',simulator=sim)
    optimizer = PySLSQP(prob, solver_options={'maxiter': 20, 'acc': 1e-6})
    optimizer.solve()
    optimizer.print_results()

    sim.run()

    CL_val = sim[CL]
    CDi_val = sim[CDi]
    CP_val = sim[CP]
    mu_val = sim[mu]
    L_val = sim[L]
    Di_val = sim[Di]
    M = sim[M]

    print('CL:', CL_val)
    print('CDi:', CDi_val)
    print("L:", L_val)
    print("Di:", Di_val)
    print("M:", M)

    panel_method.points_orig = sim[projected_variable_vertices]
    panel_method.plot(CP_val, bounds=[-1.5,1])
    panel_method.plot(mu_val)

    exit("hi")

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
    final_htail_sdf, _ = htail_sdf_model.project(
        np.asarray(moved_htail_coefficients.value, dtype=float),
        updated_vertices,
    )
    final_union_sdf, _ = _smooth_minimum_signed_distance_numpy(
        np.column_stack([final_wing_sdf, final_fuse_sdf, final_htail_sdf]),
        ks_rho=step9_smooth_union_rho_schedule[-1],
    )
    moving_owned_interpolation_mask = wing_owned_interpolation_mask | htail_owned_interpolation_mask
    combined_seam_support_interp = np.maximum(
        np.asarray(wing_fuse_seam_support_interp.value, dtype=float),
        np.asarray(htail_fuse_seam_support_interp.value, dtype=float),
    )

    print("")
    print("Single-master-RBF native-CSDL movement test")
    print("    Mesh:", mesh_filename)
    print("    Master component:", master_component_name)
    print("    Vertices:", num_vertices)
    print("    Interpolation vertices:", interpolation_indices.size)
    print("    Exact seam seed vertices:", seam_seed_indices.size)
    print("    Wing/fuselage exact seam seed vertices:", wing_fuse_seam_seed_indices.size)
    print("    Htail/fuselage exact seam seed vertices:", htail_fuse_seam_seed_indices.size)
    print("    Wing-owned interpolation vertices:", int(np.count_nonzero(wing_owned_interpolation_mask)))
    print("    Htail-owned interpolation vertices:", int(np.count_nonzero(htail_owned_interpolation_mask)))
    print("    Non-moving interpolation vertices:", int(np.count_nonzero(~moving_owned_interpolation_mask)))
    print("    Aft fuselage symmetry anchors:", aft_fuse_symmetry_anchor_indices.size)
    print("    Seam candidate vertices:", seam_candidate_indices.size)
    print("    Protected wing feature vertices:", protected_wing_feature_indices.size)
    print("    Protected htail feature vertices:", protected_htail_feature_indices.size)
    print("    Wing root chord proxy:", f"{root_chord_proxy:.6e}")
    print("    Htail root chord proxy:", f"{htail_root_chord_proxy:.6e}")
    print(
        "    Wing envelope translation bounds:",
        f"{-translation_envelope_mac * root_chord_proxy:.6e} to "
        f"{translation_envelope_mac * root_chord_proxy:.6e}",
    )
    print(
        "    Htail envelope translation bounds:",
        f"{-translation_envelope_mac * htail_root_chord_proxy:.6e} to "
        f"{translation_envelope_mac * htail_root_chord_proxy:.6e}",
    )
    print(
        "    Envelope rotation bounds:",
        f"{-rotation_envelope_degrees:.6e} to {rotation_envelope_degrees:.6e}",
    )
    print("    Active wing translation:", f"{wing_translation_amount:.6e}")
    print("    Active htail translation:", f"{htail_translation_amount:.6e}")
    print(
        "    Active wing rotation (deg):",
        f"{float(np.asarray(wing_root_rotation_degrees.value).reshape(-1)[0]):.6e}",
    )
    print(
        "    Active htail rotation (deg):",
        f"{float(np.asarray(htail_root_rotation_degrees.value).reshape(-1)[0]):.6e}",
    )
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
        "    Seam support at interpolation vertices:",
        _format_stats(combined_seam_support_interp),
    )
    print(
        "    Provisional target displacement magnitude:",
        _format_stats(np.linalg.norm(provisional_interpolation_target_displacements.value, axis=1)),
    )
    print(
        "    Corrected target displacement magnitude:",
        _format_stats(np.linalg.norm(corrected_interpolation_target_displacements.value, axis=1)),
    )
    print(
        "    Single-RBF interpolation fit error:",
        _format_stats(np.linalg.norm(interpolation_target_error.value, axis=1)),
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
