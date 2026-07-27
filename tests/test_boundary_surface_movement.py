from __future__ import annotations

import numpy as np
import pytest
import scipy.sparse as sp

import csdl_alpha as csdl
import lsdo_function_spaces as lfs

from bsm3.component_parameters import ComponentParameters, WingParameters
from bsm3.core.boundary_surface_movement import (
    AxisRange,
    ComponentDisplacementData,
    ComponentFreeRegion,
    ComponentReevaluation,
    CornerInversionBarrierModel,
    CornerInversionBarrierOperation,
    CorotationalMembraneAssembler,
    CurrentGraphDistortionModel,
    CurrentGraphModel,
    classify_patch_sides,
    DisplacementInterpolationParameters,
    DisplacementInterpolator,
    ElasticityMotionSolver,
    GraphDistanceWeighting,
    GraphLaplacianAssembler,
    GraphLoadStepResult,
    IntersectionParameters,
    build_graph_distance_weighting,
    compute_multisource_geodesic_distance,
    OMLQualityModel,
    OMLQualityOperation,
    ParameterizedProjectionGroup,
    QuadraticDistortionAssembler,
    QuadraticDistortionConfig,
    DistortionModeCoefficients,
    SPDSolveOperation,
    assemble_fixed_projected_tangential_smoother,
    combine_vertices,
    deform_geometry,
    evaluate_mesh_quality,
    element_neighbors,
    enforce_symmetry_plane,
    factorize_spd,
    identify_symmetry_plane_vertices,
    project_onto_oml,
    reevaluate_vertices,
    run_graph_load_steps,
    select_fixed_vertex_band,
    select_free_vertices,
    solve_intersection,
    stack_component_coefficients,
)
from bsm3.core.projections.function_set_evaluation_custom_op import (
    FunctionSetEvaluationModel,
)
from bsm3.core.weighting_functions import (
    GaussianWeighting,
    InverseDistanceWeighting,
    LinearWeighting,
)
from bsm3.preprocessing import (
    MeshData,
    ProjectionMetadata,
    VertexEvaluationMetadata,
    detect_symmetry,
    reconstruct_full_from_half,
    split_symmetric_mesh,
)


def _plane_function_set(kind: str, *, patch_id: int = 0, z_offset: float = 0.0):
    knots = (np.array([0.0, 0.0, 1.0, 1.0]),) * 2
    space = lfs.BSplineSpaceNew(
        num_parametric_dimensions=2,
        degree=(1, 1),
        coefficients_shape=(2, 2),
        knots=knots,
    )
    u, v = np.meshgrid([0.0, 1.0], [0.0, 1.0], indexing="ij")
    if kind == "xy":
        coefficients = np.stack(
            (2.0 * u - 1.0, 2.0 * v - 1.0, np.full_like(u, z_offset)),
            axis=-1,
        )
    elif kind == "yz":
        coefficients = np.stack(
            (np.zeros_like(u), 2.0 * u - 1.0, 2.0 * v - 1.0),
            axis=-1,
        )
    else:
        raise ValueError(kind)
    return lfs.FunctionSet(
        functions={
            patch_id: lfs.Function(
                space=space,
                coefficients=coefficients,
            )
        }
    )


def _surface_mesh(vertices):
    triangles = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    return MeshData(
        vertices=np.asarray(vertices, dtype=float),
        connectivity=triangles,
        cell_types=np.array(["triangle", "triangle"], dtype=object),
        cell_blocks={"triangle": triangles},
    )


@pytest.mark.parametrize(
    "weighting",
    [InverseDistanceWeighting(), GaussianWeighting(), LinearWeighting()],
)
def test_influence_weights_are_compact_and_bounded(weighting):
    values = weighting(np.array([0.0, 0.25, 0.75, 1.0, 2.0]))
    assert values[0] == pytest.approx(1.0)
    assert np.all((values >= 0.0) & (values <= 1.0))
    assert values[-2] == 0.0
    assert values[-1] == 0.0


def test_wing_planform_scaling_and_rigid_transform_are_differentiable():
    recorder = csdl.Recorder(inline=True)
    recorder.start()
    wing = _plane_function_set("xy")
    translation = csdl.Variable(name="translation", value=0.4)
    area = csdl.Variable(name="area", value=8.0)
    aspect_ratio = csdl.Variable(name="aspect_ratio", value=4.0)
    translation.set_as_design_variable()
    area.set_as_design_variable()
    aspect_ratio.set_as_design_variable()

    coefficients = deform_geometry(
        component=wing,
        parameters=WingParameters(
            translation_x=translation,
            area=area,
            aspect_ratio=aspect_ratio,
            reference_area=4.0,
            reference_aspect_ratio=1.0,
            pivot=np.zeros(3),
        ),
    )
    objective = csdl.sum(coefficients)
    derivative = csdl.derivative(
        objective,
        [translation, area, aspect_ratio],
    )
    recorder.stop()

    assert coefficients.shape == (4, 3)
    assert np.all(np.isfinite(np.asarray(coefficients.value)))
    assert all(np.all(np.isfinite(np.asarray(item.value))) for item in derivative.values())


def test_normal_sdf_bracketed_search_reaches_tight_intersection():
    recorder = csdl.Recorder(inline=True)
    recorder.start()
    driving = _plane_function_set("xy")
    query = _plane_function_set("yz")
    translation_z = csdl.Variable(name="translation_z", value=0.1)
    translation_z.set_as_design_variable()
    driving_coefficients = deform_geometry(
        component=driving,
        parameters=ComponentParameters(
            translation_x=0.2,
            translation_z=translation_z,
            pivot=np.zeros(3),
        ),
    )
    parametric_coordinates = np.array(
        [[0.0, 0.5, 0.2], [0.0, 0.5, 0.5], [0.0, 0.5, 0.8]]
    )
    solution = solve_intersection(
        IntersectionParameters(
            parametric_coords=parametric_coordinates,
            driving_component=driving,
            sdf_query_component=query,
            bisection_search_direction="u",
            bisection_tolerance=1e-11,
            projection_options={
                "warm_start_nu": 10,
                "warm_start_nv": 10,
                "edge_map_num_samples": 7,
            },
        ),
        driving_coefficients=driving_coefficients,
    )
    z_sum = csdl.sum(solution.deformed_vertices[csdl.slice[:, 2]])
    dz_sum = csdl.derivative(z_sum, translation_z)
    recorder.stop()

    np.testing.assert_allclose(solution.deformed_vertices.value[:, 0], 0.0, atol=1e-10)
    np.testing.assert_allclose(solution.deformed_vertices.value[:, 2], 0.1, atol=1e-12)
    np.testing.assert_allclose(dz_sum.value, 3.0, rtol=1e-10, atol=1e-10)
    # The RBF anchor must be the *baseline* intersection even though the graph
    # was built at a deformed design.  Snapshotting the live solve here would
    # zero out every seam displacement.
    np.testing.assert_allclose(solution.initial_vertices[:, 0], 0.0, atol=1e-9)
    np.testing.assert_allclose(solution.initial_vertices[:, 2], 0.0, atol=1e-9)


def test_rbf_preserves_all_exact_intersection_rows():
    recorder = csdl.Recorder(inline=True)
    recorder.start()
    driving = _plane_function_set("xy")
    query = _plane_function_set("yz")
    translation_z = csdl.Variable(name="translation_z", value=0.1)
    driving_coefficients = deform_geometry(
        component=driving,
        parameters=ComponentParameters(
            translation_z=translation_z,
            pivot=np.zeros(3),
        ),
    )
    y = np.linspace(-1.0, 1.0, 5)
    seam = np.column_stack((np.zeros(5), y, np.zeros(5)))
    extra = np.array(
        [
            [-1.0, -1.0, 0.0],
            [-1.0, 1.0, 0.0],
            [1.0, -1.0, 0.0],
            [1.0, 1.0, 0.0],
        ]
    )
    vertices = np.vstack((seam, extra))
    mesh = _surface_mesh(vertices[:4])
    mesh.vertices = vertices
    parameters = IntersectionParameters(
        parametric_coords=np.column_stack(
            (np.zeros(5), np.full(5, 0.5), 0.5 * (y + 1.0))
        ),
        vertex_ids=np.arange(5),
        driving_component=driving,
        sdf_query_component=query,
        bisection_search_direction="u",
        influence_x=(1.0, -1.0),
        influence_y=(1.0, -1.0),
        influence_z=(1.0, -1.0),
        projection_options={
            "warm_start_nu": 10,
            "warm_start_nv": 10,
            "edge_map_num_samples": 7,
        },
    )
    surrogate = DisplacementInterpolator(
        mesh=mesh,
        interpolation_params=DisplacementInterpolationParameters(
            intersection_params=[parameters],
            num_interpolation_vertices=4,
            regularization=1e-9,
        ),
    ).train(component_coeffs=[driving_coefficients])
    deformed = surrogate.evaluate(
        vertices=csdl.Variable(value=vertices),
        vertex_ids=np.arange(vertices.shape[0]),
    )
    recorder.stop()

    np.testing.assert_allclose(deformed.value[:5, 0], 0.0, atol=1e-10)
    np.testing.assert_allclose(deformed.value[:5, 2], 0.1, atol=1e-12)


