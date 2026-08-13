import json
import pickle
from pathlib import Path
from types import SimpleNamespace

from voltron.configs import configs
from voltron.learning_bundle import (
    LearningBundleError,
    export_learning_bundle,
    import_learning_bundle,
)
from voltron.learner.automata import MealyMachine
from voltron.synthesizer.synthesizer import AsyncProducer


def _assets(root: Path, target: str = "demo") -> tuple[Path, Path]:
    equipment = root / "component" / "equipment" / target
    generator = equipment / "generators" / "PING"
    parser = equipment / "parsers"
    generator.mkdir(parents=True)
    parser.mkdir(parents=True)
    (generator / "id0.py").write_text(
        "def generate():\n    return b'PING\\r\\n'\n", encoding="utf-8"
    )
    (parser / "id0.py").write_text(
        "def packet_parser(data):\n    return b'OK'\n", encoding="utf-8"
    )
    (equipment / "generators" / "generator_info.json").write_text(
        json.dumps({"PING": [{"msg_type": "PING", "name": "id0"}]}),
        encoding="utf-8",
    )
    (parser / "parser_info.json").write_text(
        json.dumps([{"name": "id0", "state_field": "code"}]), encoding="utf-8"
    )
    model = root / "component" / "models" / target
    model.mkdir(parents=True)
    with (model / "evolved_hypothesis.pkl").open("wb") as stream:
        pickle.dump(
            MealyMachine(
                id="1", states=set(), alphabet=set(), delta={}, output={},
                start=0, table=(),
            ),
            stream,
        )
    results = root / "results"
    results.mkdir()
    (results / "phase_metrics.csv").write_text("phase,status\nmodel_learning,completed\n")
    return equipment, results


def test_export_then_stage_import_validates_components_and_model(tmp_path):
    _assets(tmp_path)
    bundle = export_learning_bundle(
        base_path=tmp_path,
        results_path=tmp_path / "results",
        target="demo",
        protocol="demo-proto",
        output_path=tmp_path / "demo.tar.gz",
    )
    staging, report = import_learning_bundle(
        bundle=bundle,
        staging_root=tmp_path / "staging",
        target="demo",
        protocol="demo-proto",
    )
    assert (staging / "import_report.json").is_file()
    assert report["complete_model"] is True
    assert report["generator_versions"] == 1


def test_import_rejects_target_mismatch_without_activation(tmp_path):
    _assets(tmp_path)
    bundle = export_learning_bundle(
        base_path=tmp_path,
        results_path=tmp_path / "results",
        target="demo",
        protocol="demo-proto",
        output_path=tmp_path / "demo.tar.gz",
    )
    try:
        import_learning_bundle(
            bundle=bundle,
            staging_root=tmp_path / "staging",
            target="wrong",
            protocol="demo-proto",
        )
    except LearningBundleError as exc:
        assert "target or protocol mismatch" in str(exc)
    else:
        raise AssertionError("mismatched bundle was accepted")
    assert not (tmp_path / "component" / "models" / "wrong").exists()


def test_activation_publishes_self_contained_model_batch(tmp_path):
    _assets(tmp_path)
    bundle = export_learning_bundle(
        base_path=tmp_path,
        results_path=tmp_path / "results",
        target="demo",
        protocol="demo-proto",
        output_path=tmp_path / "demo.tar.gz",
    )
    _staging, report = import_learning_bundle(
        bundle=bundle,
        staging_root=tmp_path / "staging",
        target="demo",
        protocol="demo-proto",
        activate=True,
        base_path=tmp_path,
    )
    batch = Path(report["batch_path"])
    assert report["activated"] is True
    assert batch.name == report["batch_id"]
    assert (batch / "evolved_hypothesis.pkl").is_file()
    assert (batch / "equipment" / "generators" / "PING" / "id0.py").is_file()
    assert not (batch / "equipment" / "demo").exists()


def test_activation_accepts_custom_batch_id_and_writes_receipt(tmp_path):
    _assets(tmp_path)
    bundle = export_learning_bundle(
        base_path=tmp_path,
        results_path=tmp_path / "results",
        target="demo",
        protocol="demo-proto",
        output_path=tmp_path / "demo.tar.gz",
    )
    _staging, report = import_learning_bundle(
        bundle=bundle,
        staging_root=tmp_path / "staging",
        target="demo",
        protocol="demo-proto",
        activate=True,
        base_path=tmp_path,
        batch_id="example",
    )

    batch = Path(report["batch_path"])
    receipt = json.loads((batch / "import_receipt.json").read_text())
    assert batch.name == report["batch_id"] == "example"
    assert receipt["batch_id"] == "example"
    assert receipt["bundle_sha256"]

    try:
        import_learning_bundle(
            bundle=bundle,
            staging_root=tmp_path / "staging",
            target="demo",
            protocol="demo-proto",
            activate=True,
            base_path=tmp_path,
            batch_id="example",
        )
    except LearningBundleError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("existing custom batch id was overwritten")


def test_custom_batch_id_requires_activation_and_is_safe(tmp_path):
    _assets(tmp_path)
    bundle = export_learning_bundle(
        base_path=tmp_path,
        results_path=tmp_path / "results",
        target="demo",
        protocol="demo-proto",
        output_path=tmp_path / "demo.tar.gz",
    )
    for batch_id in ("../outside", "", "has space"):
        try:
            import_learning_bundle(
                bundle=bundle,
                staging_root=tmp_path / "staging",
                target="demo",
                protocol="demo-proto",
                activate=True,
                base_path=tmp_path,
                batch_id=batch_id,
            )
        except LearningBundleError as exc:
            assert "batch id" in str(exc)
        else:
            raise AssertionError(f"unsafe batch id accepted: {batch_id!r}")

    try:
        import_learning_bundle(
            bundle=bundle,
            staging_root=tmp_path / "staging",
            target="demo",
            protocol="demo-proto",
            batch_id="example",
        )
    except LearningBundleError as exc:
        assert "requires activation" in str(exc)
    else:
        raise AssertionError("custom batch id accepted without activation")


def test_selected_batch_scopes_producer_to_its_own_equipment(
    tmp_path, monkeypatch,
):
    batch = tmp_path / "component" / "models" / "demo" / "batch-a"
    equipment = batch / "equipment"
    monkeypatch.setattr(configs, "base_path", tmp_path)
    monkeypatch.setattr(configs, "target_name", "demo", raising=False)
    monkeypatch.setattr(configs, "models_path", batch, raising=False)
    monkeypatch.setattr(configs, "equipment_path", equipment, raising=False)
    monkeypatch.setattr(configs, "model_batch", "batch-a", raising=False)
    monkeypatch.setattr(configs, "info_path", tmp_path / "info.md", raising=False)
    monkeypatch.setattr(configs, "results_path", tmp_path / "results", raising=False)

    producer = AsyncProducer(
        chater=object(),
        rfcp=SimpleNamespace(
            req_ir=None, res_ir=None, req_types=set(), res_types=set(),
            req_dep_map={}, poss_res={},
        ),
    )

    assert producer.synthesizer_path == equipment
    assert producer.generator_path == equipment / "generators"
    assert producer.best_equipment_path == batch / "best_equipment"
