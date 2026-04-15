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


def _cubic_rbf_kernel(distances: np.ndarray) -> np.ndarray:
    return distances**3


def _fit_vector_rbf(
    training_points: np.ndarray,
    training_displacements: np.ndarray,
    *,
    regularization: float,
) -> tuple[np.ndarray, np.ndarray]:
    training_points = np.asarray(training_points, dtype=float)
    training_displacements = np.asarray(training_displacements, dtype=float)

    num_points = training_points.shape[0]
    pairwise_distances = np.linalg.norm(
        training_points[:, None, :] - training_points[None, :, :],
        axis=2,
    )
    kernel_matrix = _cubic_rbf_kernel(pairwise_distances)
    kernel_matrix = kernel_matrix + regularization * np.eye(num_points)

    polynomial_terms = np.column_stack(
        [
            np.ones(num_points, dtype=float),
            training_points,
        ]
    )

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

    weights = solution[:num_points, :]
    polynomial_coefficients = solution[num_points:, :]
    return weights, polynomial_coefficients


def _evaluate_vector_rbf(
    query_points: np.ndarray,
    training_points: np.ndarray,
    weights: np.ndarray,
    polynomial_coefficients: np.ndarray,
) -> np.ndarray:
    query_points = np.asarray(query_points, dtype=float)
    training_points = np.asarray(training_points, dtype=float)

    query_distances = np.linalg.norm(
        query_points[:, None, :] - training_points[None, :, :],
        axis=2,
    )
    kernel_values = _cubic_rbf_kernel(query_distances)
    polynomial_terms = np.column_stack(
        [
            np.ones(query_points.shape[0], dtype=float),
            query_points,
        ]
    )
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


def _format_stats(values: np.ndarray) -> str:
    values = np.asarray(values, dtype=float)
    return (
        f"min={np.min(values):.6e}, "
        f"mean={np.mean(values):.6e}, "
        f"max={np.max(values):.6e}"
    )


