"""Command-line entry point."""

import typer

from kick_commenter import __version__
from kick_commenter.config import Settings

app = typer.Typer(help="A friendly chat companion for Kick streams.", no_args_is_help=True)


@app.command()
def version() -> None:
    """Show the installed version."""
    typer.echo(__version__)


@app.command()
def settings() -> None:
    """Show the active settings."""
    for name, value in Settings().model_dump().items():
        typer.echo(f"{name} = {value}")
