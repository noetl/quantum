"""Invoke the official competition verifier scripts.

The script names, arguments, and seed below match a private Kaggle notebook
run (Version 3, seed 20261108) that exited 0. This module does not contain
that dataset and does not claim to have repeated that run.

A process exit of 0 counts only when the executable path is the official
script. A generic ``verifiers/<task>/verify`` hook does not. Fixture roots
marked with ``.vqcc-fixture`` cannot set ``competition_verified``.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path

FIXTURE_MARKER = ".vqcc-fixture"
KAGGLE_MOUNT = Path(
    "/kaggle/input/competitions/google-verifiable-quantum-circuit-compilation"
)
REFERENCE_SEED = "20261108"

# External evidence from the user's notebook. Not a result of this process.
EXTERNAL_REFERENCE_NOTE = {
    "source": "kaggle notebook kadyapam/noetl-quantum-competition-pipeline-vqcc version 3",
    "executed_by_this_repository": False,
    "seed": REFERENCE_SEED,
    "mount": str(KAGGLE_MOUNT),
    "reported_runtime_seconds": {
        "invsqrt": 800.080,
        "dqi": 230.628,
        "dfthcsos": 85.019,
    },
    "reported_raw_task_costs": {
        "invsqrt": 2076774.233715282,
        "dqi": 24439466758900.453,
        "dfthcsos": 3355599588.3155375,
    },
    "note": (
        "These figures are the user's private reference-circuit run. "
        "They are not an aggregate leaderboard score and not a measurement "
        "made by this codebase."
    ),
}

OFFICIAL_SCRIPTS = {
    "invsqrt": "verifiers/invsqrt/verify_submission_invsqrt.py",
    "dqi": "verifiers/dqi/verify_submission_dqi.py",
    "dfthcsos": "verifiers/dfthcsos/verify.py",
}
SAMPLE_ARTIFACTS = {
    "invsqrt": "sample_submission/invsqrt.kmb",
    "dqi": "sample_submission/dqi.kmb",
    "dfthcsos": "sample_submission/dfthcsos",
}
# Above the notebook's observed times. Full default invsqrt is the long one.
# Tests pass a short timeout explicitly.
DEFAULT_TIMEOUT_S = {
    "invsqrt": 7200,
    "dqi": 7200,
    "dfthcsos": 3600,
}

# One unambiguous line only. Multiple hits are not treated as a cost.
_COST_LINE = re.compile(
    r"(?im)^[ \t]*(?:raw[ _-]?)?(?:score|cost)[ \t]*[:=][ \t]*"
    r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)[ \t]*$"
)


class VerifierError(RuntimeError):
    """The official scripts cannot be launched. Not a verifier failure."""


def discover_dataset_root(
    explicit: Path | None = None,
    search_roots: list[Path] | None = None,
    max_depth: int = 6,
    require: bool = False,
) -> dict:
    """Find a directory that contains all three official scripts.

    ``explicit`` is searched and, if it does not contain the scripts, the
    error names every path that was checked. Other roots are not a fallback
    for a wrong explicit path.
    """

    if explicit is not None:
        found, checked = _search_tree(Path(explicit), max_depth)
        if found is None:
            missing = _missing_scripts(Path(explicit))
            message = (
                "dataset root "
                f"{explicit} does not contain the official verifier scripts. "
                f"Missing under that path: {missing}. Checked: {checked}."
            )
            if require:
                raise VerifierError(message)
            return {
                "found": False,
                "root": None,
                "evidence_class": None,
                "checked": checked,
                "missing": missing,
                "reason": message,
            }
        return _root_record(found, "explicit")

    roots = list(search_roots or [])
    env_root = os.environ.get("VQCC_DATA_ROOT")
    if env_root:
        roots.insert(0, Path(env_root))
    if KAGGLE_MOUNT not in roots:
        roots.append(KAGGLE_MOUNT)
    checked: list[str] = []
    for root in roots:
        found, local_checked = _search_tree(root, max_depth)
        checked.extend(local_checked)
        if found is not None:
            how = "kaggle_mount" if found == KAGGLE_MOUNT.resolve() else "search"
            if env_root and found == Path(env_root).resolve():
                how = "VQCC_DATA_ROOT"
            return _root_record(found, how)
    return {
        "found": False,
        "root": None,
        "evidence_class": None,
        "checked": checked,
        "reason": "official verifier scripts were not found",
    }


def run_official_task(
    *,
    root: Path,
    task: str,
    artifact: Path | None = None,
    seed: str = REFERENCE_SEED,
    timeout_s: int | None = None,
    log_dir: Path | None = None,
    python: str = "python3",
) -> dict:
    """Run one official verifier. Does not read the artifact into memory."""

    if task not in OFFICIAL_SCRIPTS:
        raise VerifierError(f"unknown task {task}")
    root = root.resolve()
    script = root / OFFICIAL_SCRIPTS[task]
    if artifact is None:
        artifact = root / SAMPLE_ARTIFACTS[task]
    else:
        artifact = artifact.resolve()
    timeout = DEFAULT_TIMEOUT_S[task] if timeout_s is None else timeout_s
    report = {
        "task": task,
        "script": str(script),
        "script_relative": OFFICIAL_SCRIPTS[task],
        "artifact": str(artifact),
        "seed": str(seed),
        "timeout_s": timeout,
        "official_script": True,
        "mock_hook": False,
        "weakened_flags": False,
        "leaderboard_score": None,
        "aggregate_score": None,
        "executed_by_this_repository_on_the_kaggle_dataset": False,
        "external_reference_note": EXTERNAL_REFERENCE_NOTE,
    }
    if not script.is_file():
        report.update(
            status="blocked",
            competition_verified=False,
            reason=f"missing official script {script}",
        )
        return report
    if not artifact.exists():
        report.update(
            status="blocked",
            competition_verified=False,
            reason=f"missing artifact {artifact}",
        )
        return report

    cwd, env, cwd_source = _launch_environment(root, script)
    command = [python, str(script), str(artifact), "--seed", str(seed)]
    report["command"] = command
    report["cwd"] = str(cwd)
    report["cwd_source"] = cwd_source
    report["bundle_role"] = _bundle_role(root, artifact)
    started = time.monotonic()
    timed_out = False
    exit_code = None
    stdout = ""
    stderr = ""
    try:
        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except OSError as exc:
        report.update(
            status="blocked",
            competition_verified=False,
            reason=f"could not start verifier: {exc}",
        )
        return report
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_group(proc)
        try:
            stdout, stderr = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            stdout, stderr = "", ""
        exit_code = proc.returncode
    duration = time.monotonic() - started
    report["duration_seconds"] = round(duration, 3)
    report["exit_code"] = exit_code
    report["timed_out"] = timed_out
    parsed, parse_status = _parse_cost(stdout or "")
    report["parsed_cost"] = parsed
    report["cost_parse"] = parse_status
    report["cost_authoritative"] = False
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / f"{task}.stdout.txt").write_text(stdout or "", encoding="utf-8")
        (log_dir / f"{task}.stderr.txt").write_text(stderr or "", encoding="utf-8")
        report["stdout_log"] = str(log_dir / f"{task}.stdout.txt")
        report["stderr_log"] = str(log_dir / f"{task}.stderr.txt")
    fixture = (root / FIXTURE_MARKER).is_file()
    report["evidence_class"] = "fixture" if fixture else _evidence_class(root)
    exit_ok = exit_code == 0 and not timed_out
    report["official_exit_pass"] = exit_ok
    # Fixture trees exist so tests can check argv without claiming a dataset pass.
    report["competition_verified"] = bool(exit_ok and not fixture)
    if timed_out:
        report["status"] = "timeout"
        report["reason"] = f"verifier exceeded {timeout}s and was killed"
    elif not exit_ok:
        report["status"] = "fail"
        report["reason"] = f"official verifier exited {exit_code}"
    elif fixture:
        report["status"] = "fixture_exit_ok"
        report["reason"] = (
            "The official relative script exited 0 inside a .vqcc-fixture root. "
            "competition_verified stays false."
        )
    else:
        report["status"] = "pass"
        report["reason"] = (
            "The official script exited 0. This is not an aggregate leaderboard "
            "score. Parsed cost is not treated as authoritative."
        )
    return report


def _launch_environment(root: Path, script: Path) -> tuple[Path, dict[str, str], str]:
    """cwd and PYTHONPATH for the official scripts.

    The notebook invocation used absolute paths. It did not record cwd.
    The default cwd is the dataset root. ``verifier_launch.json`` in that
    root, when present, overrides cwd and extra PYTHONPATH entries. That
    file is how a local copy of the scripts' own instructions is applied
    without guessing them here.
    """

    cwd = root
    extra = [str(root), str(root / "verifiers"), str(script.parent)]
    source = "default_cwd_dataset_root_unconfirmed_by_script_source"
    launch = root / "verifier_launch.json"
    if launch.is_file():
        payload = json.loads(launch.read_text(encoding="utf-8"))
        if payload.get("cwd"):
            raw = Path(payload["cwd"])
            cwd = raw if raw.is_absolute() else (root / raw).resolve()
        if isinstance(payload.get("pythonpath"), list):
            for item in payload["pythonpath"]:
                path = Path(item)
                extra.append(str(path if path.is_absolute() else (root / path).resolve()))
        source = "verifier_launch.json"
    env = os.environ.copy()
    previous = env.get("PYTHONPATH")
    parts = extra + ([previous] if previous else [])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return cwd, env, source


def _parse_cost(stdout: str) -> tuple[float | None, str]:
    matches = _COST_LINE.findall(stdout)
    if len(matches) == 1:
        return float(matches[0]), "one_line"
    if len(matches) == 0:
        return None, "unparsed"
    return None, "ambiguous"


def _search_tree(start: Path, max_depth: int) -> tuple[Path | None, list[str]]:
    start = Path(start)
    checked: list[str] = []
    if not start.exists():
        checked.append(f"{start} (absent)")
        return None, checked
    if start.is_file():
        checked.append(f"{start} (file, not a dataset root)")
        return None, checked
    found = _match_dir(start)
    checked.append(str(start))
    if found is not None:
        return found, checked
    for directory in _bounded_dirs(start, max_depth):
        checked.append(str(directory))
        found = _match_dir(directory)
        if found is not None:
            return found, checked
    return None, checked


def _bounded_dirs(start: Path, max_depth: int):
    start = start.resolve()
    for dirpath, dirnames, _filenames in os.walk(start):
        current = Path(dirpath)
        depth = len(current.relative_to(start).parts)
        if depth > max_depth:
            dirnames.clear()
            continue
        dirnames[:] = [
            name
            for name in dirnames
            if name not in {".git", "runs", "__pycache__", ".venv", "node_modules"}
        ]
        if current != start:
            yield current


def _match_dir(directory: Path) -> Path | None:
    if all((directory / relative).is_file() for relative in OFFICIAL_SCRIPTS.values()):
        return directory.resolve()
    return None


def _missing_scripts(root: Path) -> list[str]:
    return [
        relative
        for relative in OFFICIAL_SCRIPTS.values()
        if not (root / relative).is_file()
    ]


def _root_record(root: Path, how: str) -> dict:
    fixture = (root / FIXTURE_MARKER).is_file()
    return {
        "found": True,
        "root": str(root),
        "discovered_via": how,
        "evidence_class": "fixture" if fixture else _evidence_class(root),
        "scripts": {task: str(root / rel) for task, rel in OFFICIAL_SCRIPTS.items()},
        "samples": {task: str(root / rel) for task, rel in SAMPLE_ARTIFACTS.items()},
    }


def _evidence_class(root: Path) -> str:
    try:
        if root.resolve() == KAGGLE_MOUNT.resolve():
            return "kaggle_mount"
    except OSError:
        pass
    return "local_dataset"


def _bundle_role(root: Path, artifact: Path) -> str:
    sample_root = (root / "sample_submission").resolve()
    try:
        artifact.resolve().relative_to(sample_root)
        return "reference"
    except ValueError:
        return "candidate"


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()
