from __future__ import annotations

import json
from urllib.parse import ParseResult, parse_qs, unquote, urlparse


class VlessConfigurationError(ValueError):
    """Raised when a VLESS share URI cannot be mapped to a proxy config."""


def _first(query: dict[str, list[str]], key: str, default: str = "") -> str:
    values = query.get(key)
    return values[0] if values else default


def _build_transport(query: dict[str, list[str]]) -> dict[str, object] | None:
    transport_type = _first(query, "type", "tcp").casefold()
    if transport_type in {"", "tcp", "none"}:
        return None

    path = unquote(_first(query, "path", "/"))
    host = _first(query, "host")

    if transport_type == "ws":
        transport: dict[str, object] = {"type": "ws", "path": path}
        if host:
            transport["headers"] = {"Host": host}
        return transport

    if transport_type == "grpc":
        service_name = _first(query, "serviceName") or path.lstrip("/")
        return {"type": "grpc", "service_name": service_name}

    if transport_type in {"http", "h2"}:
        transport = {"type": "http", "path": path}
        if host:
            transport["host"] = [host]
        return transport

    if transport_type in {"httpupgrade", "http-upgrade"}:
        transport = {"type": "httpupgrade", "path": path}
        if host:
            transport["host"] = host
        return transport

    raise VlessConfigurationError(
        f"Unsupported VLESS transport type: {transport_type}"
    )


def _parse_vless_uri(uri: str) -> tuple[ParseResult, dict[str, list[str]]]:
    try:
        parsed = urlparse(uri.strip())
        port = parsed.port
    except ValueError as exc:
        raise VlessConfigurationError("VLESS URI has an invalid server or port") from exc
    if parsed.scheme.casefold() != "vless":
        raise VlessConfigurationError("Expected a vless:// URI")
    if not parsed.username:
        raise VlessConfigurationError("VLESS URI does not contain a UUID")
    if not parsed.hostname or port is None or port == 0:
        raise VlessConfigurationError("VLESS URI must contain server and port")

    return parsed, parse_qs(parsed.query, keep_blank_values=True)


def vless_uri_to_sing_box_config(uri: str) -> dict[str, object]:
    parsed, query = _parse_vless_uri(uri)
    outbound: dict[str, object] = {
        "type": "vless",
        "tag": "vless-out",
        "server": parsed.hostname,
        "server_port": parsed.port,
        "uuid": unquote(parsed.username),
    }

    flow = _first(query, "flow")
    if flow:
        outbound["flow"] = flow

    security = _first(query, "security").casefold()
    if security in {"tls", "reality"}:
        tls: dict[str, object] = {"enabled": True}
        server_name = _first(query, "sni")
        if server_name:
            tls["server_name"] = server_name

        fingerprint = _first(query, "fp")
        if fingerprint:
            tls["utls"] = {
                "enabled": True,
                "fingerprint": fingerprint,
            }

        if security == "reality":
            public_key = _first(query, "pbk")
            if not public_key:
                raise VlessConfigurationError(
                    "Reality VLESS URI does not contain pbk (public key)"
                )
            reality: dict[str, object] = {
                "enabled": True,
                "public_key": public_key,
            }
            short_id = _first(query, "sid")
            if short_id:
                reality["short_id"] = short_id
            tls["reality"] = reality

        outbound["tls"] = tls
    elif security not in {"", "none"}:
        raise VlessConfigurationError(
            f"Unsupported VLESS security mode: {security}"
        )

    transport = _build_transport(query)
    if transport is not None:
        outbound["transport"] = transport

    return {
        "log": {"level": "info"},
        "inbounds": [
            {
                "type": "socks",
                "tag": "socks-in",
                "listen": "0.0.0.0",
                "listen_port": 1080,
            }
        ],
        "outbounds": [outbound],
        "route": {
            "final": "vless-out",
            "auto_detect_interface": True,
        },
    }


def vless_uri_to_xray_config(uri: str) -> dict[str, object]:
    parsed, query = _parse_vless_uri(uri)
    if _first(query, "type").casefold() != "xhttp":
        raise VlessConfigurationError("Xray mode requires type=xhttp")
    if _first(query, "security").casefold() != "tls":
        raise VlessConfigurationError("Xray XHTTP mode requires security=tls")
    if _first(query, "flow"):
        raise VlessConfigurationError("XHTTP + TLS does not support VLESS flow")
    if _first(query, "encryption", "none") != "none":
        raise VlessConfigurationError("Xray mode supports encryption=none only")
    if _first(query, "allowInsecure").casefold() in {"1", "true"}:
        raise VlessConfigurationError("Xray mode requires a valid TLS certificate")

    mode = _first(query, "mode") or "auto"
    if mode not in {"auto", "packet-up", "stream-up", "stream-one"}:
        raise VlessConfigurationError("Unsupported XHTTP mode")
    transport: dict[str, object] = {
        "path": _first(query, "path") or "/",
        "mode": mode,
    }
    host = _first(query, "host")
    if host:
        transport["host"] = host
    extra = _first(query, "extra")
    if extra:
        try:
            extra_settings = json.loads(extra)
        except json.JSONDecodeError as exc:
            raise VlessConfigurationError("XHTTP extra must be a JSON object") from exc
        if not isinstance(extra_settings, dict):
            raise VlessConfigurationError("XHTTP extra must be a JSON object")
        transport["extra"] = extra_settings

    tls: dict[str, object] = {
        "serverName": _first(query, "sni") or parsed.hostname,
        "allowInsecure": False,
    }
    fingerprint = _first(query, "fp")
    if fingerprint:
        tls["fingerprint"] = fingerprint
    alpn = _first(query, "alpn")
    if alpn:
        tls["alpn"] = [value.strip() for value in alpn.split(",") if value.strip()]

    return {
        "log": {"loglevel": "warning", "access": "none"},
        "inbounds": [
            {
                "tag": "socks-in",
                "listen": "0.0.0.0",
                "port": 1080,
                "protocol": "socks",
                "settings": {"auth": "noauth", "udp": False},
            }
        ],
        "outbounds": [
            {
                "tag": "vless-out",
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": parsed.hostname,
                            "port": parsed.port,
                            "users": [
                                {"id": unquote(parsed.username), "encryption": "none"}
                            ],
                        }
                    ]
                },
                "streamSettings": {
                    "network": "xhttp",
                    "security": "tls",
                    "tlsSettings": tls,
                    "xhttpSettings": transport,
                },
            }
        ],
    }
