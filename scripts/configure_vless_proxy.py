from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from historical_bloodlines.presentation.telegram.vless import (  # noqa: E402
    VlessConfigurationError,
    vless_uri_to_sing_box_config,
    vless_uri_to_xray_config,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a private proxy config from a VLESS share URI."
    )
    parser.add_argument("uri", nargs="?", help="vless:// URI; omitted = hidden prompt")
    parser.add_argument("--engine", choices=("sing-box", "xray"), default="sing-box")
    parser.add_argument(
        "--output",
        help="Output path (default: deploy/proxy/config.json or deploy/proxy/xray.json)",
    )
    args = parser.parse_args()

    uri = args.uri or getpass.getpass("VLESS URI: ")
    converter = (
        vless_uri_to_xray_config
        if args.engine == "xray"
        else vless_uri_to_sing_box_config
    )
    try:
        config = converter(uri)
    except VlessConfigurationError as exc:
        parser.error(str(exc))
    filename = "xray.json" if args.engine == "xray" else "config.json"
    output = Path(args.output) if args.output else Path("deploy/proxy") / filename
    output.parent.mkdir(parents=True, exist_ok=True)
    output.touch(mode=0o600, exist_ok=True)
    try:
        output.chmod(0o600)
    except OSError:
        pass
    output.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Created private {args.engine} config: {output}")


if __name__ == "__main__":
    main()
