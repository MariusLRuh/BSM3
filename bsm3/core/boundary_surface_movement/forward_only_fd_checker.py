"""Forward-only centered finite-difference derivative checker.

The stock CSDL ``check_optimization_derivatives`` builds the analytical
derivative (adjoint) operations into the active graph *before* it runs the
finite-difference pass, and the FD pass then re-executes that augmented graph.
For a DAFoam chain this silently reruns the CL/CD adjoint solves during every
nominally forward-only perturbation, which is both wrong and enormously
expensive.

This module provides a checker that structurally cannot do that:

* the finite-difference sweep only ever calls a caller-supplied ``forward_fn``
  (primal only); no derivative graph exists while it runs;
* each perturbation is evaluated independently from the stored baseline design
  point -- never chained ``+h -> -h`` -- and an optional ``reset_fn`` restores
  the baseline mesh / converged flow state before each evaluation;
* the analytical derivatives are computed exactly once, afterwards;
* the forward-only stage is wrapped in a file-descriptor-level output guard that
  fails if the adjoint marker ``"Solving Linear Equation"`` is emitted (DAFoam
  prints it from the C/PETSc layer, below Python ``stdout``).

It prints the mandated stage markers so a batch log can be audited:

    START FORWARD-ONLY FD / END FORWARD-ONLY FD
    START ANALYTICAL ADJOINT / END ANALYTICAL ADJOINT
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import math
import os
import sys
import tempfile
from typing import Any, Callable, Iterable, Mapping, Optional

import numpy as np


DesignPoint = Mapping[str, np.ndarray]
ForwardFunction = Callable[[DesignPoint], Mapping[str, float]]
AnalyticalFunction = Callable[
    [], Mapping[tuple[str, str], np.ndarray]
]

ADJOINT_MARKER = "Solving Linear Equation"


# ---------------------------------------------------------------------------
# Output guard
# ---------------------------------------------------------------------------
@contextmanager
def guard_against_adjoint_output(
    *,
    markers: Iterable[str] = (ADJOINT_MARKER,),
    raise_on_match: bool = True,
    echo: bool = True,
):
    """Capture fd-1 output, then re-emit it and fail if a marker appears.

    DAFoam/PETSc write ``"Solving Linear Equation"`` at the file-descriptor
    level, so Python ``stdout`` redirection would miss it.  This redirects the
    real fd 1 to a temporary file, restores it on exit, re-emits everything that
    was written (so logs are preserved), and raises if any adjoint marker was
    found while the guard was active.
    """

    marker_list = [str(m) for m in markers]
    sys.stdout.flush()
    saved_fd = os.dup(1)
    temp = tempfile.TemporaryFile(mode="w+b")
    os.dup2(temp.fileno(), 1)
    try:
        yield
    finally:
        sys.stdout.flush()
        os.dup2(saved_fd, 1)
        os.close(saved_fd)
        temp.seek(0)
        captured = temp.read().decode("utf-8", errors="replace")
        temp.close()
        if echo and captured:
            sys.stdout.write(captured)
            sys.stdout.flush()
        offenders = [m for m in marker_list if m in captured]
        if offenders and raise_on_match:
            raise RuntimeError(
                "Adjoint solve detected during the forward-only FD stage "
                f"(found {offenders!r}). The finite-difference pass must not "
                "execute analytical-derivative operations."
            )


# ---------------------------------------------------------------------------
# Scales and steps
# ---------------------------------------------------------------------------
def characteristic_scales(
    design_variable_specs: Mapping[str, tuple[int, ...]],
    scales: Optional[Mapping[str, float]] = None,
) -> dict[str, float]:
    """Return a positive characteristic scale per design variable.

    Defaults to 1.0 for any variable without an explicit scale.  Steps are
    ``h_i = eta * s_i`` so a single ``eta`` sweep is meaningful across variables
    with very different physical magnitudes (translation vs. area vs. degrees).
    """

    resolved: dict[str, float] = {}
    for name in design_variable_specs:
        scale = 1.0 if scales is None else float(scales.get(name, 1.0))
        if scale <= 0.0:
            raise ValueError(f"Characteristic scale for {name!r} must be > 0.")
        resolved[name] = scale
    return resolved


# ---------------------------------------------------------------------------
# Centered finite differences (forward-only)
# ---------------------------------------------------------------------------
def _copy_design_point(baseline: DesignPoint) -> dict[str, np.ndarray]:
    return {name: np.asarray(value, dtype=float).copy() for name, value in baseline.items()}


def centered_finite_difference(
    forward_fn: ForwardFunction,
    baseline: DesignPoint,
    *,
    output_names: tuple[str, ...],
    design_variable_specs: Mapping[str, tuple[int, ...]],
    eta: float,
    scales: Mapping[str, float],
    reset_fn: Optional[Callable[[], None]] = None,
) -> dict[tuple[str, str], np.ndarray]:
    """Centered FD of every scalar output wrt every design-variable component.

    Every ``+h`` and ``-h`` evaluation starts from a fresh copy of ``baseline``
    and calls ``reset_fn`` (if given) first, so no perturbation warm-starts from
    another.  Returns ``{(output, dv): gradient}`` with ``gradient`` shaped like
    the design variable.
    """

    gradients: dict[tuple[str, str], np.ndarray] = {
        (output, dv): np.zeros(design_variable_specs[dv], dtype=float)
        for output in output_names
        for dv in design_variable_specs
    }
    for dv, shape in design_variable_specs.items():
        step = eta * scales[dv]
        if step <= 0.0:
            raise ValueError(f"Non-positive FD step for {dv!r}.")
        size = int(np.prod(shape)) if shape else 1
        flat_shape = shape if shape else (1,)
        for index in range(size):
            multi_index = np.unravel_index(index, flat_shape)

            plus = _copy_design_point(baseline)
            plus[dv] = np.asarray(plus[dv], dtype=float).reshape(flat_shape)
            plus[dv][multi_index] += step
            if reset_fn is not None:
                reset_fn()
            f_plus = forward_fn(plus)

            minus = _copy_design_point(baseline)
            minus[dv] = np.asarray(minus[dv], dtype=float).reshape(flat_shape)
            minus[dv][multi_index] -= step
            if reset_fn is not None:
                reset_fn()
            f_minus = forward_fn(minus)

            for output in output_names:
                derivative = (
                    float(np.asarray(f_plus[output]).reshape(-1)[0])
                    - float(np.asarray(f_minus[output]).reshape(-1)[0])
                ) / (2.0 * step)
                gradients[output, dv].reshape(flat_shape)[multi_index] = derivative
    return gradients


def run_forward_only_fd_sweep(
    forward_fn: ForwardFunction,
    baseline: DesignPoint,
    *,
    output_names: tuple[str, ...],
    design_variable_specs: Mapping[str, tuple[int, ...]],
    etas: tuple[float, ...],
    scales: Optional[Mapping[str, float]] = None,
    reset_fn: Optional[Callable[[], None]] = None,
    guard: bool = True,
) -> dict[float, dict[tuple[str, str], np.ndarray]]:
    """Run the guarded, forward-only centered-FD step sweep."""

    resolved_scales = characteristic_scales(design_variable_specs, scales)
    print("START FORWARD-ONLY FD", flush=True)
    sweep: dict[float, dict[tuple[str, str], np.ndarray]] = {}

    def _run_all() -> None:
        for eta in etas:
            sweep[eta] = centered_finite_difference(
                forward_fn,
                baseline,
                output_names=output_names,
                design_variable_specs=design_variable_specs,
                eta=eta,
                scales=resolved_scales,
                reset_fn=reset_fn,
            )

    if guard:
        with guard_against_adjoint_output():
            _run_all()
    else:
        _run_all()
    print("END FORWARD-ONLY FD", flush=True)
    return sweep


def run_analytical_once(
    analytical_fn: AnalyticalFunction,
) -> dict[tuple[str, str], np.ndarray]:
    """Compute analytical derivatives exactly once, inside adjoint markers."""

    print("START ANALYTICAL ADJOINT", flush=True)
    try:
        analytical = {
            key: np.asarray(value, dtype=float)
            for key, value in analytical_fn().items()
        }
    finally:
        print("END ANALYTICAL ADJOINT", flush=True)
    return analytical


# ---------------------------------------------------------------------------
# Comparison and reporting
# ---------------------------------------------------------------------------
@dataclass
class DerivativeComparison:
    analytical: dict[tuple[str, str], np.ndarray]
    fd_by_eta: dict[float, dict[tuple[str, str], np.ndarray]]
    relative_error_by_eta: dict[float, dict[tuple[str, str], float]] = field(
        default_factory=dict
    )

    def best(self) -> dict[tuple[str, str], tuple[float, float]]:
        """Return ``{(output, dv): (best_eta, best_relative_error)}``."""

        result: dict[tuple[str, str], tuple[float, float]] = {}
        keys = self.analytical.keys()
        for key in keys:
            best_eta = None
            best_error = math.inf
            for eta, errors in self.relative_error_by_eta.items():
                error = errors.get(key, math.inf)
                if error < best_error:
                    best_error = error
                    best_eta = eta
            result[key] = (best_eta, best_error)
        return result


def _relative_error(analytical: np.ndarray, fd: np.ndarray) -> float:
    analytical = np.asarray(analytical, dtype=float).reshape(-1)
    fd = np.asarray(fd, dtype=float).reshape(-1)
    denominator = max(np.linalg.norm(analytical), np.linalg.norm(fd), 1e-30)
    return float(np.linalg.norm(analytical - fd) / denominator)


def compare_and_report(
    analytical: Mapping[tuple[str, str], np.ndarray],
    fd_by_eta: Mapping[float, Mapping[tuple[str, str], np.ndarray]],
    *,
    print_results: bool = True,
) -> DerivativeComparison:
    """Assemble relative errors for the step sweep and optionally print them."""

    comparison = DerivativeComparison(
        analytical={k: np.asarray(v, dtype=float) for k, v in analytical.items()},
        fd_by_eta={
            eta: {k: np.asarray(v, dtype=float) for k, v in grads.items()}
            for eta, grads in fd_by_eta.items()
        },
    )
    for eta, grads in comparison.fd_by_eta.items():
        comparison.relative_error_by_eta[eta] = {
            key: _relative_error(comparison.analytical[key], grads[key])
            for key in comparison.analytical
            if key in grads
        }

    if print_results:
        etas = sorted(comparison.fd_by_eta, reverse=True)
        keys = sorted(comparison.analytical)
        print("\n=== Forward-only centered-FD vs analytical derivatives ===")
        header = "  (output, dv)".ljust(34) + "".join(
            f"{eta:>14.1e}" for eta in etas
        )
        print(header)
        for key in keys:
            label = f"  ({key[0]}, {key[1]})".ljust(34)
            row = "".join(
                f"{comparison.relative_error_by_eta[eta].get(key, float('nan')):>14.3e}"
                for eta in etas
            )
            print(label + row)
        print()
        for key, (best_eta, best_error) in comparison.best().items():
            regime = "converges" if best_error < 1.0e-1 else "NO CLEAR REGIME"
            print(
                f"  ({key[0]}, {key[1]}): min rel error {best_error:.3e} at "
                f"eta {best_eta:.1e}  ({regime})"
            )
        print()
    return comparison


def check_derivatives_forward_first(
    forward_fn: ForwardFunction,
    analytical_fn: AnalyticalFunction,
    baseline: DesignPoint,
    *,
    output_names: tuple[str, ...],
    design_variable_specs: Mapping[str, tuple[int, ...]],
    etas: tuple[float, ...],
    scales: Optional[Mapping[str, float]] = None,
    reset_fn: Optional[Callable[[], None]] = None,
    guard: bool = True,
    print_results: bool = True,
) -> DerivativeComparison:
    """Full forward-first ladder: guarded FD sweep, then one analytical solve.

    The finite-difference pass runs to completion before ``analytical_fn`` is
    ever called, so no analytical-derivative operation exists while FD executes.
    """

    fd_by_eta = run_forward_only_fd_sweep(
        forward_fn,
        baseline,
        output_names=output_names,
        design_variable_specs=design_variable_specs,
        etas=etas,
        scales=scales,
        reset_fn=reset_fn,
        guard=guard,
    )
    analytical = run_analytical_once(analytical_fn)
    return compare_and_report(
        analytical, fd_by_eta, print_results=print_results
    )


# ---------------------------------------------------------------------------
# Degree/radian consistency
# ---------------------------------------------------------------------------
def degree_radian_relative_error(
    gradient_wrt_degrees: np.ndarray,
    gradient_wrt_radians: np.ndarray,
) -> float:
    """Relative error of ``dF/dtheta_deg`` vs ``(pi/180) dF/dtheta_rad``.

    Documents and independently verifies the rotation-unit convention required
    by the derivative study, without needing a second full model evaluation.
    """

    expected = (math.pi / 180.0) * np.asarray(
        gradient_wrt_radians, dtype=float
    )
    return _relative_error(expected, np.asarray(gradient_wrt_degrees, dtype=float))


__all__ = [
    "ADJOINT_MARKER",
    "DerivativeComparison",
    "guard_against_adjoint_output",
    "characteristic_scales",
    "centered_finite_difference",
    "run_forward_only_fd_sweep",
    "run_analytical_once",
    "compare_and_report",
    "check_derivatives_forward_first",
    "degree_radian_relative_error",
]
