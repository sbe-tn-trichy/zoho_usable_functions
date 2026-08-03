import argparse
from unittest.mock import MagicMock, patch

import pytest

from zoho_usable_functions.core.cli import ScriptContext, init_script_context


def test_init_script_context_parses_arguments():
    def custom_args(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--test-param", type=str, default="default_value")

    ctx = init_script_context(
        description="Test Script",
        configure_parser=custom_args,
        argv=["--verbose", "--test-param", "custom_value"],
    )

    assert ctx.args.verbose is True
    assert ctx.args.test_param == "custom_value"


@patch("zoho_usable_functions.core.cli.get_books_client")
def test_script_context_lazy_initializes_books_client(mock_get_books):
    mock_client = MagicMock()
    mock_get_books.return_value = mock_client

    ctx = init_script_context("Test Script", argv=[])
    mock_get_books.assert_not_called()

    client = ctx.books_client
    assert client == mock_client
    mock_get_books.assert_called_once()
