"""Environment -> frozen Config."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    lncrawler_url: str
    worker_token: str
    worker_id: str
    profile: str
    languages: tuple[str, ...]
    castwright_url: str
    castwright_ref: str
    hz_ref: str
    data_dir: str
    workspace_dir: str
    qwen_main_min_lines: int
    qwen_max_designed: int
    ping_interval_s: float
    heartbeat_interval_s: float
    idle_retry_s: float
    llm_url: str
    llm_timeout_s: float
    llm_idle_s: float
    llm_restart_flag: str  # the file that asks the llama container to restart its server; "" turns this off

    @property
    def api_base(self) -> str:
        return self.lncrawler_url.rstrip("/") + "/api/audiobook-worker/"


def _required(env: Mapping[str, str], name: str) -> str:
    value = (env.get(name) or "").strip()
    if not value:
        raise ConfigError(f"{name} is required")
    return value


def _number(env: Mapping[str, str], name: str, default: str, cast):
    raw = (env.get(name) or "").strip() or default
    try:
        return cast(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc


def _positive(env: Mapping[str, str], name: str, default: str) -> float:
    """A number of seconds that must be above 0: a zero interval would spin the loop."""
    value = _number(env, name, default, float)
    if not value > 0:
        raise ConfigError(f"{name} must be above 0")
    return value


PROFILES = ("qwen-mixed", "kokoro")
MAX_LANGUAGES = 20


def _profile(env: Mapping[str, str]) -> str:
    profile = (env.get("WORKER_PROFILE") or "qwen-mixed").strip()
    if profile not in PROFILES:
        raise ConfigError(f"WORKER_PROFILE must be one of {', '.join(PROFILES)}, got {profile!r}")
    return profile


def _languages(env: Mapping[str, str]) -> tuple[str, ...]:
    """Lower-cased, de-duplicated, at most MAX_LANGUAGES codes."""
    raw = env.get("WORKER_LANGUAGES") or "en"
    languages: list[str] = []
    for part in raw.split(","):
        code = part.strip().lower()
        if code and code not in languages:
            languages.append(code)
    if not languages:
        raise ConfigError("WORKER_LANGUAGES must list at least one language code")
    if len(languages) > MAX_LANGUAGES:
        raise ConfigError(f"WORKER_LANGUAGES takes at most {MAX_LANGUAGES} codes, got {len(languages)}")
    return tuple(languages)


def _llm_settings(env: Mapping[str, str]) -> dict[str, object]:
    """The local LLM the analysis calls, its timeouts, and the flag file that asks its server to restart."""
    timeout = _number(env, "LLM_TIMEOUT_S", "600", float)
    if not timeout > 0:
        raise ConfigError("LLM_TIMEOUT_S must be above 0")
    idle = _number(env, "LLM_IDLE_S", "30", float)
    if not idle >= 0:
        raise ConfigError("LLM_IDLE_S must be 0 or more")
    restart_flag = env.get("LLM_RESTART_FLAG")
    return {
        "llm_url": (env.get("LLM_URL") or "http://llama:8080/v1").strip().rstrip("/"),
        "llm_timeout_s": timeout,
        "llm_idle_s": idle,
        "llm_restart_flag": "/control/restart" if restart_flag is None else restart_flag.strip(),
    }


def load_config(env: Mapping[str, str] | None = None) -> Config:
    env = os.environ if env is None else env
    return Config(
        lncrawler_url=_required(env, "LNCRAWLER_URL"),
        worker_token=_required(env, "WORKER_TOKEN"),
        worker_id=_required(env, "WORKER_ID"),
        profile=_profile(env),
        languages=_languages(env),
        castwright_url=(env.get("CASTWRIGHT_URL") or "http://castwright:8080").rstrip("/"),
        castwright_ref=(env.get("CASTWRIGHT_REF") or "3a52b28").strip(),
        hz_ref=(env.get("HZ_REF") or "74feb58").strip(),
        data_dir=(env.get("DATA_DIR") or "/data").rstrip("/") or "/",
        workspace_dir=(env.get("WORKSPACE_DIR") or "/workspace").rstrip("/") or "/",
        qwen_main_min_lines=_number(env, "QWEN_MAIN_MIN_LINES", "8", int),
        qwen_max_designed=_number(env, "QWEN_MAX_DESIGNED", "14", int),
        ping_interval_s=_positive(env, "PING_INTERVAL_S", "300"),
        heartbeat_interval_s=_positive(env, "HEARTBEAT_INTERVAL_S", "60"),
        idle_retry_s=_positive(env, "IDLE_RETRY_S", "300"),
        **_llm_settings(env),
    )
