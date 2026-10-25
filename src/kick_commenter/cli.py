"""Command-line entry point."""

import asyncio
import webbrowser
from collections.abc import Awaitable, Callable

import httpx
import typer

from kick_commenter import __version__
from kick_commenter.config import Settings
from kick_commenter.kick.bots import BotRegistry
from kick_commenter.kick.callback import wait_for_code
from kick_commenter.kick.client import KickApi
from kick_commenter.kick.errors import KickError
from kick_commenter.kick.login import add_bot, remove_bot
from kick_commenter.kick.oauth import OAuthClient, utc_now
from kick_commenter.kick.token_store import KeyringTokenStore
from kick_commenter.kick.tokens import AppTokenProvider

app = typer.Typer(help="A friendly chat companion for Kick streams.", no_args_is_help=True)
bots_app = typer.Typer(help="Manage the bot accounts sessions can use.", no_args_is_help=True)
app.add_typer(bots_app, name="bots")

HTTP_TIMEOUT = httpx.Timeout(10.0)


@app.command()
def version() -> None:
    """Show the installed version."""
    typer.echo(__version__)


@app.command()
def settings() -> None:
    """Show the active settings (secrets are hidden)."""
    for name, value in Settings().model_dump().items():
        typer.echo(f"{name} = {value}")


@app.command()
def channel(slug: str) -> None:
    """Look up a channel by its name, for example ``thetoxicparty``."""

    async def run(http: httpx.AsyncClient, oauth: OAuthClient) -> None:
        api = KickApi(http, AppTokenProvider(oauth, utc_now))
        found = await api.channels_by_slug([slug])
        if not found:
            typer.echo(f"No channel named {slug!r}.")
            raise typer.Exit(1)
        match = found[0]
        status = "live" if match.is_live else "offline"
        typer.echo(f"{match.slug}: broadcaster id {match.broadcaster_user_id}, {status}")

    _run_with_kick(run)


@bots_app.command("add")
def bots_add() -> None:
    """Add a bot: log in as the bot account in your browser."""
    config = Settings()

    async def run(http: httpx.AsyncClient, oauth: OAuthClient) -> None:
        typer.echo("Opening Kick in your browser. Log in as the BOT account and approve.")
        bot = await add_bot(
            http=http,
            oauth=oauth,
            store=KeyringTokenStore(),
            registry=BotRegistry(config.bots_file),
            open_browser=webbrowser.open,
            wait_for_code=lambda state: wait_for_code(
                "localhost", config.redirect_port, state, config.login_timeout_seconds
            ),
            clock=utc_now,
        )
        typer.echo(f"Added bot {bot.name}.")

    _run_with_kick(run)


@bots_app.command("list")
def bots_list() -> None:
    """Show the saved bots."""
    bots = BotRegistry(Settings().bots_file).all()
    if not bots:
        typer.echo("No bots yet. Add one with: kick-commenter bots add")
        return
    for bot in bots:
        typer.echo(f"{bot.name} (id {bot.user_id}, added {bot.added_at:%Y-%m-%d})")


@bots_app.command("remove")
def bots_remove(name: str) -> None:
    """Remove a bot and revoke its access."""
    config = Settings()

    async def run(_http: httpx.AsyncClient, oauth: OAuthClient) -> None:
        try:
            bot = await remove_bot(
                name=name,
                oauth=oauth,
                store=KeyringTokenStore(),
                registry=BotRegistry(config.bots_file),
            )
        except KeyError:
            typer.echo(f"No bot named {name!r}.")
            raise typer.Exit(1) from None
        typer.echo(f"Removed bot {bot.name}.")

    _run_with_kick(run)


def _run_with_kick(
    action: Callable[[httpx.AsyncClient, OAuthClient], Awaitable[None]],
) -> None:
    config = Settings()
    if not config.client_id or config.client_secret is None:
        typer.echo(
            "Set KICK_COMMENTER_CLIENT_ID and KICK_COMMENTER_CLIENT_SECRET in .env first "
            "(see .env.example)."
        )
        raise typer.Exit(1)
    client_id, client_secret = config.client_id, config.client_secret.get_secret_value()

    async def main() -> None:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as http:
            oauth = OAuthClient(http, client_id, client_secret, config.redirect_uri)
            await action(http, oauth)

    try:
        asyncio.run(main())
    except KickError as error:
        typer.echo(f"Kick error: {error}")
        raise typer.Exit(1) from None
