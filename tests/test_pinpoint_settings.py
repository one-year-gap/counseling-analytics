from app.core.config import Settings


def test_pinpoint_disabled_by_default():
    settings = Settings()

    assert settings.pinpoint_enabled is False
    assert settings.pinpoint_agent_id == "intelligence-server"
    assert settings.pinpoint_application_name == "intelligence-server"
    assert settings.pinpoint_collector_agent_uri == ""


def test_pinpoint_settings_can_be_overridden():
    settings = Settings(
        pinpoint_enabled=True,
        pinpoint_agent_id="intelligence-server-1",
        pinpoint_application_name="intelligence-server",
        pinpoint_collector_agent_uri="tcp:grafana-server.holliverse.internal:10000",
        pinpoint_trace_limit=64,
        pinpoint_timeout_ms=500,
        pinpoint_log_level="DEBUG",
    )

    assert settings.pinpoint_enabled is True
    assert settings.pinpoint_agent_id == "intelligence-server-1"
    assert settings.pinpoint_application_name == "intelligence-server"
    assert settings.pinpoint_collector_agent_uri == "tcp:grafana-server.holliverse.internal:10000"
    assert settings.pinpoint_trace_limit == 64
    assert settings.pinpoint_timeout_ms == 500
    assert settings.pinpoint_log_level == "DEBUG"
