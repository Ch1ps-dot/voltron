"""Portable, auditable exports for Voltron learning artifacts.

Bundles are intended for trusted Voltron installations.  They may contain
Python components and pickles, so callers must not import an untrusted bundle.
"""

from __future__ import annotations

import hashlib
import json
import pickle
import shutil
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from voltron.learner.automata import MealyMachine
from voltron.learner.partial_guidance import PartialStateGraph
from voltron.synthesizer.component_paths import component_type_dir


BUNDLE_FORMAT = 1
_ALLOWED_PREFIXES = ("models/", "equipment/", "metrics/", "diagnostics/")


class LearningBundleError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_members(archive: tarfile.TarFile):
    for member in archive.getmembers():
        name = member.name
        if (member.issym() or member.islnk() or not (member.isfile() or member.isdir())
                or Path(name).is_absolute() or ".." in Path(name).parts):
            raise LearningBundleError(f"unsafe bundle member: {name!r}")
        if name == "manifest.json" or any(name.startswith(prefix) for prefix in _ALLOWED_PREFIXES):
            yield member
        else:
            raise LearningBundleError(f"unexpected bundle member: {name!r}")


def _copy_tree_if_exists(source: Path, destination: Path) -> None:
    if source.exists():
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)


def export_learning_bundle(*, base_path: Path, results_path: Path, target: str,
                           protocol: str, output_path: Path) -> Path:
    """Export reusable model/equipment plus learning-only metrics to a tarball."""
    base_path = base_path.resolve()
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="voltron-learning-export-") as temporary:
        root = Path(temporary)
        _copy_tree_if_exists(base_path / "component" / "models" / target, root / "models" / target)
        _copy_tree_if_exists(base_path / "component" / "equipment" / target, root / "equipment" / target)
        for name in (
            "phase_metrics.csv", "model_learning_iterations.csv",
            "generator_iteration_metrics.csv", "llm_usage_metrics.csv",
        ):
            source = results_path / name
            if source.is_file():
                _copy_tree_if_exists(source, root / "metrics" / name)
        _copy_tree_if_exists(results_path / "diagnostics", root / "diagnostics")
        files = {}
        for item in sorted(root.rglob("*")):
            if item.is_file():
                files[item.relative_to(root).as_posix()] = _sha256(item)
        manifest = {
            "format": BUNDLE_FORMAT,
            "target": target,
            "protocol": protocol,
            "created_at": time.time(),
            "python": f"{sys.version_info.major}.{sys.version_info.minor}",
            "files": files,
        }
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        temporary_archive = output_path.with_suffix(output_path.suffix + ".tmp")
        with tarfile.open(temporary_archive, "w:gz") as archive:
            for item in sorted(root.rglob("*")):
                if item.is_file():
                    archive.add(item, arcname=item.relative_to(root).as_posix(), recursive=False)
        temporary_archive.replace(output_path)
    return output_path


def _validate_components(root: Path, target: str) -> dict:
    equipment = root / "equipment" / target
    generator_info = equipment / "generators" / "generator_info.json"
    parser_info = equipment / "parsers" / "parser_info.json"
    if not generator_info.is_file() or not parser_info.is_file():
        raise LearningBundleError("bundle lacks generator or parser metadata")
    generators = json.loads(generator_info.read_text(encoding="utf-8"))
    parsers = json.loads(parser_info.read_text(encoding="utf-8"))
    generator_count = 0
    for message_type, versions in generators.items():
        for version in versions:
            source = component_type_dir(equipment / "generators", message_type) / f"{version['name']}.py"
            namespace: dict = {}
            exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"), namespace)
            value = namespace.get("generate", lambda: None)()
            if not isinstance(value, bytes) or not value:
                raise LearningBundleError(f"invalid generator {message_type}/{version['name']}")
            generator_count += 1
    for parser in parsers:
        source = equipment / "parsers" / f"{parser['name']}.py"
        namespace = {}
        exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"), namespace)
        if not callable(namespace.get("packet_parser")):
            raise LearningBundleError(f"invalid parser {parser['name']}")
    return {"generator_versions": generator_count, "parser_versions": len(parsers)}


def validate_learning_bundle(root: Path, *, target: str, protocol: str) -> dict:
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise LearningBundleError("bundle lacks manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != BUNDLE_FORMAT:
        raise LearningBundleError("unsupported learning bundle format")
    if manifest.get("target") != target or manifest.get("protocol") != protocol:
        raise LearningBundleError("bundle target or protocol mismatch")
    for relative, expected in manifest.get("files", {}).items():
        path = root / relative
        if not path.is_file() or _sha256(path) != expected:
            raise LearningBundleError(f"checksum mismatch: {relative}")
    report = _validate_components(root, target)
    model = root / "models" / target / "evolved_hypothesis.pkl"
    partial = root / "models" / target / "partial_guidance.pkl"
    if model.is_file():
        with model.open("rb") as stream:
            if not isinstance(pickle.load(stream), MealyMachine):
                raise LearningBundleError("invalid evolved hypothesis")
        report["complete_model"] = True
    if partial.is_file():
        with partial.open("rb") as stream:
            graph = pickle.load(stream)
        if not isinstance(graph, PartialStateGraph) or not graph.seed_sequences():
            raise LearningBundleError("invalid partial guidance")
        report["partial_guidance"] = len(graph.traces)
    if not model.is_file() and not partial.is_file():
        raise LearningBundleError("bundle lacks a model or partial guidance")
    return report


def import_learning_bundle(*, bundle: Path, staging_root: Path, target: str,
                           protocol: str, activate: bool = False,
                           base_path: Path | None = None) -> tuple[Path, dict]:
    """Verify a trusted bundle in staging and optionally atomically activate it."""
    bundle = bundle.resolve()
    bundle_id = f"{bundle.stem}-{_sha256(bundle)[:12]}"
    destination = staging_root.resolve() / bundle_id
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    try:
        with tarfile.open(bundle, "r:gz") as archive:
            archive.extractall(
                destination, members=list(_safe_members(archive)), filter="data",
            )
        report = validate_learning_bundle(destination, target=target, protocol=protocol)
        report.update({
            "bundle": str(bundle), "staging": str(destination),
            "batch_id": bundle_id, "activated": False,
        })
        if activate:
            if base_path is None:
                raise LearningBundleError("activation requires base_path")
            # Imported assets are immutable, target-scoped batches.  Do not
            # overwrite the workspace equipment cache: a batch must load its
            # model and every component from the same provenance boundary.
            batches_root = base_path.resolve() / "component" / "models" / target
            live = batches_root / bundle_id
            if live.exists():
                raise LearningBundleError(f"model batch already exists: {live}")
            temporary = batches_root / (bundle_id + ".importing")
            if temporary.exists():
                shutil.rmtree(temporary)
            temporary.mkdir(parents=True)
            shutil.copy2(destination / "manifest.json", temporary / "manifest.json")
            for item in ("metrics", "diagnostics"):
                _copy_tree_if_exists(destination / item, temporary / item)
            _copy_tree_if_exists(
                destination / "models" / target,
                temporary,
            )
            _copy_tree_if_exists(
                destination / "equipment" / target,
                temporary / "equipment",
            )
            temporary.replace(live)
            report["batch_path"] = str(live)
            report["activated"] = True
        (destination / "import_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return destination, report
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