def test_seam_neighbor_drive_closes_sparse_rbf_gap():
    recorder = csdl.Recorder(inline=True)
    recorder.start()
    driving = _plane_function_set("xy")
    query = _plane_function_set("yz")
    translation_z = csdl.Variable(name="seam_neighbor_translation_z", value=0.0)
    translation_z.set_as_design_variable()
    driving_coefficients = deform_geometry(
        component=driving,
        parameters=ComponentParameters(
            translation_z=translation_z,
            pivot=np.zeros(3),
        ),
    )
    y = np.linspace(-1.0, 1.0, 5)
    seam = np.column_stack((np.zeros(5), y, np.zeros(5)))
    neighbor = np.array([[0.2, 0.0, 0.0]])
    vertices = np.vstack((seam, neighbor))
    triangles = np.array(
        [[0, 1, 5], [1, 2, 5], [2, 3, 5], [3, 4, 5]],
        dtype=np.int64,
    )
    mesh = MeshData(
        vertices=vertices,
        connectivity=triangles,
        cell_types=np.full(triangles.shape[0], "triangle", dtype=object),
        cell_blocks={"triangle": triangles},
    )
    parameters = IntersectionParameters(
        parametric_coords=np.column_stack(
            (np.zeros(5), np.full(5, 0.5), 0.5 * (y + 1.0))
        ),
        vertex_ids=np.arange(5),
        driving_component=driving,
        sdf_query_component=query,
        bisection_search_direction="u",
        projection_options={
            "warm_start_nu": 10,
            "warm_start_nv": 10,
            "edge_map_num_samples": 7,
        },
    )
    surrogate = DisplacementInterpolator(
        mesh=mesh,
        interpolation_params=DisplacementInterpolationParameters(
            intersection_params=[parameters],
            rbf_kernel="wendland_c2",
            rbf_kernel_scale=0.01,
            num_interpolation_vertices=0,
            seam_neighbor_blend_radius=1.0,
        ),
    ).train(component_coeffs=[driving_coefficients])
    deformed = surrogate.evaluate(
        vertices=csdl.Variable(value=vertices),
        vertex_ids=np.arange(vertices.shape[0]),
    )
    recorder.stop()
    simulator = csdl.experimental.JaxSimulator(
        recorder=recorder,
        additional_outputs=[deformed],
        gpu=False,
    )
    simulator[translation_z] = np.asarray([0.1])
    simulator.run()
    values = np.asarray(simulator[deformed], dtype=float)

    # The compact RBF has no support 0.2 m from the seam.  Graph-distance
    # driving must nevertheless carry the first off-seam row with it.
    assert values[-1, 2] > 0.09
    np.testing.assert_allclose(values[:5, 2], 0.1, atol=1e-12)


def test_soft_blended_targets_follow_components_and_decay_from_seam():
    recorder = csdl.Recorder(inline=True)
    recorder.start()
    driving = _plane_function_set("xy")
    query = _plane_function_set("yz")
    translation_z = csdl.Variable(name="soft_blend_translation_z", value=0.1)
    translation_z.set_as_design_variable()
    driving_coefficients = deform_geometry(
        component=driving,
        parameters=ComponentParameters(
            translation_z=translation_z,
            pivot=np.zeros(3),
        ),
    )
    y = np.linspace(-1.0, 1.0, 5)
    seam = np.column_stack((np.zeros(5), y, np.zeros(5)))
    driving_extra = np.array(
        [[0.7, 0.5, 0.0], [-0.7, -0.5, 0.0], [0.7, -0.5, 0.0]]
    )
    query_near = np.array([[0.0, 0.3, 0.25]])
    query_far = np.array([[0.0, -0.3, -0.9]])
    vertices = np.vstack((seam, driving_extra, query_near, query_far))
    triangles = np.array(
        [[0, 1, 5], [1, 2, 6], [2, 3, 7], [3, 4, 8], [0, 4, 9]],
        dtype=np.int64,
    )
    mesh = MeshData(
        vertices=vertices,
        connectivity=triangles,
        cell_types=np.full(triangles.shape[0], "triangle", dtype=object),
        cell_blocks={"triangle": triangles},
    )
    projection_options = {
        "warm_start_nu": 10,
        "warm_start_nv": 10,
        "edge_map_num_samples": 7,
    }
    parameters = IntersectionParameters(
        parametric_coords=np.column_stack(
            (np.zeros(5), np.full(5, 0.5), 0.5 * (y + 1.0))
        ),
        vertex_ids=np.arange(5),
        driving_component=driving,
        sdf_query_component=query,
        bisection_search_direction="u",
        influence_x=(1.0, -1.0),
        influence_y=(2.0, -2.0),
        influence_z=(1.0, -1.0),
        weighting_function=LinearWeighting(),
        projection_options=projection_options,
    )
    # Closest-point coordinates and unsigned baseline distances of every mesh
    # vertex on each plane, computed analytically.
    driving_coordinates = np.column_stack(
        (
            np.zeros(vertices.shape[0]),
            np.clip(0.5 * (vertices[:, 0] + 1.0), 0.0, 1.0),
            np.clip(0.5 * (vertices[:, 1] + 1.0), 0.0, 1.0),
        )
    )
    query_coordinates = np.column_stack(
        (
            np.zeros(vertices.shape[0]),
            np.clip(0.5 * (vertices[:, 1] + 1.0), 0.0, 1.0),
            np.clip(0.5 * (vertices[:, 2] + 1.0), 0.0, 1.0),
        )
    )
    component_data = [
        ComponentDisplacementData(
            component=driving,
            vertex_ids=np.arange(vertices.shape[0]),
            parametric_coordinates=driving_coordinates,
            distances=np.abs(vertices[:, 2]),
        ),
        ComponentDisplacementData(
            component=query,
            vertex_ids=np.arange(vertices.shape[0]),
            parametric_coordinates=query_coordinates,
            distances=np.abs(vertices[:, 0]),
        ),
    ]
    surrogate = DisplacementInterpolator(
        mesh=mesh,
        interpolation_params=DisplacementInterpolationParameters(
            intersection_params=[parameters],
            component_displacement_data=component_data,
            num_interpolation_vertices=5,
            regularization=1e-9,
            projection_options=projection_options,
        ),
    ).train(component_coeffs=[driving_coefficients])
    deformed = surrogate.evaluate(
        vertices=csdl.Variable(value=vertices),
        vertex_ids=np.arange(vertices.shape[0]),
    )
    recorder.stop()

    displacement_z = deformed.value[:, 2] - vertices[:, 2]
    # Exact seam rows land on the deformed intersection.
    np.testing.assert_allclose(deformed.value[:5, 0], 0.0, atol=1e-10)
    np.testing.assert_allclose(deformed.value[:5, 2], 0.1, atol=1e-12)
    # Driving-plane (hard) rows follow the component exactly.
    np.testing.assert_allclose(displacement_z[5:8], 0.1, atol=1e-10)
    # Query-plane rows: driven near the seam, decaying to zero away from it.
    assert displacement_z[8] > 0.04
    assert abs(displacement_z[9]) < 0.02
    assert displacement_z[8] > displacement_z[9]


def test_parent_patch_projection_and_parametric_reevaluation_assemble_in_order():
    recorder = csdl.Recorder(inline=True)
    recorder.start()
    component = _plane_function_set("xy", patch_id=5)
    translation_z = csdl.Variable(name="translation_z", value=0.1)
    translation_z.set_as_design_variable()
    coefficients = deform_geometry(
        component=component,
        parameters=ComponentParameters(
            translation_z=translation_z,
            pivot=np.zeros(3),
        ),
    )
    candidate_points = csdl.Variable(
        value=np.array([[0.2, 0.3, 0.4], [0.8, 0.7, -0.2]])
    )
    projected = project_onto_oml(
        deformed_mesh_vertices=candidate_points,
        deformed_mesh_vertex_ids=np.array([0, 1]),
        projection_metadata=[
            ProjectionMetadata(
                component=component,
                vertex_ids=np.array([0, 1]),
                allowed_patch_ids=(5,),
                parent_patch_ids=np.array([5, 5]),
            )
        ],
        component_coefficients={id(component): coefficients},
        projection_options={
            "warm_start_nu": 10,
            "warm_start_nv": 10,
            "edge_map_num_samples": 7,
        },
    )
    mesh = _surface_mesh(
        [[0.2, 0.3, 0.0], [0.8, 0.7, 0.0], [0.5, 0.5, 0.0], [0.0, 0.0, 0.0]]
    )
    reevaluated = reevaluate_vertices(
        mesh=mesh,
        metadata=[
            VertexEvaluationMetadata(
                component=component,
                vertex_ids=np.array([2, 3]),
                parametric_coordinates=np.array(
                    [[5.0, 0.75, 0.75], [5.0, 0.5, 0.5]]
                ),
            )
        ],
        component_coefficients={id(component): coefficients},
    )
    final = combine_vertices(
        oml_projected_vertices=projected,
        reevaluated_mesh_vertices=reevaluated,
    )
    derivative = csdl.derivative(csdl.sum(final), translation_z)
    recorder.stop()

    np.testing.assert_allclose(final.value[:, 2], 0.1, atol=1e-12)
    np.testing.assert_allclose(derivative.value, 4.0, rtol=1e-10, atol=1e-10)


def test_projection_can_preserve_a_parent_patch_boundary_curve():
    recorder = csdl.Recorder(inline=True)
    recorder.start()
    component = _plane_function_set("xy")
    point_x = csdl.Variable(name="boundary_query_x", value=-0.8)
    point_x.set_as_design_variable()
    query = csdl.concatenate(
        (
            csdl.reshape(point_x, (1, 1)),
            np.array([[0.25, 0.4]]),
        ),
        axis=1,
    )
    projected = project_onto_oml(
        deformed_mesh_vertices=query,
        deformed_mesh_vertex_ids=np.array([0]),
        projection_metadata=[
            ProjectionMetadata(
                component=component,
                vertex_ids=np.array([0]),
                allowed_patch_ids=(0,),
                parent_patch_ids=np.array([0]),
                fixed_parametric_coordinates=np.array([[0.0, np.nan]]),
            )
        ],
        projection_options={
            "warm_start_nu": 8,
            "warm_start_nv": 8,
            "edge_map_num_samples": 7,
        },
    )
    derivative = csdl.derivative(csdl.sum(projected.values), point_x)
    recorder.stop()

    np.testing.assert_allclose(projected.values.value, [[-1.0, 0.25, 0.0]], atol=1e-10)
    np.testing.assert_allclose(derivative.value, 0.0, atol=1e-10)


