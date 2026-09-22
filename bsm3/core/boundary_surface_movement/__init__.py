"""Reusable differentiable boundary-surface mesh movement.

The public API separates setup-time topology detection (in
``bsm3.preprocessing``) from differentiable CSDL operations.  Component
intersections are recomputed with an implicit bracketed solve, a swappable
propagation strategy carries their displacements into the mesh interior, and
final vertices are projected to explicit component/patch restrictions.

Propagation is a strategy: ``RBFMotionSolver`` wraps the meshless RBF field and
``ElasticityMotionSolver`` is the reference-config graph-Laplacian / edge-spring
solve; ``CorotationalMembraneMotionSolver`` adds the coupled membrane/barrier
path.  All implement the ``MeshMotionSolver`` / ``MeshMotionField`` contract.
"""

from .elasticity import (
    AssembledSystem,
    CorotationalMembraneAssembler,
    CoupledAssembledSystem,
    GraphLaplacianAssembler,
    StiffnessAssembler,
    element_neighbors,
    graph_neighbors,
)
from .constraints import (
    enforce_symmetry_plane,
    identify_symmetry_plane_vertices,
)
from .dafoam_csdl import (
    DAFoamAnalysisOperation,
    DAFoamAnalysisVJP,
    DAFoamBackend,
    PYDAFoamBackend,
    add_csdl_inputs_to_da_options,
    build_local_volume_coordinate_map,
    make_patch_velocity,
)
from .current_graph_solve import (
    CurrentGraphModel,
    CurrentGraphSolveOperation,
    CurrentGraphSolveVJP,
)
from .free_region import (
    AxisRange,
    ComponentFreeRegion,
    select_free_vertices,
)
from .geometry import (
    classify_patch_sides,
    component_patch_ids,
    deform_geometry,
    stack_component_coefficients,
    stack_component_coefficients_numpy,
)
from .graph_distance import (
    GraphDistanceWeighting,
    build_graph_distance_weighting,
    compute_multisource_geodesic_distance,
)
from .motion import (
    ComponentReevaluation,
    CorotationalMembraneMotionSolver,
    ElasticityMotionField,
    ElasticityMotionSolver,
    GraphLoadStepState,
    MeshMotionField,
    MeshMotionSolver,
    RBFMotionSolver,
)
from .intersections import (
    IntersectionParameters,
    IntersectionSolution,
    solve_intersection,
)
from .load_stepping import (
    GraphLoadStepResult,
    linear_load_fractions,
    run_graph_load_steps,
)
from .tangential_smoothing import (
    FixedProjectedTangentialSmoother,
    assemble_fixed_projected_tangential_smoother,
)
from .quadratic_distortion import (
    CurrentGraphDistortionModel,
    CurrentGraphDistortionSolveOperation,
    CurrentGraphDistortionSolveVJP,
    DistortionModeCoefficients,
    ElementRecord,
    QuadraticDistortionAssembler,
    QuadraticDistortionConfig,
    QuadraticDistortionSystem,
    SubtriangleRecord,
)
from .ngon_affine import (
    CurrentGraphNgonAffineModel,
    CurrentGraphNgonAffineSolveOperation,
    CurrentGraphNgonAffineSolveVJP,
    NgonAffineAssembler,
    NgonAffineConfig,
    NgonAffineSystem,
)
from .inversion_barrier import (
    BarrierSolveInfo,
    CornerInversionBarrierModel,
    CornerInversionBarrierOperation,
    CornerInversionBarrierVJP,
    FallbackCornerInversionBarrierOperation,
    FallbackCornerInversionBarrierVJP,
)
from .projection import (
    ParameterizedProjection,
    ParameterizedProjectionGroup,
    VertexBatch,
    combine_vertices,
    project_onto_oml,
    project_onto_oml_parameterized,
    reevaluate_vertices,
)
from .oml_quality import (
    OMLQualityModel,
    OMLQualityOperation,
    OMLQualitySolveInfo,
    OMLQualityVJP,
    optimize_mesh_on_oml,
    select_fixed_vertex_band,
)
from .quality import (
    ElementInversionReport,
    MeshQualityReport,
    check_element_inversion,
    compare_mesh_quality,
    evaluate_mesh_quality,
)
from .rbf import (
    ComponentDisplacementData,
    DisplacementInterpolationParameters,
    DisplacementInterpolator,
    DisplacementSurrogate,
)
from .spd_solve_custom_op import (
    SPDFactor,
    SPDSolveOperation,
    SPDSolveVJP,
    factorize_spd,
)
from .volume_mesh_motion import (
    ElasticVolumeSystem,
    GraphVolumeSystem,
    LoadStepRecord,
    LoadSteppedVolumeResult,
    TetraVolumeMesh,
    VolumeBoundaryPartition,
    VolumeQualityReport,
    WallPositionHistory,
    assemble_elastic_volume_system,
    assemble_graph_volume_system,
    evaluate_gmsh_tetra_quality,
    evaluate_volume_quality,
    extract_aircraft_wall_mesh,
    load_wall_to_volume_map,
    make_boundary_partition,
    read_gmsh22_volume,
    read_wall_position_history,
    run_forward_volume_load_steps,
    write_comparison_summary,
    write_aircraft_wall_gmsh22,
    write_deformed_gmsh22,
    write_wall_position_history,
)

