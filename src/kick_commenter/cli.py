"""Command-line entry point."""

import asyncio
import os
import webbrowser
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Annotated

import httpx
import typer

from kick_commenter import __version__
from kick_commenter.collector.collector import Collector, CollectorStats
from kick_commenter.collector.lookup import (
    ChannelIds,
    ChannelLookup,
    ChannelLookupError,
    read_cache,
)
from kick_commenter.collector.pusher import PusherChatSource
from kick_commenter.collector.realtime import PusherApp, RealtimeConfig
from kick_commenter.config import Settings
from kick_commenter.kick.bots import BotAccount, BotRegistry
from kick_commenter.kick.callback import wait_for_code
from kick_commenter.kick.client import KickApi
from kick_commenter.kick.errors import KickError
from kick_commenter.kick.login import add_bot, remove_bot
from kick_commenter.kick.oauth import OAuthClient, utc_now
from kick_commenter.kick.token_store import KeyringTokenStore
from kick_commenter.kick.tokens import AppTokenProvider
from kick_commenter.models import ChatMessage
from kick_commenter.nlp.language import LinguaGuesser
from kick_commenter.nlp.pipeline import TextPipeline
from kick_commenter.profile.builder import ProfileBuilder
from kick_commenter.profile.terms import ScoredTerm
from kick_commenter.profile.warmup import WarmupTracker
from kick_commenter.session.commands import HELP_TEXT
from kick_commenter.session.idle import IdleTimer, minutes
from kick_commenter.session.lock import ChannelBusyError, ChannelLock, LockInfo
from kick_commenter.session.session import Session, StopReason
from kick_commenter.session.terminal import typed_lines
from kick_commenter.storage.chat_store import ChatStore

app = typer.Typer(help="A friendly chat companion for Kick streams.", no_args_is_help=True)
bots_app = typer.Typer(help="Manage the bot accounts sessions can use.", no_args_is_help=True)
app.add_typer(bots_app, name="bots")

HTTP_TIMEOUT = httpx.Timeout(10.0)

ChatroomIdOption = Annotated[
    int | None, typer.Option(help="Skip the lookup: the channel's chatroom id.")
]
ChannelIdOption = Annotated[int | None, typer.Option(help="Skip the lookup: the channel's id.")]
QuietOption = Annotated[bool, typer.Option(help="Don't print each message.")]


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


@app.command()
def collect(
    slug: str,
    chatroom_id: ChatroomIdOption = None,
    channel_id: ChannelIdOption = None,
    quiet: QuietOption = False,
) -> None:
    """Read a channel's chat and save it locally. Read-only; stop with Ctrl+C."""
    config = Settings()
    store = ChatStore(config.chat_db)
    collector: Collector | None = None

    async def main() -> None:
        nonlocal collector
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as http:
            ids = await _resolve_channel(config, http, slug, chatroom_id, channel_id)
            typer.echo(f"Collecting {ids.slug} (read-only). Press Ctrl+C to stop.")
            collector = _collector(config, http, ids, store, quiet=quiet)
            await collector.run(asyncio.Event())

    try:
        asyncio.run(main())
    except ChannelLookupError as error:
        typer.echo(str(error))
        raise typer.Exit(1) from None
    except KeyboardInterrupt:
        pass
    finally:
        store.close()
    if collector is not None:
        typer.echo(f"Stopped. {_summary(collector.stats)}")


@app.command()
def languages(slug: str) -> None:
    """Show which languages a channel's saved chat is in."""
    ids, pipeline, _ = _read_saved_chat(Settings(), slug)
    mix = pipeline.mix
    if mix.total == 0:
        typer.echo(f"Not enough saved chat for {ids.slug} yet ({mix.unknown} messages).")
        return
    shares = ", ".join(f"{lang} {share:.0%}" for lang, share in mix.shares().items())
    typer.echo(f"{ids.slug}: {mix.total + mix.unknown} messages. Languages: {shares}.")
    typer.echo(f"{mix.unknown} messages were too short to tell.")
    main = mix.dominant()
    typer.echo(f"Main language: {main}" if main else "No main language yet.")


