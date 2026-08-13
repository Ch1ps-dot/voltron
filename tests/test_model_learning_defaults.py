from voltron.configs import Config


def test_partial_guidance_is_enabled_and_reused_by_default():
    config = Config()
    assert config.partial_guidance_enabled is True
    assert config.reuse_imported_partial_guidance is True
