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
import math
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
# Official scripts print a JSON object, not this line. The line remains a
# non-authoritative fallback for stubs that echo "cost:" or "score:".
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
        "parsed_cost": None,
        "cost_parse": None,
        "cost_authoritative": False,
        "verifier_status": None,
        "score_source": None,
        "score_inputs": {},
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
    parsed = parse_verifier_stdout(stdout or "")
    report["parsed_cost"] = parsed["parsed_cost"]
    report["cost_parse"] = parsed["cost_parse"]
    report["verifier_status"] = parsed["verifier_status"]
    report["score_source"] = parsed["score_source"]
    report["score_inputs"] = parsed["score_inputs"]
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
    json_rejected = parsed["cost_parse"] == "json_not_pass"
    # Fixture trees exist so tests can check argv without claiming a dataset pass.
    # A JSON status other than PASS is a verifier failure even if the process
    # exited 0. A missing JSON document does not veto an exit-0 stub.
    report["competition_verified"] = bool(exit_ok and not fixture and not json_rejected)
    # A JSON score is the verifier's own task cost (spec FR-004). A bare
    # cost:/score: line is not that document, and a fixture is not the dataset.
    report["cost_authoritative"] = bool(
        exit_ok and not fixture and parsed["cost_parse"] == "json_score"
    )
    if timed_out:
        report["status"] = "timeout"
        report["reason"] = f"verifier exceeded {timeout}s and was killed"
    elif not exit_ok:
        report["status"] = "fail"
        report["reason"] = f"official verifier exited {exit_code}"
    elif json_rejected:
        report["status"] = "fail"
        report["reason"] = (
            "official verifier JSON status is "
            f"{parsed['verifier_status']}; the process exited {exit_code}"
        )
    elif fixture:
        report["status"] = "fixture_exit_ok"
        report["reason"] = (
            "The official relative script exited 0 inside a .vqcc-fixture root. "
            "competition_verified stays false."
        )
    else:
        report["status"] = "pass"
        if report["cost_authoritative"]:
            report["reason"] = (
                "The official script exited 0 and stdout JSON status is PASS. "
                "parsed_cost is that object's score field (FR-004). "
                "leaderboard_score stays null (FR-008, FR-009, FR-016)."
            )
        else:
            report["reason"] = (
                "The official script exited 0. This is not an aggregate "
                "leaderboard score. The stdout is not one PASS JSON score, "
                "so the task cost is not authoritative."
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


def parse_verifier_stdout(stdout: str) -> dict:
    """Read one verifier stdout.

    The official scripts write a JSON object whose ``score`` is the task cost
    and whose ``status`` is ``PASS`` or ``FAIL``. That is the document the
    invsqrt verifier redirects to ``result.json``, and the same ``status`` /
    ``score`` pair is what a full dqi run prints. A bare ``cost:`` or
    ``score:`` line is kept for stubs and is never authoritative.

    Several top-level objects that each carry ``score`` are ambiguous. Nested
    objects are not separate hits. A JSON array is not searched for an inner
    score.
    """

    objects = _top_level_objects(stdout or "")
    scored = [obj for obj in objects if isinstance(obj, dict) and "score" in obj]
    if len(scored) > 1:
        return _parse_result(None, "ambiguous", None, None, {})
    if len(scored) == 1:
        return _from_score_object(scored[0])
    if objects:
        return _parse_result(
            None,
            "json_missing_score",
            _status_of(objects[0]),
            None,
            _scalar_inputs(objects[0]),
        )
    parsed, status = _parse_cost_line(stdout or "")
    if status == "one_line":
        return _parse_result(parsed, "one_line", None, "text_line", {})
    if status == "ambiguous":
        return _parse_result(None, "ambiguous", None, None, {})
    return _parse_result(None, "unparsed", None, None, {})


def _from_score_object(obj: dict) -> dict:
    status = _status_of(obj)
    score = _as_score(obj.get("score"))
    inputs = _scalar_inputs(obj)
    if status is None:
        kind = "json_missing_status" if score is not None else "json_missing_score"
        return _parse_result(score, kind, None, "json.score", inputs)
    if status != "PASS":
        return _parse_result(score, "json_not_pass", status, "json.score", inputs)
    if score is None or score <= 0.0:
        return _parse_result(score, "json_invalid_score", status, "json.score", inputs)
    return _parse_result(score, "json_score", status, "json.score", inputs)


def _parse_result(
    parsed_cost: float | None,
    cost_parse: str,
    verifier_status: str | None,
    score_source: str | None,
    score_inputs: dict,
) -> dict:
    return {
        "parsed_cost": parsed_cost,
        "cost_parse": cost_parse,
        "verifier_status": verifier_status,
        "score_source": score_source,
        "score_inputs": score_inputs,
    }


def _status_of(obj: dict) -> str | None:
    status = obj.get("status")
    if not isinstance(status, str):
        return None
    text = status.strip().upper()
    return text or None


def _as_score(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _scalar_inputs(obj: dict) -> dict:
    """Keep JSON scalars so a cost can name the verifier's own inputs.

    Nested maps such as per-shot operation counts are omitted. They are not
    formula inputs, and a dqi run's count map is large.
    """

    inputs: dict = {}
    for key, value in obj.items():
        if not isinstance(key, str):
            continue
        if isinstance(value, str):
            if len(value) > 256:
                continue
            inputs[key] = value
        elif isinstance(value, bool) or value is None:
            inputs[key] = value
        elif isinstance(value, (int, float)) and math.isfinite(float(value)):
            inputs[key] = value
        if len(inputs) >= 40:
            break
    return inputs


def _top_level_objects(text: str) -> list[dict]:
    stripped = text.strip()
    if not stripped:
        return []
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        value = None
    else:
        if isinstance(value, dict):
            return [value]
        if isinstance(value, list):
            return []
    decoder = json.JSONDecoder()
    found: list[dict] = []
    index = 0
    length = len(text)
    while index < length:
        start = text.find("{", index)
        if start < 0:
            break
        try:
            obj, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(obj, dict):
            found.append(obj)
        index = max(end, start + 1)
    return found


def _parse_cost_line(stdout: str) -> tuple[float | None, str]:
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