@app.command()
def profile(slug: str) -> None:
    """Learn how a channel's chat talks from its saved chat, and show it."""
    config = Settings()
    ids, _, builder = _read_saved_chat(config, slug)
    learned = builder.build(utc_now())
    path = config.profiles_dir / f"{ids.slug}.json"
    learned.save(path)
    style = learned.style

    def terms(items: list[ScoredTerm], limit: int = 15) -> str:
        return ", ".join(t.term for t in items[:limit]) or "(not enough chat yet)"

    typer.echo(f"{ids.slug}: learned from {learned.messages} messages.")
    typer.echo(f"Main language: {learned.main_language or 'not clear yet'}")
    typer.echo(f"Their words: {terms(learned.words)}")
    typer.echo(f"Their phrases: {terms(learned.phrases, 10)}")
    typer.echo(f"How they address people: {terms(learned.address_terms, 8)}")
    emotes = ", ".join(name for name, _ in style.top_emotes[:10]) or "(none yet)"
    typer.echo(f"Favorite emotes: {emotes}")
    typer.echo(
        f"Style: about {style.median_words:g} words per message, "
        f"{style.caps_share:.0%} in caps, {style.emote_share:.0%} with emotes, "
        f"{style.emoji_share:.0%} with emoji, {style.question_share:.0%} questions."
    )
    typer.echo(f"Saved to {path}")


@app.command()
def start(  # noqa: PLR0913, PLR0917 - one parameter per CLI option
    slug: str,
    bot: Annotated[str | None, typer.Option(help="Which saved bot to use.")] = None,
    idle_minutes: Annotated[
        int | None, typer.Option(min=2, help="Stop after this many minutes without input.")
    ] = None,
    chatroom_id: ChatroomIdOption = None,
    channel_id: ChannelIdOption = None,
    quiet: QuietOption = False,
) -> None:
    """Start a session in a channel. It stops by itself when you stop answering."""
    config = Settings()
    account = _pick_bot(config, bot)
    if KeyringTokenStore().load(account.token_key) is None:
        typer.echo(f"No saved login for {account.name}. Run: kick-commenter bots add")
        raise typer.Exit(1)
    timeout = timedelta(minutes=idle_minutes or config.idle_timeout_minutes)
    warning = min(timedelta(minutes=config.idle_warning_minutes), timeout / 2)
    store = ChatStore(config.chat_db)
    collector: Collector | None = None

    async def main(channel: str) -> StopReason:
        nonlocal collector
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as http:
            ids = await _resolve_channel(config, http, channel, chatroom_id, channel_id)
            collector = _collector(config, http, ids, store, quiet=quiet)
            stats = collector.stats
            session = Session(
                collector.run,
                IdleTimer(timeout=timeout, warning=warning, last_input=utc_now()),
                clock=utc_now,
                say=typer.echo,
                status=lambda: f"Listening in {ids.slug} as {account.name}. {_summary(stats)}",
            )
            typer.echo(
                f"Session started in {ids.slug} as {account.name}. "
                "Dry run: nothing is posted yet.\n"
                f"It stops after {minutes(timeout)} min without input. {HELP_TEXT}"
            )
            return await session.run(typed_lines())

    channel = slug.removeprefix("@").lower()
    lock = ChannelLock(
        config.locks_dir,
        channel,
        LockInfo(pid=os.getpid(), bot=account.name, started_at=utc_now()),
    )
    try:
        with lock:
            asyncio.run(main(channel))
    except (ChannelBusyError, ChannelLookupError) as error:
        typer.echo(str(error))
        raise typer.Exit(1) from None
    except KeyboardInterrupt:
        pass
    finally:
        store.close()
    if collector is not None:
        typer.echo(f"Session ended. {_summary(collector.stats)}")


