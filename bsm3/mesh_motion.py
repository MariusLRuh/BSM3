"""Compact public namespace for differentiable surface mesh motion.

This module is the intended entry point. A user writes::

    import bsm3.mesh_motion as mm

and then builds three things: the input files, a :class:`GeometryModel`
describing what moves, and a :class:`MeshMotion` settings object describing how
the mesh follows. :func:`run` evaluates the differentiable model and returns a
:class:`MeshMotionResult`.

Only high-level names are re-exported here. Solver-assembly types, component
records, projection callbacks, and polygon helpers stay internal, because a
caller never needs them to deform a surface mesh.
"""

from __future__ import annotations

from typing import Any

import csdl_alpha as csdl

from .core.boundary_surface_movement import (
    DerivativeCheck,
    DistanceWeighting,
    DistortionPenalty,
    GeometryModel,
    InputFiles,
    MeshMotion,
    MeshMotionResult,
    PolygonRegularization,
    QualityChecks,
    SurfaceMotion,
    Visualization,
    VolumeMotion,
    run_mesh_motion,
)

__all__ = [
    "DerivativeCheck",
    "DistanceWeighting",
    "DistortionPenalty",
    "GeometryModel",
    "InputFiles",
    "MeshMotion",
    "MeshMotionResult",
    "PolygonRegularization",
    "QualityChecks",
    "SurfaceMotion",
    "Visualization",
    "VolumeMotion",
    "run",
]


def run(
    *,
    inputs: InputFiles,
    geometry: GeometryModel,
    motion: MeshMotion,
    recorder: csdl.Recorder | None = None,
    aerodynamic_analysis: Any = None,
    aerodynamic_volume_method: str = "elasticity",
) -> MeshMotionResult:
    """Evaluate the differentiable mesh-motion model.

    Parameters
    ----------
    inputs
        Geometry, surface-mesh, and optional volume-mesh paths.
    geometry
        Design variables and the components they move.
    motion
        Surface, volume, quality, visualization, and derivative-check settings.
    recorder
        Optional CSDL recorder. When ``None`` an inline recorder is created,
        started, and stopped here, and retained on the result. When supplied,
        its lifecycle belongs to the caller and is not touched, so this call
        composes inside a larger graph such as the DAFoam driver.
    aerodynamic_analysis
        Optional downstream builder receiving the selected volume coordinates.
    aerodynamic_volume_method
        Volume-motion method handed to ``aerodynamic_analysis``.

    Returns
    -------
    MeshMotionResult
        Differentiable outputs plus forward diagnostics. Call
        :meth:`MeshMotionResult.print_summary` for a readable report.
    """
    if recorder is not None:
        active, owned = recorder, False
    elif getattr(geometry, "owns_recorder", False):
        # GeometryModel started an inline recorder so design variables could
        # be created before this call; stopping it is this call's job.
        active, owned = geometry.recorder, True
    else:
        active, owned = csdl.Recorder(inline=True), True
        active.start()
    try:
        result = run_mesh_motion(
            recorder=active,
            input_files=inputs,
            geometry=geometry,
            config=motion,
            aerodynamic_analysis=aerodynamic_analysis,
            aerodynamic_volume_method=aerodynamic_volume_method,
        )
    finally:
        if owned:
            active.stop()
    result.recorder = active
    return result
