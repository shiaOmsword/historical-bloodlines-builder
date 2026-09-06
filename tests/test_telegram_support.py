from __future__ import annotations

import pytest

from historical_bloodlines.presentation.telegram.config import (
    TelegramBotConfigurationError,
    _parse_allowed_user_ids,
)
from historical_bloodlines.presentation.telegram.vless import (
    VlessConfigurationError,
    vless_uri_to_sing_box_config,
)


def test_parse_allowed_user_ids() -> None:
    assert _parse_allowed_user_ids("123, 456") == frozenset({123, 456})


def test_parse_allowed_user_ids_rejects_invalid_value() -> None:
    with pytest.raises(TelegramBotConfigurationError):
        _parse_allowed_user_ids("123,abc")


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