if __name__ == "__main__":
    plot = False
    debug_projections = False
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
    wing_patch_id_set = set(int(key) for key in wing_keys)
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

    nose_mask = vertices[:, 0] <= x_min + 0.2 * dx
    tail_mask = vertices[:, 0] >= x_max - 0.2 * dx

    # Outer 50% of each half-span:
    left_tip_mask = vertices[:, 1] <= y_mid - 0.25 * dy
    right_tip_mask = vertices[:, 1] >= y_mid + 0.25 * dy

    wing_anchor_mask = left_tip_mask | right_tip_mask
    fuse_anchor_mask = (nose_mask | tail_mask) & ~wing_anchor_mask
    fixed_indices = np.where(
        nose_mask | tail_mask | left_tip_mask | right_tip_mask
    )[0]

    fixed_vertices = vertices[fixed_indices]
    wing_anchor_indices = np.where(wing_anchor_mask)[0]
    fuse_anchor_indices = np.where(fuse_anchor_mask)[0]
    wing_anchor_vertices = vertices[wing_anchor_indices]
    fuse_anchor_vertices = vertices[fuse_anchor_indices]

    # The rest of the vertices are free to move
    variable_indices = np.setdiff1d(np.arange(vertices.shape[0]), fixed_indices)
    variable_local_indices = -np.ones(vertices.shape[0], dtype=int)
    variable_local_indices[variable_indices] = np.arange(variable_indices.size)
    vertex_neighbors = _build_vertex_neighbors(vertices.shape[0], triangles)

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
    interpolation_vertices = vertices[intersection_global_indices]
    interpolation_vertices_plot = lfs.plot_points(interpolation_vertices, color="green", show=False)
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
    # We start with a wing translation along the fuselage (i.e., in the x-direction)
    translation_amount = 0.25
    translation_amount_np = np.zeros_like(reshaped_wing_coeffs_stacked.value)
    translation_amount_np[:, 0] = translation_amount
    translation_amount_csdl = csdl.Variable(name="translation_amount", value=translation_amount_np)
    reshaped_wing_coeffs_stacked = reshaped_wing_coeffs_stacked + translation_amount_csdl
    moved_wing_coeffs = np.asarray(reshaped_wing_coeffs_stacked.value, dtype=float).copy()
    moved_total_coeffs = np.vstack([moved_wing_coeffs, initial_fuse_coeffs])

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
    print("interp_verts_displacement_wing", interp_verts_displacement_wing.value)
    print("interp_verts_displacement_fuse", interp_verts_displacement_fuse.value)
    second_closest_scale = np.median(np.max(interp_component_distances, axis=1))
    # alpha = 4.0 / max(second_closest_scale, 1e-8)
    unnormalized_weights = np.exp(-1. * interp_component_distances)
    normalized_weights = unnormalized_weights / np.sum(unnormalized_weights, axis=1, keepdims=True)
    interpolation_displacements = (
        normalized_weights[:, [0]] * np.asarray(interp_verts_displacement_wing.value, dtype=float)
        + normalized_weights[:, [1]] * np.asarray(interp_verts_displacement_fuse.value, dtype=float)
    )
    print("interpolation_displacements", interpolation_displacements)
    print("unnormalized_weights \n", unnormalized_weights)
    print("normalized_weights \n", normalized_weights)
    exit()

    moved_wing_anchor_vertices = np.empty((0, 3), dtype=float)
    if wing_anchor_vertices.size > 0:
        moved_wing_anchor_vertices = wing_eval_model.evaluate(
            moved_wing_coeffs,
            wing_anchor_parametric_coordinates,
        )
    

    #################### Step 4 ####################
    # Fit an exact cubic RBF with an affine tail to the interpolation-node
    # displacement data, augmented with a sparse subset of anchor constraints.
    # The affine tail preserves rigid-body trends, which matters for the
    # wing-translation test case.
    rbf_training_points = interpolation_vertices.copy()
    rbf_training_displacements = interpolation_displacements.copy()

    length_scale = np.linalg.norm(
        np.max(rbf_training_points, axis=0) - np.min(rbf_training_points, axis=0)
    )
    rbf_regularization = 1e-10 * max(length_scale**3, 1.0)
    rbf_weights, rbf_polynomial_coefficients = _fit_vector_rbf(
        rbf_training_points,
        rbf_training_displacements,
        regularization=rbf_regularization,
    )

    #################### Step 5 ####################
    variable_vertices = vertices[variable_indices]
    predicted_variable_displacements = _evaluate_vector_rbf(
        variable_vertices,
        rbf_training_points,
        rbf_weights,
        rbf_polynomial_coefficients,
    )
    predicted_variable_vertices = variable_vertices + predicted_variable_displacements

    #################### Step 6 ####################
    oml_projection_model = bsm3.FunctionSetProjectionModel(
        wing_fuse,
        warm_start_nu=40,
        warm_start_nv=40,
        edge_map_num_samples=25,
        debug=debug_projections,
    )
    _, projected_variable_state = oml_projection_model.project(
        moved_total_coeffs,
        predicted_variable_vertices,
    )
    projected_variable_vertices = np.asarray(
        projected_variable_state["projected_points"],
        dtype=float,
    )
    projection_correction = projected_variable_vertices - predicted_variable_vertices

    updated_vertices = vertices.copy()
    updated_vertices[variable_indices] = projected_variable_vertices
    if wing_anchor_indices.size > 0:
        updated_vertices[wing_anchor_indices] = moved_wing_anchor_vertices
    if fuse_anchor_indices.size > 0:
        updated_vertices[fuse_anchor_indices] = fuse_anchor_vertices

    original_area_vectors = np.cross(
        vertices[triangles[:, 1]] - vertices[triangles[:, 0]],
        vertices[triangles[:, 2]] - vertices[triangles[:, 0]],
    )
    max_flip_repair_iterations = 3
    for _ in range(max_flip_repair_iterations):
        current_area_vectors = np.cross(
            updated_vertices[triangles[:, 1]] - updated_vertices[triangles[:, 0]],
            updated_vertices[triangles[:, 2]] - updated_vertices[triangles[:, 0]],
        )
        current_flipped_triangles = np.where(
            np.einsum("ij,ij->i", original_area_vectors, current_area_vectors) < 0.0
        )[0]
        if current_flipped_triangles.size == 0:
            break

        seam_repair_vertices = {"wing": set(), "fuse": set()}
        for flipped_triangle_index in current_flipped_triangles:
            flipped_triangle = triangles[int(flipped_triangle_index)]
            _, flipped_triangle_projection_state = oml_projection_model.project(
                moved_total_coeffs,
                updated_vertices[flipped_triangle],
            )
            flipped_patch_ids = np.asarray(flipped_triangle_projection_state["patch_id"], dtype=int)
            flipped_components = np.asarray(
                [
                    "wing" if int(patch_id) in wing_patch_id_set else "fuse"
                    for patch_id in flipped_patch_ids
                ],
                dtype=object,
            )
            unique_components, component_counts = np.unique(flipped_components, return_counts=True)
            if unique_components.size != 2:
                continue

            majority_component = str(unique_components[np.argmax(component_counts)])
            minority_vertices = flipped_triangle[flipped_components != majority_component]
            for vertex_index in minority_vertices:
                if variable_local_indices[int(vertex_index)] >= 0:
                    seam_repair_vertices[majority_component].add(int(vertex_index))

        seam_repair_applied = False
        for component_name, vertex_set in seam_repair_vertices.items():
            if not vertex_set:
                continue
            vertex_indices = np.asarray(sorted(vertex_set), dtype=int)
            if component_name == "wing":
                repair_model = wing_projection_model
                repair_coefficients = moved_wing_coeffs
            else:
                repair_model = fuse_projection_model
                repair_coefficients = initial_fuse_coeffs
            _, seam_repair_state = repair_model.project(
                repair_coefficients,
                updated_vertices[vertex_indices],
            )
            repaired_points = np.asarray(seam_repair_state["projected_points"], dtype=float)
            updated_vertices[vertex_indices] = repaired_points
            projected_variable_vertices[variable_local_indices[vertex_indices]] = repaired_points
            seam_repair_applied = True

        if seam_repair_applied:
            continue

        flipped_vertices = np.unique(triangles[current_flipped_triangles].ravel())
        flipped_free_vertices = flipped_vertices[variable_local_indices[flipped_vertices] >= 0]
        if flipped_free_vertices.size == 0:
            break

        smoothed_points = []
        smoothed_vertex_indices = []
        for vertex_index in flipped_free_vertices:
            neighbor_indices = vertex_neighbors[int(vertex_index)]
            if neighbor_indices.size == 0:
                continue
            neighbor_centroid = np.mean(updated_vertices[neighbor_indices], axis=0)
            smoothed_points.append(0.5 * updated_vertices[int(vertex_index)] + 0.5 * neighbor_centroid)
            smoothed_vertex_indices.append(int(vertex_index))

        if not smoothed_vertex_indices:
            break

        _, repaired_projection_state = oml_projection_model.project(
            moved_total_coeffs,
            np.asarray(smoothed_points, dtype=float),
        )
        repaired_points = np.asarray(repaired_projection_state["projected_points"], dtype=float)
        updated_vertices[np.asarray(smoothed_vertex_indices, dtype=int)] = repaired_points
        projected_variable_vertices[
            variable_local_indices[np.asarray(smoothed_vertex_indices, dtype=int)]
        ] = repaired_points

    #################### Step 7 ####################
    updated_interpolation_vertices = projected_variable_vertices[
        variable_local_indices[interpolation_indices]
    ]
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

    original_triangle_areas = _triangle_areas(vertices, triangles)
    updated_triangle_areas = _triangle_areas(updated_vertices, triangles)
    triangle_area_ratio = updated_triangle_areas / np.maximum(original_triangle_areas, 1e-12)
    num_small_area_triangles = int(np.sum(triangle_area_ratio < 0.5))
    num_large_area_triangles = int(np.sum(triangle_area_ratio > 2.0))
    updated_area_vectors = np.cross(
        updated_vertices[triangles[:, 1]] - updated_vertices[triangles[:, 0]],
        updated_vertices[triangles[:, 2]] - updated_vertices[triangles[:, 0]],
    )
    triangle_orientation_dot = np.einsum("ij,ij->i", original_area_vectors, updated_area_vectors)
    flipped_triangle_indices = np.where(triangle_orientation_dot < 0.0)[0]
    num_flipped_triangles = int(flipped_triangle_indices.size)

    final_projection_model = bsm3.FunctionSetProjectionModel(
        wing_fuse,
        warm_start_nu=40,
        warm_start_nv=40,
        edge_map_num_samples=25,
        output_mode="distance",
        debug=False,
    )
    final_surface_distance, _ = final_projection_model.project(
        moved_total_coeffs,
        updated_vertices,
    )

    wing_anchor_displacement = np.empty((0,), dtype=float)
    if wing_anchor_vertices.size > 0:
        wing_anchor_displacement = np.linalg.norm(
            moved_wing_anchor_vertices - wing_anchor_projected_initial,
            axis=1,
        )

    print("")
    print("Surface mesh movement diagnostics")
    print("    Random seed:", random_seed)
    print("    Interpolation vertices:", interpolation_vertices.shape[0])
    print("    RBF training points:", rbf_training_points.shape[0])
    print("    Alpha:", f"{alpha:.6e}")
    print("    RBF regularization:", f"{rbf_regularization:.6e}")
    print("    Blended interpolation displacement:", _format_stats(np.linalg.norm(interpolation_displacements, axis=1)))
    print("    Predicted free-node displacement:", _format_stats(np.linalg.norm(predicted_variable_displacements, axis=1)))
    print("    Projection correction:", _format_stats(np.linalg.norm(projection_correction, axis=1)))
    print("    Final OML distance:", _format_stats(final_surface_distance))
    print("    Updated triangle area:", _format_stats(updated_triangle_areas))
    print("    Triangle area ratio:", _format_stats(triangle_area_ratio))
    print("    Triangle ratios < 0.5:", num_small_area_triangles)
    print("    Triangle ratios > 2.0:", num_large_area_triangles)
    print("    Flipped triangles:", num_flipped_triangles)
    if num_flipped_triangles > 0:
        flipped_triangle = triangles[flipped_triangle_indices[0]]
        _, flipped_triangle_projection_state = oml_projection_model.project(
            moved_total_coeffs,
            updated_vertices[flipped_triangle],
        )
        flipped_patch_ids = np.asarray(flipped_triangle_projection_state["patch_id"], dtype=int)
        print("    First flipped triangle index:", int(flipped_triangle_indices[0]))
        print("    First flipped triangle vertices:", flipped_triangle.tolist())
        print(
            "    First flipped triangle vertex types:",
            [
                "wing_anchor" if wing_anchor_mask[idx]
                else "fuse_anchor" if fuse_anchor_mask[idx]
                else "free"
                for idx in flipped_triangle
            ],
        )
        print("    First flipped triangle patch ids:", flipped_patch_ids.tolist())
        print(
            "    First flipped triangle area ratio:",
            f"{triangle_area_ratio[flipped_triangle_indices[0]]:.6e}",
        )
    if wing_anchor_displacement.size > 0:
        print("    Wing-anchor displacement:", _format_stats(wing_anchor_displacement))
    print("    Refreshed interpolation distance to OML:", _format_stats(refreshed_interp_verts_distance_to_oml))

    
    # Visualize the updated mesh and geometry
    if True:
        initial_mesh_plot = pv.PolyData(vertices, _make_faces(mesh))
        updated_mesh_plot = pv.PolyData(updated_vertices, _make_faces(mesh))
        plotter = pv.Plotter()
        # plotter.add_mesh(initial_mesh_plot, color="lightgray", opacity=0.35, show_edges=False, label="Initial mesh")
        plotter.add_mesh(updated_mesh_plot, opacity=1., show_edges=True, label="Updated mesh")
        plotter.add_mesh(
            pv.PolyData(updated_interpolation_vertices),
            color="green",
            point_size=8,
            render_points_as_spheres=True,
            label="Updated interpolation points",
        )
        if moved_wing_anchor_vertices.size > 0:
            plotter.add_mesh(
                pv.PolyData(moved_wing_anchor_vertices),
                color="royalblue",
                point_size=6,
                render_points_as_spheres=True,
                label="Wing anchors",
            )
        plotter.add_legend()
        plotter.show()
