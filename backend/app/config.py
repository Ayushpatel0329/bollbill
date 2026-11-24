"""All settings come from environment variables (see .env.example)."""
import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_anon_key: str
    nvidia_main_api_key: str
    nvidia_main_model: str
    nvidia_base_url: str
    nvidia_stt_api_key: str
    nvidia_stt_function_id: str
    anthropic_api_key: str
    grok_api_key: str
    model_fast: str
    model_smart: str
    allowed_origins: list
    rate_limit_per_min: int
    daily_ai_limit: int
    max_tool_rounds: int
    timezone: str


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        raise ConfigError(f"{name} must be a number")


def _load_dotenv(path: str = ".env") -> None:
    """Reads KEY=VALUE lines from a local .env file (for running on your own computer).
    Real environment variables always win, so on the hosting service this does nothing."""
    paths_to_check = [path, os.path.join("..", path), os.path.join(os.path.dirname(__file__), "..", "..", path)]
    for p in paths_to_check:
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            return
        except FileNotFoundError:
            pass


def load_settings() -> Settings:
    _load_dotenv()
    env = os.environ
    missing = [k for k in ("SUPABASE_URL", "SUPABASE_ANON_KEY") if not env.get(k)]
    if missing:
        raise ConfigError("Missing environment variables: " + ", ".join(missing))
    origins = [o.strip().rstrip("/") for o in env.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
    return Settings(
        supabase_url=env["SUPABASE_URL"].rstrip("/"),
        supabase_anon_key=env["SUPABASE_ANON_KEY"],
        nvidia_main_api_key=env.get("NVIDIA_MAIN_API_KEY", ""),
        nvidia_main_model=env.get("NVIDIA_MAIN_MODEL", "nvidia/nemotron-3.5-super-vl-120b-a12b"),
        nvidia_base_url=env.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        nvidia_stt_api_key=env.get("NVIDIA_STT_API_KEY", env.get("NVIDIA_API_KEY", "")),
        nvidia_stt_function_id=env.get("NVIDIA_STT_FUNCTION_ID", ""),
        anthropic_api_key=env.get("ANTHROPIC_API_KEY", "dummy"),
        grok_api_key=env.get("GROK_API_KEY", ""),
        model_fast=env.get("MODEL_FAST", "nvidia/nemotron-3.5-super-vl-120b-a12b"),
        model_smart=env.get("MODEL_SMART", "nvidia/nemotron-3.5-super-vl-120b-a12b"),
        allowed_origins=origins or ["*"],
        rate_limit_per_min=_int("RATE_LIMIT_PER_MIN", 60),
        daily_ai_limit=_int("DAILY_AI_LIMIT", 500),
        max_tool_rounds=_int("MAX_TOOL_ROUNDS", 5),
        timezone=env.get("SHOP_TIMEZONE", "Asia/Kolkata"),
    )