def test_quality_report_detects_surface_inversion():
    mesh = _surface_mesh(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]]
    )
    baseline = evaluate_mesh_quality(mesh=mesh)
    inverted_vertices = mesh.vertices.copy()
    inverted_vertices[[1, 3]] = inverted_vertices[[3, 1]]
    inverted = evaluate_mesh_quality(mesh=mesh, vertices=inverted_vertices)

    assert baseline.inverted_elements == 0
    assert baseline.minimum_scaled_jacobian > 0.0
    assert inverted.inverted_elements > 0
    assert inverted.minimum_scaled_jacobian < 0.0


def test_quality_report_detects_folded_quad_with_positive_polygon_normal():
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
        ]
    )
    quad = np.array([[0, 1, 2, 3]], dtype=np.int64)
    mesh = MeshData(
        vertices=vertices,
        connectivity=quad,
        cell_types=np.array(["quad"], dtype=object),
        cell_blocks={"quad": quad},
    )
    folded = vertices.copy()
    folded[2] = [0.2, 0.2, 0.0]

    # Its area-weighted normal still points in +z, so an aggregate face-normal
    # test alone misses the concave/folded corner.
    baseline_normal = np.sum(
        np.cross(vertices, np.roll(vertices, -1, axis=0)),
        axis=0,
    )
    folded_normal = np.sum(
        np.cross(folded, np.roll(folded, -1, axis=0)),
        axis=0,
    )
    assert np.dot(baseline_normal, folded_normal) > 0.0

    quality = evaluate_mesh_quality(mesh=mesh, vertices=folded)
    assert quality.inverted_elements == 1
    assert quality.inverted_corners == 1
    assert quality.minimum_scaled_jacobian < 0.0


def _grid_strip(nx, ny):
    """Regular quad grid strip; returns mesh, interior ids, boundary ids."""

    xs, ys = np.meshgrid(np.arange(nx), np.arange(ny), indexing="ij")
    vertices = np.column_stack(
        (xs.ravel().astype(float), ys.ravel().astype(float), np.zeros(nx * ny))
    )

    def vid(i, j):
        return i * ny + j

    quads = np.asarray(
        [
            [vid(i, j), vid(i + 1, j), vid(i + 1, j + 1), vid(i, j + 1)]
            for i in range(nx - 1)
            for j in range(ny - 1)
        ],
        dtype=np.int64,
    )
    mesh = MeshData(
        vertices=vertices,
        connectivity=quads,
        cell_types=np.full(quads.shape[0], "quad", dtype=object),
        cell_blocks={"quad": quads},
    )
    interior = np.asarray(
        [vid(i, j) for i in range(1, nx - 1) for j in range(1, ny - 1)],
        dtype=np.int64,
    )
    boundary = np.setdiff1d(np.arange(nx * ny, dtype=np.int64), interior)
    return mesh, interior, boundary


def test_fixed_projected_tangential_smoother_preserves_reference_and_has_fixed_vjp():
    mesh, _, _ = _grid_strip(3, 3)
    mesh.vertices = 0.8 * (mesh.vertices - np.array([1.0, 1.0, 0.0]))
    active_ids = np.array([4], dtype=np.int64)

    recorder = csdl.Recorder(inline=True)
    recorder.start()
    surface = _plane_function_set("xy")
    metadata = [
        ProjectionMetadata(
            component=surface,
            vertex_ids=active_ids,
            allowed_patch_ids=(0,),
        )
    ]
    smoother = assemble_fixed_projected_tangential_smoother(
        mesh,
        active_ids=active_ids,
        projection_metadata=metadata,
        iterations=1,
        relaxation=0.5,
        preserve_reference=True,
    )

    reference_output = smoother.evaluate(
        csdl.Variable(value=mesh.vertices),
        projection_options={"warm_start_nu": 8, "warm_start_nv": 8},
    )
    candidate_value = mesh.vertices.copy()
    candidate_value[4] += np.array([0.4, -0.2, 0.6])
    center_x = csdl.Variable(name="smoother_center_x", value=0.4)
    center_x.set_as_design_variable()
    candidate = csdl.Variable(value=candidate_value)
    candidate = candidate.set(
        csdl.slice[4:5, 0:1],
        csdl.reshape(center_x, (1, 1)),
    )
    smoothed = smoother.evaluate(
        candidate,
        projection_options={"warm_start_nu": 8, "warm_start_nv": 8},
    )
    derivative = csdl.derivative(csdl.sum(smoothed), center_x)
    recorder.stop()

    # The reference mesh is an exact fixed point.  Only the prescribed active
    # row moves; the surrounding fixed ring remains untouched.
    np.testing.assert_allclose(reference_output.value, mesh.vertices, atol=1e-10)
    np.testing.assert_allclose(
        np.delete(smoothed.value, 4, axis=0),
        np.delete(candidate_value, 4, axis=0),
        atol=1e-12,
    )
    np.testing.assert_allclose(smoothed.value[4], [0.2, -0.1, 0.0], atol=1e-10)
    np.testing.assert_array_equal(
        smoother.fixed_neighbor_ids,
        np.array([1, 3, 5, 7], dtype=np.int64),
    )
    np.testing.assert_allclose(derivative.value, 0.5, atol=1e-10)


def test_final_only_tangential_smoother_defers_projection_and_differentiates():
    """``final_only`` skips the internal OML projection but stays differentiable.

    The active rows the smoother returns are the raw Jacobi/tangential updates
    (off the OML); a single downstream projection reproduces the
    ``every_iteration`` result and the whole path is FD-consistent.
    """

    mesh, _, _ = _grid_strip(3, 3)
    mesh.vertices = 0.8 * (mesh.vertices - np.array([1.0, 1.0, 0.0]))
    active_ids = np.array([4], dtype=np.int64)

    recorder = csdl.Recorder(inline=True)
    recorder.start()
    surface = _plane_function_set("xy")
    metadata = [
        ProjectionMetadata(
            component=surface,
            vertex_ids=active_ids,
            allowed_patch_ids=(0,),
        )
    ]
    options = {"warm_start_nu": 8, "warm_start_nv": 8}

    every = assemble_fixed_projected_tangential_smoother(
        mesh,
        active_ids=active_ids,
        projection_metadata=metadata,
        iterations=1,
        relaxation=0.5,
        preserve_reference=True,
        projection_mode="every_iteration",
    )
    final_only = assemble_fixed_projected_tangential_smoother(
        mesh,
        active_ids=active_ids,
        projection_metadata=metadata,
        iterations=1,
        relaxation=0.5,
        preserve_reference=True,
        projection_mode="final_only",
    )

    candidate_value = mesh.vertices.copy()
    candidate_value[4] += np.array([0.4, -0.2, 0.6])
    center_x = csdl.Variable(name="final_only_center_x", value=0.4)
    center_x.set_as_design_variable()
    candidate = csdl.Variable(value=candidate_value)
    candidate = candidate.set(
        csdl.slice[4:5, 0:1],
        csdl.reshape(center_x, (1, 1)),
    )

    every_smoothed = every.evaluate(candidate, projection_options=options)
    preprojected = final_only.evaluate(candidate, projection_options=options)
    # The single ordinary projection the driver performs after final_only.
    downstream = project_onto_oml(
        deformed_mesh_vertices=preprojected[csdl.slice[4:5, :]],
        deformed_mesh_vertex_ids=active_ids,
        projection_metadata=metadata,
        projection_options=options,
    )
    projected = preprojected.set(csdl.slice[4:5, :], downstream.values)
    objective = csdl.sum(projected)
    objective.set_as_objective()
    derivative = csdl.derivative(objective, center_x)
    recorder.stop()

    # final_only leaves the active row OFF the plane (z retained); the ring
    # neighbors are still untouched.
    np.testing.assert_allclose(preprojected.value[4], [0.2, -0.1, 0.6], atol=1e-10)
    np.testing.assert_allclose(
        np.delete(preprojected.value, 4, axis=0),
        np.delete(candidate_value, 4, axis=0),
        atol=1e-12,
    )
    # A single downstream projection reproduces the every_iteration result and
    # lands the active row exactly on the z=0 OML.
    np.testing.assert_allclose(projected.value[4], [0.2, -0.1, 0.0], atol=1e-8)
    np.testing.assert_allclose(
        projected.value, every_smoothed.value, atol=1e-8
    )

    simulator = csdl.experimental.JaxSimulator(recorder=recorder, gpu=False)
    check = simulator.check_optimization_derivatives(
        step_size=1e-6,
        print_results=False,
        raise_on_error=False,
    )
    relative_errors = [float(entry["rel_error"]) for entry in check.values()]
    assert relative_errors and max(relative_errors) < 1e-6


def test_fixed_symmetry_plane_constraint_overwrites_only_the_normal_coordinate():
    values = np.array(
        [
            [0.0, 0.0, 1.0],
            [1.0, 2.0e-9, 2.0],
            [2.0, 0.4, 3.0],
        ]
    )
    plane_ids = identify_symmetry_plane_vertices(
        values,
        axis=1,
        tolerance=1e-8,
    )
    np.testing.assert_array_equal(plane_ids, np.array([0, 1], dtype=np.int64))

    recorder = csdl.Recorder(inline=True)
    recorder.start()
    plane_y = csdl.Variable(name="candidate_plane_y", value=0.25)
    plane_y.set_as_design_variable()
    candidate = csdl.Variable(value=values)
    candidate = candidate.set(
        csdl.slice[0:1, 1:2],
        csdl.reshape(plane_y, (1, 1)),
    )
    constrained = enforce_symmetry_plane(
        candidate,
        vertex_ids=plane_ids,
        axis=1,
    )
    derivative = csdl.derivative(csdl.sum(constrained), plane_y)
    recorder.stop()

    np.testing.assert_allclose(constrained.value[plane_ids, 1], 0.0, atol=0.0)
    np.testing.assert_allclose(constrained.value[:, (0, 2)], values[:, (0, 2)])
    np.testing.assert_allclose(constrained.value[2, 1], values[2, 1])
    np.testing.assert_allclose(derivative.value, 0.0, atol=0.0)


