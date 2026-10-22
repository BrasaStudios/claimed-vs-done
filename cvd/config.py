"""Model routes and secret lookup."""

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path


@dataclass(frozen=True)
class Profile:
    name: str
    kind: str = "http"
    base_url: str = ""
    model: str = ""
    key_env: str | None = None
    reasoning_effort: str | None = None
    extra_body: dict = field(default_factory=dict)
    price_in_per_m: float = 0.0
    price_out_per_m: float = 0.0
    timeout_s: float = 300.0
    max_tokens: int | None = None
    temperature: float | None = None
    script: str | None = None


class KeyMissing(Exception):
    """The named environment variable has no nonempty key."""


def load_profiles(path="models.toml") -> dict[str, Profile]:
    path = Path(path)
    with path.open("rb") as stream:
        document = tomllib.load(stream)
    unknown = set(document) - {"profiles"}
    if unknown:
        raise ValueError("Unknown key: " + sorted(unknown)[0])
    tables = document.get("profiles", {})
    if not isinstance(tables, dict):
        raise ValueError("profiles must be a table")
    allowed = {item.name for item in fields(Profile)} - {"name"}
    profiles = {}
    for name, table in tables.items():
        if not isinstance(table, dict):
            raise ValueError("Profile " + name + " must be a table")
        unknown = set(table) - allowed
        if unknown:
            raise ValueError("Unknown profile key: " + sorted(unknown)[0])
        values = dict(table)
        kind = values.get("kind", "http")
        if kind not in ("http", "scripted"):
            raise ValueError("Profile " + name + " has an invalid kind")
        if kind == "http":
            for required in ("base_url", "model", "key_env"):
                if not isinstance(values.get(required), str) or not values[required]:
                    raise ValueError("Profile " + name + " requires " + required)
        if not isinstance(values.get("extra_body", {}), dict):
            raise ValueError("extra_body must be a table")
        if values.get("script") is not None:
            values["script"] = str((path.parent / values["script"]).resolve())
        profiles[name] = Profile(name=name, **values)
    return profiles


def _registry_key(key_env: str) -> str | None:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as handle:
            value, _ = winreg.QueryValueEx(handle, key_env)
        return value if isinstance(value, str) and value else None
    except (ImportError, OSError):
        return None


def get_key(key_env: str) -> str:
    value = os.environ.get(key_env)
    if value:
        return value
    if os.name == "nt":
        value = _registry_key(key_env)
        if value:
            return value
    raise KeyMissing("Missing API key in environment variable " + key_env)


def cost_usd(profile: Profile, prompt_tokens: int, completion_tokens: int) -> float:
    return (
        prompt_tokens * profile.price_in_per_m
        + completion_tokens * profile.price_out_per_m
    ) / 1_000_000
