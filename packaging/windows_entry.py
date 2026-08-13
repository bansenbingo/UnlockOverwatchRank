"""PyInstaller entry point for the Windows one-file distribution."""

from ow_automation.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
