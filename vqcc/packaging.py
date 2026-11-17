"""Build a competition submission zip from files the caller already has.

The layout follows the competition's sample_submission/ and the official
dfthcsos verifier (verifiers/dfthcsos/SCORING_README.md, "Submission files"):

    invsqrt.kmb or invsqrt.kmx
    dqi.kmb or dqi.kmx
    dfthcsos/angle_k_0.kmb .. angle_k_N.kmb   (or all .kmx; no gaps)
    dfthcsos/submission.npz            (U, W, H2_I, H1_I, Hsym_lower, tree_edges)

The team hub listed extensionless angle_k_N names. The official verifier
looks for angle_k_*.kmb or angle_k_*.kmx, and the sample ships .kmb, so an
extensionless angle file is rejected here (issue #7).

This module does not create circuits and does not fill in missing arrays.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

# Keys the hub lists inside submission.npz. The verifier may require more;
# that question is tracked in docs/open-questions.md.
REQUIRED_NPZ_KEYS = (
    "U",
    "W",
    "H2_I",
    "H1_I",
    "Hsym_lower",
    "tree_edges",
)


_CIRCUIT_EXTENSIONS = (".kmb", ".kmx")


class PackageError(ValueError):
    """The supplied files are not a valid submission layout."""


def build_submission_zip(
    *,
    invsqrt: Path,
    dqi: Path,
    dfthcsos_dir: Path,
    output: Path,
) -> dict[str, object]:
    """Write the zip. Raises PackageError and writes nothing on failure."""

    invsqrt = Path(invsqrt)
    dqi = Path(dqi)
    dfthcsos_dir = Path(dfthcsos_dir)
    output = Path(output)

    inv_ext = _circuit_extension(invsqrt, "invsqrt")
    dqi_ext = _circuit_extension(dqi, "dqi")
    angle_names = inspect_dfthcsos_dir(dfthcsos_dir)

    output.parent.mkdir(parents=True, exist_ok=True)
    entries = [
        f"invsqrt{inv_ext}",
        f"dqi{dqi_ext}",
        "dfthcsos/submission.npz",
        *[f"dfthcsos/{name}" for name in angle_names],
    ]
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(invsqrt, arcname=entries[0])
        archive.write(dqi, arcname=entries[1])
        archive.write(dfthcsos_dir / "submission.npz", arcname=entries[2])
        for name in angle_names:
            archive.write(dfthcsos_dir / name, arcname=f"dfthcsos/{name}")
    return {
        "output": str(output),
        "entries": entries,
        "disclaimer": (
            "Archive layout only. This zip is not evidence that any verifier "
            "accepted the circuits, and it is not a score."
        ),
    }


def inspect_dfthcsos_dir(directory: Path) -> list[str]:
    """Return angle file names in order, or raise PackageError."""

    directory = Path(directory)
    if not directory.is_dir():
        raise PackageError(f"dfthcsos directory not found: {directory}")

    files = sorted(path for path in directory.iterdir() if path.is_file())
    unexpected: list[str] = []
    indices: list[int] = []
    extensions: set[str] = set()
    has_npz = False
    for path in files:
        name = path.name
        if name == "submission.npz":
            has_npz = True
            continue
        stem, extension = path.stem, path.suffix
        suffix = stem.removeprefix("angle_k_")
        # Official names are angle_k_0.kmb, angle_k_1.kmb, ... (or .kmx),
        # with no leading zeros.
        if (
            extension in _CIRCUIT_EXTENSIONS
            and stem.startswith("angle_k_")
            and suffix.isdigit()
            and str(int(suffix)) == suffix
        ):
            indices.append(int(suffix))
            extensions.add(extension)
            continue
        unexpected.append(name)

    if unexpected:
        raise PackageError(
            "unexpected files in dfthcsos (official names are angle_k_0..N "
            "with a .kmb or .kmx extension, plus submission.npz): "
            + ", ".join(unexpected)
        )
    if len(extensions) > 1:
        raise PackageError(
            "angle files mix .kmb and .kmx; the verifier detects one format "
            "from angle_k_0: " + ", ".join(sorted(extensions))
        )
    if not has_npz:
        raise PackageError("missing dfthcsos/submission.npz")
    if not indices:
        raise PackageError("missing angle_k_0..N")

    indices = sorted(set(indices))
    expected = list(range(indices[-1] + 1))
    if indices != expected:
        raise PackageError(
            "angle files must be angle_k_0..angle_k_N with no gaps; "
            f"found indices {indices}"
        )
    _require_npz_keys(directory / "submission.npz")
    (extension,) = extensions
    return [f"angle_k_{index}{extension}" for index in indices]


def _circuit_extension(path: Path, label: str) -> str:
    if not path.is_file():
        raise PackageError(f"missing {label} circuit: {path}")
    extension = path.suffix.lower()
    if extension not in _CIRCUIT_EXTENSIONS:
        raise PackageError(f"{label} must be a .kmb or .kmx file, got {path.name}")
    return extension


def _require_npz_keys(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    except zipfile.BadZipFile as exc:
        raise PackageError(f"submission.npz is not a readable npz/zip: {exc}") from exc
    keys = set()
    for name in names:
        base = name.split("/")[-1]
        if base.endswith(".npy"):
            keys.add(base[: -len(".npy")])
        elif base:
            keys.add(base)
    missing = [key for key in REQUIRED_NPZ_KEYS if key not in keys]
    if missing:
        raise PackageError(
            "submission.npz is missing hub-listed keys: " + ", ".join(missing)
        )
