"""Core differentiable geometry and mesh-movement algorithms.

Exposes two submodules. :mod:`bsm3.core.boundary_surface_movement` holds the
surface and volume mesh-motion machinery together with its CSDL custom
operations; :mod:`bsm3.core.weighting_functions` holds the compact influence
functions used to blend intersection-driven displacement data.

The projection subpackage, :mod:`bsm3.core.projections`, is deliberately not
imported here: it depends on optional research packages, so importing it
eagerly would make this module fail wherever those are absent.
"""

from . import boundary_surface_movement, weighting_functions

__all__ = ["boundary_surface_movement", "weighting_functions"]
