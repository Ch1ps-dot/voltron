import json
import pickle
import threading
import time
from pathlib import Path

import voltron.fuzz as fuzz_module
from voltron.analyzer.analyzer import analyzer
from voltron.configs import configs
from voltron.fuzz import Fuzzer
from voltron.learner.automata import MealyMachine
from voltron.synthesizer.generator import Generator
from voltron.synthesizer.parser import Parser
from voltron.synthesizer.synthesizer import AsyncProducer


def make_snapshot_producer(tmp_path: Path) -> AsyncProducer:
    producer = AsyncProducer.__new__(AsyncProducer)
    producer.generator_path = tmp_path / "equipment" / "generators"
    producer.parser_path = tmp_path / "equipment" / "parsers"
    producer.best_equipment_path = tmp_path / "models" / "best_equipment"
    producer.best_generator_path = (
        producer.best_equipment_path / "generators"
    )
    producer.best_parser_path = producer.best_equipment_path / "parser.py"
    producer.best_equipment_info_path = (
        producer.best_equipment_path / "best_equipment.json"
    )
    producer.best_generators = {}
    producer.best_parser_info = {}
    return producer


def test_best_equipment_snapshot_copies_and_reloads_source(tmp_path):
    producer = make_snapshot_producer(tmp_path)
    generator_path = (
        producer.generator_path / "PING" / "id2.py"
    )
    generator_path.parent.mkdir(parents=True)
    generator_path.write_text(
        "def generate():\n    return b'PING\\r\\n'\n",
        encoding="utf-8",
    )
    parser_path = producer.parser_path / "id3.py"
    parser_path.parent.mkdir(parents=True)
    parser_path.write_text(
        "def parse(_message):\n    return b'PONG'\n",
        encoding="utf-8",
    )
    generator = Generator(
        msg_type="PING",
        evolved_from="id1",
        name="id2",
        path=str(generator_path),
    )
    parser = Parser(
        evolved_from="id2",
        name="id3",
        state_field="status",
    )

    producer.save_best_equipment(
        model_id="7",
        generators={"PING": generator},
        parser=parser,
    )

    manifest = json.loads(
        producer.best_equipment_info_path.read_text(encoding="utf-8")
    )
    assert manifest["model_id"] == "7"
    assert manifest["selection_metric"] == (
        "max_response_transition_types"
    )
    assert Path(manifest["generators"]["PING"]["path"]).read_text(
        encoding="utf-8"
    ) == generator_path.read_text(encoding="utf-8")
    assert Path(manifest["parser"]["path"]).read_text(
        encoding="utf-8"
    ) == parser_path.read_text(encoding="utf-8")

    producer.best_generators = {}
    producer.best_parser_info = {}
    producer.load_best_equipment()

    assert producer.best_generators["PING"].name == "id2"
    assert producer.best_parser_info["name"] == "id3"


def test_model_learning_persists_model_and_equipment_from_best_iteration(
    tmp_path,
    monkeypatch,
):
    transition_counts = iter([1, 2, 1, 1, 1])
    graphed_models = []

    class FakeMealyLstar:
        def __init__(self, *_args):
            pass

        def run(self, model_id):
            count = next(transition_counts)
            analyzer.cur_res_types_cnt = {"response": 1}
            analyzer.cur_resp_trans_cnt = {
                f"edge-{index}": 1
                for index in range(count)
            }
            return MealyMachine(
                id=model_id,
                states={0},
                alphabet={"PING"},
                delta={(0, "PING"): 0},
                output={(0, "PING"): "PONG"},
                start=0,
                table=([], [], {}),
            )

    monkeypatch.setattr(fuzz_module, "MealyLstar", FakeMealyLstar)
    monkeypatch.setattr(
        MealyMachine,
        "graph",
        lambda self, _name: graphed_models.append(self.id),
    )
    monkeypatch.setattr(
        analyzer,
        "record_model_learning_iteration",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        analyzer,
        "record_generator_checkpoint",
        lambda **_kwargs: None,
    )

    equipment_version = {"value": 0}
    saved = {}

    class FakeProducer:
        def capture_current_equipment(self, parser):
            version = equipment_version["value"]
            return {"PING": f"generator-{version}"}, f"{parser}-{version}"

        def generator_evo(self, _hypothesis):
            equipment_version["value"] += 1

        def save_best_equipment(
            self,
            model_id,
            generators,
            parser,
        ):
            saved.update(
                model_id=model_id,
                generators=generators,
                parser=parser,
            )

    class FakeMapper:
        cur_parser = "parser"

        def register_mapper(self, hypothesis):
            hypothesis.map = {}

    fuzzer = Fuzzer.__new__(Fuzzer)
    fuzzer.producer = FakeProducer()
    fuzzer.mapper = FakeMapper()
    fuzzer.spec_knowledge = True
    fuzzer.stop_event = threading.Event()

    monkeypatch.setattr(configs, "models_path", tmp_path, raising=False)
    monkeypatch.setattr(configs, "time_limit_s", 60, raising=False)
    monkeypatch.setattr(
        analyzer,
        "start_time",
        time.time(),
        raising=False,
    )
    monkeypatch.setattr(analyzer, "iter", 0, raising=False)

    result = fuzzer.model_learning(
        mq=object(),
        eq=object(),
        stop_event=fuzzer.stop_event,
    )

    with (tmp_path / "evolved_hypothesis.pkl").open("rb") as stream:
        persisted = pickle.load(stream)

    assert result.id == "1"
    assert persisted.id == "1"
    assert saved == {
        "model_id": "1",
        "generators": {"PING": "generator-1"},
        "parser": "parser-1",
    }
    assert graphed_models == ["1"]
