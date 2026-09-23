"""Configuration, parameterization, and result types for mesh motion."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

import csdl_alpha as csdl
import numpy as np


@dataclass(frozen=True)
class ModelFiles:
    """Geometry and surface/optional-volume mesh inputs for one analysis.

    When volume motion is enabled, ``surface_mesh_file`` must be the
    aircraft-wall boundary extracted from ``volume_mesh_file`` and
    ``volume_wall_map_file`` must store the corresponding surface-to-volume
    node map. Surface-only analyses may omit both volume paths.

    Parameters
    ----------
    geometry_step_file
        STEP file containing the source geometry.
    surface_mesh_file
        Surface mesh whose nodes are moved and reprojected.
    volume_mesh_file
        Optional volume mesh associated with the surface mesh.
    volume_wall_map_file
        Optional surface-to-volume node map.
    setup_cache_directory
        Optional directory for reusable setup data.
    """

    geometry_step_file: Path
    surface_mesh_file: Path
    volume_mesh_file: Path | None = None
    volume_wall_map_file: Path | None = None
    setup_cache_directory: Path | None = None

    def __post_init__(self):
        for name in (
            "geometry_step_file",
            "surface_mesh_file",
            "volume_mesh_file",
            "volume_wall_map_file",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, Path(value).expanduser())
        if self.setup_cache_directory is not None:
            object.__setattr__(
                self,
                "setup_cache_directory",
                Path(self.setup_cache_directory).expanduser(),
            )


@dataclass(frozen=True)
class GraphDistanceWeightingConfig:
    """Configure distance-dependent graph-edge stiffening.

    Parameters
    ----------
    enabled
        Whether graph-distance weighting is active.
    beta
        Nonnegative magnitude of the edge-weight increase.
    length_scale
        Positive physical decay length.
    cap
        Upper bound on the resulting multiplier.
    decay
        Decay law, either ``"exp"`` or ``"rational"``.
    power
        Exponent used by the rational decay law.
    seed_intersections
        Optional intersection names used as distance seeds.

    Raises
    ------
    ValueError
        If a numeric bound, decay law, or seed-name list is invalid.
    """

    enabled: bool = True
    beta: float = 2.0
    length_scale: float = 4.0
    cap: float = np.inf
    decay: str = "exp"
    power: float = 1.0
    seed_intersections: tuple[str, ...] | None = None

    def __post_init__(self):
        if self.beta < 0.0 or self.length_scale <= 0.0 or self.cap < 1.0:
            raise ValueError("Invalid graph-distance weighting parameters.")
        if self.decay not in ("exp", "rational"):
            raise ValueError("Distance decay must be exp or rational.")
        if self.seed_intersections is not None:
            names = tuple(str(name) for name in self.seed_intersections)
            if not names or any(not name for name in names):
                raise ValueError(
                    "Distance seed_intersections must contain nonempty names."
                )
            if len(set(names)) != len(names):
                raise ValueError(
                    "Distance seed_intersections must not contain duplicates."
                )
            object.__setattr__(self, "seed_intersections", names)


@dataclass(frozen=True)
class DistortionRegularizationConfig:
    """Configure the fixed quadratic element-distortion penalty.

    Parameters
    ----------
    weight
        Nonnegative global regularization strength.
    mode
        Distortion formulation selected by the assembler.
    area
        Relative area-change penalty.
    deviatoric
        Relative deviatoric-strain penalty.
    shear
        Relative shear penalty.
    rotation
        Relative in-plane rotation penalty.
    normal
        Relative out-of-plane normal penalty.

    Raises
    ------
    ValueError
        If ``weight`` is negative.
    """

    weight: float = 0.0
    mode: str = "strain_distortion"
    area: float = 1.0
    deviatoric: float = 1.0
    shear: float = 1.0
    rotation: float = 0.0
    normal: float = 0.5

    def __post_init__(self):
        if self.weight < 0.0:
            raise ValueError("Distortion regularization weight cannot be negative.")


@dataclass(frozen=True)
class NgonAffineRegularizationConfig:
    """Configure the element-local affine-residual polygon penalty.

    Parameters
    ----------
    weight
        Finite nonnegative penalty applied to polygons with at least four
        vertices.

    Raises
    ------
    ValueError
        If ``weight`` is negative or non-finite.
    """

    weight: float = 0.0

    def __post_init__(self):
        value = float(self.weight)
        if not np.isfinite(value) or value < 0.0:
            raise ValueError(
                "N-gon affine regularization weight must be finite and nonnegative."
            )
        object.__setattr__(self, "weight", value)


@dataclass(frozen=True)
class SurfaceMotionConfig:
    """Configure graph-Laplacian surface-mesh propagation.

    Parameters
    ----------
    load_steps
        Positive number of continuation increments.
    stiffening_exponent
        Reference-area exponent used by graph edge weights.
    quad_diagonal_weight
        Nonnegative weight for optional quadrilateral bracing.
    quad_bracing_mode
        Bracing topology used when diagonal weighting is active.
    graph_distance_weighting
        Settings for distance-dependent graph stiffening.
    distortion
        Optional quadratic distortion penalty.
    ngon_affine
        Optional affine-residual polygon penalty.

    Raises
    ------
    ValueError
        If an option is invalid or incompatible regularizers are enabled.
    """

    load_steps: int = 2
    stiffening_exponent: float = 1.5
    quad_diagonal_weight: float = 0.0
    quad_bracing_mode: str = "both_diagonals"
    graph_distance_weighting: GraphDistanceWeightingConfig = field(
        default_factory=GraphDistanceWeightingConfig
    )
    distortion: DistortionRegularizationConfig = field(
        default_factory=DistortionRegularizationConfig
    )
    ngon_affine: NgonAffineRegularizationConfig = field(
        default_factory=NgonAffineRegularizationConfig
    )

    def __post_init__(self):
        if self.load_steps < 1:
            raise ValueError("Surface load_steps must be positive.")
        if (
            not np.isfinite(float(self.quad_diagonal_weight))
            or float(self.quad_diagonal_weight) < 0.0
        ):
            raise ValueError(
                "Surface quad_diagonal_weight must be finite and non-negative."
            )
        if self.quad_bracing_mode not in (
            "single_diagonal",
            "both_diagonals",
            "virtual_center",
        ):
            raise ValueError(
                "Surface quad_bracing_mode must be single_diagonal, "
                "both_diagonals, or virtual_center."
            )
        if self.distortion.weight > 0.0 and self.ngon_affine.weight > 0.0:
            raise ValueError(
                "The first-milestone n-gon study does not combine affine and "
                "quadratic distortion regularization."
            )


@dataclass(frozen=True)
class VolumeMotionConfig:
    """Configure propagation from the surface into a volume mesh.

    Parameters
    ----------
    mode
        Enabled volume solver: ``"off"``, ``"graph"``, ``"elasticity"``,
        or ``"both"``.
    load_mode
        Apply only the final surface state or synchronized increments.
    synchronized_load_steps
        Optional positive override for synchronized continuation.
    graph_stiffening_exponent
        Cell-size exponent for graph volume motion.
    elasticity_poisson_ratio
        Poisson ratio for linear elasticity.
    elasticity_stiffening_exponent
        Cell-size exponent for elasticity stiffness.
    output_directory
        Optional directory for generated volume meshes.
    write_meshes
        Whether to write deformed meshes to disk.

    Raises
    ------
    ValueError
        If a mode or physical/numerical parameter is invalid.
    """

    mode: str = "elasticity"
    load_mode: str = "final"
    synchronized_load_steps: int | None = None
    graph_stiffening_exponent: float = 0.3
    elasticity_poisson_ratio: float = 0.3
    elasticity_stiffening_exponent: float = 0.75
    output_directory: Path | None = None
    write_meshes: bool = True

    def __post_init__(self):
        if self.mode not in ("off", "graph", "elasticity", "both"):
            raise ValueError("Invalid volume motion mode.")
        if self.load_mode not in ("final", "synchronized"):
            raise ValueError("Volume load_mode must be final or synchronized.")
        if (
            self.synchronized_load_steps is not None
            and self.synchronized_load_steps < 1
        ):
            raise ValueError("Volume synchronized_load_steps must be positive.")
        if (
            self.synchronized_load_steps is not None
            and self.load_mode != "synchronized"
        ):
            raise ValueError(
                "Volume synchronized_load_steps requires synchronized mode."
            )
        if not (0.0 <= self.elasticity_poisson_ratio < 0.5):
            raise ValueError("Elasticity Poisson ratio must lie in [0, 0.5).")
        if self.elasticity_stiffening_exponent < 0.0:
            raise ValueError("Elasticity stiffening exponent must be nonnegative.")

    @property
    def methods(self) -> tuple[str, ...]:
        """Return the concrete volume solvers selected by ``mode``.

        Returns
        -------
        tuple[str, ...]
            Zero, one, or both of ``"graph"`` and ``"elasticity"``.
        """

        return {
            "off": (),
            "graph": ("graph",),
            "elasticity": ("elasticity",),
            "both": ("graph", "elasticity"),
        }[self.mode]


@dataclass(frozen=True)
class MeshQualityOutputConfig:
    """Configure surface and volume quality evaluation.

    Parameters
    ----------
    surface
        Whether to evaluate surface metrics.
    volume
        Whether to evaluate volume metrics.
    gmsh_volume_metrics
        Whether to request Gmsh-specific volume metrics.
    fail_on_surface_inversion
        Whether inverted surface elements raise an error.
    fail_on_volume_inversion
        Whether inverted volume elements raise an error.
    """

    surface: bool = True
    volume: bool = True
    gmsh_volume_metrics: bool = True
    fail_on_surface_inversion: bool = True
    fail_on_volume_inversion: bool = True


@dataclass(frozen=True)
class VisualizationConfig:
    """Configure optional interactive surface visualization.

    Parameters
    ----------
    enabled
        Whether visualization is produced.
    opacity
        Surface opacity supplied to the plotting backend.
    """

    enabled: bool = True
    opacity: float = 1.0


@dataclass(frozen=True)
class FiniteDifferenceConfig:
    """Configure the optional driver-level finite-difference sweep.

    Parameters
    ----------
    enabled
        Whether to run the sweep.
    objective
        Named scalar objective selected from the pipeline result.
    step_sizes
        Perturbation sizes evaluated by the derivative checker.
    """

    enabled: bool = False
    objective: str = "surface_coordinates"
    step_sizes: tuple[float, ...] = (
        1.0e-2,
        1.0e-3,
        1.0e-4,
        1.0e-5,
        1.0e-6,
    )


@dataclass(frozen=True)
class PipelineConfig:
    """Collect all mesh-motion pipeline settings.

    Parameters
    ----------
    surface_motion
        Surface graph-motion configuration.
    volume_motion
        Optional volume-motion configuration.
    quality
        Quality evaluation and failure policy.
    visualization
        Interactive visualization settings.
    finite_difference
        Optional derivative-sweep settings.
    symmetry
        Whether a fixed symmetry plane is enforced.
    symmetry_plane_tolerance
        Coordinate tolerance used to identify symmetry-plane vertices.
    setup_projection_resolution
        Sampling resolution for setup-time projection.
    projection_warm_start_resolution
        Sampling resolution for projection warm starts.
    rebuild_setup_cache
        Whether cached setup data is ignored and rebuilt.
    query_seam_reference
        Whether seam reference points follow the query component.
    lifting_surface_patch_mode
        Patch restriction used for lifting-surface projection.
    diagnostic_dump
        Optional path for diagnostic output.

    Raises
    ------
    ValueError
        If a tolerance, resolution, or patch mode is invalid.
    """

    surface_motion: SurfaceMotionConfig = field(
        default_factory=SurfaceMotionConfig
    )
    volume_motion: VolumeMotionConfig = field(
        default_factory=VolumeMotionConfig
    )
    quality: MeshQualityOutputConfig = field(
        default_factory=MeshQualityOutputConfig
    )
    visualization: VisualizationConfig = field(
        default_factory=VisualizationConfig
    )
    finite_difference: FiniteDifferenceConfig = field(
        default_factory=FiniteDifferenceConfig
    )
    symmetry: bool = False
    symmetry_plane_tolerance: float = 1.0e-8
    setup_projection_resolution: int = 80
    projection_warm_start_resolution: int = 130
    rebuild_setup_cache: bool = False
    query_seam_reference: bool = True
    lifting_surface_patch_mode: str = "side"
    diagnostic_dump: Path | None = None

    def __post_init__(self):
        if self.symmetry_plane_tolerance < 0.0:
            raise ValueError("Symmetry-plane tolerance cannot be negative.")
        if self.setup_projection_resolution < 1:
            raise ValueError("Setup projection resolution must be positive.")
        if self.projection_warm_start_resolution < 1:
            raise ValueError("Projection warm-start resolution must be positive.")
        if self.lifting_surface_patch_mode not in ("side", "any", "parent"):
            raise ValueError(
                "Lifting-surface patch mode must be side, any, or parent."
            )


@dataclass(frozen=True)
class ComponentSpec:
    """Describe one geometry component without embedding aircraft-specific logic.

    Parameters
    ----------
    name
        Stable identifier used in mappings and cache keys.
    search_name
        Name supplied to the geometry importer's component search.
    coefficient_builder
        Driver-supplied callable returning the component coefficients for one
        load fraction. It receives the imported component, the load fraction,
        and the baseline intersection-vertex mapping.
    free_region_factory
        Driver-supplied callable creating the component's graph free region.
    projection_name
        Diagnostic name used by projection and reevaluation metadata.
    projection_mode
        ``"lifting_surface"`` uses the configured patch-side restriction;
        ``"all"`` projects against every patch on the component.
    """

    name: str
    search_name: str
    coefficient_builder: Callable[[Any, float, Mapping[str, np.ndarray]], Any]
    free_region_factory: Callable[[Any], Any]
    projection_name: str | None = None
    projection_mode: str = "all"

    def __post_init__(self):
        if not self.name or not self.name.isidentifier():
            raise ValueError("ComponentSpec.name must be a nonempty identifier.")
        if not self.search_name:
            raise ValueError("ComponentSpec.search_name cannot be empty.")
        if self.projection_mode not in ("lifting_surface", "all"):
            raise ValueError(
                "ComponentSpec.projection_mode must be lifting_surface or all."
            )
        if self.projection_name is None:
            object.__setattr__(self, "projection_name", self.name)


@dataclass(frozen=True)
class IntersectionSpec:
    """Describe one independent closed component-intersection curve.

    Parameters
    ----------
    name
        Stable identifier for the intersection.
    driving_component
        Component whose parametric line drives the solve.
    query_component
        Component providing the signed-distance residual.
    bisection_search_direction
        Parametric coordinate varied by the bracketed solve.
    solver_name
        Optional diagnostic name; defaults to ``name``.

    Raises
    ------
    ValueError
        If the name is invalid or both component names are equal.
    """

    name: str
    driving_component: str
    query_component: str
    bisection_search_direction: str = "u"
    solver_name: str | None = None

    def __post_init__(self):
        if not self.name or not self.name.isidentifier():
            raise ValueError(
                "IntersectionSpec.name must be a nonempty identifier."
            )
        if self.driving_component == self.query_component:
            raise ValueError(
                "An intersection must use different driving and query components."
            )
        if self.solver_name is None:
            object.__setattr__(self, "solver_name", self.name)


class GeometryParameterization(Protocol):
    """Specify design variables and declarative component behavior.

    Attributes
    ----------
    design_variables
        Named differentiable geometry controls.
    component_specs
        Component declarations used to build geometry coefficients.
    intersection_specs
        Independent closed-intersection declarations.
    """

    design_variables: Mapping[str, csdl.Variable]
    component_specs: list[ComponentSpec]
    intersection_specs: list[IntersectionSpec]


@dataclass(frozen=True)
class DeclarativeGeometryParameterization:
    """Store a validated declarative geometry parameterization.

    Parameters
    ----------
    design_variables
        Nonempty mapping of geometry control names to CSDL variables.
    component_specs
        Nonempty component declarations with unique names.
    intersection_specs
        Intersection declarations with unique names and known components.

    Raises
    ------
    ValueError
        If names are missing, duplicated, or reference unknown components.
    """

    design_variables: Mapping[str, csdl.Variable]
    component_specs: list[ComponentSpec]
    intersection_specs: list[IntersectionSpec]

    def __post_init__(self):
        design_variables = dict(self.design_variables)
        component_specs = list(self.component_specs)
        intersection_specs = list(self.intersection_specs)
        if not design_variables:
            raise ValueError("At least one geometry design variable is required.")
        component_names = [spec.name for spec in component_specs]
        if not component_names or len(set(component_names)) != len(component_names):
            raise ValueError("ComponentSpec names must be nonempty and unique.")
        intersection_names = [spec.name for spec in intersection_specs]
        if len(set(intersection_names)) != len(intersection_names):
            raise ValueError("IntersectionSpec names must be unique.")
        known = set(component_names)
        for spec in intersection_specs:
            referenced = {spec.driving_component, spec.query_component}
            if not referenced.issubset(known):
                missing = ", ".join(sorted(referenced.difference(known)))
                raise ValueError(
                    f"IntersectionSpec {spec.name!r} references unknown "
                    f"components: {missing}."
                )
        object.__setattr__(self, "design_variables", design_variables)
        object.__setattr__(self, "component_specs", component_specs)
        object.__setattr__(self, "intersection_specs", intersection_specs)


@dataclass
class MeshMotionResult:
    """Collect differentiable outputs and forward diagnostics.

    Attributes
    ----------
    model_files
        Input file contracts used to build the model.
    geometry_parameterization
        User-supplied geometry controls and declarations.
    initial_surface_coordinates
        Baseline surface coordinates.
    preprojected_surface_coordinates
        Surface coordinates before OML reprojection.
    surface_coordinates
        Final reprojected surface coordinates.
    volume_coordinates
        Deformed volume coordinates keyed by motion method.
    aerodynamic_outputs
        Optional downstream aerodynamic results.
    surface_inversion_report
        Surface-orientation diagnostics.
    surface_quality_report
        Aggregate surface-quality diagnostics.
    volume_quality_summary
        Optional volume-quality metrics.
    volume_mesh
        Optional loaded volume-mesh object.
    surface_mesh
        Loaded surface-mesh object.
    """

    model_files: ModelFiles
    geometry_parameterization: GeometryParameterization
    initial_surface_coordinates: np.ndarray
    preprojected_surface_coordinates: csdl.Variable
    surface_coordinates: csdl.Variable
    volume_coordinates: dict[str, csdl.Variable]
    aerodynamic_outputs: dict[str, csdl.Variable]
    surface_inversion_report: Any
    surface_quality_report: Any
    volume_quality_summary: dict | None
    volume_mesh: Any | None
    surface_mesh: Any


__all__ = [
    "ComponentSpec",
    "DeclarativeGeometryParameterization",
    "DistortionRegularizationConfig",
    "FiniteDifferenceConfig",
    "GeometryParameterization",
    "GraphDistanceWeightingConfig",
    "IntersectionSpec",
    "MeshMotionResult",
    "MeshQualityOutputConfig",
    "ModelFiles",
    "NgonAffineRegularizationConfig",
    "PipelineConfig",
    "SurfaceMotionConfig",
    "VisualizationConfig",
    "VolumeMotionConfig",
]
