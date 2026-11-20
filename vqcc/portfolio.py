#!/usr/bin/env python3
"""Portfolio steps: import external circuits, verify them at several salts,
keep the cheapest per task, optionally polish, and package.

RANKING ONLY. The external circuits this module imports are other authors'
public work (Apache-2.0 or CC0, credited in ``portfolio/candidates.json`` and
``portfolio/CREDITS.md``). A submission built from them counts for
leaderboard ranking only. It is not an original NoETL result and is not
eligible for prizes, which require the entrant's own original work.

Each subcommand prints one JSON object on stdout and nothing else.

    python3 -m vqcc.portfolio prepare --data-dir D --candidates-dir C --runs-root R
    python3 -m vqcc.portfolio import  --runs-root R
    python3 -m vqcc.portfolio verify  --runs-root R --task invsqrt
    python3 -m vqcc.portfolio polish  --runs-root R --task invsqrt
    python3 -m vqcc.portfolio select  --runs-root R
    python3 -m vqcc.portfolio package --runs-root R

Nothing here submits to Kaggle or publishes anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import secrets
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from vqcc.official_verifier import (
    OFFICIAL_SCRIPTS,
    SAMPLE_ARTIFACTS,
    _launch_environment,
    discover_dataset_root,
    parse_verifier_stdout,
)
from vqcc.packaging import build_submission_zip

TASKS = ("invsqrt", "dqi", "dfthcsos")
POLICY = (
    "RANKING ONLY. External candidates are other authors' public circuits, "
    "credited per file. A package that uses them is not an original NoETL "
    "result and is not eligible for prizes."
)
# The empty salt is the verifier default (the circuit hash alone seeds it).
# The others stand in for the hidden private-board salt. A candidate is kept
# only when it passes at every salt listed here.
DEFAULT_SALTS = ("", "noetl-salt-1", "noetl-salt-2", "noetl-salt-3", "noetl-salt-4")
VERIFY_TIMEOUT_S = {"invsqrt": 7200, "dqi": 7200, "dfthcsos": 3600}
ACTIVE = "active-portfolio.json"
_KEEP_FIELDS = (
    "status", "score", "num_qubits", "toffoli_count", "max_toffoli_count", "t_count",
    "value_errors", "phase_errors", "verified_shots", "worst_error_over_tolerance",
    "lambda_eff", "circuit_sha256", "submission_sha256",
)


class PortfolioError(RuntimeError):
    """A step cannot run with the state it was given."""


# ---------------------------------------------------------------- helpers


def tree_sha256(path: Path) -> str:
    """sha256 of a file, or of a directory as sorted ``name\\0sha256\\n`` lines."""

    path = Path(path)
    if path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    if path.is_dir():
        lines = []
        for child in sorted(p for p in path.iterdir() if p.is_file()):
            lines.append(f"{child.name}\0{tree_sha256(child)}\n")
        return hashlib.sha256("".join(lines).encode()).hexdigest()
    raise PortfolioError(f"missing candidate path {path}")


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _run_dir(runs_root: Path) -> Path:
    pointer = Path(runs_root) / ACTIVE
    if not pointer.is_file():
        raise PortfolioError(f"no active portfolio run: {pointer} is missing (run prepare first)")
    return Path(json.loads(pointer.read_text(encoding="utf-8"))["run_dir"])


def _load(runs_root: Path) -> tuple[Path, dict]:
    run_dir = _run_dir(runs_root)
    return run_dir, json.loads((run_dir / "state.json").read_text(encoding="utf-8"))


def _save(run_dir: Path, state: dict) -> None:
    _atomic_json(run_dir / "state.json", state)


def geometric_mean(values: list[float]) -> float:
    return math.exp(sum(math.log(v) for v in values) / len(values))


# ---------------------------------------------------------------- steps


def prepare(
    *,
    runs_root: Path,
    data_dir: Path,
    candidates_dir: Path,
    manifest: Path,
    salts: list[str],
    repo_root: Path,
) -> dict:
    found = discover_dataset_root(Path(data_dir), require=False)
    root = found.get("root") if isinstance(found, dict) else None
    if not root:
        raise PortfolioError(f"official verifiers not found under {data_dir}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(runs_root).resolve() / f"portfolio-{stamp}-{secrets.token_hex(4)}"
    run_dir.mkdir(parents=True)
    manifest_data = json.loads(Path(manifest).read_text(encoding="utf-8"))
    state = {
        "schema": "vqcc.portfolio/1",
        "policy": POLICY,
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "created_at": stamp,
        "dataset_root": str(root),
        "candidates_dir": str(Path(candidates_dir).resolve()),
        "manifest": str(Path(manifest).resolve()),
        "manifest_sha256": tree_sha256(Path(manifest)),
        "repo_head": _git_head(repo_root),
        "salts": list(salts),
        "tasks": {task: {"candidates": []} for task in TASKS},
        "external": manifest_data.get("candidates", []),
        "leaderboard_score": None,
    }
    _save(run_dir, state)
    _atomic_json(Path(runs_root) / ACTIVE, {"run_dir": str(run_dir)})
    return {"step": "prepare", "run_id": run_dir.name, "dataset_root": str(root), "salts": list(salts)}


def import_candidates(*, runs_root: Path) -> dict:
    run_dir, state = _load(runs_root)
    root = Path(state["dataset_root"])
    summary: dict[str, list] = {}
    for task in TASKS:
        reference = root / SAMPLE_ARTIFACTS[task]
        rows = [{
            "id": "reference",
            "task": task,
            "path": str(reference),
            "sha256": tree_sha256(reference),
            "status": "imported",
            "origin": "competition reference circuit (sample_submission)",
            "authors": ["Google Quantum AI (competition reference)"],
            "license": "competition data",
            "external": False,
        }]
        for entry in state["external"]:
            if entry["task"] != task:
                continue
            path = Path(state["candidates_dir"]) / task / entry["id"] / entry["path"]
            row = {key: entry.get(key) for key in ("id", "task", "authors", "license", "source", "credit")}
            row.update(path=str(path), external=True, expected_sha256=entry["sha256"])
            if not path.exists():
                row.update(status="missing", reason=f"{path} not found")
            else:
                actual = tree_sha256(path)
                row["sha256"] = actual
                if actual != entry["sha256"]:
                    row.update(status="refused", reason="sha256 does not match the manifest")
                else:
                    row["status"] = "imported"
            rows.append(row)
        state["tasks"][task]["candidates"] = rows
        summary[task] = [(row["id"], row["status"]) for row in rows]
    _save(run_dir, state)
    return {"step": "import", "run_id": state["run_id"], "candidates": summary}


def _verify_once(root: Path, task: str, artifact: Path, salt: str, log_dir: Path, timeout: int) -> dict:
    script = root / OFFICIAL_SCRIPTS[task]
    cwd, env, _ = _launch_environment(root, script)
    command = [sys.executable, str(script), str(artifact)]
    if salt:
        command += ["--salt", salt]
    tag = salt or "default"
    started = time.time()
    proc = subprocess.Popen(
        command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        stdout, stderr = proc.communicate()
        timed_out = True
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / f"{tag}.stdout.txt").write_text(stdout or "", encoding="utf-8")
    (log_dir / f"{tag}.stderr.txt").write_text(stderr or "", encoding="utf-8")
    parsed = parse_verifier_stdout(stdout or "")
    verdict: dict = {}
    try:
        verdict = json.loads(stdout)
    except (TypeError, ValueError):
        verdict = {}
    passed = (
        not timed_out
        and proc.returncode == 0
        and parsed.get("verifier_status") == "PASS"
        and parsed.get("parsed_cost") is not None
    )
    return {
        "salt": salt,
        "command": command,
        "exit_code": proc.returncode,
        "timed_out": timed_out,
        "duration_s": round(time.time() - started, 1),
        "pass": passed,
        "score": parsed.get("parsed_cost"),
        "verifier": {key: verdict.get(key) for key in _KEEP_FIELDS if key in verdict},
    }


def verify_task(*, runs_root: Path, task: str, jobs: int = 2, timeout_s: int | None = None) -> dict:
    run_dir, state = _load(runs_root)
    root = Path(state["dataset_root"])
    timeout = timeout_s or VERIFY_TIMEOUT_S[task]
    rows = [row for row in state["tasks"][task]["candidates"] if row["status"] == "imported"]
    work = [(row, salt) for row in rows for salt in state["salts"] if salt not in row.get("salts_done", [])]

    def run(item):
        row, salt = item
        log_dir = run_dir / "verify" / task / row["id"]
        return row["id"], _verify_once(root, task, Path(row["path"]), salt, log_dir, timeout)

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        results = list(pool.map(run, work))
    by_id = {row["id"]: row for row in rows}
    for cid, result in results:
        row = by_id[cid]
        row.setdefault("verifications", []).append(result)
        row.setdefault("salts_done", []).append(result["salt"])
    for row in rows:
        _summarize(row, state["salts"])
    _save(run_dir, state)
    return {
        "step": "verify",
        "task": task,
        "candidates": {
            row["id"]: {"all_salts_pass": row.get("all_salts_pass"), "worst_score": row.get("worst_score")}
            for row in rows
        },
    }


def _summarize(row: dict, salts: list[str]) -> None:
    results = {v["salt"]: v for v in row.get("verifications", [])}
    complete = all(salt in results for salt in salts)
    row["all_salts_pass"] = complete and all(results[s]["pass"] for s in salts)
    scores = [results[s]["score"] for s in salts if s in results and results[s]["score"] is not None]
    row["worst_score"] = max(scores) if row["all_salts_pass"] else None
    row["default_score"] = results.get("", {}).get("score") if "" in results else None


def polish_task(
    *,
    runs_root: Path,
    repo_root: Path,
    task: str,
    budget_s: float,
    window: int = 4096,
    jobs: int = 2,
) -> dict:
    """Run the existing NoETL rewrite pass on the cheapest passing candidate.

    The polished file becomes one more candidate. It is kept by ``select``
    only if it passes at every salt and is strictly cheaper.
    """

    run_dir, state = _load(runs_root)
    best = _best(state["tasks"][task]["candidates"])
    if best is None:
        return {"step": "polish", "task": task, "status": "skipped", "reason": "no candidate passed every salt"}
    if best["id"].startswith("polish-"):
        return {"step": "polish", "task": task, "status": "skipped", "reason": "already polished"}
    src = Path(best["path"])
    out = run_dir / "polish" / task
    out.mkdir(parents=True, exist_ok=True)
    dst = out / src.name
    result_path = out / "transform.json"
    deadline = time.time() + budget_s
    command = [
        sys.executable, "-m", "vqcc.pipeline", "optimize-transform",
        "--repo-root", str(repo_root), "--runs-root", str(runs_root),
        "--task", task, "--src", str(src), "--dst", str(dst),
        "--window", str(window), "--memory-budget-bytes", str(4 * 1024**3),
        "--deadline-epoch", str(deadline), "--transform-budget-s", str(budget_s),
        "--result", str(result_path), "--profile", str(out / "profile.json"),
        "--log", str(out / "transform.log"),
    ]
    proc = subprocess.Popen(command, cwd=repo_root, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                            text=True, start_new_session=True)
    try:
        _, stderr = proc.communicate(timeout=budget_s + 120)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        _, stderr = proc.communicate()
    transform = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else {}
    if not transform.get("wrote") or not dst.exists():
        state["tasks"][task]["polish"] = {"status": "no_rewrite", "base": best["id"], "transform": transform}
        _save(run_dir, state)
        return {"step": "polish", "task": task, "status": "no_rewrite", "base": best["id"],
                "reason": transform.get("reason") or (stderr or "")[-300:]}
    row = {
        "id": f"polish-{best['id']}",
        "task": task,
        "path": str(dst),
        "sha256": tree_sha256(dst),
        "status": "imported",
        "external": best.get("external", False),
        "authors": list(best.get("authors") or []) + ["NoETL rewrite pass (noetl/quantum vqcc.optimize)"],
        "license": best.get("license"),
        "source": best.get("source"),
        "credit": (best.get("credit") or "") + " Polished by the NoETL rewrite pass.",
        "polished_from": best["id"],
        "transform": {key: transform.get(key) for key in ("before", "after", "stats")},
    }
    state["tasks"][task]["candidates"].append(row)
    state["tasks"][task]["polish"] = {"status": "written", "base": best["id"]}
    _save(run_dir, state)
    verified = verify_task(runs_root=runs_root, task=task, jobs=jobs)
    return {"step": "polish", "task": task, "status": "written", "base": best["id"], "verify": verified}


def _best(rows: list[dict]) -> dict | None:
    passing = [row for row in rows if row.get("all_salts_pass") and row.get("worst_score")]
    return min(passing, key=lambda row: row["worst_score"]) if passing else None


def select(*, runs_root: Path) -> dict:
    run_dir, state = _load(runs_root)
    chosen: dict[str, dict] = {}
    ratios = []
    for task in TASKS:
        rows = state["tasks"][task]["candidates"]
        reference = next(row for row in rows if row["id"] == "reference")
        best = _best(rows)
        if best is None:
            raise PortfolioError(f"{task}: no candidate, not even the reference, passed every salt")
        ref_score = reference.get("default_score")
        ratio = ref_score / best["default_score"] if ref_score and best.get("default_score") else None
        worst_ratio = ref_score / best["worst_score"] if ref_score and best.get("worst_score") else None
        chosen[task] = {
            "id": best["id"],
            "path": best["path"],
            "sha256": best["sha256"],
            "external": best.get("external", False),
            "authors": best.get("authors"),
            "license": best.get("license"),
            "source": best.get("source"),
            "credit": best.get("credit"),
            "default_salt_score": best.get("default_score"),
            "worst_salt_score": best.get("worst_score"),
            "reference_default_score": ref_score,
            "ratio_default_salt": ratio,
            "ratio_worst_salt": worst_ratio,
        }
        if ratio:
            ratios.append(ratio)
    state["selection"] = chosen
    state["geometric_mean_default_salt"] = geometric_mean(ratios) if len(ratios) == 3 else None
    state["geometric_mean_note"] = (
        "Local calculation from the official verifiers' default-salt scores on this machine. "
        "Not a Kaggle measurement and not a leaderboard score."
    )
    _save(run_dir, state)
    return {
        "step": "select",
        "policy": POLICY,
        "selection": {task: {k: chosen[task][k] for k in ("id", "default_salt_score", "ratio_default_salt", "ratio_worst_salt")} for task in TASKS},
        "geometric_mean_default_salt": state["geometric_mean_default_salt"],
        "leaderboard_score": None,
    }


def package(*, runs_root: Path, repo_root: Path) -> dict:
    run_dir, state = _load(runs_root)
    if "selection" not in state:
        raise PortfolioError("run select before package")
    sel = state["selection"]
    out = run_dir / "package"
    result = build_submission_zip(
        invsqrt=Path(sel["invsqrt"]["path"]),
        dqi=Path(sel["dqi"]["path"]),
        dfthcsos_dir=Path(sel["dfthcsos"]["path"]),
        output=out / "submission.zip",
    )
    credits_src = Path(repo_root) / "portfolio" / "CREDITS.md"
    lines = [
        "# Credits for this submission package",
        "",
        POLICY,
        "",
        f"Run `{state['run_id']}`, repo `{state['repo_head']}`, salts tested: "
        + ", ".join(repr(s) for s in state["salts"]),
        "",
        "| Task | Candidate | sha256 | Authors | License | Source |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for task in TASKS:
        row = sel[task]
        source = row.get("source") or {}
        lines.append(
            f"| {task} | {row['id']} | `{row['sha256'][:16]}` | {'; '.join(row.get('authors') or [])} | "
            f"{row.get('license')} | {source.get('ref', 'competition data') if isinstance(source, dict) else source} |"
        )
    lines += ["", "Per-file credit chains:", ""]
    for task in TASKS:
        lines.append(f"- **{task}**: {sel[task].get('credit') or 'competition reference circuit'}")
    if credits_src.is_file():
        lines += ["", "---", "", credits_src.read_text(encoding="utf-8")]
    (out / "CREDITS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    notice = Path(repo_root) / "portfolio" / "NOTICE"
    if notice.is_file():
        (out / "NOTICE").write_text(notice.read_text(encoding="utf-8"), encoding="utf-8")
    zip_sha = tree_sha256(out / "submission.zip")
    state["package"] = {
        "zip": str(out / "submission.zip"),
        "zip_sha256": zip_sha,
        "entries": result["entries"],
        "credits": str(out / "CREDITS.md"),
        "submitted": False,
        "note": "Staged only. Nothing was submitted or published.",
    }
    _save(run_dir, state)
    _atomic_json(run_dir / "provenance.json", state)
    return {"step": "package", "zip": str(out / "submission.zip"), "zip_sha256": zip_sha,
            "entries": len(result["entries"]), "policy": POLICY, "leaderboard_score": None}


def _git_head(repo_root: Path) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(repo_root), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


# ---------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--runs-root", type=Path, default=Path("runs"))
    common.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    prep = sub.add_parser("prepare", parents=[common])
    prep.add_argument("--data-dir", type=Path, required=True)
    prep.add_argument("--candidates-dir", type=Path, required=True)
    prep.add_argument("--manifest", type=Path, default=Path("portfolio/candidates.json"))
    prep.add_argument("--salts", default=",".join(DEFAULT_SALTS),
                      help="comma-separated; an empty item is the verifier's default salt")
    sub.add_parser("import", parents=[common])
    ver = sub.add_parser("verify", parents=[common])
    ver.add_argument("--task", required=True, choices=TASKS)
    ver.add_argument("--jobs", type=int, default=2)
    ver.add_argument("--timeout-s", type=int, default=None)
    pol = sub.add_parser("polish", parents=[common])
    pol.add_argument("--task", required=True, choices=TASKS)
    pol.add_argument("--budget-s", type=float, default=1800.0)
    pol.add_argument("--window", type=int, default=4096)
    pol.add_argument("--jobs", type=int, default=2)
    pol.add_argument("--enabled", default="true")
    sub.add_parser("select", parents=[common])
    sub.add_parser("package", parents=[common])

    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            salts = args.salts.split(",") if args.salts != "" else [""]
            payload = prepare(runs_root=args.runs_root, data_dir=args.data_dir,
                              candidates_dir=args.candidates_dir, manifest=args.manifest,
                              salts=salts, repo_root=args.repo_root)
        elif args.command == "import":
            payload = import_candidates(runs_root=args.runs_root)
        elif args.command == "verify":
            payload = verify_task(runs_root=args.runs_root, task=args.task, jobs=args.jobs, timeout_s=args.timeout_s)
        elif args.command == "polish":
            if str(args.enabled).lower() not in {"1", "true", "yes"}:
                payload = {"step": "polish", "task": args.task, "status": "disabled"}
            else:
                payload = polish_task(runs_root=args.runs_root, repo_root=args.repo_root, task=args.task,
                                      budget_s=args.budget_s, window=args.window, jobs=args.jobs)
        elif args.command == "select":
            payload = select(runs_root=args.runs_root)
        else:
            payload = package(runs_root=args.runs_root, repo_root=args.repo_root)
    except PortfolioError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    json.dump(payload, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
