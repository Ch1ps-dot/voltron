import pytest

from voltron.analyzer.analyzer import analyzer
from voltron.configs import configs
from voltron.scheduler.berserker import Berserker


class Mapper:
    request_types = {"PREFIX", "MUTATOR", "SUFFIX"}
    req_dep = {}
    mutators = {"MUTATOR": [object()]}


class Executor:
    def __init__(self):
        self.sequences = []

    def interact(self, sequence, **_kwargs):
        self.sequences.append(sequence)
        return False, None


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        (
            "cat",
            ["PREFIX_1", "PREFIX_2", "MUTATOR_1", "MUTATOR_2", "SUFFIX"],
        ),
        (
            "int",
            ["PREFIX_1", "MUTATOR_1", "PREFIX_2", "MUTATOR_2", "SUFFIX"],
        ),
    ],
)
def test_scheduler_appends_suffix_once_after_prefix_and_mutator(
    monkeypatch, method, expected,
):
    """Suffix is a distinct tail, never part of the mutable middle segment."""
    monkeypatch.setattr(configs, "offline_mutation_enabled", False, raising=False)
    monkeypatch.setattr(analyzer, "set_progress", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(analyzer, "clean_progress", lambda: None)
    executor = Executor()
    berserker = Berserker(Mapper(), executor, None)
    berserker.methods = [method]

    def select_prefix():
        berserker.selected_base_state = None
        berserker.selected_partial_prefix = False
        berserker.selected_imported_seed_prefix = False
        return [("PREFIX_1", b"P1"), ("PREFIX_2", b"P2")]

    berserker.select_base_state = select_prefix
    berserker.select_mutated_seq = lambda: [
        ("MUTATOR_1", b"M1"), ("MUTATOR_2", b"M2"),
    ]
    berserker.select_suffix = lambda: [("SUFFIX", b"S")]

    berserker.run(0)

    assert len(executor.sequences) == 1
    assert [kind for kind, _data in executor.sequences[0]] == expected
