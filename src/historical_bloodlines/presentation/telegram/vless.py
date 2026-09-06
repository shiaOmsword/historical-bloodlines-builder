from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse


class VlessConfigurationError(ValueError):
    """Raised when a VLESS share URI cannot be mapped to sing-box."""


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


def vless_uri_to_sing_box_config(uri: str) -> dict[str, object]:
    parsed = urlparse(uri.strip())
    if parsed.scheme.casefold() != "vless":
        raise VlessConfigurationError("Expected a vless:// URI")
    if not parsed.username:
        raise VlessConfigurationError("VLESS URI does not contain a UUID")
    if not parsed.hostname or parsed.port is None:
        raise VlessConfigurationError("VLESS URI must contain server and port")

    query = parse_qs(parsed.query, keep_blank_values=True)
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
