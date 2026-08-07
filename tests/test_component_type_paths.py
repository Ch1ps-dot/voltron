import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from lxml import etree
import pytest

from voltron.configs import configs
from voltron.executor.mapper import Mapper
from voltron.synthesizer.component_paths import (
    component_type_dir,
    path_within,
    type_to_slug,
)
from voltron.synthesizer.generator import Generator
from voltron.synthesizer.synthesizer import AsyncProducer


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("type_name", "slug"),
    [
        ("PING", "PING"),
        ("/update", "%2Fupdate"),
        ("A/B", "A%2FB"),
        ("PLAY NOTIFY", "PLAY%20NOTIFY"),
        ("%2Fupdate", "%252Fupdate"),
        ("..", "%2E."),
        (".hidden", "%2Ehidden"),
        ("", "%00"),
    ],
)
def test_type_to_slug_is_stable_and_collision_free(type_name, slug):
    assert type_to_slug(type_name) == slug


def test_type_to_slug_encodes_unicode_and_bounds_long_names():
    assert type_to_slug("更新") == "%E6%9B%B4%E6%96%B0"
    first = type_to_slug("A" * 300)
    second = type_to_slug("A" * 299 + "B")
    assert len(first) <= 180
    assert len(second) <= 180
    assert "~" in first
    assert first != second


def test_component_type_dir_never_escapes_root(tmp_path):
    root = tmp_path / "generators"
    root.mkdir()
    path = component_type_dir(root, "/../../outside")
    assert path.name == "%2F..%2F..%2Foutside"
    assert path_within(root, path)
    with pytest.raises(ValueError, match="NUL"):
        component_type_dir(root, "bad\x00type")


def _producer_for_initial_generation(tmp_path, request_types):
    class Chater:
        async def llm_generator_gen(self, *, msg_type, **_kwargs):
            return (
                "def generate():\n"
                f"    return {msg_type.encode()!r}\n"
            )

        async def llm_code_repair(self, **_kwargs):
            raise AssertionError("valid generators must not be repaired")

    info_path = tmp_path / "info.md"
    info_path.write_text("target info", encoding="utf-8")
    producer = AsyncProducer.__new__(AsyncProducer)
    producer.chater = Chater()
    producer.rfcp = SimpleNamespace(
        pro_name="example",
        req_fields=["method"],
        req_types=set(request_types),
        req_dep_map={name: {} for name in request_types},
        poss_res={name: ["OK"] for name in request_types},
    )
    producer.req_ir = etree.fromstring(
        "<ir>"
        + "".join(f'<message name="{name}"/>' for name in request_types)
        + "</ir>"
    )
    producer.generator_path = tmp_path / "generators"
    producer.generator_path.mkdir()
    producer.generator_info_path = (
        producer.generator_path / "generator_info.json"
    )
    producer.info_path = info_path
    producer.req_types = set(request_types)
    producer.req_dep = dict(producer.rfcp.req_dep_map)
    producer.poss_response = dict(producer.rfcp.poss_res)
    producer.generators = {}
    producer._record_generation = lambda *_args, **_kwargs: None
    producer._generated_code_timeout = lambda: 1
    producer._generated_message_limit = lambda: 4096
    producer._request_type_rule_info = lambda _msg_type: "rule"
    return producer


def test_initial_generator_uses_slug_but_preserves_display_type(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(configs, "async_sem_fuzz", 1, raising=False)
    producer = _producer_for_initial_generation(tmp_path, ["/update"])

    producer.generator_gen()

    source = producer.generator_path / "%2Fupdate" / "id0.py"
    assert source.is_file()
    assert not (tmp_path / "update").exists()
    assert producer.generators["/update"][0].msg_type == "/update"
    assert producer.generators["/update"][0].path == str(source.resolve())
    mapping = json.loads(
        (tmp_path / "type_path_map.json").read_text(encoding="utf-8")
    )
    assert mapping["types"]["/update"] == "%2Fupdate"


def test_all_daap_request_types_persist_under_generator_root(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(configs, "async_sem_fuzz", 4, raising=False)
    req_ir = etree.parse(
        str(PROJECT_ROOT / "component" / "ir" / "daap" / "req_ir.xml")
    ).getroot()
    request_types = [message.get("name") for message in req_ir.findall("message")]
    producer = _producer_for_initial_generation(tmp_path, request_types)
    producer.req_ir = req_ir

    producer.generator_gen()

    assert set(producer.generators) == set(request_types)
    for request_type in request_types:
        source = Path(producer.generators[request_type][0].path)
        assert path_within(producer.generator_path, source)
        assert source.parent.name == type_to_slug(request_type)
        assert source.is_file()


def test_initial_generator_save_failure_isolated_to_one_type(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(configs, "async_sem_fuzz", 2, raising=False)
    producer = _producer_for_initial_generation(tmp_path, ["GOOD", "BAD"])
    original_save = producer._save_initial_generator

    def save_with_one_failure(msg_type, code):
        if msg_type == "BAD":
            raise OSError("simulated per-type write failure")
        original_save(msg_type, code)

    producer._save_initial_generator = save_with_one_failure
    producer.generator_gen()

    assert set(producer.generators) == {"GOOD"}
    assert producer.req_types == {"GOOD"}
    assert (producer.generator_path / "GOOD" / "id0.py").is_file()


def test_mapper_uses_slug_and_rejects_metadata_outside_component_root(
    tmp_path,
):
    root = tmp_path / "generators"
    source = root / "%2Fupdate" / "id0.py"
    source.parent.mkdir(parents=True)
    source.write_text("def generate(): return b'x'\n", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("raise RuntimeError\n", encoding="utf-8")
    generator = Generator(
        msg_type="/update",
        name="id0",
        evolved_from="init",
        path=str(outside),
    )
    mapper = Mapper.__new__(Mapper)
    mapper.gs_path = root
    mapper.best_gs_path = None

    assert mapper.g_path(generator) == source

    source.unlink()
    assert mapper.g_path(generator) == source
    assert mapper.g_path(generator) != outside