def test_spd_solve_op_forward_and_adjoint_match_dense():
    rng = np.random.default_rng(0)
    n, k = 10, 3
    root = rng.standard_normal((n, n))
    dense = root @ root.T + n * np.eye(n)
    factor = factorize_spd(sp.csc_matrix(dense))
    rhs_value = rng.standard_normal((n, k))
    weights = rng.standard_normal((n, k))

    recorder = csdl.Recorder(inline=True)
    recorder.start()
    rhs = csdl.Variable(name="spd_rhs", value=rhs_value)
    rhs.set_as_design_variable()
    u_f = SPDSolveOperation(factor).evaluate(rhs)
    objective = csdl.sum(u_f * csdl.Variable(value=weights))
    objective.set_as_objective()
    d_obj = csdl.derivative(objective, rhs)
    recorder.stop()

    # Forward matches the dense solve; adjoint matches the closed form A^{-T} w.
    np.testing.assert_allclose(u_f.value, np.linalg.solve(dense, rhs_value), atol=1e-10)
    np.testing.assert_allclose(
        np.asarray(d_obj.value).reshape(n, k),
        np.linalg.solve(dense.T, weights),
        atol=1e-10,
    )


def test_harmonic_solve_reproduces_affine_field_exactly():
    # The uniform-weight (chi=0) graph Laplacian on a regular grid must
    # reproduce a prescribed affine displacement field exactly at the interior.
    mesh, free_ids, prescribed_ids = _grid_strip(7, 5)
    system = GraphLaplacianAssembler(stiffening_exponent=0.0).assemble(
        mesh, free_ids=free_ids, prescribed_ids=prescribed_ids
    )
    gradient = np.array([[0.3, -0.2, 0.0], [0.1, 0.4, 0.0], [0.0, 0.0, 0.0]])
    offset = np.array([1.5, -0.7, 0.25])
    affine = mesh.vertices @ gradient.T + offset

    u_f = system.factor.solve(-(system.coupling @ affine[prescribed_ids]))
    np.testing.assert_allclose(u_f, affine[free_ids], atol=1e-9)

    # A constant field (partition of unity) is likewise reproduced exactly.
    constant = system.factor.solve(-(system.coupling @ np.ones((system.num_prescribed, 3))))
    np.testing.assert_allclose(constant, 1.0, atol=1e-9)


def test_coupled_membrane_patch_test_and_interleaved_dofs():
    mesh, free_ids, prescribed_ids = _grid_strip(7, 5)
    system = CorotationalMembraneAssembler(
        poisson_ratio=0.4,
        normal_stabilization=0.02,
    ).assemble(
        mesh,
        free_ids=free_ids,
        prescribed_ids=prescribed_ids,
    )
    assert system.coupling.shape == (3 * free_ids.size, 3 * prescribed_ids.size)
    np.testing.assert_array_equal(
        system.active_free_dofs,
        np.arange(3 * free_ids.size, dtype=np.int64),
    )

    # A regular CST patch must reproduce an affine in-plane field.  The weak
    # 3D stabilization also reproduces the affine normal component on this
    # regular grid, while removing the membrane's out-of-plane nullspace.
    gradient = np.array(
        [[0.3, -0.2, 0.0], [0.1, 0.4, 0.0], [0.05, -0.08, 0.0]]
    )
    offset = np.array([1.5, -0.7, 0.25])
    affine = mesh.vertices @ gradient.T + offset
    rhs = -(system.coupling @ affine[prescribed_ids].reshape(-1))
    active = system.factor.solve(rhs)
    full = np.asarray(system.scatter @ active).reshape((-1, 3))
    np.testing.assert_allclose(full, affine[free_ids], atol=2e-9)


def test_coupled_membrane_can_pin_one_symmetry_component():
    mesh, free_ids, prescribed_ids = _grid_strip(5, 5)
    constrained = np.asarray((1,), dtype=np.int64)  # y DOF of free vertex row 0
    system = CorotationalMembraneAssembler(
        poisson_ratio=0.3,
        normal_stabilization=0.02,
    ).assemble(
        mesh,
        free_ids=free_ids,
        prescribed_ids=prescribed_ids,
        constrained_free_dofs=constrained,
    )
    assert system.num_active_free_dofs == 3 * free_ids.size - 1
    active = system.factor.solve(
        np.zeros(system.num_active_free_dofs, dtype=float)
    )
    full = np.asarray(system.scatter @ active).reshape(-1)
    assert full[1] == 0.0


def test_corner_barrier_repairs_quad_and_ift_vjp_matches_finite_difference():
    vertices = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]]
    )
    quad = np.array([[0, 1, 2, 3]], dtype=np.int64)
    mesh = MeshData(
        vertices=vertices,
        connectivity=quad,
        cell_types=np.array(["quad"], dtype=object),
        cell_blocks={"quad": quad},
    )
    model = CornerInversionBarrierModel(
        mesh,
        free_ids=np.array([2], dtype=np.int64),
        prescribed_ids=np.array([0, 1, 3], dtype=np.int64),
        activation_margin=0.5,
        target_margin=0.1,
        barrier_weight=5000.0,
        max_iterations=1000,
        tolerance=1e-14,
    )
    free_value = np.array([[0.2, -0.2, 0.0]])
    prescribed_value = vertices[[0, 1, 3]]
    weights = np.array([[0.3, -0.7, 0.2]])

    recorder = csdl.Recorder(inline=True)
    recorder.start()
    free = csdl.Variable(value=free_value)
    prescribed = csdl.Variable(value=prescribed_value)
    repaired = CornerInversionBarrierOperation(model).evaluate(free, prescribed)
    objective = csdl.sum(repaired * csdl.Variable(value=weights))
    d_free = csdl.derivative(objective, free)
    d_prescribed = csdl.derivative(objective, prescribed)
    recorder.stop()

    repaired_mesh = vertices.copy()
    repaired_mesh[2] = repaired.value[0]
    repaired_quality = evaluate_mesh_quality(mesh=mesh, vertices=repaired_mesh)
    assert repaired_quality.inverted_elements == 0
    assert repaired_quality.minimum_scaled_jacobian > 0.0

    def scalar(candidate_free, candidate_prescribed):
        return float(
            np.sum(model.solve(candidate_free, candidate_prescribed) * weights)
        )

    step = 1e-5
    finite_free = np.zeros_like(free_value)
    finite_prescribed = np.zeros_like(prescribed_value)
    for component in range(3):
        plus = free_value.copy()
        minus = free_value.copy()
        plus[0, component] += step
        minus[0, component] -= step
        finite_free[0, component] = (
            scalar(plus, prescribed_value) - scalar(minus, prescribed_value)
        ) / (2.0 * step)
    for row in range(prescribed_value.shape[0]):
        for component in range(3):
            plus = prescribed_value.copy()
            minus = prescribed_value.copy()
            plus[row, component] += step
            minus[row, component] -= step
            finite_prescribed[row, component] = (
                scalar(free_value, plus) - scalar(free_value, minus)
            ) / (2.0 * step)
    np.testing.assert_allclose(d_free.value, finite_free, atol=2e-7)
    np.testing.assert_allclose(
        np.asarray(d_prescribed.value).reshape(prescribed_value.shape),
        finite_prescribed,
        atol=2e-7,
    )


def test_fixed_oml_quality_repairs_on_surface_and_ift_vjp_matches_fd():
    recorder = csdl.Recorder(inline=True)
    recorder.start()
    surface = _plane_function_set("xy")
    coefficients_value = np.asarray(
        surface.functions[0].coefficients.value,
        dtype=float,
    ).reshape((-1, 3))
    baseline = np.array(
        [
            [-1.0, -1.0, 0.0],
            [1.0, -1.0, 0.0],
            [1.0, 1.0, 0.0],
            [-1.0, 1.0, 0.0],
        ]
    )
    quad = np.array([[0, 1, 2, 3]], dtype=np.int64)
    mesh = MeshData(
        vertices=baseline,
        connectivity=quad,
        cell_types=np.array(["quad"], dtype=object),
        cell_blocks={"quad": quad},
    )
    candidate_value = baseline.copy()
    candidate_value[2] = np.array([0.0, -0.5, 0.0])
    parametric_value = np.array([[0.0, 0.5, 0.25]])

    candidate = csdl.Variable(value=candidate_value)
    parametric = csdl.Variable(value=parametric_value)
    coefficients = csdl.Variable(value=coefficients_value)
    group = ParameterizedProjectionGroup(
        vertex_ids=np.array([2], dtype=np.int64),
        parametric_coordinates=parametric,
        coefficients=coefficients,
        evaluation_model=FunctionSetEvaluationModel(
            surface,
            patch_indices=(0,),
        ),
    )
    model = OMLQualityModel(
        mesh,
        quality_vertex_ids=np.array([2], dtype=np.int64),
        parameter_groups=(group,),
        barrier_weight=10.0,
        max_feasibility_iterations=500,
        max_quality_iterations=500,
        tolerance=1e-12,
    )
    repaired = OMLQualityOperation(model, (group,)).evaluate(candidate)
    weights = np.array([[0.3, -0.7, 0.2]])
    objective = csdl.sum(repaired * csdl.Variable(value=weights))
    d_candidate = np.asarray(
        csdl.derivative(objective, candidate).value,
        dtype=float,
    ).reshape(candidate_value.shape)
    recorder.stop()

    repaired_mesh = candidate_value.copy()
    repaired_mesh[2] = repaired.value[0]
    report = evaluate_mesh_quality(mesh=mesh, vertices=repaired_mesh)
    assert report.inverted_elements == 0
    assert report.minimum_scaled_jacobian > 0.0
    # The plane has z=0 everywhere: the solve moved CAD parameters, not XYZ.
    assert repaired.value[0, 2] == pytest.approx(0.0, abs=1e-13)

    def scalar(values):
        output = model.solve(
            values,
            (parametric_value,),
            (coefficients_value,),
        )
        return float(np.sum(output * weights))

    step = 2e-5
    plus = candidate_value.copy()
    minus = candidate_value.copy()
    plus[2, 0] += step
    minus[2, 0] -= step
    finite = (scalar(plus) - scalar(minus)) / (2.0 * step)
    np.testing.assert_allclose(
        d_candidate[2, 0],
        finite,
        atol=1e-6,
        rtol=1e-5,
    )

    band = select_fixed_vertex_band(
        mesh,
        seed_ids=np.array([0], dtype=np.int64),
        allowed_ids=np.arange(4, dtype=np.int64),
        excluded_ids=np.array([0], dtype=np.int64),
        element_layers=1,
    )
    np.testing.assert_array_equal(band, np.array([1, 2, 3], dtype=np.int64))


