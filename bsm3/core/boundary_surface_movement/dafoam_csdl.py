"""CSDL interface for a DAFoam primal and discrete-adjoint analysis.

The mesh-motion pipeline owns the complete, global volume-coordinate variable.
DAFoam, on the other hand, owns a partitioned OpenFOAM mesh and expects local
``volCoord`` arrays.  This module keeps that distinction behind a small backend
interface:

``DAFoamAnalysisOperation``
    A CSDL explicit operation whose outputs are aerodynamic functions.  Its
    custom VJP asks the backend for total derivatives, so the mesh-coordinate
    cotangent remains connected to the upstream volume and surface motion.

``PYDAFoamBackend``
    The live DAFoam implementation.  It runs the primal, forms the function and
    residual Jacobian-transpose products, solves the discrete adjoint, and
    scatters the partitioned volume-coordinate gradient back to the global
    BSM3/Gmsh node ordering.

DAFoam, PETSc, and MPI are imported lazily.  Importing BSM3 and running its unit
tests therefore does not require a sourced DAFoam/OpenFOAM environment.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

import csdl_alpha as csdl
import numpy as np
from scipy.spatial import cKDTree


@runtime_checkable
class DAFoamBackend(Protocol):
    """Backend contract used by :class:`DAFoamAnalysisOperation`."""

    function_names: tuple[str, ...]

    def run_primal(
        self, inputs: Mapping[str, np.ndarray]
    ) -> Mapping[str, float | np.ndarray]:
        """Run the primal and return every configured aerodynamic function."""

    def compute_vjp(
        self,
        inputs: Mapping[str, np.ndarray],
        output_seeds: Mapping[str, np.ndarray],
    ) -> Mapping[str, np.ndarray]:
        """Return total input cotangents from the discrete adjoint."""


class DAFoamAnalysisOperation(csdl.experimental.CustomExplicitOperationBeta):
    """Expose converged DAFoam functions as CSDL variables.

    Parameters
    ----------
    backend
        A live :class:`PYDAFoamBackend` or a contract-compatible test backend.

    Notes
    -----
    ``volume_coordinates`` is always the global ``(num_points, 3)`` BSM3
    coordinate array. Additional keyword inputs use their DAFoam ``inputInfo``
    names, e.g. ``patch_velocity``.
    """

    def __init__(self, backend: DAFoamBackend):
        super().__init__()
        self.backend = backend
        names = tuple(str(name) for name in backend.function_names)
        if not names or len(set(names)) != len(names):
            raise ValueError("DAFoam function_names must be unique and nonempty.")
        self.function_names = names

    def evaluate(self, volume_coordinates, **additional_inputs):
        self.declare_input("volume_coordinates", volume_coordinates)
        for name, variable in additional_inputs.items():
            if name == "volume_coordinates":
                raise ValueError("volume_coordinates is a reserved input name.")
            if (
                hasattr(self.backend, "volume_input_name")
                and name == self.backend.volume_input_name
            ):
                raise ValueError(
                    f"{name!r} is managed internally from volume_coordinates."
                )
            self.declare_input(str(name), variable)

        outputs = {
            name: self.create_output(name, (1,))
            for name in self.function_names
        }
        self.declare_vjp_function(
            DAFoamAnalysisVJP,
            backend=self.backend,
            function_names=self.function_names,
        )
        return outputs

    def compute(self, inputs, outputs):
        values = self.backend.run_primal(_copy_array_mapping(inputs))
        missing = set(self.function_names).difference(values)
        if missing:
            raise KeyError(
                "DAFoam backend did not return functions: "
                + ", ".join(sorted(missing))
            )
        for name in self.function_names:
            value = np.asarray(values[name], dtype=float).reshape(-1)
            if value.size != 1:
                raise ValueError(
                    f"DAFoam function {name!r} must be scalar; got {value.shape}."
                )
            outputs[name] = value


class DAFoamAnalysisVJP(csdl.experimental.CustomExplicitOperationBeta):
    """Custom reverse-mode derivative supplied by the DAFoam adjoint."""

    def __init__(
        self,
        backend: DAFoamBackend,
        function_names: tuple[str, ...],
    ):
        super().__init__()
        self.backend = backend
        self.function_names = tuple(function_names)
        self._input_names: tuple[str, ...] = ()

    def evaluate(self, inputs, d_outputs):
        self._input_names = tuple(inputs)
        for name, variable in inputs.items():
            self.declare_input(name, variable)
        for name in self.function_names:
            self.declare_input(f"d_{name}", d_outputs[name])

        derivatives = {}
        for name, variable in inputs.items():
            derivatives[name] = self.create_output(
                f"d_{name}", variable.shape
            )
        return derivatives

    def compute(self, inputs, outputs):
        primal_inputs = {
            name: np.asarray(inputs[name], dtype=float).copy()
            for name in self._input_names
        }
        seeds = {
            name: np.asarray(inputs[f"d_{name}"], dtype=float).copy()
            for name in self.function_names
        }
        derivatives = self.backend.compute_vjp(primal_inputs, seeds)
        missing = set(self._input_names).difference(derivatives)
        if missing:
            raise KeyError(
                "DAFoam backend did not return input VJPs: "
                + ", ".join(sorted(missing))
            )
        for name in self._input_names:
            derivative = np.asarray(derivatives[name], dtype=float)
            if derivative.shape != primal_inputs[name].shape:
                raise ValueError(
                    f"DAFoam VJP for {name!r} has shape {derivative.shape}; "
                    f"expected {primal_inputs[name].shape}."
                )
            outputs[f"d_{name}"] = derivative


def add_csdl_inputs_to_da_options(
    options: Mapping[str, Any],
    *,
    volume_input_name: str = "aero_vol_coords",
    patch_velocity_input_name: str | None = "patch_velocity",
    farfield_patches: tuple[str, ...] | list[str] = ("farfield",),
    flow_axis: str = "x",
    normal_axis: str = "z",
) -> dict[str, Any]:
    """Return DAFoam options with differentiable mesh/flow inputs enabled."""

    result = deepcopy(dict(options))
    input_info = deepcopy(result.get("inputInfo", {}))
    input_info[str(volume_input_name)] = {
        "type": "volCoord",
        "components": ["solver", "function"],
    }
    if patch_velocity_input_name is not None:
        patches = [str(name) for name in farfield_patches]
        if not patches:
            raise ValueError("farfield_patches cannot be empty.")
        input_info[str(patch_velocity_input_name)] = {
            "type": "patchVelocity",
            "patches": patches,
            "flowAxis": str(flow_axis),
            "normalAxis": str(normal_axis),
            "components": ["solver", "function"],
        }
    result["inputInfo"] = input_info
    return result


def make_patch_velocity(airspeed_m_per_s, angle_of_attack_deg):
    """Create the two-entry DAFoam ``patchVelocity`` CSDL input."""

    return csdl.concatenate((airspeed_m_per_s, angle_of_attack_deg))


def build_local_volume_coordinate_map(
    dafoam_instance,
    reference_volume_coordinates: np.ndarray,
    *,
    absolute_tolerance: float | None = None,
) -> np.ndarray:
    """Map local OpenFOAM points to global BSM3/Gmsh point indices.

    The map is coordinate based because ``gmshToFoam`` and domain decomposition
    are free to reorder points. Processor-boundary duplicates intentionally map
    to the same global point; their adjoint contributions are summed later.
    """

    reference = np.asarray(reference_volume_coordinates, dtype=float)
    if reference.ndim != 2 or reference.shape[1] != 3:
        raise ValueError("reference_volume_coordinates must have shape (n, 3).")
    if not np.all(np.isfinite(reference)):
        raise ValueError("reference_volume_coordinates contains nonfinite values.")

    number_local = int(dafoam_instance.getNLocalPoints())
    local_flat = np.empty(3 * number_local, dtype=float)
    dafoam_instance.solver.getOFMeshPoints(local_flat)
    local = local_flat.reshape((-1, 3))

    extent = float(np.max(np.ptp(reference, axis=0)))
    tolerance = (
        max(1.0, extent) * 1.0e-9
        if absolute_tolerance is None
        else float(absolute_tolerance)
    )
    if tolerance <= 0.0:
        raise ValueError("absolute_tolerance must be positive.")

    tree = cKDTree(reference)
    distance, index = tree.query(local, k=1)
    worst = float(np.max(distance)) if distance.size else 0.0
    if worst > tolerance:
        row = int(np.argmax(distance))
        raise ValueError(
            "Could not match the local OpenFOAM points to the reference Gmsh "
            f"mesh: worst distance {worst:.6e} exceeds {tolerance:.6e} at "
            f"local point {row}."
        )
    if reference.shape[0] > 1 and local.shape[0]:
        nearest_two, _ = tree.query(local, k=2)
        ambiguous = np.where(nearest_two[:, 1] <= tolerance)[0]
        if ambiguous.size:
            raise ValueError(
                "The reference Gmsh mesh has coincident points within the "
                f"coordinate-match tolerance near local point "
                f"{int(ambiguous[0])}; a unique OpenFOAM-to-Gmsh map cannot "
                "be constructed."
            )
    return np.asarray(index, dtype=np.int64)


class PYDAFoamBackend:
    """Live DAFoam primal/discrete-adjoint backend.

    The backend owns one stateful ``PYDAFOAM`` instance. It caches the last
    converged primal state, restores it before an adjoint evaluation, and reruns
    the primal if a VJP is requested at input values different from the cached
    point.
    """

    def __init__(
        self,
        dafoam_instance,
        reference_volume_coordinates: np.ndarray,
        *,
        case_directory: str | Path,
        volume_input_name: str = "aero_vol_coords",
        function_names: tuple[str, ...] = ("CL", "CD"),
        check_mesh: bool = True,
        coordinate_match_tolerance: float | None = None,
        volume_gradient_ownership: str = "replicated",
        deterministic_fd_mode: bool = False,
        invalidate_adjoint_on_primal: bool = True,
    ):
        self.dafoam_instance = dafoam_instance
        self.case_directory = Path(case_directory).expanduser().resolve()
        self.volume_input_name = str(volume_input_name)
        self.function_names = tuple(str(name) for name in function_names)
        self.check_mesh = bool(check_mesh)
        if volume_gradient_ownership not in ("replicated", "root"):
            raise ValueError(
                "volume_gradient_ownership must be 'replicated' or 'root'; got "
                f"{volume_gradient_ownership!r}."
            )
        # 'replicated' keeps the validated Allreduce path (every rank holds the
        # full global gradient); 'root' uses MPI.Reduce so only rank 0 owns it.
        # Validate the two against one another before dropping 'replicated'.
        self.volume_gradient_ownership = str(volume_gradient_ownership)
        self.reference_volume_coordinates = np.asarray(
            reference_volume_coordinates, dtype=float
        ).copy()
        self.local_to_global = build_local_volume_coordinate_map(
            dafoam_instance,
            self.reference_volume_coordinates,
            absolute_tolerance=coordinate_match_tolerance,
        )
        self._validate_dafoam_options()

        try:
            from petsc4py import PETSc
        except ImportError as error:
            raise RuntimeError(
                "petsc4py is required by the live DAFoam adjoint backend. "
                "Source the DAFoam environment before launching Python."
            ) from error
        self.PETSc = PETSc

        dafoam_instance.solverAD.initializedRdWTMatrixFree()
        self._psi = PETSc.Vec().create(comm=dafoam_instance.comm)
        self._psi.setSizes(
            (int(dafoam_instance.getNLocalAdjointStates()), PETSc.DECIDE),
            bsize=1,
        )
        self._psi.setFromOptions()
        self._psi.zeroEntries()
        self._run_coloring = (
            dafoam_instance.getOption("adjEqnSolMethod") != "fixedPoint"
        )
        # Deterministic finite-difference mode: restore one fixed converged
        # baseline state before every primal so +h/-h/baseline samples are
        # independent (see the derivative-review addendum, finding 1).
        self.deterministic_fd_mode = bool(deterministic_fd_mode)
        # Invalidate the adjoint preconditioner/linearization whenever a new
        # primal point is accepted, so an adjoint never reuses a factorization
        # assembled at a different mesh/state (addendum finding 2).
        self.invalidate_adjoint_on_primal = bool(invalidate_adjoint_on_primal)
        self._baseline_states: np.ndarray | None = None
        self._cached_inputs: dict[str, np.ndarray] | None = None
        self._cached_states: np.ndarray | None = None
        self._cached_functions: dict[str, np.ndarray] | None = None

    @classmethod
    def from_options(
        cls,
        options: Mapping[str, Any],
        comm,
        reference_volume_coordinates: np.ndarray,
        *,
        case_directory: str | Path,
        **kwargs,
    ) -> "PYDAFoamBackend":
        """Instantiate ``PYDAFOAM`` lazily inside a prepared OpenFOAM case."""

        try:
            from dafoam import PYDAFOAM
        except ImportError as error:
            raise RuntimeError(
                "Could not import dafoam.PYDAFOAM. Source the DAFoam "
                "loadDAFoam.sh environment before launching Python."
            ) from error

        case = Path(case_directory).expanduser().resolve()
        previous = Path.cwd()
        try:
            import os

            os.chdir(case)
            instance = PYDAFOAM(options=deepcopy(dict(options)), comm=comm)
        finally:
            os.chdir(previous)
        instance.run_directory = str(case)
        return cls(
            instance,
            reference_volume_coordinates,
            case_directory=case,
            **kwargs,
        )

    def run_primal(
        self, inputs: Mapping[str, np.ndarray]
    ) -> Mapping[str, np.ndarray]:
        arrays = _copy_array_mapping(inputs)
        solver_inputs = self._solver_inputs(arrays)
        dafoam = self.dafoam_instance

        with self._working_directory():
            dafoam.set_solver_input(solver_inputs)
            if self.check_mesh and int(dafoam.solver.checkMesh()) != 1:
                dafoam.solver.writeFailedMesh()
                raise RuntimeError("DAFoam rejected the deformed volume mesh.")

            # In deterministic FD mode restore the fixed converged baseline
            # before every primal; otherwise fall back to the production warm
            # start from the previous solution.  A missing baseline is an error,
            # never a silent fall-back to a history-dependent cached state.
            if self.deterministic_fd_mode:
                if self._baseline_states is None:
                    raise RuntimeError(
                        "deterministic_fd_mode is enabled but no baseline state "
                        "has been captured. Run a converged baseline primal and "
                        "call set_deterministic_baseline() first."
                    )
                dafoam.setStates(self._baseline_states.copy())
            elif self._cached_states is not None:
                dafoam.setStates(self._cached_states.copy())
            dafoam()
            if int(getattr(dafoam, "primalFail", 0)) != 0:
                raise RuntimeError(
                    f"DAFoam primal failed with primalFail={dafoam.primalFail}."
                )

            states = np.asarray(dafoam.getStates(), dtype=float).copy()
            dafoam.solverAD.calcPrimalResidualStatistics("calc")
            functions = {
                name: np.asarray(
                    dafoam.solver.calcFunction(name), dtype=float
                ).reshape(1)
                for name in self.function_names
            }

        # A newly accepted primal makes any previously assembled adjoint
        # linearization/preconditioner stale.
        if self.invalidate_adjoint_on_primal:
            self._invalidate_adjoint_linearization()
        self._cached_inputs = arrays
        self._cached_states = states
        self._cached_functions = functions
        return {name: value.copy() for name, value in functions.items()}

    def set_deterministic_baseline(
        self, states: np.ndarray | None = None
    ) -> None:
        """Freeze the converged baseline state used by deterministic FD mode.

        With no argument the most recent cached (converged) state is used, so
        the intended sequence is: run one tightly converged baseline primal,
        call this, enable :attr:`deterministic_fd_mode`, then evaluate every
        ``+h``/``-h`` perturbation from that fixed state.
        """

        source = self._cached_states if states is None else states
        if source is None:
            raise RuntimeError(
                "No converged state available; run a baseline primal before "
                "capturing the deterministic FD baseline."
            )
        self._baseline_states = np.asarray(source, dtype=float).copy()

    def reset_primal_state(self) -> None:
        """Clear the warm-start cache so the next primal cold-starts."""

        self._cached_states = None
        self._cached_inputs = None

    def _invalidate_adjoint_linearization(self) -> None:
        """Destroy and clear the state/mesh-dependent adjoint matrix and PC.

        Coloring depends only on the topology (the Jacobian sparsity pattern),
        not on the state or coordinate values, so it is intentionally NOT reset
        here and is reused across deformations.  Only the state-dependent
        ``dRdWTPC`` matrix and its ``ksp`` are rebuilt (lazily inside
        :meth:`_solve_adjoint`).  The old PETSc objects are explicitly destroyed
        so their memory is released instead of leaked.
        """

        dafoam = self.dafoam_instance
        ksp = getattr(dafoam, "ksp", None)
        if ksp is not None:
            try:
                ksp.destroy()
            except Exception:
                pass
            dafoam.ksp = None
        preconditioner = getattr(dafoam, "dRdWTPC", None)
        if preconditioner is not None:
            try:
                preconditioner.destroy()
            except Exception:
                pass
            dafoam.dRdWTPC = None

    def invalidate_topology(self) -> None:
        """Invalidate coloring *and* the linearization for a topology change.

        Call this only when the mesh connectivity/sparsity actually changes
        (a different mesh), which is the sole case where the reusable coloring
        becomes stale. A pure coordinate deformation does not need it.
        """

        self._run_coloring = (
            self.dafoam_instance.getOption("adjEqnSolMethod") != "fixedPoint"
        )
        self._invalidate_adjoint_linearization()

    def compute_vjp(
        self,
        inputs: Mapping[str, np.ndarray],
        output_seeds: Mapping[str, np.ndarray],
    ) -> Mapping[str, np.ndarray]:
        arrays = _copy_array_mapping(inputs)
        if not _same_array_mapping(arrays, self._cached_inputs):
            self.run_primal(arrays)
        assert self._cached_states is not None

        dafoam = self.dafoam_instance
        solver_inputs = self._solver_inputs(arrays)
        states = self._cached_states.copy()
        direct = {
            name: np.zeros_like(value)
            for name, value in solver_inputs.items()
        }
        d_function_d_state = np.zeros_like(states)

        with self._working_directory():
            dafoam.set_solver_input(solver_inputs)
            dafoam.setStates(states)
            input_info = dafoam.getOption("inputInfo")

            for function_name in self.function_names:
                seed = np.asarray(
                    output_seeds.get(function_name, np.zeros(1)), dtype=float
                ).reshape(1)
                if not np.any(seed):
                    continue

                state_product = np.zeros_like(states)
                dafoam.solverAD.calcJacTVecProduct(
                    "dafoam_solver_states",
                    "stateVar",
                    states,
                    function_name,
                    "function",
                    seed,
                    state_product,
                )
                d_function_d_state += state_product

                for input_name, input_value in solver_inputs.items():
                    if "function" not in input_info[input_name].get(
                        "components", ()
                    ):
                        continue
                    product = np.zeros_like(input_value)
                    dafoam.solverAD.calcJacTVecProduct(
                        input_name,
                        input_info[input_name]["type"],
                        input_value,
                        function_name,
                        "function",
                        seed,
                        product,
                    )
                    direct[input_name] += product

            psi = self._solve_adjoint(d_function_d_state)
            for input_name, input_value in solver_inputs.items():
                if "solver" not in input_info[input_name].get("components", ()):
                    continue
                residual_product = np.zeros_like(input_value)
                dafoam.solverAD.calcJacTVecProduct(
                    input_name,
                    input_info[input_name]["type"],
                    input_value,
                    "aero_residuals",
                    "residual",
                    psi,
                    residual_product,
                )
                direct[input_name] -= residual_product

        result: dict[str, np.ndarray] = {}
        result["volume_coordinates"] = self._global_volume_vjp(
            direct[self.volume_input_name]
        )
        for name, value in arrays.items():
            if name == "volume_coordinates":
                continue
            result[name] = np.asarray(direct[name], dtype=float).reshape(
                value.shape
            )
        return result

    def _solver_inputs(
        self, inputs: Mapping[str, np.ndarray]
    ) -> dict[str, np.ndarray]:
        if "volume_coordinates" not in inputs:
            raise KeyError("volume_coordinates")
        global_coordinates = np.asarray(
            inputs["volume_coordinates"], dtype=float
        )
        if global_coordinates.shape != self.reference_volume_coordinates.shape:
            raise ValueError(
                "volume_coordinates has shape "
                f"{global_coordinates.shape}; expected "
                f"{self.reference_volume_coordinates.shape}."
            )
        if not np.all(np.isfinite(global_coordinates)):
            raise ValueError("volume_coordinates contains nonfinite values.")

        result = {
            self.volume_input_name: global_coordinates[
                self.local_to_global
            ].reshape(-1)
        }
        for name, value in inputs.items():
            if name == "volume_coordinates":
                continue
            result[name] = np.asarray(value, dtype=float).copy()
        return result

    def _solve_adjoint(self, right_hand_side: np.ndarray) -> np.ndarray:
        dafoam = self.dafoam_instance
        if not np.all(np.isfinite(right_hand_side)):
            raise FloatingPointError("DAFoam adjoint RHS contains NaN or Inf.")
        rhs = dafoam.array2Vec(right_hand_side)

        if dafoam.getOption("adjUseColoring") and self._run_coloring:
            dafoam.solver.runColoring()
            self._run_coloring = False

        method = dafoam.getOption("adjEqnSolMethod")
        self._psi.zeroEntries()
        if method == "Krylov":
            if dafoam.dRdWTPC is None:
                dafoam.dRdWTPC = self.PETSc.Mat().create(dafoam.comm)
                dafoam.solver.calcdRdWT(1, dafoam.dRdWTPC)
            if dafoam.ksp is None:
                dafoam.ksp = self.PETSc.KSP().create(dafoam.comm)
                dafoam.solverAD.createMLRKSPMatrixFree(
                    dafoam.dRdWTPC, dafoam.ksp
                )
            failed = dafoam.solverAD.solveLinearEqn(
                dafoam.ksp, rhs, self._psi
            )
        elif method == "fixedPoint":
            failed = dafoam.solverAD.runFPAdj(rhs, self._psi)
        else:
            raise ValueError(
                f"Unsupported DAFoam adjEqnSolMethod {method!r}."
            )
        if failed:
            raise RuntimeError("DAFoam discrete-adjoint solve failed.")
        return np.asarray(dafoam.vec2Array(self._psi), dtype=float)

    def _global_volume_vjp(self, local_flat: np.ndarray) -> np.ndarray:
        from bsm3.core.boundary_surface_movement.geometry_volume_mpi import (
            assemble_local_gradient,
            reduce_gradient,
        )

        local = np.asarray(local_flat, dtype=float).reshape((-1, 3))
        if local.shape[0] != self.local_to_global.size:
            raise ValueError(
                "DAFoam returned a volCoord VJP with the wrong local size."
            )
        # np.add.at (inside assemble_local_gradient) is required because
        # processor-boundary duplicate points map several local rows to the same
        # global point and their contributions must add, not overwrite.
        global_gradient = assemble_local_gradient(
            local,
            self.local_to_global,
            self.reference_volume_coordinates.shape[0],
        )
        return reduce_gradient(
            self.dafoam_instance.comm,
            global_gradient,
            ownership=self.volume_gradient_ownership,
        )

    def _validate_dafoam_options(self) -> None:
        dafoam = self.dafoam_instance
        input_info = dafoam.getOption("inputInfo")
        if self.volume_input_name not in input_info:
            raise KeyError(
                f"DAFoam inputInfo has no {self.volume_input_name!r} entry."
            )
        if input_info[self.volume_input_name]["type"] != "volCoord":
            raise ValueError(
                f"{self.volume_input_name!r} must have type 'volCoord'."
            )
        functions = dafoam.getOption("function")
        missing = set(self.function_names).difference(functions)
        if missing:
            raise KeyError(
                "DAFoam function options are missing: "
                + ", ".join(sorted(missing))
            )

    @contextmanager
    def _working_directory(self):
        import os

        previous = Path.cwd()
        os.chdir(self.case_directory)
        try:
            yield
        finally:
            os.chdir(previous)


def _copy_array_mapping(
    values: Mapping[str, Any],
) -> dict[str, np.ndarray]:
    return {
        str(name): np.asarray(value, dtype=float).copy()
        for name, value in values.items()
    }


def _same_array_mapping(
    left: Mapping[str, np.ndarray],
    right: Mapping[str, np.ndarray] | None,
) -> bool:
    if right is None or set(left) != set(right):
        return False
    return all(
        left[name].shape == right[name].shape
        and np.array_equal(left[name], right[name])
        for name in left
    )


__all__ = [
    "DAFoamAnalysisOperation",
    "DAFoamAnalysisVJP",
    "DAFoamBackend",
    "PYDAFoamBackend",
    "add_csdl_inputs_to_da_options",
    "build_local_volume_coordinate_map",
    "make_patch_velocity",
]
