from voltron.config_loader import load_runtime_config


def _write_base_config(config_dir):
    (config_dir / "configs.yaml").write_text(
        """
llm_doc:
  api_key: ${VOLTRON_LLM_DOC_API_KEY}
  model: base-model
llm_fuzz:
  api_key: none
target:
  protocol: demo
""".lstrip(),
        encoding="utf-8",
    )


def test_env_api_key_overrides_public_placeholder(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _write_base_config(config_dir)
    monkeypatch.setenv("VOLTRON_LLM_DOC_API_KEY", "test-key")

    loaded = load_runtime_config(config_dir)

    assert loaded["llm_doc"]["api_key"] == "test-key"


def test_ignored_local_config_overrides_only_requested_fields(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _write_base_config(config_dir)
    (config_dir / "configs.local.yaml").write_text(
        """
llm_doc:
  api_key: local-test-key
target:
  host: 127.0.0.1
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_runtime_config(config_dir)

    assert loaded["llm_doc"]["api_key"] == "local-test-key"
    assert loaded["llm_doc"]["model"] == "base-model"
    assert loaded["target"]["protocol"] == "demo"
    assert loaded["target"]["host"] == "127.0.0.1"
