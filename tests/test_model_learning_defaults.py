from voltron.configs import Config


def test_observation_table_partial_guidance_threshold_is_disabled_by_default():
    assert Config().partial_guidance_enabled is False
