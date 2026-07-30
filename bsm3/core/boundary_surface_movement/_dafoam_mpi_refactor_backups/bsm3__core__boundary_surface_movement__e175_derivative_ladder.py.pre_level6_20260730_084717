"""E175 DAFoam derivative validation ladder (Levels 0-5).

This diagnostic runs on TSCC through Slurm, never on a login node.  It locates
the failing derivative layer before attempting another full six-derivative
end-to-end run, following the validation ladder in
``DAFoam_CSDL_MPI_Custom_Operation_Implementation_Instructions.md``:

    Level 0  deterministic forward repetition (function noise)
    Level 1  MPI-independent mesh-motion forward (np = 1, 2, 4, 8)
    Level 2  mesh-motion custom-op VJP dot-product (no DAFoam)
    Level 3  DAFoam-only volume-coordinate VJP directional check
    Level 4  explicit chain-rule test (DAFoam cotangent -> mesh-motion VJP)
    Level 5  one-DV, one-output end-to-end centered FD with a step sweep

It reuses the configuration objects from ``cfd_mesh_dafoam_analysis`` so the
design point, mesh files, flow settings, and OpenFOAM case are defined in exactly
one place.  Levels 0 and 3-5 require a configured DAFoam case; Levels 1-2 need
only the mesh-motion stack.

Invocation (through Slurm; see slurm/e175_derivative_ladder.sbatch):

    mpirun -np <N> python -m \
        bsm3.core.boundary_surface_movement.e175_derivative_ladder <level>

``<level>`` is one of ``0 1 2 3 4 5``.  Results and a timestamped log are
written under ``LADDER_OUTPUT_DIRECTORY`` on Lustre scratch.
"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable

import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from bsm3.core.boundary_surface_movement import cfd_mesh_dafoam_analysis as driver
from bsm3.core.boundary_surface_movement.forward_only_fd_checker import (
    check_derivatives_forward_first,
    run_forward_only_fd_sweep,
    run_analytical_once,
    compare_and_report,
)
from bsm3.core.boundary_surface_movement.geometry_volume_backend import (
    E175GeometryVolumeBackend,
    read_gmsh_volume_point_count,
)
from bsm3.core.boundary_surface_movement.geometry_volume_mpi import (
    broadcast_array,
    comm_rank,
    comm_size,
    is_root,
    resolve_comm,
    run_on_root,
)


# ---------------------------------------------------------------------------
# Ladder configuration
# ---------------------------------------------------------------------------
# Reuse the single source of truth from the coupled driver.
MODEL_FILES = driver.MODEL_FILES
GEOMETRY_VALUES = driver.GEOMETRY_VALUES
MESH_MOTION = driver.MESH_MOTION
FLOW = driver.FLOW
CASE = driver.CASE

LADDER_OUTPUT_DIRECTORY = Path("ladder_results")

# Scale-aware FD steps h_i = eta * s_i.  Characteristic scales come from the
# design-variable ranges/scalers used in the driver.
DESIGN_VARIABLE_SCALES = {
    "wing_translation_x": 3.0,
    "wing_rotation_degrees": 5.0,
    "tail_rotation_degrees": 8.0,
    "wing_area": 70.0,
    "wing_aspect_ratio": 8.4,
    "fuselage_diameter_scale": 0.2,
}
ETAS = (1.0e-2, 3.0e-3, 1.0e-3, 3.0e-4, 1.0e-4)

# Smoothest design variable first for the one-DV end-to-end check (Level 5).
LEVEL5_DESIGN_VARIABLE = "wing_translation_x"
LEVEL5_OUTPUT = "CD"


def _timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _write_result(name: str, payload: dict[str, Any], comm) -> None:
    if not is_root(comm):
        return
    LADDER_OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    path = LADDER_OUTPUT_DIRECTORY / f"{name}_np{comm_size(comm)}_{_timestamp()}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[ladder] wrote {path.resolve()}", flush=True)


def _coordinate_checksum(coordinates: np.ndarray) -> float:
    array = np.asarray(coordinates, dtype=np.float64)
    return float(np.sum(array) + np.sum(np.abs(array)) + np.linalg.norm(array))


# ---------------------------------------------------------------------------
# Backend construction
# ---------------------------------------------------------------------------
def _make_geometry_backend(comm) -> E175GeometryVolumeBackend | None:
    if not is_root(comm):
        return None
    return E175GeometryVolumeBackend(
        model_files=MODEL_FILES,
        geometry_values=GEOMETRY_VALUES,
        pipeline_config=MESH_MOTION,
        aerodynamic_volume_method="elasticity",
    )


def _make_dafoam_backend(comm, *, deterministic: bool = False):
    backend = driver.create_dafoam_backend(FLOW, CASE, MODEL_FILES, comm)
    # Deterministic FD mode + adjoint-linearization invalidation give
    # history-independent finite differences (addendum findings 1 and 2).
    backend.deterministic_fd_mode = bool(deterministic)
    backend.invalidate_adjoint_on_primal = True
    return backend


def _prepare_deterministic_baseline(backend, coordinates, patch_velocity):
    """Run one baseline primal, freeze it, and enable deterministic FD mode.

    Every subsequent primal then restores this fixed converged state, so +h/-h
    perturbations are independent rather than chained warm starts.
    """

    backend.deterministic_fd_mode = False
    backend.reset_primal_state()
    backend.run_primal(
        {"volume_coordinates": coordinates, "patch_velocity": patch_velocity}
    )
    backend.set_deterministic_baseline()
    backend.deterministic_fd_mode = True


# ---------------------------------------------------------------------------
# Level 0: deterministic forward repetition
# ---------------------------------------------------------------------------
def level0_forward_repetition(comm, repetitions: int = 2) -> dict[str, Any]:
    driver._require_case_directory(CASE)
    backend = _make_dafoam_backend(comm, deterministic=True)
    geometry_backend = _make_geometry_backend(comm)

    output_shape = (read_gmsh_volume_point_count(MODEL_FILES.volume_mesh_file), 3)
    # run_on_root: rank 0 deforms the mesh; a root exception is broadcast before
    # the following collective so no rank is stranded.
    baseline_coordinates = run_on_root(
        comm, lambda: geometry_backend.forward(GEOMETRY_VALUES)
    )
    coordinates = broadcast_array(
        comm, baseline_coordinates, shape=output_shape, dtype=np.float64
    )
    patch_velocity = np.array([FLOW.velocity_m_per_s, FLOW.angle_of_attack_deg])
    _prepare_deterministic_baseline(backend, coordinates, patch_velocity)

    functions_history = []
    for _ in range(repetitions):
        # Deterministic mode restores the same converged baseline before each
        # primal, so any residual difference is genuine solver noise.
        functions = backend.run_primal(
            {"volume_coordinates": coordinates, "patch_velocity": patch_velocity}
        )
        functions_history.append({k: float(np.asarray(v).reshape(-1)[0]) for k, v in functions.items()})

    payload: dict[str, Any] = {
        "level": 0,
        "mpi_ranks": comm_size(comm),
        "coordinate_checksum": _coordinate_checksum(coordinates),
        "functions": functions_history,
    }
    if len(functions_history) >= 2:
        payload["function_noise"] = {
            name: abs(functions_history[1][name] - functions_history[0][name])
            for name in functions_history[0]
        }
    _write_result("level0_forward_repetition", payload, comm)
    return payload


# ---------------------------------------------------------------------------
# Level 1: MPI-independent mesh-motion forward
# ---------------------------------------------------------------------------
def level1_mesh_motion_forward(comm) -> dict[str, Any]:
    geometry_backend = _make_geometry_backend(comm)
    output_shape = (read_gmsh_volume_point_count(MODEL_FILES.volume_mesh_file), 3)

    coordinates = run_on_root(
        comm, lambda: geometry_backend.forward(GEOMETRY_VALUES)
    )
    coordinates = broadcast_array(comm, coordinates, shape=output_shape, dtype=np.float64)

    payload = {
        "level": 1,
        "mpi_ranks": comm_size(comm),
        "num_points": int(output_shape[0]),
        "coordinate_checksum": _coordinate_checksum(coordinates),
        "coordinate_min": [float(v) for v in coordinates.min(axis=0)],
        "coordinate_max": [float(v) for v in coordinates.max(axis=0)],
    }
    _write_result("level1_mesh_motion_forward", payload, comm)
    print(
        f"[level1] np={comm_size(comm)} checksum={payload['coordinate_checksum']:.10e}",
        flush=True,
    )
    return payload


# ---------------------------------------------------------------------------
# Level 2: mesh-motion custom-op VJP dot-product (no DAFoam)
# ---------------------------------------------------------------------------
def level2_mesh_motion_vjp(comm, seed_index: int = 0) -> dict[str, Any]:
    # No DAFoam: all mesh-motion work is on rank 0. Every rank still drives the
    # same run_on_root sequence so a root exception cannot strand the others
    # (this level is intended for np=1 but stays collective-safe for any np).
    geometry_backend = _make_geometry_backend(comm)
    baseline = {name: np.asarray(value, dtype=float) for name, value in GEOMETRY_VALUES.items()}
    output_shape = (read_gmsh_volume_point_count(MODEL_FILES.volume_mesh_file), 3)

    # Identical seed/direction on every rank (only used inside root-only lambdas).
    rng = np.random.default_rng(seed_index)
    seed = rng.standard_normal(output_shape)
    delta = {
        name: np.asarray(rng.standard_normal() * DESIGN_VARIABLE_SCALES[name], dtype=float)
        for name in baseline
    }

    run_on_root(comm, lambda: geometry_backend.forward(baseline))
    vjp = run_on_root(comm, lambda: geometry_backend.compute_vjp(baseline, seed))
    directional_adjoint = None
    if is_root(comm):
        directional_adjoint = float(sum(np.sum(vjp[name] * delta[name]) for name in baseline))

    sweep: dict[float, dict[str, float]] = {}
    for eta in ETAS:
        x_plus = run_on_root(
            comm,
            lambda e=eta: geometry_backend.forward(
                {k: baseline[k] + e * delta[k] for k in baseline}
            ),
        )
        x_minus = run_on_root(
            comm,
            lambda e=eta: geometry_backend.forward(
                {k: baseline[k] - e * delta[k] for k in baseline}
            ),
        )
        if is_root(comm):
            directional_fd = float(np.sum(seed * (x_plus - x_minus) / (2.0 * eta)))
            rel = abs(directional_fd - directional_adjoint) / max(abs(directional_adjoint), 1e-30)
            sweep[eta] = {"fd": directional_fd, "relative_error": rel}
            print(
                f"[level2] eta={eta:.1e} fd={directional_fd:.8e} "
                f"adj={directional_adjoint:.8e} rel={rel:.3e}",
                flush=True,
            )

    payload: dict[str, Any] = {}
    if is_root(comm):
        payload = {
            "level": 2,
            "directional_adjoint": directional_adjoint,
            "sweep": {f"{eta:.1e}": sweep[eta] for eta in ETAS},
            "best_relative_error": min(v["relative_error"] for v in sweep.values()),
        }
    _write_result("level2_mesh_motion_vjp", payload, comm)
    return payload


# ---------------------------------------------------------------------------
# Level 3: DAFoam-only volume-coordinate VJP directional check
# ---------------------------------------------------------------------------
def level3_dafoam_volume_vjp(comm, seed_index: int = 0) -> dict[str, Any]:
    driver._require_case_directory(CASE)
    backend = _make_dafoam_backend(comm, deterministic=True)
    geometry_backend = _make_geometry_backend(comm)
    output_shape = (read_gmsh_volume_point_count(MODEL_FILES.volume_mesh_file), 3)

    baseline = {name: np.asarray(value, dtype=float) for name, value in GEOMETRY_VALUES.items()}
    # Smooth, mesh-valid coordinate direction J_mesh . delta_d, built from a
    # PROPER central difference (normalized by 2h). The old code used a one-sided,
    # unnormalized X(d+h)-X(d) that was then re-scaled by eta -- a doubly-small,
    # ill-defined direction. delta_d is O(scale); h is the JVP step.
    h_direction = 1.0e-4
    rng = np.random.default_rng(seed_index)
    delta_d = {
        name: np.asarray(DESIGN_VARIABLE_SCALES[name] * rng.standard_normal(), dtype=float)
        for name in baseline
    }

    coordinates = run_on_root(comm, lambda: geometry_backend.forward(baseline))

    def _build_direction():
        x_plus = geometry_backend.forward(
            {k: baseline[k] + h_direction * delta_d[k] for k in baseline}
        )
        x_minus = geometry_backend.forward(
            {k: baseline[k] - h_direction * delta_d[k] for k in baseline}
        )
        return (x_plus - x_minus) / (2.0 * h_direction)

    direction = run_on_root(comm, _build_direction)
    coordinates = broadcast_array(comm, coordinates, shape=output_shape, dtype=np.float64)
    direction = broadcast_array(comm, direction, shape=output_shape, dtype=np.float64)

    patch_velocity = np.array([FLOW.velocity_m_per_s, FLOW.angle_of_attack_deg])
    _prepare_deterministic_baseline(backend, coordinates, patch_velocity)

    def run(coords):
        functions = backend.run_primal(
            {"volume_coordinates": coords, "patch_velocity": patch_velocity}
        )
        return {k: float(np.asarray(v).reshape(-1)[0]) for k, v in functions.items()}

    # One converged baseline primal establishes the cache; both the CL and CD
    # adjoints are then solved about that same state WITHOUT re-running the
    # primal between them (compute_vjp is a cache hit; the preconditioner built
    # for the first adjoint is reused by the second).
    baseline_functions = run(coordinates)
    adjoint = {}
    for function_name in backend.function_names:
        vjp = backend.compute_vjp(
            {"volume_coordinates": coordinates, "patch_velocity": patch_velocity},
            {function_name: np.array([1.0])},
        )
        adjoint[function_name] = float(np.sum(vjp["volume_coordinates"] * direction))

    sweep: dict[float, dict[str, Any]] = {}
    for eta in ETAS:
        f_plus = run(coordinates + eta * direction)
        f_minus = run(coordinates - eta * direction)
        displacement = eta * direction
        sweep[eta] = {
            "displacement_rms": float(np.sqrt(np.mean(displacement**2))),
            "displacement_max": float(np.max(np.abs(displacement))),
        }
        for function_name in backend.function_names:
            numerator = f_plus[function_name] - f_minus[function_name]
            fd = numerator / (2.0 * eta)
            rel = abs(fd - adjoint[function_name]) / max(abs(adjoint[function_name]), 1e-30)
            sweep[eta][function_name] = {
                "numerator": numerator,
                "fd": fd,
                "relative_error": rel,
            }
            if is_root(comm):
                print(
                    f"[level3] {function_name} eta={eta:.1e} "
                    f"disp_rms={sweep[eta]['displacement_rms']:.3e} "
                    f"num={numerator:.6e} fd={fd:.8e} "
                    f"adj={adjoint[function_name]:.8e} rel={rel:.3e}",
                    flush=True,
                )

    payload = {
        "level": 3,
        "mpi_ranks": comm_size(comm),
        "direction_norm": float(np.linalg.norm(direction)),
        "baseline_functions": baseline_functions,
        "directional_adjoint": adjoint,
        "sweep": {f"{eta:.1e}": sweep[eta] for eta in ETAS},
    }
    _write_result("level3_dafoam_volume_vjp", payload, comm)
    return payload


# ---------------------------------------------------------------------------
# Level 4: explicit chain-rule test
# ---------------------------------------------------------------------------
def level4_chain_rule(comm, seed_index: int = 0) -> dict[str, Any]:
    driver._require_case_directory(CASE)
    backend = _make_dafoam_backend(comm, deterministic=True)
    geometry_backend = _make_geometry_backend(comm)
    output_shape = (read_gmsh_volume_point_count(MODEL_FILES.volume_mesh_file), 3)

    baseline = {name: np.asarray(value, dtype=float) for name, value in GEOMETRY_VALUES.items()}
    coordinates = run_on_root(comm, lambda: geometry_backend.forward(baseline))
    coordinates = broadcast_array(comm, coordinates, shape=output_shape, dtype=np.float64)
    patch_velocity = np.array([FLOW.velocity_m_per_s, FLOW.angle_of_attack_deg])
    # One baseline primal (inside prepare) is reused by every function's adjoint.
    _prepare_deterministic_baseline(backend, coordinates, patch_velocity)

    rng = np.random.default_rng(seed_index)
    delta_dv = {
        name: np.asarray(rng.standard_normal() * DESIGN_VARIABLE_SCALES[name], dtype=float)
        for name in baseline
    }
    h_direction = 1.0e-4

    payload: dict[str, Any] = {"level": 4, "mpi_ranks": comm_size(comm), "functions": {}}
    for function_name in backend.function_names:
        # Collective adjoint; no primal rerun (cache hit at the frozen baseline).
        dafoam_vjp = backend.compute_vjp(
            {"volume_coordinates": coordinates, "patch_velocity": patch_velocity},
            {function_name: np.array([1.0])},
        )
        volume_cotangent = dafoam_vjp["volume_coordinates"]

        def _compare_paths(cotangent=volume_cotangent):
            # Path A: Xbar^T (J_mesh delta_d), via a mesh-motion central FD.
            plus = geometry_backend.forward(
                {k: baseline[k] + h_direction * delta_dv[k] for k in baseline}
            )
            minus = geometry_backend.forward(
                {k: baseline[k] - h_direction * delta_dv[k] for k in baseline}
            )
            j_delta = (plus - minus) / (2.0 * h_direction)
            path_a = float(np.sum(cotangent * j_delta))
            # Path B: delta_d^T dbar, via the mesh-motion VJP of Xbar.
            dbar = geometry_backend.compute_vjp(baseline, cotangent)
            path_b = float(sum(np.sum(dbar[name] * delta_dv[name]) for name in baseline))
            return {
                "xbar_jmesh_delta": path_a,
                "delta_dbar": path_b,
                "relative_error": abs(path_a - path_b) / max(abs(path_b), 1e-30),
            }

        result = run_on_root(comm, _compare_paths)
        if is_root(comm):
            payload["functions"][function_name] = result
            print(
                f"[level4] {function_name} A={result['xbar_jmesh_delta']:.8e} "
                f"B={result['delta_dbar']:.8e} rel={result['relative_error']:.3e}",
                flush=True,
            )
    _write_result("level4_chain_rule", payload, comm)
    return payload


# ---------------------------------------------------------------------------
# Level 5: one-DV, one-output end-to-end centered FD
# ---------------------------------------------------------------------------
def level5_end_to_end(comm) -> dict[str, Any]:
    driver._require_case_directory(CASE)
    backend = _make_dafoam_backend(comm, deterministic=True)
    geometry_backend = _make_geometry_backend(comm)
    output_shape = (read_gmsh_volume_point_count(MODEL_FILES.volume_mesh_file), 3)

    baseline = {name: np.asarray(value, dtype=float) for name, value in GEOMETRY_VALUES.items()}
    patch_velocity = np.array([FLOW.velocity_m_per_s, FLOW.angle_of_attack_deg])

    # Freeze the converged baseline flow state; every FD sample restores it.
    baseline_coords = run_on_root(comm, lambda: geometry_backend.forward(baseline))
    baseline_coords = broadcast_array(
        comm, baseline_coords, shape=output_shape, dtype=np.float64
    )
    _prepare_deterministic_baseline(backend, baseline_coords, patch_velocity)

    def evaluate_functions(design_point) -> dict[str, float]:
        coords = run_on_root(comm, lambda: geometry_backend.forward(design_point))
        coords = broadcast_array(comm, coords, shape=output_shape, dtype=np.float64)
        functions = backend.run_primal(
            {"volume_coordinates": coords, "patch_velocity": patch_velocity}
        )
        return {k: float(np.asarray(v).reshape(-1)[0]) for k, v in functions.items()}

    def analytical() -> dict[tuple[str, str], np.ndarray]:
        # One end-to-end reverse: DAFoam volume cotangent -> mesh-motion VJP.
        coords = run_on_root(comm, lambda: geometry_backend.forward(baseline))
        coords = broadcast_array(comm, coords, shape=output_shape, dtype=np.float64)
        backend.run_primal({"volume_coordinates": coords, "patch_velocity": patch_velocity})
        result: dict[tuple[str, str], np.ndarray] = {}
        vjp = backend.compute_vjp(
            {"volume_coordinates": coords, "patch_velocity": patch_velocity},
            {LEVEL5_OUTPUT: np.array([1.0])},
        )
        volume_cotangent = vjp["volume_coordinates"]
        dbar = run_on_root(comm, lambda: geometry_backend.compute_vjp(baseline, volume_cotangent))
        if is_root(comm):
            result[(LEVEL5_OUTPUT, LEVEL5_DESIGN_VARIABLE)] = np.asarray(
                dbar[LEVEL5_DESIGN_VARIABLE]
            )
        return result

    comparison = check_derivatives_forward_first(
        evaluate_functions,
        analytical,
        baseline,
        output_names=(LEVEL5_OUTPUT,),
        design_variable_specs={LEVEL5_DESIGN_VARIABLE: ()},
        etas=ETAS,
        scales={LEVEL5_DESIGN_VARIABLE: DESIGN_VARIABLE_SCALES[LEVEL5_DESIGN_VARIABLE]},
        guard=True,
        print_results=is_root(comm),
    )
    payload = {
        "level": 5,
        "mpi_ranks": comm_size(comm),
        "design_variable": LEVEL5_DESIGN_VARIABLE,
        "output": LEVEL5_OUTPUT,
        "best": {
            f"{k[0]}::{k[1]}": {"eta": v[0], "relative_error": v[1]}
            for k, v in comparison.best().items()
        },
    }
    _write_result("level5_end_to_end", payload, comm)
    return payload


LEVELS: dict[str, Callable[[Any], dict[str, Any]]] = {
    "0": level0_forward_repetition,
    "1": level1_mesh_motion_forward,
    "2": level2_mesh_motion_vjp,
    "3": level3_dafoam_volume_vjp,
    "4": level4_chain_rule,
    "5": level5_end_to_end,
}


def main() -> None:
    comm = resolve_comm()
    if len(sys.argv) < 2 or sys.argv[1] not in LEVELS:
        if is_root(comm):
            print(
                "Usage: python -m bsm3.core.boundary_surface_movement."
                "e175_derivative_ladder <level 0-5>",
                file=sys.stderr,
                flush=True,
            )
        raise SystemExit(2)
    level = sys.argv[1]
    if is_root(comm):
        print(
            f"[ladder] Level {level} on np={comm_size(comm)} "
            f"(rank {comm_rank(comm)})",
            flush=True,
        )
    LEVELS[level](comm)


if __name__ == "__main__":
    main()
