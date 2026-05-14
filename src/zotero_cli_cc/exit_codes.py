"""Stable CLI exit codes for orchestrators and agents."""

from __future__ import annotations

import json
from typing import NoReturn

import click

from zotero_cli_cc.formatter import envelope_error

EXIT_OK = 0
EXIT_RUNTIME = 1
EXIT_AUTH = 2
EXIT_VALIDATION = 3
EXIT_NOT_FOUND = 4
EXIT_NETWORK = 5
EXIT_CONFLICT = 6

CODE_TO_EXIT = {
    "auth_missing": EXIT_AUTH,
    "auth_invalid": EXIT_AUTH,
    "auth_expired": EXIT_AUTH,
    "validation_error": EXIT_VALIDATION,
    "not_found": EXIT_NOT_FOUND,
    "network_error": EXIT_NETWORK,
    "rate_limited": EXIT_NETWORK,
    "conflict": EXIT_CONFLICT,
    "confirmation_required": EXIT_VALIDATION,
    # Local Zotero bridge (`zot find-pdf`):
    "not_reachable": EXIT_NETWORK,  # Zotero desktop not running / port closed
    "bridge_missing": EXIT_VALIDATION,  # plugin not installed — setup issue
    "bridge_error": EXIT_RUNTIME,  # bridge replied with an error
}


def exit_code_for(error_code: str) -> int:
    return CODE_TO_EXIT.get(error_code, EXIT_RUNTIME)


def report_error(
    code: str,
    message: str,
    *,
    output_json: bool,
    retryable: bool = False,
    hint: str = "",
    context: str = "",
) -> None:
    """Emit an error without exiting. JSON → stdout envelope; text → stderr human line."""
    if output_json:
        env = envelope_error(code=code, message=message, retryable=retryable, hint=hint, context=context)
        click.echo(json.dumps(env, indent=2, ensure_ascii=False))
    else:
        click.echo(f"Error: {message}", err=True)
        if hint:
            click.echo(f"Hint: {hint}", err=True)


def emit_error(
    code: str,
    message: str,
    *,
    output_json: bool,
    retryable: bool = False,
    hint: str = "",
    context: str = "",
    exit_code: int | None = None,
) -> NoReturn:
    """Emit an error and exit with a code mapped from `code`."""
    report_error(code, message, output_json=output_json, retryable=retryable, hint=hint, context=context)
    raise SystemExit(exit_code if exit_code is not None else exit_code_for(code))
