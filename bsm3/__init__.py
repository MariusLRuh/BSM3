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
