import pytest

from worker.config import ConfigError, load_config

BASE = {
    "LNCRAWLER_URL": "http://prod",
    "WORKER_TOKEN": "t",
    "WORKER_ID": "w",
}


def _load(**env):
    return load_config({**BASE, **env})


def test_the_worker_loads_with_only_the_three_required_variables():
    cfg = load_config(BASE)
    assert cfg.profile == "qwen-mixed"
    assert cfg.languages == ("en",)
    assert cfg.llm_url == "http://llama:8080/v1"


def test_required_variables_are_named_in_the_error():
    for name in ("LNCRAWLER_URL", "WORKER_TOKEN", "WORKER_ID"):
        env = {k: v for k, v in BASE.items() if k != name}
        with pytest.raises(ConfigError, match=f"{name} is required"):
            load_config(env)


def test_profile_must_be_a_known_one():
    assert _load(WORKER_PROFILE="kokoro").profile == "kokoro"
    with pytest.raises(ConfigError):
        _load(WORKER_PROFILE="bogus")


def test_languages_are_lower_cased_and_deduplicated():
    assert _load(WORKER_LANGUAGES=" EN, fr ,en ").languages == ("en", "fr")


def test_languages_are_capped_at_twenty():
    many = ",".join(f"l{i}" for i in range(20))
    assert len(_load(WORKER_LANGUAGES=many).languages) == 20
    with pytest.raises(ConfigError):
        _load(WORKER_LANGUAGES=many + ",extra")


def test_empty_languages_is_an_error():
    with pytest.raises(ConfigError):
        _load(WORKER_LANGUAGES=" , ")


def test_old_engine_profiles_variable_is_ignored():
    cfg = _load(WORKER_ENGINE_PROFILES="kokoro")
    assert cfg.profile == "qwen-mixed"


def test_removed_analyzer_variables_are_ignored():
    cfg = _load(ANALYSIS_MODE="castwright", ANALYZER="gemini", LLM_PROXY_URL="http://proxy.test:9000/v1")
    assert cfg.llm_url == "http://llama:8080/v1"
    assert not hasattr(cfg, "analysis_mode")


# -- the local LLM ----------------------------------------------------------------


def test_llm_defaults_are_the_local_server_with_a_five_minute_timeout():
    cfg = _load()
    assert cfg.llm_url == "http://llama:8080/v1"
    assert cfg.llm_timeout_s == 600.0
    assert cfg.llm_idle_s == 30.0
    assert cfg.llm_restart_flag == "/control/restart"


def test_llm_url_is_read_and_trimmed():
    assert _load(LLM_URL=" http://llm.test:9000/v1/ ").llm_url == "http://llm.test:9000/v1"


def test_llm_timeout_must_be_positive_and_idle_may_be_zero():
    assert _load(LLM_TIMEOUT_S="120").llm_timeout_s == 120.0
    assert _load(LLM_IDLE_S="0").llm_idle_s == 0.0
    with pytest.raises(ConfigError):
        _load(LLM_TIMEOUT_S="0")
    with pytest.raises(ConfigError):
        _load(LLM_IDLE_S="-1")
    with pytest.raises(ConfigError):
        _load(LLM_TIMEOUT_S="soon")


def test_restart_flag_can_be_moved_or_turned_off_with_an_empty_value():
    assert _load(LLM_RESTART_FLAG="/tmp/x/restart").llm_restart_flag == "/tmp/x/restart"
    assert _load(LLM_RESTART_FLAG="").llm_restart_flag == ""


@pytest.mark.parametrize("name", ["PING_INTERVAL_S", "HEARTBEAT_INTERVAL_S", "IDLE_RETRY_S"])
def test_worker_intervals_must_be_above_zero(name):
    assert getattr(_load(**{name: "2.5"}), name.lower()) == 2.5
    with pytest.raises(ConfigError, match=f"{name} must be above 0"):
        _load(**{name: "0"})
    with pytest.raises(ConfigError):
        _load(**{name: "-5"})
