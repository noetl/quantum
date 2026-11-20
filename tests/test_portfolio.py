"""Portfolio steps: hash-pinned import, multi-salt verification, selection,
packaging, and the vqcc_portfolio playbook on the NoETL local runtime.

The verifier scripts here are stubs. A stub's score is the first number in
the artifact's bytes, and it FAILs when the artifact contains
``FAIL_SALT=<salt>`` for the salt it was run with. No real circuit is used.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

from vqcc import portfolio
from vqcc.official_verifier import OFFICIAL_SCRIPTS, SAMPLE_ARTIFACTS

ROOT = Path(__file__).resolve().parents[1]

_STUB = r'''
import argparse, json, pathlib, re, sys
p = argparse.ArgumentParser()
p.add_argument("artifact")
p.add_argument("--salt", default="")
p.add_argument("--seed", default=None)
a = p.parse_args()
path = pathlib.Path(a.artifact)
if path.is_dir():
    text = "".join(f.read_text() for f in sorted(path.iterdir()) if f.suffix in (".kmb", ".kmx"))
else:
    text = path.read_text()
score = float(re.search(r"[0-9.]+", text).group())
bad = f"FAIL_SALT={a.salt or 'default'}" in text
print(json.dumps({"status": "FAIL" if bad else "PASS", "score": score, "num_qubits": 1}))
'''


def _npz(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as z:
        for key in ("U", "W", "H2_I", "H1_I", "Hsym_lower", "tree_edges"):
            z.writestr(f"{key}.npy", b"\x93NUMPY")


def _dataset(root: Path) -> Path:
    for rel in OFFICIAL_SCRIPTS.values():
        script = root / rel
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(_STUB, encoding="utf-8")
    sample = root / "sample_submission"
    (sample / "dfthcsos").mkdir(parents=True)
    (sample / "invsqrt.kmb").write_text("1000\n")
    (sample / "dqi.kmb").write_text("5000\n")
    (sample / "dfthcsos" / "angle_k_0.kmb").write_text("300\n")
    _npz(sample / "dfthcsos" / "submission.npz")
    return root


def _candidates(root: Path) -> tuple[Path, Path]:
    cand = root / "candidates"
    files = {
        # invsqrt: a cheap one that fails one salt, and a slightly dearer one that passes all.
        ("invsqrt", "cheap-fragile", "invsqrt.kmb"): "10 FAIL_SALT=s2\n",
        ("invsqrt", "solid", "invsqrt.kmb"): "40\n",
        # dqi: one good external.
        ("dqi", "good", "dqi.kmb"): "100\n",
        # dqi: bytes that do not match the manifest hash are refused.
        ("dqi", "tampered", "dqi.kmb"): "1\n",
    }
    entries = []
    for (task, cid, name), body in files.items():
        path = cand / task / cid / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
        sha = portfolio.tree_sha256(path)
        if cid == "tampered":
            sha = "0" * 64
        entries.append({"task": task, "id": cid, "path": name, "sha256": sha,
                        "authors": [f"author-of-{cid}"], "license": "Apache-2.0",
                        "source": {"ref": f"someone/{cid}"}, "credit": f"credit for {cid}"})
    # dfthcsos: a directory candidate.
    d = cand / "dfthcsos" / "dir1" / "dfthcsos"
    d.mkdir(parents=True)
    (d / "angle_k_0.kmb").write_text("30\n")
    _npz(d / "submission.npz")
    entries.append({"task": "dfthcsos", "id": "dir1", "path": "dfthcsos", "sha256": portfolio.tree_sha256(d),
                    "authors": ["author-of-dir1"], "license": "CC0", "source": {"ref": "someone/dir1"},
                    "credit": "credit for dir1"})
    manifest = root / "candidates.json"
    manifest.write_text(json.dumps({"candidates": entries}))
    return cand, manifest


def _quiet(fn, **kwargs):
    with redirect_stdout(io.StringIO()):
        return fn(**kwargs)


class PortfolioStepTests(unittest.TestCase):
    def test_multisalt_selection_and_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            data = _dataset(tmp / "data")
            cand, manifest = _candidates(tmp)
            runs = tmp / "runs"
            portfolio.prepare(runs_root=runs, data_dir=data, candidates_dir=cand, manifest=manifest,
                              salts=["", "s1", "s2"], repo_root=ROOT)
            imported = portfolio.import_candidates(runs_root=runs)
            self.assertIn(("tampered", "refused"), imported["candidates"]["dqi"])
            for task in portfolio.TASKS:
                portfolio.verify_task(runs_root=runs, task=task, jobs=2)
            sel = portfolio.select(runs_root=runs)
            chosen = sel["selection"]
            # The cheaper invsqrt failed salt s2, so the solid one is kept.
            self.assertEqual(chosen["invsqrt"]["id"], "solid")
            self.assertAlmostEqual(chosen["invsqrt"]["ratio_default_salt"], 1000 / 40)
            self.assertEqual(chosen["dqi"]["id"], "good")
            self.assertEqual(chosen["dfthcsos"]["id"], "dir1")
            expected = ((1000 / 40) * (5000 / 100) * (300 / 30)) ** (1 / 3)
            self.assertAlmostEqual(sel["geometric_mean_default_salt"], expected)
            self.assertIsNone(sel["leaderboard_score"])
            self.assertIn("RANKING ONLY", sel["policy"])
            out = portfolio.package(runs_root=runs, repo_root=ROOT)
            with zipfile.ZipFile(out["zip"]) as z:
                names = sorted(z.namelist())
            self.assertEqual(names, ["dfthcsos/angle_k_0.kmb", "dfthcsos/submission.npz", "dqi.kmb", "invsqrt.kmb"])
            credits = (Path(out["zip"]).parent / "CREDITS.md").read_text()
            self.assertIn("author-of-solid", credits)
            self.assertIn("not eligible for prizes", credits)
            run_dir, state = portfolio._load(runs)
            fragile = next(r for r in state["tasks"]["invsqrt"]["candidates"] if r["id"] == "cheap-fragile")
            self.assertFalse(fragile["all_salts_pass"])
            self.assertEqual(state["package"]["submitted"], False)

    def test_reference_is_the_fallback_when_every_external_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            data = _dataset(tmp / "data")
            cand = tmp / "candidates"
            p = cand / "invsqrt" / "x" / "invsqrt.kmb"
            p.parent.mkdir(parents=True)
            p.write_text("1 FAIL_SALT=default\n")
            manifest = tmp / "m.json"
            manifest.write_text(json.dumps({"candidates": [{"task": "invsqrt", "id": "x", "path": "invsqrt.kmb",
                                                            "sha256": portfolio.tree_sha256(p)}]}))
            runs = tmp / "runs"
            portfolio.prepare(runs_root=runs, data_dir=data, candidates_dir=cand, manifest=manifest,
                              salts=["", "s1"], repo_root=ROOT)
            portfolio.import_candidates(runs_root=runs)
            for task in portfolio.TASKS:
                portfolio.verify_task(runs_root=runs, task=task)
            sel = portfolio.select(runs_root=runs)
            self.assertEqual(sel["selection"]["invsqrt"]["id"], "reference")
            self.assertAlmostEqual(sel["geometric_mean_default_salt"], 1.0)

    def test_manifest_pins_every_shipped_external_file(self) -> None:
        manifest = json.loads((ROOT / "portfolio" / "candidates.json").read_text(encoding="utf-8"))
        self.assertIn("RANKING ONLY", manifest["policy"])
        self.assertEqual({c["task"] for c in manifest["candidates"]}, set(portfolio.TASKS))
        for entry in manifest["candidates"]:
            self.assertEqual(len(entry["sha256"]), 64)
            self.assertTrue(entry["authors"])
            self.assertTrue(entry["credit"])
            self.assertTrue(entry["license"])
        credits = (ROOT / "portfolio" / "CREDITS.md").read_text(encoding="utf-8")
        for entry in manifest["candidates"]:
            self.assertIn(entry["id"], credits)


class PortfolioPlaybookTests(unittest.TestCase):
    def test_portfolio_playbook_runs_on_noetl(self) -> None:
        try:
            import noetl
        except ImportError:
            self.skipTest("noetl==5.3.2 is not installed")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            data = _dataset(tmp / "data")
            cand, manifest = _candidates(tmp)
            runs = tmp / "runs"
            outcome = noetl.run(
                str(ROOT / "playbooks" / "vqcc_portfolio.yaml"),
                variables={"repo_root": str(ROOT), "data_dir": str(data), "runs_root": str(runs),
                           "candidates_dir": str(cand), "manifest": str(manifest),
                           "salts": ",s1,s2", "polish": "false"},
                quiet=True,
            )
            self.assertEqual(outcome["status"], "ok", outcome)
            self.assertEqual(outcome["executed_steps"][0], "start")
            self.assertEqual(outcome["executed_steps"][-1], "package")
            final = json.loads(outcome["final_result"])
            self.assertIsNone(final["leaderboard_score"])
            self.assertTrue(Path(final["zip"]).is_file())


if __name__ == "__main__":
    unittest.main()
