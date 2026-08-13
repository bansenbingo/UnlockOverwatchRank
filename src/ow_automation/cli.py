"""Command-line entry point used by local checks and the Windows executable."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Keep the runtime adapters visible to PyInstaller when building the one-file
# Windows distribution. Their constructors remain inert unless explicitly used.
from . import capture, input_control, runtime, vision, windows  # noqa: F401
from .config import load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="UnlockOverwatchRank",
        description="Conservative screen-driven automation tooling for authorized testing.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="YAML configuration path (default: config.yaml)",
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="validate Python imports and configuration without capturing or sending input",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.self_check:
        print(
            "No live automation loop is enabled by default. Use --self-check for an offline check."
        )
        return 0
    if not args.config.exists():
        print(f"Configuration file not found: {args.config}", file=sys.stderr)
        print("Copy config.example.yaml to config.yaml before running --self-check.", file=sys.stderr)
        return 2
    config = load_config(args.config)
    config.state_machine_config()
    print("Configuration and safety limits are valid.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
