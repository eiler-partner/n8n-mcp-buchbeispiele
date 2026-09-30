from pathlib import Path
from unittest.mock import patch

import pytest

from init_env import create_env
from smoke import check_health, read_port


def test_env_is_created_once_and_kept(tmp_path: Path):
    target = tmp_path / ".env"
    assert create_env(target)
    first = target.read_text()
    assert "REPLACE" not in first
    assert first.count("PASSWORD=") == 1
    assert first.count("ENCRYPTION_KEY=") == 1
    assert not create_env(target)
    assert target.read_text() == first
    assert target.stat().st_mode & 0o077 == 0


@pytest.mark.parametrize("value", ["0", "65536", "abc"])
def test_invalid_port_fails(tmp_path: Path, value: str):
    target = tmp_path / ".env"
    target.write_text(f"LAB_N8N_HOST_PORT={value}\n")
    with pytest.raises(ValueError):
        read_port(target)


def test_default_port(tmp_path: Path):
    target = tmp_path / ".env"
    target.write_text("POSTGRES_PASSWORD=hidden\n")
    assert read_port(target) == 15678


def test_unreachable_health_fails():
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        with pytest.raises(OSError):
            check_health(15678)


def test_compose_has_no_default_secrets():
    compose = (Path(__file__).parents[1] / "compose.yaml").read_text()
    assert "postgres:17.11-alpine" in compose
    assert "n8nio/n8n:2.40.7" in compose
    assert "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?" in compose
    assert "N8N_ENCRYPTION_KEY: ${N8N_ENCRYPTION_KEY:?" in compose
    assert "127.0.0.1:${LAB_N8N_HOST_PORT:-15678}:5678" in compose
    assert "condition: service_healthy" in compose
    assert "http://127.0.0.1:5678/healthz" in compose