def test_elasticity_motion_solver_seam_exact_and_free_harmonic():
    # fuselage = yz plane (x=0, patch 10); wing = xy plane (z=0, patch 0) that
    # translates in z.  The seam (x=0, z=0) moves up by dz; on this uniform grid
    # the free band midway between seam (z=0) and frozen ring (z=+/-1) follows
    # harmonically to exactly dz/2.
    recorder = csdl.Recorder(inline=True)
    recorder.start()
    wing = _plane_function_set("xy", patch_id=0)
    fuselage = _plane_function_set("yz", patch_id=10)

    ys = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])
    zs = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])
    ny, nz = ys.size, zs.size
    vertices = np.array([[0.0, y, z] for y in ys for z in zs], dtype=float)

    def vid(iy, iz):
        return iy * nz + iz

    quads = np.asarray(
        [
            [vid(iy, iz), vid(iy + 1, iz), vid(iy + 1, iz + 1), vid(iy, iz + 1)]
            for iy in range(ny - 1)
            for iz in range(nz - 1)
        ],
        dtype=np.int64,
    )
    mesh = MeshData(
        vertices=vertices,
        connectivity=quads,
        cell_types=np.full(quads.shape[0], "quad", dtype=object),
        cell_blocks={"quad": quads},
    )
    parametric = np.array(
        [[10.0, (y + 1) / 2, (z + 1) / 2] for y in ys for z in zs], dtype=float
    )
    seam_ids = np.asarray([vid(iy, 2) for iy in range(ny)], dtype=np.int64)
    free_ids = np.asarray(
        [vid(iy, iz) for iy in range(ny) for iz in (1, 3)], dtype=np.int64
    )
    seam_wing_parametric = np.array([[0.0, 0.5, (y + 1) / 2] for y in ys], dtype=float)

    dz = csdl.Variable(name="dz", value=0.2)
    dz.set_as_design_variable()
    wing_coefficients = deform_geometry(
        component=wing,
        parameters=ComponentParameters(translation_z=dz, pivot=np.zeros(3)),
    )
    intersection = IntersectionParameters(
        parametric_coords=seam_wing_parametric,
        vertex_ids=seam_ids,
        driving_component=wing,
        sdf_query_component=fuselage,
        bisection_search_direction="u",
        projection_options={
            "warm_start_nu": 10,
            "warm_start_nv": 10,
            "edge_map_num_samples": 7,
        },
    )
    field = ElasticityMotionSolver(
        mesh=mesh,
        free_ids=free_ids,
        intersection_params=[intersection],
        parametric_coordinates=parametric,
        components=[wing, fuselage],
        component_reevaluations=(),
        stiffening_exponent=0.0,
    ).train(component_coeffs=[wing_coefficients])

    query_ids = np.concatenate((free_ids, seam_ids))
    deformed = field.evaluate(
        vertices=csdl.Variable(value=vertices[query_ids]),
        vertex_ids=query_ids,
    )
    derivative = csdl.derivative(csdl.sum(deformed), dz)
    recorder.stop()

    out = np.asarray(deformed.value)
    row_by_id = {int(v): r for r, v in enumerate(query_ids)}
    seam_rows = [row_by_id[int(s)] for s in seam_ids]
    free_rows = [row_by_id[int(f)] for f in free_ids]
    # Seam rows land on the deformed intersection (x=0, dz up); free band = dz/2.
    np.testing.assert_allclose(out[seam_rows, 0], 0.0, atol=1e-9)
    np.testing.assert_allclose(out[seam_rows, 2], vertices[seam_ids][:, 2] + 0.2, atol=1e-9)
    np.testing.assert_allclose(
        out[free_rows, 2] - vertices[free_ids][:, 2], 0.1, atol=1e-6
    )
    # Closed form: 5 seam rows contribute d z/d dz = 1, 10 free rows contribute
    # 0.5, so d(sum)/d(dz) = 5 + 5 = 10.
    np.testing.assert_allclose(np.asarray(derivative.value).reshape(-1)[0], 10.0, atol=1e-6)


@pytest.mark.parametrize("distortion_lambda", [0.0, 0.2])
def test_fixed_graph_load_steps_project_each_increment_and_differentiate(
    distortion_lambda,
):
    """The unrolled path retains exact seams and the fixed-factor derivative."""

    recorder = csdl.Recorder(inline=True)
    recorder.start()
    wing = _plane_function_set("xy", patch_id=0)
    fuselage = _plane_function_set("yz", patch_id=10)

    ys = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])
    zs = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])
    ny, nz = ys.size, zs.size
    vertices = np.array([[0.0, y, z] for y in ys for z in zs], dtype=float)

    def vid(iy, iz):
        return iy * nz + iz

    quads = np.asarray(
        [
            [vid(iy, iz), vid(iy + 1, iz), vid(iy + 1, iz + 1), vid(iy, iz + 1)]
            for iy in range(ny - 1)
            for iz in range(nz - 1)
        ],
        dtype=np.int64,
    )
    mesh = MeshData(
        vertices=vertices,
        connectivity=quads,
        cell_types=np.full(quads.shape[0], "quad", dtype=object),
        cell_blocks={"quad": quads},
    )
    parametric = np.array(
        [[10.0, (y + 1) / 2, (z + 1) / 2] for y in ys for z in zs],
        dtype=float,
    )
    seam_ids = np.asarray([vid(iy, 2) for iy in range(ny)], dtype=np.int64)
    free_ids = np.asarray(
        [vid(iy, iz) for iy in range(ny) for iz in (1, 3)],
        dtype=np.int64,
    )
    deformation_ids = np.concatenate((free_ids, seam_ids))
    reevaluation_ids = np.setdiff1d(np.arange(vertices.shape[0]), deformation_ids)
    seam_coordinates = np.array(
        [[0.0, 0.5, (y + 1) / 2] for y in ys],
        dtype=float,
    )

    dz = csdl.Variable(name="load_step_dz", value=0.2)
    dz.set_as_design_variable()
    fractions = (1.0 / 3.0, 2.0 / 3.0, 1.0)
    coefficient_steps = []
    for fraction in fractions:
        coefficient_steps.append(
            {
                id(wing): deform_geometry(
                    component=wing,
                    parameters=ComponentParameters(
                        translation_z=fraction * dz,
                        pivot=np.zeros(3),
                    ),
                ),
                id(fuselage): stack_component_coefficients(fuselage),
            }
        )

    intersection = IntersectionParameters(
        parametric_coords=seam_coordinates,
        vertex_ids=seam_ids,
        driving_component=wing,
        sdf_query_component=fuselage,
        bisection_search_direction="u",
        projection_options={
            "warm_start_nu": 10,
            "warm_start_nv": 10,
            "edge_map_num_samples": 7,
        },
    )
    motion = ElasticityMotionSolver(
        mesh=mesh,
        free_ids=free_ids,
        intersection_params=[intersection],
        parametric_coordinates=parametric,
        components=[wing, fuselage],
        component_reevaluations=(),
        stiffening_exponent=0.9,
        symmetry_plane_ids=np.where(np.abs(vertices[:, 1]) <= 1e-12)[0],
    )
    plane_ids = np.where(np.abs(vertices[:, 1]) <= 1e-12)[0]
    result = run_graph_load_steps(
        motion=motion,
        mesh=mesh,
        initial_deformation_vertices=vertices[deformation_ids],
        deformation_vertex_ids=deformation_ids,
        component_coefficient_steps=coefficient_steps,
        projection_metadata=[
            ProjectionMetadata(
                component=fuselage,
                vertex_ids=free_ids,
                allowed_patch_ids=(10,),
                parent_patch_ids=np.full(free_ids.size, 10),
            ),
            ProjectionMetadata(
                component=wing,
                vertex_ids=seam_ids,
                allowed_patch_ids=(0,),
                parent_patch_ids=np.zeros(seam_ids.size, dtype=np.int64),
            ),
        ],
        reevaluation_metadata=[
            VertexEvaluationMetadata(
                component=fuselage,
                vertex_ids=reevaluation_ids,
                parametric_coordinates=parametric[reevaluation_ids],
            )
        ],
        projection_options={
            "warm_start_nu": 10,
            "warm_start_nv": 10,
            "edge_map_num_samples": 7,
        },
        load_fractions=fractions,
        distortion_config=QuadraticDistortionConfig(
            lambda_dist=distortion_lambda
        ),
        symmetry_plane_vertex_ids=plane_ids,
    )
    assert isinstance(result, GraphLoadStepResult)
    objective = csdl.sum(result.final_mesh_vertices)
    derivative = csdl.derivative(objective, dz)
    objective.set_as_objective()
    recorder.stop()

    final = np.asarray(result.final_mesh_vertices.value)
    # The exact seam follows dz; the two adjacent free rows follow dz/2.
    np.testing.assert_allclose(final[seam_ids, 2], 0.2, atol=1e-8)
    np.testing.assert_allclose(
        final[free_ids, 2] - vertices[free_ids, 2],
        0.1,
        atol=1e-6,
    )
    np.testing.assert_allclose(final[plane_ids, 1], 0.0, atol=0.0)
    # Five seam rows contribute 1 and ten free rows contribute 1/2.
    np.testing.assert_allclose(
        np.asarray(derivative.value).reshape(-1)[0],
        10.0,
        atol=2e-6,
    )
    simulator = csdl.experimental.JaxSimulator(recorder=recorder, gpu=False)
    derivative_check = simulator.check_optimization_derivatives(
        step_size=1e-5,
        print_results=False,
        raise_on_error=False,
    )
    relative_errors = [
        float(entry["rel_error"]) for entry in derivative_check.values()
    ]
    assert relative_errors and max(relative_errors) < 1e-5


