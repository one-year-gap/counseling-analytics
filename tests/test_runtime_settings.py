from app.core.config import Settings


def test_cdc_analysis_disabled_by_default_when_app_mode_is_unset():
    settings = Settings()

    assert settings.effective_cdc_analysis_enabled is False


def test_server_mode_enables_cdc_analysis_by_default():
    settings = Settings(app_mode="server")

    assert settings.effective_cdc_analysis_enabled is True


def test_analysis_server_mode_enables_cdc_analysis_by_default():
    settings = Settings(app_mode="analysis-server")

    assert settings.effective_cdc_analysis_enabled is True


def test_explicit_cdc_flag_overrides_server_mode_default():
    settings = Settings(app_mode="server", cdc_analysis_enabled=False)

    assert settings.effective_cdc_analysis_enabled is False
