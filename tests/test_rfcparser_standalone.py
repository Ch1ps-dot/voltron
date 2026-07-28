from pathlib import Path

from voltron.configs import configs
from voltron.rfcparser import standalone


def test_parse_target_section_trees_loads_minimum_configuration(
    tmp_path,
    monkeypatch,
):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "configs.yaml").write_text(
        """
demo:
  protocol: ftp
  rfc_name: [rfc959, rfc2428]
llm_doc:
  base_url: https://example.invalid/v1
  api_key: test-key
  model: test-model
  async_sem: 3
""".lstrip(),
        encoding="utf-8",
    )
    captured = {}

    class FakeChater:
        def __init__(self, base_url, api_key, model):
            captured["chater"] = (base_url, api_key, model)

    class FakeParser:
        def __init__(self, chater):
            captured["parser_chater"] = chater
            self.tree_path = tmp_path / "component" / "tree" / "ftp"

        def parse_section_trees(self):
            return [
                ("rfc959", "regenerated"),
                ("rfc2428", "loaded"),
            ]

    monkeypatch.setattr(configs, "base_path", tmp_path)
    monkeypatch.setattr(standalone, "AsyncChater", FakeChater)
    monkeypatch.setattr(standalone, "AsyncRFCParser", FakeParser)

    results = standalone.parse_target_section_trees("demo")

    assert captured["chater"] == (
        "https://example.invalid/v1",
        "test-key",
        "test-model",
    )
    assert configs.pro_name == "ftp"
    assert configs.rfc_name == ["rfc959", "rfc2428"]
    assert configs.doc_paths == [
        tmp_path / "config" / "rfcs" / "rfc959.txt",
        tmp_path / "config" / "rfcs" / "rfc2428.txt",
    ]
    assert configs.async_sem_doc == 3
    assert [result.output_path for result in results] == [
        tmp_path / "component" / "tree" / "ftp" / "rfc959.pkl",
        tmp_path / "component" / "tree" / "ftp" / "rfc2428.pkl",
    ]


def test_generate_target_ir_runs_complete_parser(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "configs.yaml").write_text(
        """
demo:
  protocol: ftp
  rfc_name: [rfc959]
llm_doc:
  base_url: https://example.invalid/v1
  api_key: test-key
  model: test-model
  async_sem: 3
""".lstrip(),
        encoding="utf-8",
    )
    calls = []

    class FakeChater:
        def __init__(self, base_url, api_key, model):
            calls.append(("chater", base_url, api_key, model))

    class FakeParser:
        def __init__(self, chater):
            calls.append(("parser", chater))
            self.ir_path = tmp_path / "component" / "ir" / "ftp"

        def run(self):
            calls.append(("run",))

    monkeypatch.setattr(configs, "base_path", tmp_path)
    monkeypatch.setattr(standalone, "AsyncChater", FakeChater)
    monkeypatch.setattr(standalone, "AsyncRFCParser", FakeParser)

    output_path = standalone.generate_target_ir("demo")

    assert output_path == tmp_path / "component" / "ir" / "ftp"
    assert calls[0] == (
        "chater",
        "https://example.invalid/v1",
        "test-key",
        "test-model",
    )
    assert calls[-1] == ("run",)