def test_current_area_graph_vjp_matches_finite_difference():
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [2.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.8, 0.35, 0.2],
        ]
    )
    triangles = np.array(
        [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]],
        dtype=np.int64,
    )
    mesh = MeshData(
        vertices=points,
        connectivity=triangles,
        cell_types=np.full(4, "triangle", dtype=object),
        cell_blocks={"triangle": triangles},
    )
    model = CurrentGraphModel(
        mesh,
        free_ids=np.array([4]),
        prescribed_ids=np.arange(4),
        stiffening_exponent=0.9,
    )
    prescribed = np.array(
        [[0.2, -0.1], [0.3, 0.4], [-0.2, 0.1], [0.5, -0.3]]
    )
    cotangent = np.array([[0.7, -0.4]])
    d_points, d_prescribed = model.compute_vjp(
        points,
        prescribed,
        cotangent,
    )

    def objective(current_points, current_prescribed):
        return float(
            np.sum(
                model.solve(current_points, current_prescribed) * cotangent
            )
        )

    step = 1e-6
    fd_points = np.zeros_like(points)
    for index in np.ndindex(points.shape):
        plus = points.copy()
        minus = points.copy()
        plus[index] += step
        minus[index] -= step
        fd_points[index] = (
            objective(plus, prescribed) - objective(minus, prescribed)
        ) / (2.0 * step)
    fd_prescribed = np.zeros_like(prescribed)
    for index in np.ndindex(prescribed.shape):
        plus = prescribed.copy()
        minus = prescribed.copy()
        plus[index] += step
        minus[index] -= step
        fd_prescribed[index] = (
            objective(points, plus) - objective(points, minus)
        ) / (2.0 * step)

    np.testing.assert_allclose(d_points, fd_points, rtol=2e-7, atol=2e-9)
    np.testing.assert_allclose(
        d_prescribed,
        fd_prescribed,
        rtol=2e-7,
        atol=2e-9,
    )


def _distance_fan_mesh():
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [2.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.8, 0.35, 0.2],
        ]
    )
    triangles = np.array(
        [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]],
        dtype=np.int64,
    )
    mesh = MeshData(
        vertices=points,
        connectivity=triangles,
        cell_types=np.full(4, "triangle", dtype=object),
        cell_blocks={"triangle": triangles},
    )
    return mesh, points


def test_graph_distance_weighting_geodesic_and_bounds():
    mesh, points = _distance_fan_mesh()
    distance = compute_multisource_geodesic_distance(mesh, np.array([0]))
    # Physical edge-length geodesic from vertex 0 (not edge-count).
    np.testing.assert_allclose(distance[0], 0.0, atol=0.0)
    np.testing.assert_allclose(distance[1], 2.0, atol=1e-12)
    np.testing.assert_allclose(distance[3], 1.0, atol=1e-12)
    assert 0.0 < distance[4] < 1.0

    weighting = build_graph_distance_weighting(
        mesh, np.array([0]), beta=1.5, length=1.0, cap=2.0
    )
    edges = np.array([[0, 1], [3, 0], [1, 4]], dtype=np.int64)
    multipliers = weighting.edge_multipliers(edges)
    # Every multiplier stays in [1, cap]; the near-seed edge is stiffer.
    assert np.all(multipliers >= 1.0) and np.all(multipliers <= 2.0)
    assert multipliers[1] > multipliers[0]  # closer edge -> larger multiplier

    # An unreachable vertex (restricted out) keeps the far-field multiplier 1.
    restricted = compute_multisource_geodesic_distance(
        mesh, np.array([0]), restrict_vertex_ids=np.array([0, 1, 4])
    )
    assert not np.isfinite(restricted[3])
    isolated = build_graph_distance_weighting(
        mesh, np.array([0]), beta=1.5, length=1.0,
        restrict_vertex_ids=np.array([0, 1, 4]),
    )
    np.testing.assert_allclose(
        isolated.edge_multipliers(np.array([[2, 3]])), 1.0, atol=0.0
    )


def test_graph_distance_weighting_beta_zero_is_exact_noop():
    mesh, points = _distance_fan_mesh()
    free_ids = np.array([4])
    prescribed_ids = np.arange(4)
    prescribed = np.array([[0.2, -0.1], [0.3, 0.4], [-0.2, 0.1], [0.5, -0.3]])

    zero = build_graph_distance_weighting(mesh, np.array([0]), beta=0.0, length=1.0)
    baseline = CurrentGraphModel(
        mesh, free_ids=free_ids, prescribed_ids=prescribed_ids,
        stiffening_exponent=0.9,
    )
    weighted = CurrentGraphModel(
        mesh, free_ids=free_ids, prescribed_ids=prescribed_ids,
        stiffening_exponent=0.9, distance_weighting=zero,
    )
    np.testing.assert_allclose(
        weighted.solve(points, prescribed),
        baseline.solve(points, prescribed),
        atol=0.0,
    )

    # The fixed-reference assembler is also an exact no-op at beta=0.
    mesh7, free7, prescribed7 = _grid_strip(7, 5)
    zero7 = build_graph_distance_weighting(
        mesh7, np.array([free7[0]]), beta=0.0, length=1.0
    )
    base_system = GraphLaplacianAssembler(stiffening_exponent=0.7).assemble(
        mesh7, free_ids=free7, prescribed_ids=prescribed7
    )
    weighted_system = GraphLaplacianAssembler(
        stiffening_exponent=0.7, distance_weighting=zero7
    ).assemble(mesh7, free_ids=free7, prescribed_ids=prescribed7)
    rhs = np.ones((base_system.num_prescribed, 3))
    np.testing.assert_allclose(
        weighted_system.factor.solve(-(weighted_system.coupling @ rhs)),
        base_system.factor.solve(-(base_system.coupling @ rhs)),
        atol=1e-12,
    )


def test_distance_weighted_current_area_graph_vjp_matches_finite_difference():
    mesh, points = _distance_fan_mesh()
    weighting = build_graph_distance_weighting(
        mesh, np.array([0]), beta=1.5, length=1.0, cap=3.0
    )
    model = CurrentGraphModel(
        mesh,
        free_ids=np.array([4]),
        prescribed_ids=np.arange(4),
        stiffening_exponent=0.9,
        distance_weighting=weighting,
    )
    prescribed = np.array([[0.2, -0.1], [0.3, 0.4], [-0.2, 0.1], [0.5, -0.3]])
    cotangent = np.array([[0.7, -0.4]])
    d_points, d_prescribed = model.compute_vjp(points, prescribed, cotangent)

    def objective(current_points, current_prescribed):
        return float(
            np.sum(model.solve(current_points, current_prescribed) * cotangent)
        )

    step = 1e-6
    fd_points = np.zeros_like(points)
    for index in np.ndindex(points.shape):
        plus = points.copy()
        minus = points.copy()
        plus[index] += step
        minus[index] -= step
        fd_points[index] = (
            objective(plus, prescribed) - objective(minus, prescribed)
        ) / (2.0 * step)
    fd_prescribed = np.zeros_like(prescribed)
    for index in np.ndindex(prescribed.shape):
        plus = prescribed.copy()
        minus = prescribed.copy()
        plus[index] += step
        minus[index] -= step
        fd_prescribed[index] = (
            objective(points, plus) - objective(points, minus)
        ) / (2.0 * step)

    np.testing.assert_allclose(d_points, fd_points, rtol=2e-6, atol=2e-9)
    np.testing.assert_allclose(d_prescribed, fd_prescribed, rtol=2e-7, atol=2e-9)


def test_distance_weighted_fixed_reference_graph_solve_differentiates():
    """The fixed-reference distance-weighted SPD solve stays FD-consistent."""

    mesh, free_ids, prescribed_ids = _grid_strip(7, 5)
    weighting = build_graph_distance_weighting(
        mesh, np.array([prescribed_ids[0]]), beta=2.0, length=1.5, cap=4.0
    )
    system = GraphLaplacianAssembler(
        stiffening_exponent=0.8, distance_weighting=weighting
    ).assemble(mesh, free_ids=free_ids, prescribed_ids=prescribed_ids)

    prescribed_value = mesh.vertices[prescribed_ids] * 0.0
    prescribed_value[:, 2] = 0.1 * np.arange(prescribed_ids.size)

    recorder = csdl.Recorder(inline=True)
    recorder.start()
    u_p = csdl.Variable(name="distance_prescribed", value=prescribed_value)
    u_p.set_as_design_variable()
    rhs = -csdl.sparse.matmat(
        system.coupling.tocsr(), u_p
    )
    u_f = SPDSolveOperation(system.factor).evaluate(rhs)
    objective = csdl.sum(u_f)
    objective.set_as_objective()
    recorder.stop()

    simulator = csdl.experimental.JaxSimulator(recorder=recorder, gpu=False)
    check = simulator.check_optimization_derivatives(
        step_size=1e-6, print_results=False, raise_on_error=False
    )
    relative_errors = [float(entry["rel_error"]) for entry in check.values()]
    assert relative_errors and max(relative_errors) < 1e-6


