"""Configuration and result types for the E175 mesh-motion examples."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import csdl_alpha as csdl
import numpy as np


@dataclass(frozen=True)
class E175ModelFiles:
    """Geometry and matching surface/volume mesh inputs for one analysis.

    ``surface_mesh_file`` must be the aircraft-wall boundary extracted from
    ``volume_mesh_file``. ``volume_wall_map_file`` stores the corresponding
    surface-to-volume node map; loading deliberately fails if those inputs do
    not match.
    """

    geometry_step_file: Path
    surface_mesh_file: Path
    volume_mesh_file: Path
    volume_wall_map_file: Path
    setup_cache_directory: Path | None = None

    def __post_init__(self):
        for name in (
            "geometry_step_file",
            "surface_mesh_file",
            "volume_mesh_file",
            "volume_wall_map_file",
        ):
            object.__setattr__(self, name, Path(getattr(self, name)).expanduser())
        if self.setup_cache_directory is not None:
            object.__setattr__(
                self,
                "setup_cache_directory",
                Path(self.setup_cache_directory).expanduser(),
            )


@dataclass(frozen=True)
class TangentialSmoothingConfig:
    enabled: bool = True
    layers: int = 16
    iterations: int = 3
    relaxation: float = 1.0
    preserve_reference: bool = False
    reprojection: str = "final_only"

    def __post_init__(self):
        if self.layers < 1 or self.iterations < 1:
            raise ValueError("Smoothing layers and iterations must be positive.")
        if not 0.0 < self.relaxation <= 1.0:
            raise ValueError("Smoothing relaxation must lie in (0, 1].")
        if self.reprojection not in ("every_iteration", "final_only"):
            raise ValueError(
                "Smoothing reprojection must be every_iteration or final_only."
            )


@dataclass(frozen=True)
class GraphDistanceWeightingConfig:
    enabled: bool = True
    beta: float = 2.0
    length_scale: float = 4.0
    cap: float = np.inf
    decay: str = "exp"
    power: float = 1.0
    seeds: str = "both"

    def __post_init__(self):
        if self.beta < 0.0 or self.length_scale <= 0.0 or self.cap < 1.0:
            raise ValueError("Invalid graph-distance weighting parameters.")
        if self.decay not in ("exp", "rational"):
            raise ValueError("Distance decay must be exp or rational.")
        if self.seeds not in ("wing", "tail", "both"):
            raise ValueError("Distance seeds must be wing, tail, or both.")


@dataclass(frozen=True)
class DistortionRegularizationConfig:
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
class FinalSurfaceQualityConfig:
    mode: str = "none"
    layers: int = 16
    barrier_floor: float = 0.01
    feasibility_target: float = 0.12
    barrier_activation: float = 0.20
    barrier_weight: float = 10.0
    maximum_iterations: int = 250
    solver: str = "lbfgs"

    def __post_init__(self):
        if self.mode not in ("none", "oml"):
            raise ValueError("Final surface quality mode must be none or oml.")
        if self.layers < 1 or self.maximum_iterations < 1:
            raise ValueError("Quality layers and iterations must be positive.")


@dataclass(frozen=True)
class SurfaceMotionConfig:
    mode: str = "graph"
    load_steps: int = 2
    stiffening_exponent: float = 1.5
    tangential_smoothing: TangentialSmoothingConfig = field(
        default_factory=TangentialSmoothingConfig
    )
    graph_distance_weighting: GraphDistanceWeightingConfig = field(
        default_factory=GraphDistanceWeightingConfig
    )
    distortion: DistortionRegularizationConfig = field(
        default_factory=DistortionRegularizationConfig
    )
    final_quality: FinalSurfaceQualityConfig = field(
        default_factory=FinalSurfaceQualityConfig
    )
    wing_free_span_fraction: float = 0.3
    tail_free_span_fraction: float = 0.3
    fuselage_free_x_range: tuple[float, float] = (0.05, 0.97)
    membrane_poisson_ratio: float = 0.4
    membrane_area_stiffening: float = 0.0
    membrane_normal_stabilization: float = 0.02
    membrane_barrier: bool = True
    membrane_barrier_activation: float = 0.6
    membrane_barrier_target: float = 0.3
    membrane_barrier_maximum_iterations: int = 500

    def __post_init__(self):
        if self.mode not in ("graph", "membrane"):
            raise ValueError("Surface motion mode must be graph or membrane.")
        if self.load_steps < 1:
            raise ValueError("Surface load_steps must be positive.")
        if self.mode != "graph" and self.load_steps != 1:
            raise ValueError("Multiple surface steps require graph motion.")
        if self.mode != "graph" and self.distortion.weight != 0.0:
            raise ValueError("Distortion regularization requires graph motion.")
        if self.mode != "graph" and self.tangential_smoothing.enabled:
            raise ValueError("Tangential smoothing requires graph motion.")
        if self.graph_distance_weighting.enabled and self.mode != "graph":
            raise ValueError("Graph-distance weighting requires graph motion.")


@dataclass(frozen=True)
class VolumeMotionConfig:
    mode: str = "elasticity"
    load_mode: str = "final"
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

    @property
    def methods(self) -> tuple[str, ...]:
        return {
            "off": (),
            "graph": ("graph",),
            "elasticity": ("elasticity",),
            "both": ("graph", "elasticity"),
        }[self.mode]


@dataclass(frozen=True)
class MeshQualityOutputConfig:
    surface: bool = True
    volume: bool = True
    gmsh_volume_metrics: bool = True
    fail_on_surface_inversion: bool = True
    fail_on_volume_inversion: bool = True


@dataclass(frozen=True)
class VisualizationConfig:
    enabled: bool = True
    opacity: float = 1.0


@dataclass(frozen=True)
class FiniteDifferenceConfig:
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
class E175PipelineConfig:
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
    setup_projection_resolution: int = 60
    projection_warm_start_resolution: int = 100
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
class E175GeometryVariables:
    wing_translation_x: csdl.Variable
    wing_rotation_degrees: csdl.Variable
    tail_rotation_degrees: csdl.Variable
    wing_area: csdl.Variable
    wing_aspect_ratio: csdl.Variable
    fuselage_diameter_scale: csdl.Variable

    def as_dict(self) -> dict[str, csdl.Variable]:
        return {
            "wing_translation_x": self.wing_translation_x,
            "wing_rotation_degrees": self.wing_rotation_degrees,
            "tail_rotation_degrees": self.tail_rotation_degrees,
            "wing_area": self.wing_area,
            "wing_aspect_ratio": self.wing_aspect_ratio,
            "fuselage_diameter_scale": self.fuselage_diameter_scale,
        }


@dataclass
class E175MeshMotionResult:
    model_files: E175ModelFiles
    geometry_variables: E175GeometryVariables
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
    "DistortionRegularizationConfig",
    "E175GeometryVariables",
    "E175MeshMotionResult",
    "E175ModelFiles",
    "E175PipelineConfig",
    "FinalSurfaceQualityConfig",
    "FiniteDifferenceConfig",
    "GraphDistanceWeightingConfig",
    "MeshQualityOutputConfig",
    "SurfaceMotionConfig",
    "TangentialSmoothingConfig",
    "VisualizationConfig",
    "VolumeMotionConfig",
]
