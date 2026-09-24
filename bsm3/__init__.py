"""Differentiable boundary-surface and volume mesh movement.

The package exposes four submodules unconditionally: :mod:`bsm3.component_parameters`
for geometry parameter containers, :mod:`bsm3.core` for the mesh-movement
algorithms, :mod:`bsm3.plotting` for optional visualization helpers, and
:mod:`bsm3.preprocessing` for mesh import, conversion, and export.

A small set of projection helpers is re-exported at package level *only when its
optional research dependencies import successfully*. When they do not, the
import is swallowed and the names are simply absent, so the base package stays
usable. Do not assume ``bsm3.FunctionSetProjectionModel`` and its siblings
exist; import them from :mod:`bsm3.core.projections` directly, or guard access
with :func:`hasattr`, if your code requires them.
"""

__version__ = '0.1.4'

from . import component_parameters, core, plotting, preprocessing

# Projection helpers depend on optional research packages. Keep the base package
# importable when those packages are absent or incompatible.
try:
    from .core.projections.function_set_closest_distance_custom_op import (
        FunctionSetClosestDistanceOperation,
        FunctionSetProjectionModel,
    )
    from .core.projections.function_set_evaluation_custom_op import (
        FunctionSetEvaluationModel,
        FunctionSetEvaluationOperation,
    )
    from .core.projections.function_set_projection_custom_op import (
        FunctionSetProjectionOperation,
    )
except Exception:
    pass