@pytest.mark.parametrize("mode", ["full_gradient", "strain_distortion"])
def test_quadratic_distortion_mixed_polygons_psd_patch_and_hourglass(mode):
    polygons = (
        np.array([[0.0, 0.0], [1.0, 0.0], [0.2, 0.9]]),
        np.array([[2.0, 0.0], [3.0, 0.0], [3.0, 1.0], [2.0, 1.0]]),
        # A fixed nonconvex pentagon exercises the ear-clipping fallback.
        np.array(
            [[4.0, 0.0], [6.0, 0.0], [5.0, 0.4], [6.0, 1.0], [4.0, 1.0]]
        ),
        np.array(
            [
                [7.0, 0.0],
                [8.0, 0.0],
                [8.5, 0.5],
                [8.0, 1.0],
                [7.0, 1.0],
                [6.5, 0.5],
            ]
        ),
    )
    vertices = []
    cell_blocks = {}
    offset = 0
    names = ("triangle", "quad", "polygon5", "polygon6")
    connectivity = []
    for name, polygon in zip(names, polygons):
        ids = np.arange(offset, offset + polygon.shape[0], dtype=np.int64)
        vertices.extend(np.column_stack((polygon, np.zeros(polygon.shape[0]))))
        cell_blocks[name] = ids.reshape((1, -1))
        connectivity.append(ids)
        offset += polygon.shape[0]
    mesh = MeshData(
        vertices=np.asarray(vertices),
        connectivity=np.asarray(connectivity, dtype=object),
        cell_types=np.asarray(names, dtype=object),
        cell_blocks=cell_blocks,
    )
    system = QuadraticDistortionAssembler(
        QuadraticDistortionConfig(
            lambda_dist=1.0,
            mode=mode,
            coefficients=DistortionModeCoefficients(normal=0.5),
        )
    ).assemble(
        mesh,
        free_ids=np.arange(offset, dtype=np.int64),
        prescribed_ids=np.empty(0, dtype=np.int64),
        retain_records=True,
    )
    matrix = system.full_matrix()
    np.testing.assert_allclose(
        (matrix - matrix.T).data,
        0.0,
        atol=1e-13,
    )
    rng = np.random.default_rng(4)
    for _ in range(10):
        vector = rng.standard_normal(3 * offset)
        assert float(vector @ (matrix @ vector)) >= -1e-10

    translation = np.tile(np.array([0.2, -0.4, 0.7]), offset)
    np.testing.assert_allclose(matrix @ translation, 0.0, atol=2e-12)
    assert system.num_ear_clipped == 1
    assert system.num_centroid_fans == 2

    # The fixed fan sees an alternating normal hourglass on the quad.
    quad_ids = cell_blocks["quad"][0]
    hourglass = np.zeros((offset, 3))
    hourglass[quad_ids, 2] = np.array([1.0, -1.0, 1.0, -1.0])
    assert float(hourglass.reshape(-1) @ (matrix @ hourglass.reshape(-1))) > 0.1

    # Every virtual triangle exactly differentiates an affine correction.
    affine_gradient = np.array(
        [[0.3, -0.2, 0.0], [0.1, 0.4, 0.0], [0.05, -0.08, 0.0]]
    )
    for record in system.records:
        element_points = mesh.vertices[record.node_ids]
        element_values = element_points @ affine_gradient.T
        for subtriangle in record.subtriangles:
            computed = element_values.T @ subtriangle.gradient_map
            expected = affine_gradient @ subtriangle.local_frame[:, :2]
            np.testing.assert_allclose(computed, expected, atol=2e-12)


def test_current_graph_distortion_vjp_matches_finite_difference():
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 1.0, 0.15],
            [2.0, 1.0, 0.0],
            [0.0, 2.0, 0.0],
            [1.0, 2.0, 0.0],
            [2.0, 2.0, 0.0],
        ]
    )
    quads = np.array(
        [[0, 1, 4, 3], [1, 2, 5, 4], [3, 4, 7, 6], [4, 5, 8, 7]],
        dtype=np.int64,
    )
    mesh = MeshData(
        vertices=points,
        connectivity=quads,
        cell_types=np.full(4, "quad", dtype=object),
        cell_blocks={"quad": quads},
    )
    free_ids = np.array([4], dtype=np.int64)
    prescribed_ids = element_neighbors(mesh, free_ids)
    graph = CurrentGraphModel(
        mesh,
        free_ids=free_ids,
        prescribed_ids=prescribed_ids,
        stiffening_exponent=0.9,
    )
    config = QuadraticDistortionConfig(lambda_dist=0.3)
    distortion = QuadraticDistortionAssembler(config).assemble(
        mesh,
        free_ids=free_ids,
        prescribed_ids=prescribed_ids,
    )
    model = CurrentGraphDistortionModel(
        graph,
        distortion,
        lambda_dist=config.lambda_dist,
        baseline_vertices=points,
    )
    rng = np.random.default_rng(12)
    incremental = rng.normal(scale=0.08, size=(prescribed_ids.size, 6))
    current_free = rng.normal(scale=0.04, size=(free_ids.size, 6))
    total_prescribed = rng.normal(scale=0.1, size=(prescribed_ids.size, 6))
    cotangent = rng.normal(size=(free_ids.size, 6))
    derivatives = model.compute_vjp(
        points,
        incremental,
        current_free,
        total_prescribed,
        cotangent,
    )

    def objective(current_points, inc, current, total):
        return float(
            np.sum(model.solve(current_points, inc, current, total) * cotangent)
        )

    inputs = (points, incremental, current_free, total_prescribed)
    step = 1e-6
    for input_index, (value, analytic) in enumerate(zip(inputs, derivatives)):
        finite_difference = np.zeros_like(value)
        for index in np.ndindex(value.shape):
            plus = [item.copy() for item in inputs]
            minus = [item.copy() for item in inputs]
            plus[input_index][index] += step
            minus[input_index][index] -= step
            finite_difference[index] = (
                objective(*plus) - objective(*minus)
            ) / (2.0 * step)
        np.testing.assert_allclose(
            analytic,
            finite_difference,
            rtol=2e-6,
            atol=2e-8,
        )


def test_select_free_vertices_and_of_slabs():
    wing = object()
    fuselage = object()
    vertices = np.array(
        [
            [0.0, -2.0, 0.0],  # 0 wing |y|/2 = 1.00 -> prescribed
            [0.0, -1.0, 0.0],  # 1 wing 0.50 -> prescribed (upper is exclusive)
            [0.0, -0.5, 0.0],  # 2 wing 0.25 -> free
            [0.0, 0.0, 0.0],   # 3 wing 0.00 -> free (excluded below as 'seam')
            [0.0, 1.5, 0.0],   # 4 wing 0.75 -> prescribed
            [0.0, 0.0, 0.0],   # 5 fuse x=0  t=0.0  -> prescribed
            [1.0, 0.0, 0.0],   # 6 fuse x=1  t=0.1  -> free (inclusive lower)
            [5.0, 0.0, 0.0],   # 7 fuse x=5  t=0.5  -> free
            [9.0, 0.0, 0.0],   # 8 fuse x=9  t=0.9  -> free
            [10.0, 0.0, 0.0],  # 9 fuse x=10 t=1.0  -> prescribed
        ]
    )
    free = select_free_vertices(
        free_regions=[
            ComponentFreeRegion(component=wing, y=AxisRange(upper=0.5, mode="abs")),
            ComponentFreeRegion(
                component=fuselage, x=AxisRange(lower=0.1, upper=0.95, mode="extent")
            ),
        ],
        component_vertex_ids={
            id(wing): np.array([0, 1, 2, 3, 4]),
            id(fuselage): np.array([5, 6, 7, 8, 9]),
        },
        mesh_vertices=vertices,
        exclude_ids=[3],
    )
    np.testing.assert_array_equal(free, np.array([2, 6, 7, 8]))


