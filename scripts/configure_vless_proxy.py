from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from historical_bloodlines.presentation.telegram.vless import (  # noqa: E402
    vless_uri_to_sing_box_config,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create private sing-box config from a VLESS share URI."
    )
    parser.add_argument("uri", nargs="?", help="vless:// URI; omitted = hidden prompt")
    parser.add_argument(
        "--output",
        default="deploy/proxy/config.json",
        help="Output sing-box config path",
    )
    args = parser.parse_args()

    uri = args.uri or getpass.getpass("VLESS URI: ")
    config = vless_uri_to_sing_box_config(uri)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        output.chmod(0o600)
    except OSError:
        pass
    print(f"Created private sing-box config: {output}")


if __name__ == "__main__":
    main()
