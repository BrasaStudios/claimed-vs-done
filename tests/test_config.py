import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pytest

from cvd import config
from cvd.config import KeyMissing, Profile, cost_usd, get_key, load_profiles


def write_config(tmp_path, text):
    path = tmp_path / "models.toml"
    path.write_text(text, encoding="ascii", newline="\n")
    return path


def test_valid_file_and_defaults(tmp_path):
    path = write_config(tmp_path, """
[profiles.example]
base_url = "http://127.0.0.1/v1"
model = "test-model"
key_env = "CVD_TEST_KEY"
reasoning_effort = "low"
price_in_per_m = 0.4
price_out_per_m = 1.2
[profiles.example.extra_body]
seed = 7
""")
    profile = load_profiles(path)["example"]
    assert profile.name == "example"
    assert profile.kind == "http"
    assert profile.timeout_s == 300.0
    assert profile.extra_body == {"seed": 7}
    assert profile.reasoning_effort == "low"
    with pytest.raises(FrozenInstanceError):
        profile.name = "changed"


def test_supplied_model_routes():
    profiles = load_profiles(Path(__file__).resolve().parents[1] / "models.toml")
    assert {"beam-hf", "beam-openrouter", "scripted-sample"} <= set(profiles)
    hf = profiles["beam-hf"]
    assert (hf.base_url, hf.model, hf.key_env) == (
        "https://router.huggingface.co/v1",
        "reflection/Beam-1.0-501B-A23B:baseten",
        "BEAM_HF_TOKEN",
    )
    assert (hf.price_in_per_m, hf.price_out_per_m) == (0.40, 1.20)
    router = profiles["beam-openrouter"]
    assert (router.base_url, router.model, router.key_env) == (
        "https://openrouter.ai/api/v1",
        "reflection/beam-1.0-501b-a23b",
        "BEAM_OPENROUTER_KEY",
    )
    assert (router.price_in_per_m, router.price_out_per_m) == (0.25, 1.00)


def test_unknown_key(tmp_path):
    path = write_config(tmp_path, '[profiles.x]\nmisspelled = 1\n')
    with pytest.raises(ValueError, match="misspelled"):
        load_profiles(path)


@pytest.mark.parametrize("missing", ["base_url", "model", "key_env"])
def test_missing_http_field(tmp_path, missing):
    values = {"base_url": "http://127.0.0.1/v1", "model": "test", "key_env": "CVD_TEST_KEY"}
    text = "[profiles.x]\n" + "".join(
        name + ' = "' + value + '"\n' for name, value in values.items() if name != missing
    )
    with pytest.raises(ValueError, match=missing):
        load_profiles(write_config(tmp_path, text))


def test_script_path_relative_to_models(tmp_path):
    profile = load_profiles(write_config(
        tmp_path, '[profiles.scripted]\nkind = "scripted"\nscript = "steps.json"\n'
    ))["scripted"]
    assert profile.script == str((tmp_path / "steps.json").resolve())


def test_key_prefers_environment(monkeypatch, fake_key):
    monkeypatch.setenv("CVD_TEST_KEY", fake_key)

    def forbidden_lookup(name):
        raise AssertionError("Environment must take priority")

    monkeypatch.setattr(config, "_registry_key", forbidden_lookup)
    assert get_key("CVD_TEST_KEY") == fake_key


@pytest.mark.parametrize("value", [None, ""])
def test_key_missing_names_variable(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("CVD_TEST_MISSING_KEY", raising=False)
    else:
        monkeypatch.setenv("CVD_TEST_MISSING_KEY", value)
    monkeypatch.setattr(config, "_registry_key", lambda name: None)
    with pytest.raises(KeyMissing, match="CVD_TEST_MISSING_KEY"):
        get_key("CVD_TEST_MISSING_KEY")


def test_non_windows_never_reads_registry(monkeypatch):
    monkeypatch.setattr(config, "os", SimpleNamespace(name="posix", environ={}))

    def forbidden_lookup(name):
        raise AssertionError("Registry lookup on non-Windows")

    monkeypatch.setattr(config, "_registry_key", forbidden_lookup)
    with pytest.raises(KeyMissing, match="CVD_TEST_KEY"):
        get_key("CVD_TEST_KEY")


def test_windows_registry_fallback(monkeypatch, fake_key):
    seen = []

    class Handle:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def open_key(root, path):
        seen.append((root, path))
        return Handle()

    def query_value(handle, name):
        seen.append(name)
        return fake_key, 1

    monkeypatch.setitem(sys.modules, "winreg", SimpleNamespace(
        HKEY_CURRENT_USER=123, OpenKey=open_key, QueryValueEx=query_value
    ))
    monkeypatch.setattr(config, "os", SimpleNamespace(name="nt", environ={}))
    assert get_key("CVD_TEST_KEY") == fake_key
    assert seen == [(123, "Environment"), "CVD_TEST_KEY"]


def test_cost_usd():
    profile = Profile("test", price_in_per_m=0.40, price_out_per_m=1.20)
    assert cost_usd(profile, 2_000_000, 500_000) == pytest.approx(1.40)
    assert cost_usd(profile, 0, 0) == 0