__all__ = [
    "AssembledSystem",
    "AxisRange",
    "BarrierSolveInfo",
    "ComponentDisplacementData",
    "ComponentFreeRegion",
    "ComponentReevaluation",
    "CorotationalMembraneAssembler",
    "CorotationalMembraneMotionSolver",
    "CurrentGraphNgonAffineModel",
    "CurrentGraphNgonAffineSolveOperation",
    "CurrentGraphNgonAffineSolveVJP",
    "CurrentGraphModel",
    "CurrentGraphSolveOperation",
    "CurrentGraphSolveVJP",
    "DAFoamAnalysisOperation",
    "DAFoamAnalysisVJP",
    "DAFoamBackend",
    "CornerInversionBarrierModel",
    "CornerInversionBarrierOperation",
    "CornerInversionBarrierVJP",
    "CoupledAssembledSystem",
    "DisplacementInterpolationParameters",
    "DisplacementInterpolator",
    "DisplacementSurrogate",
    "ElasticVolumeSystem",
    "ElasticityMotionField",
    "ElasticityMotionSolver",
    "ElementInversionReport",
    "GraphDistanceWeighting",
    "GraphVolumeSystem",
    "GraphLaplacianAssembler",
    "GraphLoadStepResult",
    "GraphLoadStepState",
    "IntersectionParameters",
    "IntersectionSolution",
    "LoadStepRecord",
    "LoadSteppedVolumeResult",
    "MeshMotionField",
    "MeshMotionSolver",
    "MeshQualityReport",
    "NgonAffineAssembler",
    "NgonAffineConfig",
    "NgonAffineSystem",
    "OMLQualityModel",
    "OMLQualityOperation",
    "OMLQualitySolveInfo",
    "OMLQualityVJP",
    "ParameterizedProjection",
    "ParameterizedProjectionGroup",
    "PYDAFoamBackend",
    "FallbackCornerInversionBarrierOperation",
    "FallbackCornerInversionBarrierVJP",
    "FixedProjectedTangentialSmoother",
    "RBFMotionSolver",
    "SPDFactor",
    "SPDSolveOperation",
    "SPDSolveVJP",
    "StiffnessAssembler",
    "TetraVolumeMesh",
    "VertexBatch",
    "VolumeBoundaryPartition",
    "VolumeQualityReport",
    "WallPositionHistory",
    "assemble_elastic_volume_system",
    "assemble_graph_volume_system",
    "assemble_fixed_projected_tangential_smoother",
    "add_csdl_inputs_to_da_options",
    "build_graph_distance_weighting",
    "build_local_volume_coordinate_map",
    "check_element_inversion",
    "compute_multisource_geodesic_distance",
    "classify_patch_sides",
    "combine_vertices",
    "compare_mesh_quality",
    "component_patch_ids",
    "deform_geometry",
    "evaluate_mesh_quality",
    "evaluate_gmsh_tetra_quality",
    "evaluate_volume_quality",
    "element_neighbors",
    "enforce_symmetry_plane",
    "extract_aircraft_wall_mesh",
    "factorize_spd",
    "graph_neighbors",
    "identify_symmetry_plane_vertices",
    "linear_load_fractions",
    "load_wall_to_volume_map",
    "make_boundary_partition",
    "make_patch_velocity",
    "optimize_mesh_on_oml",
    "project_onto_oml",
    "project_onto_oml_parameterized",
    "reevaluate_vertices",
    "read_gmsh22_volume",
    "read_wall_position_history",
    "run_forward_volume_load_steps",
    "run_graph_load_steps",
    "select_fixed_vertex_band",
    "select_free_vertices",
    "solve_intersection",
    "stack_component_coefficients",
    "stack_component_coefficients_numpy",
    "write_comparison_summary",
    "write_aircraft_wall_gmsh22",
    "write_deformed_gmsh22",
    "write_wall_position_history",
]