def test_elasticity_free_band_may_span_components():
    # T-shaped mesh: fuselage yz-plane (x=0, patch 10) and wing xy-plane
    # (z=0, patch 0) sharing the seam line x=0,z=0.  Wing translates in z.  The
    # wing free band's far ring moves WITH the wing (frozen owner picked by
    # patch), so it follows to dz; the fuselage free band blends harmonically to
    # dz/2 against its stationary far ring.
    recorder = csdl.Recorder(inline=True)
    recorder.start()
    wing = _plane_function_set("xy", patch_id=0)
    fuselage = _plane_function_set("yz", patch_id=10)

    grid = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])
    coord_to_id: dict[tuple, int] = {}
    coords: list[np.ndarray] = []

    def get_id(point):
        key = tuple(np.round(point, 6))
        if key not in coord_to_id:
            coord_to_id[key] = len(coords)
            coords.append(np.asarray(point, dtype=float))
        return coord_to_id[key]

    fuse_vid = {
        (iy, iz): get_id((0.0, y, z))
        for iy, y in enumerate(grid)
        for iz, z in enumerate(grid)
    }
    wing_vid = {
        (ix, iy): get_id((x, y, 0.0))
        for ix, x in enumerate(grid)
        for iy, y in enumerate(grid)
    }
    vertices = np.asarray(coords, dtype=float)

    quads = [
        [fuse_vid[(iy, iz)], fuse_vid[(iy + 1, iz)], fuse_vid[(iy + 1, iz + 1)], fuse_vid[(iy, iz + 1)]]
        for iy in range(4)
        for iz in range(4)
    ] + [
        [wing_vid[(ix, iy)], wing_vid[(ix + 1, iy)], wing_vid[(ix + 1, iy + 1)], wing_vid[(ix, iy + 1)]]
        for ix in range(4)
        for iy in range(4)
    ]
    quads = np.asarray(quads, dtype=np.int64)
    mesh = MeshData(
        vertices=vertices,
        connectivity=quads,
        cell_types=np.full(quads.shape[0], "quad", dtype=object),
        cell_blocks={"quad": quads},
    )

    parametric = np.zeros((vertices.shape[0], 3))
    for (iy, iz), vid in fuse_vid.items():
        parametric[vid] = [10.0, (grid[iy] + 1) / 2, (grid[iz] + 1) / 2]
    for (ix, iy), vid in wing_vid.items():
        if abs(grid[ix]) > 1e-9:  # keep the fuselage owner on the shared seam column
            parametric[vid] = [0.0, (grid[ix] + 1) / 2, (grid[iy] + 1) / 2]

    seam_ids = np.array([fuse_vid[(iy, 2)] for iy in range(5)], dtype=np.int64)
    wing_owned = np.array(
        sorted({v for (ix, _), v in wing_vid.items() if abs(grid[ix]) > 1e-9}), dtype=np.int64
    )
    fuse_owned = np.array(
        sorted({v for (_, iz), v in fuse_vid.items() if abs(grid[iz]) > 1e-9}), dtype=np.int64
    )
    free_ids = select_free_vertices(
        free_regions=[
            ComponentFreeRegion(component=wing, x=AxisRange(upper=0.75, mode="abs")),
            ComponentFreeRegion(component=fuselage, z=AxisRange(upper=0.75, mode="abs")),
        ],
        component_vertex_ids={id(wing): wing_owned, id(fuselage): fuse_owned},
        mesh_vertices=vertices,
        exclude_ids=seam_ids,
    )

    dz = csdl.Variable(name="dz_multi", value=0.2)
    dz.set_as_design_variable()
    wing_coefficients = deform_geometry(
        component=wing,
        parameters=ComponentParameters(translation_z=dz, pivot=np.zeros(3)),
    )
    intersection = IntersectionParameters(
        parametric_coords=np.array([[0.0, 0.5, (y + 1) / 2] for y in grid], dtype=float),
        vertex_ids=seam_ids,
        driving_component=wing,
        sdf_query_component=fuselage,
        bisection_search_direction="u",
        projection_options={"warm_start_nu": 10, "warm_start_nv": 10, "edge_map_num_samples": 7},
    )
    field = ElasticityMotionSolver(
        mesh=mesh,
        free_ids=free_ids,
        intersection_params=[intersection],
        parametric_coordinates=parametric,
        components=[wing, fuselage],
        component_reevaluations=(),
        stiffening_exponent=0.0,
    ).train(component_coeffs=[wing_coefficients])

    query_ids = np.concatenate((free_ids, seam_ids))
    deformed = field.evaluate(
        vertices=csdl.Variable(value=vertices[query_ids]), vertex_ids=query_ids
    )
    recorder.stop()

    out = np.asarray(deformed.value)
    row = {int(v): r for r, v in enumerate(query_ids)}
    wing_free = np.intersect1d(free_ids, wing_owned)
    fuse_free = np.intersect1d(free_ids, fuse_owned)
    seam_dz = out[[row[int(i)] for i in seam_ids], 2] - vertices[seam_ids][:, 2]
    wing_dz = out[[row[int(i)] for i in wing_free], 2] - vertices[wing_free][:, 2]
    fuse_dz = out[[row[int(i)] for i in fuse_free], 2] - vertices[fuse_free][:, 2]
    np.testing.assert_allclose(seam_dz, 0.2, atol=1e-6)
    np.testing.assert_allclose(wing_dz, 0.2, atol=1e-6)   # follows the moving wing far ring
    np.testing.assert_allclose(fuse_dz, 0.1, atol=1e-6)   # harmonic to the stationary ring


def test_allowed_patch_subset_projection_matches_parent_patch_path():
    """A strict ``allowed_patch_ids`` subset must project like the parent path.

    ``FunctionSetProjectionModel`` lays out its coefficient offsets over the
    *selected* patches only, so restricting to a subset requires handing it the
    matching coefficient subset.  Passing the full component stack silently
    misaligns every patch and projects onto the wrong surface.
    """

    recorder = csdl.Recorder(inline=True)
    recorder.start()
    # two disjoint parallel planes, patch 0 at z=0 and patch 1 at z=1
    lower = _plane_function_set("xy", patch_id=0, z_offset=0.0)
    upper = _plane_function_set("xy", patch_id=1, z_offset=1.0)
    component = lfs.FunctionSet(
        functions={0: lower.functions[0], 1: upper.functions[1]}
    )
    coefficients = stack_component_coefficients(component)

    points = np.array([[0.2, 0.1, 0.7], [-0.3, 0.4, 0.9], [0.5, -0.2, 0.8]])
    ids = np.arange(points.shape[0])
    options = {"warm_start_nu": 10, "warm_start_nv": 10, "edge_map_num_samples": 7}

    def project(metadata):
        return np.asarray(
            project_onto_oml(
                deformed_mesh_vertices=csdl.Variable(value=points),
                deformed_mesh_vertex_ids=ids,
                projection_metadata=[metadata],
                component_coefficients={id(component): coefficients},
                projection_options=options,
            ).values.value
        )

    # known-good route: parent-patch restriction (subsets coefficients itself)
    parent = project(
        ProjectionMetadata(
            component=component,
            vertex_ids=ids,
            allowed_patch_ids=(0, 1),
            parent_patch_ids=np.full(points.shape[0], 1),
        )
    )
    # route under test: a strict allowed_patch_ids subset
    subset = project(
        ProjectionMetadata(
            component=component,
            vertex_ids=ids,
            allowed_patch_ids=(1,),
            parent_patch_ids=None,
        )
    )
    recorder.stop()

    np.testing.assert_allclose(subset, parent, atol=1e-9)
    # and it really landed on patch 1 (z=1), not the nearer-in-index patch 0
    np.testing.assert_allclose(subset[:, 2], 1.0, atol=1e-9)


def test_classify_patch_sides_separates_skins_and_excludes_caps():
    recorder = csdl.Recorder(inline=True)
    recorder.start()
    knots = (np.array([0.0, 0.0, 1.0, 1.0]),) * 2
    space = lfs.BSplineSpaceNew(
        num_parametric_dimensions=2, degree=(1, 1), coefficients_shape=(2, 2), knots=knots
    )
    u, v = np.meshgrid([0.0, 1.0], [0.0, 1.0], indexing="ij")

    def patch(z_sign, span_scale):
        # span along y; z_sign flips the control-net normal (upper vs lower skin)
        coefficients = np.stack(
            (2.0 * u - 1.0, span_scale * (2.0 * v - 1.0), z_sign * 0.1 * np.ones_like(u)),
            axis=-1,
        )
        if z_sign < 0:  # reverse a parametric direction to flip the normal
            coefficients = coefficients[::-1]
        return lfs.Function(space=space, coefficients=coefficients)

    component = lfs.FunctionSet(
        functions={0: patch(+1, 1.0), 1: patch(-1, 1.0), 2: patch(+1, 0.01)}
    )
    sides = classify_patch_sides(component, axis=2, span_axis=1)
    recorder.stop()

    assert sides[0] == -sides[1] != 0, "the two skins must land on opposite sides"
    assert sides[2] == 0, "the short-span end cap must be excluded"


def _symmetric_grid(nx=4, ny_half=2):
    """Flat quad grid symmetric about y=0, with a node row exactly on y=0."""

    xs = np.arange(nx, dtype=float)
    ys = np.arange(-ny_half, ny_half + 1, dtype=float)
    vertices = np.array([[x, y, 0.0] for x in xs for y in ys], dtype=float)

    def vid(i, j):
        return i * ys.size + j

    quads = np.asarray(
        [
            [vid(i, j), vid(i + 1, j), vid(i + 1, j + 1), vid(i, j + 1)]
            for i in range(nx - 1)
            for j in range(ys.size - 1)
        ],
        dtype=np.int64,
    )
    return MeshData(
        vertices=vertices,
        connectivity=quads,
        cell_types=np.full(quads.shape[0], "quad", dtype=object),
        cell_blocks={"quad": quads},
    )


def test_symmetry_split_and_reconstruct_round_trip():
    mesh = _symmetric_grid()
    assert detect_symmetry(mesh) is True

    split = split_symmetric_mesh(mesh)
    vertices = np.asarray(mesh.vertices, dtype=float)
    # kept half is y >= 0 (three of the five rows), plane row is y == 0
    assert split.half_to_full.size == 3 * 4
    assert split.plane_local_ids.size == 4
    np.testing.assert_allclose(
        np.asarray(split.half_mesh.vertices)[split.plane_local_ids][:, 1], 0.0
    )

    recorder = csdl.Recorder(inline=True)
    recorder.start()
    rebuilt = reconstruct_full_from_half(
        csdl.Variable(value=np.asarray(split.half_mesh.vertices, dtype=float)), split
    )
    recorder.stop()
    # mirroring the undeformed half must reproduce the original full mesh
    np.testing.assert_allclose(np.asarray(rebuilt.value), vertices, atol=1e-12)


def test_symmetry_reconstruct_mirrors_a_half_displacement():
    mesh = _symmetric_grid()
    split = split_symmetric_mesh(mesh)
    half = np.asarray(split.half_mesh.vertices, dtype=float).copy()
    # push the half outboard in y and up in z
    half[:, 1] += 0.25 * half[:, 1]
    half[:, 2] += 0.1

    recorder = csdl.Recorder(inline=True)
    recorder.start()
    full = reconstruct_full_from_half(csdl.Variable(value=half), split)
    recorder.stop()
    full_value = np.asarray(full.value)

    # the result is exactly mirror-symmetric and the plane stays on y=0
    mirrored = full_value.copy()
    mirrored[:, 1] *= -1.0
    order = np.lexsort((full_value[:, 2], full_value[:, 1], full_value[:, 0]))
    mirror_order = np.lexsort((mirrored[:, 2], mirrored[:, 1], mirrored[:, 0]))
    np.testing.assert_allclose(full_value[order], mirrored[mirror_order], atol=1e-12)
    plane = np.abs(np.asarray(mesh.vertices)[:, 1]) < 1e-12
    np.testing.assert_allclose(full_value[plane, 1], 0.0, atol=1e-12)