@app.command()
def warmup(slug: str) -> None:
    """Show whether the bot has listened to a channel long enough to join in."""
    config = Settings()
    ids = read_cache(config.channels_file).get(slug.removeprefix("@").lower())
    if ids is None:
        typer.echo(f"No saved chat for {slug}. Collect some first: kick-commenter collect {slug}")
        raise typer.Exit(1)
    pipeline = TextPipeline(LinguaGuesser())
    tracker = WarmupTracker()
    store = ChatStore(config.chat_db)
    try:
        for message in store.messages(ids.channel_id):
            tracker.observe(pipeline.process(message))
    finally:
        store.close()
    status, policy = tracker.status(), tracker.policy
    listened = int(status.listening_seconds // 60)
    typer.echo(
        f"{ids.slug}: {status.messages}/{policy.min_messages} messages, "
        f"{listened}/{int(policy.min_listening.total_seconds() // 60)} min listened, "
        f"{status.stable_windows}/{policy.stable_windows} calm stretches in a row."
    )
    if status.converged:
        typer.echo("Warm-up done: the profile has settled, so the bot is ready to join in.")
    else:
        typer.echo("Still warming up. Keep collecting during streams; progress adds up.")


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


def _read_saved_chat(
    config: Settings, slug: str
) -> tuple[ChannelIds, TextPipeline, ProfileBuilder]:
    ids = read_cache(config.channels_file).get(slug.removeprefix("@").lower())
    if ids is None:
        typer.echo(f"No saved chat for {slug}. Collect some first: kick-commenter collect {slug}")
        raise typer.Exit(1)
    pipeline = TextPipeline(LinguaGuesser())
    builder = ProfileBuilder(ids.slug, pipeline.mix)
    store = ChatStore(config.chat_db)
    try:
        for message in store.messages(ids.channel_id):
            builder.add(pipeline.process(message))
    finally:
        store.close()
    return ids, pipeline, builder


def _pick_bot(config: Settings, name: str | None) -> BotAccount:
    registry = BotRegistry(config.bots_file)
    if name is not None:
        try:
            return registry.get(name)
        except KeyError:
            typer.echo(f"No bot named {name!r}. See: kick-commenter bots list")
            raise typer.Exit(1) from None
    bots = registry.all()
    if len(bots) == 1:
        return bots[0]
    if not bots:
        typer.echo("No bots yet. Add one with: kick-commenter bots add")
    else:
        names = ", ".join(b.name for b in bots)
        typer.echo(f"Pick a bot with --bot. Saved bots: {names}")
    raise typer.Exit(1)


async def _resolve_channel(
    config: Settings,
    http: httpx.AsyncClient,
    slug: str,
    chatroom_id: int | None,
    channel_id: int | None,
) -> ChannelIds:
    lookup = ChannelLookup(http, config.channels_file)
    if chatroom_id is None or channel_id is None:
        return await lookup.resolve(slug)
    ids = ChannelIds(
        slug=slug.removeprefix("@").lower(), channel_id=channel_id, chatroom_id=chatroom_id
    )
    lookup.remember(ids)
    return ids


def _collector(
    config: Settings, http: httpx.AsyncClient, ids: ChannelIds, store: ChatStore, *, quiet: bool
) -> Collector:
    def show(message: ChatMessage) -> None:
        typer.echo(f"{message.sender.username}: {message.text}")

    async def endpoint() -> str:
        if config.pusher_app_key:
            return PusherApp(app_key=config.pusher_app_key, cluster=config.pusher_cluster).url
        return (await RealtimeConfig(http).pusher_app(ids.channel_id)).url

    return Collector(
        PusherChatSource(ids.chatroom_id, ids.channel_id, endpoint=endpoint),
        store,
        on_message=None if quiet else show,
    )


def _summary(stats: CollectorStats) -> str:
    return (
        f"Saved {stats.messages} messages and {stats.events} events "
        f"({stats.reconnects} reconnects)."
    )


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
