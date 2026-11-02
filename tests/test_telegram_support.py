from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode

import pytest

from historical_bloodlines.presentation.telegram.config import (
    TelegramBotConfigurationError,
    _parse_allowed_user_ids,
)
from historical_bloodlines.presentation.telegram.vless import (
    VlessConfigurationError,
    vless_uri_to_sing_box_config,
    vless_uri_to_xray_config,
)


def test_parse_allowed_user_ids() -> None:
    assert _parse_allowed_user_ids("123, 456") == frozenset({123, 456})


def test_parse_allowed_user_ids_rejects_invalid_value() -> None:
    with pytest.raises(TelegramBotConfigurationError):
        _parse_allowed_user_ids("123,abc")


def test_vless_module_imports_with_stdlib_only() -> None:
    project_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(project_root / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            (
                "from historical_bloodlines.presentation.telegram.vless "
                "import vless_uri_to_sing_box_config; "
                "print(vless_uri_to_sing_box_config('vless://11111111-1111-1111-1111-111111111111@example.com:443?security=none')['outbounds'][0]['type'])"
            ),
        ],
        cwd=project_root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "vless"


def test_vless_reality_uri_maps_to_sing_box() -> None:
    config = vless_uri_to_sing_box_config(
        "vless://11111111-1111-1111-1111-111111111111@example.com:443"
        "?security=reality&sni=cdn.example.com&fp=chrome"
        "&pbk=PUBLICKEY&sid=0123&type=tcp&flow=xtls-rprx-vision"
    )

    outbound = config["outbounds"][0]
    assert outbound["type"] == "vless"
    assert outbound["server"] == "example.com"
    assert outbound["server_port"] == 443
    assert outbound["flow"] == "xtls-rprx-vision"
    assert outbound["tls"]["server_name"] == "cdn.example.com"
    assert outbound["tls"]["utls"]["fingerprint"] == "chrome"
    assert outbound["tls"]["reality"]["public_key"] == "PUBLICKEY"
    assert outbound["tls"]["reality"]["short_id"] == "0123"


def test_vless_websocket_transport_maps_host_and_path() -> None:
    config = vless_uri_to_sing_box_config(
        "vless://11111111-1111-1111-1111-111111111111@example.com:443"
        "?security=tls&sni=example.com&type=ws&path=%2Ftelegram&host=edge.example.com"
    )

    transport = config["outbounds"][0]["transport"]
    assert transport == {
        "type": "ws",
        "path": "/telegram",
        "headers": {"Host": "edge.example.com"},
    }


def test_vless_reality_requires_public_key() -> None:
    with pytest.raises(VlessConfigurationError):
        vless_uri_to_sing_box_config(
            "vless://11111111-1111-1111-1111-111111111111@example.com:443"
            "?security=reality&type=tcp"
        )


def test_xhttp_tls_link_preserves_connection_settings() -> None:
    query = urlencode({
        "type": "xhttp", "security": "tls", "encryption": "none",
        "sni": "tls.example.com", "fp": "chrome", "alpn": "h2,http/1.1",
        "host": "edge.example.com", "path": "/proxy/%2F/", "mode": "packet-up",
        "extra": json.dumps({"xmux": {"maxConcurrency": 1}}),
    })
    config = vless_uri_to_xray_config(
        f"vless://11111111-1111-1111-1111-111111111111@192.0.2.1:8443?{query}"
    )
    outbound = config["outbounds"][0]
    assert outbound["settings"]["vnext"] == [{
        "address": "192.0.2.1", "port": 8443,
        "users": [{"id": "11111111-1111-1111-1111-111111111111", "encryption": "none"}],
    }]
    assert outbound["streamSettings"] == {
        "network": "xhttp", "security": "tls",
        "tlsSettings": {
            "serverName": "tls.example.com", "allowInsecure": False,
            "fingerprint": "chrome", "alpn": ["h2", "http/1.1"],
        },
        "xhttpSettings": {
            "host": "edge.example.com", "path": "/proxy/%2F/", "mode": "packet-up",
            "extra": {"xmux": {"maxConcurrency": 1}},
        },
    }
    assert len(config["outbounds"]) == 1
    assert config["inbounds"][0]["port"] == 1080
    assert config["inbounds"][0]["protocol"] == "socks"


@pytest.mark.parametrize("mode", ["auto", "packet-up", "stream-up", "stream-one"])
def test_xhttp_modes_and_tls_defaults(mode: str) -> None:
    config = vless_uri_to_xray_config(
        "vless://11111111-1111-1111-1111-111111111111@[2001:db8::1]:443"
        f"?type=xhttp&security=tls&mode={mode}"
    )
    stream = config["outbounds"][0]["streamSettings"]
    assert stream["tlsSettings"] == {"serverName": "2001:db8::1", "allowInsecure": False}
    assert stream["xhttpSettings"] == {"path": "/", "mode": mode}


@pytest.mark.parametrize("query", [
    "type=ws&security=tls", "type=xhttp&security=reality",
    "type=xhttp&security=tls&flow=xtls-rprx-vision",
    "type=xhttp&security=tls&encryption=unsupported",
    "type=xhttp&security=tls&allowInsecure=1",
    "type=xhttp&security=tls&mode=unknown",
    "type=xhttp&security=tls&extra=not-json",
    "type=xhttp&security=tls&extra=%5B%5D",
])
def test_xhttp_rejects_unsupported_link_settings(query: str) -> None:
    with pytest.raises(VlessConfigurationError):
        vless_uri_to_xray_config(
            f"vless://11111111-1111-1111-1111-111111111111@example.com:443?{query}"
        )


def test_xray_cli_writes_private_config_without_overwriting_sing_box(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts/configure_vless_proxy.py"
    proxy_directory = tmp_path / "deploy/proxy"
    proxy_directory.mkdir(parents=True)
    sing_box_config = proxy_directory / "config.json"
    sing_box_config.write_text('{"existing": true}', encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-S", str(script), "--engine", "xray",
         "vless://11111111-1111-1111-1111-111111111111@example.com:443?type=xhttp&security=tls"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    output = proxy_directory / "xray.json"
    assert json.loads(output.read_text())["outbounds"][0]["protocol"] == "vless"
    assert sing_box_config.read_text() == '{"existing": true}'
    if os.name == "posix":
        assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_xray_cli_invalid_link_keeps_existing_config_and_hides_uri(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts/configure_vless_proxy.py"
    output = tmp_path / "xray.json"
    output.write_text("existing config", encoding="utf-8")
    secret = "11111111-1111-1111-1111-111111111111"
    result = subprocess.run(
        [sys.executable, "-S", str(script), "--engine", "xray", "--output", str(output),
         f"vless://{secret}@example.com:443?type=xhttp&security=tls&extra=not-json"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert "XHTTP extra must be a JSON object" in result.stderr
    assert secret not in result.stderr
    assert "Traceback" not in result.stderr
    assert output.read_text() == "existing config"
