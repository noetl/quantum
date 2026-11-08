"""Run-state for the VQCC baseline.

Competition mode does not write circuit bytes unless a baseline file is
already on disk. Structural mode writes a real kickmix circuit and labels it
as a fixture, never as a verifier pass. Official competition verification stays
blocked until the Kaggle verifier package is present and its entry point is
confirmed.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from vqcc.official_verifier import (
    REFERENCE_SEED,
    discover_dataset_root,
    run_official_task,
)
from vqcc.formulas import (
    E_GAP_FLOOR_HA,
    FROBENIUS_TOLERANCE_HA,
    LAMBDA_FLOOR_HA,
    QUBIT_CAP,
    FormulaSource,
    dfthcsos_constraint_notes,
    invsqrt_cost,
)

# main SHA inspected before this implementation. The spec at this commit is
# the contract. Later commits on the implementation branch do not retarget it.
# main inspected for this implementation (merge of PR #10). The spec file
# itself was introduced at 0b3915b and was not edited by that merge.
SPEC_MAIN_SHA = "d47053659fed3b110eb057f58d048ac50bf9ba7d"
SPEC_PATH = "specs/001-noetl-pipeline/spec.md"
NOETL_TESTED_VERSION = "5.3.2"
KICKMIX_TESTED_VERSION = "1.0.0"

TASKS = ("invsqrt", "dqi", "dfthcsos")

# Layouts the public write-ups mention. None of these paths is treated as
# proof that the official archive uses them. A missing path is a block, not
# a guess that the file would have passed.
BASELINE_RELATIVE = {
    "invsqrt": (
        "sample_submission/invsqrt.kmb",
        "sample_submission/invsqrt.kmx",
        "invsqrt.kmb",
        "invsqrt.kmx",
    ),
    "dqi": (
        "sample_submission/dqi.kmb",
        "sample_submission/dqi.kmx",
        "dqi.kmb",
        "dqi.kmx",
    ),
    "dfthcsos": (
        "sample_submission/dfthcsos",
        "dfthcsos",
    ),
}

STRUCTURAL_KMX = {
    "invsqrt": (
        "# structural fixture for pipeline wiring\n"
        "# Not an invsqrt submission and not verifier-accepted.\n"
        "X q0\n"
        "CCX q0 q1 q2\n"
        "Z_POW q2 0.25\n"
    ),
    "dqi": (
        "# structural fixture for pipeline wiring\n"
        "# Not a dqi submission and not verifier-accepted.\n"
        "CX q0 q1\n"
        "CCX q1 q2 q3\n"
        "CCX q0 q2 q3\n"
    ),
    "dfthcsos": (
        "# structural fixture for pipeline wiring\n"
        "# Not a dfthcsos angle circuit and not verifier-accepted.\n"
        "CX q0 q1\n"
        "CCX q0 q1 q2\n"
    ),
}


class PipelineError(RuntimeError):
    """The playbook step cannot continue. Not a leaderboard result."""


def prepare_run(
    repo_root: Path,
    runs_root: Path,
    mode: str,
    data_dir: Path,
    seed: str = REFERENCE_SEED,
    package_when_verified: bool = False,
) -> dict:
    if mode not in {"competition", "structural"}:
        raise PipelineError("mode must be competition or structural")
    repo_root = repo_root.resolve()
    runs_root = _abs(repo_root, runs_root)
    data_dir = _abs(repo_root, data_dir)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    state = {
        "schema": "vqcc.run/v1",
        "run_id": run_id,
        "run_dir": str(run_dir),
        "repo_root": str(repo_root),
        "mode": mode,
        "data_dir": str(data_dir),
        "spec": {
            "path": SPEC_PATH,
            "main_sha": SPEC_MAIN_SHA,
            "issues": [
                "https://github.com/noetl/quantum/issues/2",
                "https://github.com/noetl/quantum/issues/3",
                "https://github.com/noetl/quantum/issues/4",
                "https://github.com/noetl/quantum/issues/5",
                "https://github.com/noetl/quantum/issues/6",
                "https://github.com/noetl/quantum/issues/7",
                "https://github.com/noetl/quantum/issues/8",
                "https://github.com/noetl/quantum/issues/9",
            ],
        },
        "runtime": {
            "noetl_tested_version": NOETL_TESTED_VERSION,
            "noetl_import_version": _noetl_version(),
            "kickmix_tested_version": KICKMIX_TESTED_VERSION,
            "kickmix": _kickmix_status(),
        },
        "seed": str(seed),
        "package_when_verified": bool(package_when_verified),
        "tasks": {},
        "verification": None,
        "costs": None,
        "package": None,
        "leaderboard_score": None,
        "experiment_log_written": False,
    }
    _save(run_dir, state)
    pointer = {"run_dir": str(run_dir)}
    runs_root.mkdir(parents=True, exist_ok=True)
    (runs_root / "active.json").write_text(json.dumps(pointer), encoding="utf-8")
    return _step("prepare", state, run_dir=str(run_dir), mode=mode)


def check_data(repo_root: Path, runs_root: Path) -> dict:
    state, run_dir = _load(repo_root, runs_root)
    data_dir = Path(state["data_dir"])
    located = _locate_dataset(data_dir, Path(state["repo_root"]))
    verifiers = data_dir / "verifiers"
    state["data"] = {
        "data_dir": str(data_dir),
        "data_dir_exists": data_dir.is_dir(),
        "verifiers_dir": str(verifiers),
        "verifiers_present": verifiers.is_dir(),
        "dataset": located,
        "status": "present" if located.get("found") else "absent",
        "note": (
            None
            if located.get("found")
            else "Official verifier scripts were not found. A shallow verifiers/ "
            "directory is not enough. Rules were not accepted and the dataset "
            "was not downloaded by this run."
        ),
    }
    _save(run_dir, state)
    return _step("check_data", state, **state["data"])


def adapt_task(repo_root: Path, runs_root: Path, task: str) -> dict:
    if task not in TASKS:
        raise PipelineError(f"unknown task {task}")
    state, run_dir = _load(repo_root, runs_root)
    mode = state["mode"]
    if mode == "structural":
        record = _write_structural_fixture(run_dir, task)
    else:
        record = _import_baseline(Path(state["data_dir"]), run_dir, task)
    record["competition_verified"] = False
    record["leaderboard_score"] = None
    state["tasks"][task] = record
    _save(run_dir, state)
    return _step("adapt", state, task=task, artifact=record)


def verify(repo_root: Path, runs_root: Path, seed: str | None = None, timeout_s: int | None = None) -> dict:
    """Run the three official verifiers one after another."""

    reports = []
    for task in TASKS:
        reports.append(
            verify_official(repo_root, runs_root, task, seed=seed, timeout_s=timeout_s)
        )
    state, _run_dir = _load(repo_root, runs_root)
    return _step("verify", state, **(state.get("verification") or {}))


def verify_official(
    repo_root: Path,
    runs_root: Path,
    task: str,
    seed: str | None = None,
    timeout_s: int | None = None,
) -> dict:
    if task not in TASKS:
        raise PipelineError(f"unknown task {task}")
    state, run_dir = _load(repo_root, runs_root)
    if state["mode"] == "structural":
        report = {
            "task": task,
            "status": "blocked",
            "competition_verified": False,
            "official_script": False,
            "mock_hook": False,
            "leaderboard_score": None,
            "reason": "structural mode does not run the official verifiers",
        }
    else:
        dataset = (state.get("data") or {}).get("dataset")
        if not dataset:
            dataset = _locate_dataset(Path(state["data_dir"]), Path(state["repo_root"]))
            state.setdefault("data", {})["dataset"] = dataset
        if not dataset.get("found"):
            report = {
                "task": task,
                "status": "blocked",
                "competition_verified": False,
                "official_script": True,
                "mock_hook": False,
                "leaderboard_score": None,
                "reason": dataset.get("reason") or "official verifier scripts were not found",
                "checked": dataset.get("checked"),
            }
        else:
            artifact = _candidate_artifact(state, task)
            report = run_official_task(
                root=Path(dataset["root"]),
                task=task,
                artifact=artifact,
                seed=seed or state.get("seed") or REFERENCE_SEED,
                timeout_s=timeout_s,
                log_dir=run_dir / "official",
            )
    task_state = state["tasks"].setdefault(
        task,
        {"role": "absent", "circuit_written": False, "competition_verified": False},
    )
    task_state["verification"] = report
    task_state["competition_verified"] = bool(report.get("competition_verified"))
    task_state["leaderboard_score"] = None
    state["tasks"][task] = task_state
    verified_flags = [
        bool((state["tasks"].get(name) or {}).get("competition_verified")) for name in TASKS
    ]
    state["verification"] = {
        "status": "pass" if all(verified_flags) else "blocked",
        "competition_verified": all(verified_flags),
        "mock": False,
        "tasks": [state["tasks"].get(name, {}).get("verification") for name in TASKS],
        "leaderboard_score": None,
        "aggregate_score": None,
    }
    _save(run_dir, state)
    return _step("verify_official", state, **report)


def cost(repo_root: Path, runs_root: Path, aggregate: bool = False) -> dict:
    state, run_dir = _load(repo_root, runs_root)
    reports = {}
    for task in TASKS:
        reports[task] = _cost_one(state["tasks"].get(task) or {})
    aggregate_report = None
    if aggregate:
        aggregate_report = {
            "requested": True,
            "computed": False,
            "unconfirmed": True,
            "source": "hub",
            "leaderboard_score": None,
            "note": (
                "FR-008 is still open. The hub geometric mean is not computed "
                "here because the three task costs are not a competition result, "
                "and the expression stays labeled unconfirmed."
            ),
        }
    else:
        aggregate_report = {
            "requested": False,
            "computed": False,
            "unconfirmed": True,
            "leaderboard_score": None,
        }
    state["costs"] = {
        "tasks": reports,
        "aggregate": aggregate_report,
        "leaderboard_score": None,
    }
    _save(run_dir, state)
    return _step("cost", state, **state["costs"])


def package(repo_root: Path, runs_root: Path) -> dict:
    from vqcc.packaging import PackageError, build_submission_zip

    state, run_dir = _load(repo_root, runs_root)
    reasons = []
    roles = []
    artifacts: dict[str, Path] = {}
    for task in TASKS:
        task_state = state["tasks"].get(task) or {}
        verification = task_state.get("verification") or {}
        if not verification.get("competition_verified"):
            reasons.append(
                f"{task}: competition_verified is false "
                f"({verification.get('status') or 'not run'})"
            )
            continue
        if verification.get("evidence_class") == "fixture":
            reasons.append(f"{task}: fixture evidence cannot open the package gate")
            continue
        roles.append(verification.get("bundle_role"))
        raw = verification.get("artifact")
        if not raw:
            reasons.append(f"{task}: verified report has no artifact path")
            continue
        artifacts[task] = Path(raw)
    if reasons:
        report = {
            "status": "not_ready",
            "zip_written": False,
            "zip_path": None,
            "reasons": reasons,
            "bundle_roles": roles,
            "leaderboard_score": None,
            "note": (
                "Packaging stays closed until all three official verifier scripts "
                "exit 0 on a non-fixture dataset. A generic hook exit 0 is not enough."
            ),
        }
    elif not state.get("package_when_verified"):
        report = {
            "status": "verified_not_packaged",
            "zip_written": False,
            "zip_path": None,
            "reasons": [],
            "bundle_roles": roles,
            "leaderboard_score": None,
            "note": (
                "Official verification passed. The zip was not written because "
                "package_when_verified is false. The reference dqi circuit is large."
            ),
        }
    else:
        output = run_dir / "submission.zip"
        try:
            built = build_submission_zip(
                invsqrt=artifacts["invsqrt"],
                dqi=artifacts["dqi"],
                dfthcsos_dir=artifacts["dfthcsos"],
                output=output,
            )
        except PackageError as exc:
            report = {
                "status": "not_ready",
                "zip_written": False,
                "zip_path": None,
                "reasons": [str(exc)],
                "bundle_roles": roles,
                "leaderboard_score": None,
            }
        else:
            distinct = sorted(set(roles))
            report = {
                "status": "packaged",
                "zip_written": True,
                "zip_path": built["output"],
                "entries": built["entries"],
                "bundle_roles": roles,
                "bundle_role": distinct[0] if len(distinct) == 1 else "mixed",
                "leaderboard_score": None,
                "disclaimer": built["disclaimer"],
                "note": (
                    "Zip of verifier-accepted files. Not a leaderboard score. "
                    "A reference bundle is not an optimized candidate."
                ),
            }
    state["package"] = report
    _save(run_dir, state)
    return _step("package", state, **report)


def record(repo_root: Path, runs_root: Path) -> dict:
    state, run_dir = _load(repo_root, runs_root)
    state["leaderboard_score"] = None
    state["experiment_log_written"] = False
    state["recorded_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    provenance = run_dir / "provenance.json"
    provenance.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _save(run_dir, state)
    summary = {
        "step": "record",
        "run_id": state["run_id"],
        "run_dir": str(run_dir),
        "provenance": str(provenance),
        "mode": state["mode"],
        "verification_status": (state.get("verification") or {}).get("status"),
        "package_status": (state.get("package") or {}).get("status"),
        "zip_written": False,
        "experiment_log_written": False,
        "leaderboard_score": None,
        "tasks": {
            task: {
                "role": (state["tasks"].get(task) or {}).get("role"),
                "competition_verified": False,
                "circuit_written": bool((state["tasks"].get(task) or {}).get("circuit_written")),
            }
            for task in TASKS
        },
    }
    return summary


def _write_structural_fixture(run_dir: Path, task: str) -> dict:
    km = _require_kickmix()
    text = STRUCTURAL_KMX[task]
    task_dir = run_dir / "structural" / task
    task_dir.mkdir(parents=True, exist_ok=True)
    kmx_path = task_dir / "fixture.kmx"
    kmb_path = task_dir / "fixture.kmb"
    circuit = km.Circuit(text)
    circuit.to_file(str(kmx_path), format="kmx")
    circuit.to_file(str(kmb_path), format="kmb")
    measurement = _measure(circuit)
    return {
        "role": "structural_fixture",
        "task": task,
        "circuit_written": True,
        "paths": {"kmx": str(kmx_path), "kmb": str(kmb_path)},
        "sha256": {"kmx": _sha256(kmx_path), "kmb": _sha256(kmb_path)},
        "measurement": measurement,
        "submission_ready": False,
        "note": (
            "Real kickmix circuit written for pipeline wiring. "
            "It is not a competition candidate and it was not verified."
        ),
    }


def _import_baseline(data_dir: Path, run_dir: Path, task: str) -> dict:
    found = _find_baseline(data_dir, task)
    if found is None:
        return {
            "role": "absent",
            "task": task,
            "circuit_written": False,
            "paths": None,
            "sha256": None,
            "measurement": None,
            "submission_ready": False,
            "searched": [str(data_dir / rel) for rel in BASELINE_RELATIVE[task]],
            "note": "No baseline file on disk. No circuit bytes were written.",
        }
    record = {
        "role": "imported_baseline",
        "task": task,
        "circuit_written": False,
        "copied": False,
        "submission_ready": False,
        "note": (
            "Existing file recorded by path and hash. It was not copied into git "
            "and it has not been verifier-accepted."
        ),
    }
    if found.is_file():
        record["paths"] = {"file": str(found)}
        record["sha256"] = {"file": _sha256(found)}
        record["measurement"] = _measure_file(found)
    else:
        files = sorted(path for path in found.rglob("*") if path.is_file())
        record["paths"] = {"directory": str(found)}
        record["sha256"] = {str(path.relative_to(found)): _sha256(path) for path in files}
        record["measurement"] = _measure_directory(found)
    record["run_dir"] = str(run_dir)
    return record


def _locate_dataset(data_dir: Path, repo_root: Path) -> dict:
    """Search data_dir, and the Kaggle mount only for the repo data directory.

    An explicit temporary directory must not fall through to a real mount.
    That would start the full official verifiers during unit tests.
    """

    primary = discover_dataset_root(explicit=data_dir, require=False)
    if primary.get("found"):
        return primary
    checked = list(primary.get("checked") or [])
    repo_data = (repo_root / "data").resolve()
    try:
        requested = data_dir.resolve()
    except OSError:
        requested = data_dir
    extras: list[Path] = []
    if requested == repo_data or not data_dir.exists():
        extras.append(
            Path("/kaggle/input/competitions/google-verifiable-quantum-circuit-compilation")
        )
    env_root = os.environ.get("VQCC_DATA_ROOT")
    if env_root:
        extras.append(Path(env_root))
    for extra in extras:
        if extra.exists() and extra.resolve() == requested:
            continue
        if not extra.exists():
            checked.append(f"{extra} (absent)")
            continue
        found = discover_dataset_root(explicit=extra, require=False)
        checked.extend(found.get("checked") or [])
        if found.get("found"):
            found["checked"] = checked
            return found
    primary["checked"] = checked
    return primary


def _candidate_artifact(state: dict, task: str) -> Path | None:
    """Use an imported candidate when one was recorded. Otherwise the sample."""

    task_state = state["tasks"].get(task) or {}
    if task_state.get("role") != "imported_baseline":
        return None
    paths = task_state.get("paths") or {}
    for key in ("file", "directory", "kmb", "kmx"):
        if paths.get(key):
            return Path(paths[key])
    return None


def _cost_one(artifact: dict) -> dict:
    measurement = artifact.get("measurement") or None
    base = {
        "role": artifact.get("role"),
        "leaderboard_score": None,
        "competition_cost": False,
    }
    if not measurement or measurement.get("status") != "measured":
        base["status"] = "not_computed"
        base["reason"] = "no kickmix measurement for this artifact"
        return base
    task = artifact.get("task")
    qubits = measurement["qubits"]
    toffoli = measurement["toffoli_like"]
    t_like = measurement["t_like"]
    if task == "invsqrt":
        value = invsqrt_cost(qubits, toffoli, t_like)
        base.update(
            {
                "status": "computed",
                "source": "hub and paper agree on Q*(Toffoli+T/4)",
                "formula_source": FormulaSource.PAPER.value,
                "expression": "Q*(toffoli_like + t_like/4)",
                "inputs": {
                    "qubits": qubits,
                    "toffoli_like": toffoli,
                    "t_like": t_like,
                    "measurement": "kickmix.Circuit.operation_statistics",
                },
                "rotation_pricing": (
                    "not applied; paper Z_POW analytical pricing needs the "
                    "per-rotation phase-error margin, which this measurement does not include"
                ),
                "value": value,
                "unconfirmed": False,
                "note": "Formula evaluation of this file's kickmix counts. Not a leaderboard score.",
            }
        )
        return base
    if task == "dqi":
        base.update(
            {
                "status": "not_computed",
                "reason": (
                    "dqi cost needs an epsilon-plus from the verifier. "
                    "None was supplied. FR-006 remains open. "
                    "Measured counts are recorded and were not turned into R(eps)."
                ),
                "inputs": {
                    "qubits": qubits,
                    "toffoli_like": toffoli,
                    "t_like": t_like,
                },
                "paper_expression_not_applied": "ln2 / (-ln(1/2 + 2*sqrt(eps))) * Q^2 * Toffoli",
                "hub_expression_not_applied": "unconfirmed hub rendering of R(eps)",
            }
        )
        return base
    notes = dfthcsos_constraint_notes(qubits=qubits)
    base.update(
        {
            "status": "not_computed",
            "reason": (
                "dfthcsos cost needs operator-supplied E_gap, Lambda, T_tot, and Q_tot. "
                "FR-007 remains open (hub product versus paper square root). "
                "The qubit cap below uses the measured kickmix qubit count of this file only."
            ),
            "inputs": {"qubits": qubits, "toffoli_like": toffoli, "t_like": t_like},
            "constraint_notes": notes,
            "published_constraints": {
                "qubit_cap": QUBIT_CAP,
                "frobenius_tolerance_ha": FROBENIUS_TOLERANCE_HA,
                "lambda_floor_ha_strict": LAMBDA_FLOOR_HA,
                "e_gap_floor_ha_strict": E_GAP_FLOOR_HA,
                "source": "hub numbers; paper states the Lambda and E_gap inequalities",
            },
        }
    )
    return base


def _measure_file(path: Path) -> dict | None:
    if path.suffix.lower() not in {".kmb", ".kmx"}:
        return {"status": "not_a_kickmix_circuit", "path": str(path)}
    km = _import_kickmix()
    if km is None:
        return {
            "status": "kickmix_unavailable",
            "path": str(path),
            "reason": f"kickmix {KICKMIX_TESTED_VERSION} is not installed",
        }
    circuit = km.Circuit.from_file(str(path))
    measured = _measure(circuit)
    measured["path"] = str(path)
    return measured


def _measure_directory(directory: Path) -> dict:
    circuits = [
        path
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.suffix.lower() in {".kmb", ".kmx"}
    ]
    return {
        "status": "directory",
        "circuit_files": [str(path) for path in circuits],
        "circuits": [_measure_file(path) for path in circuits],
    }


def _measure(circuit) -> dict:
    stats = circuit.operation_statistics()
    return {
        "status": "measured",
        "tool": "kickmix.Circuit.operation_statistics",
        "kickmix_version": _kickmix_version(),
        "qubits": int(circuit.num_qubits),
        "bits": int(circuit.num_bits),
        "instructions": _stat_int(stats, "num_instructions"),
        "toffoli_like": _stat_int(stats, "num_toffoli_like"),
        "t_like": _stat_int(stats, "num_t_like"),
    }


def _stat_int(stats, name: str) -> int:
    value = getattr(stats, name)
    if callable(value):
        value = value()
    return int(value)


def _find_baseline(data_dir: Path, task: str) -> Path | None:
    for relative in BASELINE_RELATIVE[task]:
        candidate = data_dir / relative
        if candidate.exists():
            return candidate
    return None


def _require_kickmix():
    module = _import_kickmix()
    if module is None:
        raise PipelineError(
            f"structural mode needs kickmix=={KICKMIX_TESTED_VERSION}. "
            "It is a public Apache-2.0 package. No fixture bytes were written."
        )
    return module


def _import_kickmix():
    try:
        import kickmix
    except ImportError:
        return None
    return kickmix


def _kickmix_status() -> dict:
    module = _import_kickmix()
    if module is None:
        return {"available": False, "version": None}
    return {"available": True, "version": _kickmix_version()}


def _kickmix_version() -> str | None:
    try:
        from importlib.metadata import version
    except ImportError:
        return None
    try:
        return version("kickmix")
    except Exception:
        return None


def _noetl_version() -> str | None:
    try:
        import noetl
    except ImportError:
        return None
    return getattr(noetl, "__version__", None)


def _load(repo_root: Path, runs_root: Path) -> tuple[dict, Path]:
    runs_root = _abs(repo_root.resolve(), runs_root)
    pointer_path = runs_root / "active.json"
    if not pointer_path.is_file():
        raise PipelineError(f"no active run at {pointer_path}. Run prepare first.")
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    run_dir = Path(pointer["run_dir"])
    state_path = run_dir / "state.json"
    if not state_path.is_file():
        raise PipelineError(f"run state missing: {state_path}")
    return json.loads(state_path.read_text(encoding="utf-8")), run_dir


def _save(run_dir: Path, state: dict) -> None:
    (run_dir / "state.json").write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _step(name: str, state: dict, **payload) -> dict:
    body = {
        "step": name,
        "run_id": state["run_id"],
        "mode": state["mode"],
        "leaderboard_score": None,
    }
    body.update(payload)
    return body


def _abs(repo_root: Path, path: Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
