"""CLI helper utilities for standardized script execution across zoho_usable_functions."""

from __future__ import annotations

import argparse
import sys
from typing import Any, Callable, Optional, Sequence

from .auth import get_books_client, get_workdrive_client
from .logging_config import setup_logging


class ScriptContext:
    """Container for common script runtime objects and settings."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self._books_client: Any = None
        self._workdrive_client: Any = None

    @property
    def books_client(self) -> Any:
        if self._books_client is None:
            self._books_client = get_books_client()
        return self._books_client

    @property
    def workdrive_client(self) -> Any:
        if self._workdrive_client is None:
            self._workdrive_client = get_workdrive_client()
        return self._workdrive_client


def init_script_context(
    description: str,
    configure_parser: Optional[Callable[[argparse.ArgumentParser], None]] = None,
    argv: Optional[Sequence[str]] = None,
) -> ScriptContext:
    """Initialize logging, parse standard CLI arguments, and return a ScriptContext.

    Standard options included by default:
    --verbose / -v : Enable debug logging
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose/debug logging")

    if configure_parser is not None:
        configure_parser(parser)

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    setup_logging(verbose=getattr(args, "verbose", False))

    return ScriptContext(args)
