<div align="center">

# kick-chat-bot

**A friendly chat companion for Kick streams that learns how each community talks.**

[![CI](https://github.com/MCantuncer/kick-chat-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/MCantuncer/kick-chat-bot/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://img.shields.io/badge/mypy-strict-2A6DB2)](https://mypy-lang.org/)
[![Tested with Hypothesis](https://img.shields.io/badge/hypothesis-tested-brightgreen)](https://hypothesis.works/)

</div>

---

## What it does

Every stream has its own culture: its nicknames, inside jokes, emotes and way of cheering. kick-chat-bot joins a channel's chat, listens first, and learns that culture. Once it gets the vibe, it joins in the way a regular would: reacting to the big plays, backing the streamer on a rough run, and using the chat's own words. It speaks rarely and never floods the chat.

## Highlights

- 👂 **Listens before it speaks.** Each new channel starts with a quiet learning phase.
- 🗣️ **Speaks the community's language.** It picks up the chat's language, slang and nicknames per channel.
- 🌱 **Keeps learning.** New jokes and phrases are picked up as the chat evolves.
- 🤏 **Low-key by design.** It speaks rarely and never floods the chat.
- 🛑 **Safe by default.** Built-in safety rules, an automatic pause and a kill switch.
- 💻 **Runs on your computer.** Start it when you want; it stops by itself when idle.
- 🔑 **No paid AI services.** Everything runs locally, so there are no API tokens to buy.

## How it works

```mermaid
flowchart LR
    A[Listen to chat] --> B[Learn the community's style]
    B --> C{Worth reacting?}
    C -- no --> A
    C -- yes --> D[Pick something that fits the moment]
    D --> E[Post it, politely paced]
    E --> A
```

## Getting started

> The project is in early development. Setup steps will be added here as features land.

Requirements: Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/MCantuncer/kick-chat-bot.git
cd kick-chat-bot
make install
uv run kick-commenter --help
```

## Development

```bash
make check    # lint, type check and tests
make format   # auto-format and fix lint issues
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for conventions.

## Status

🚧 Early development. Follow progress in the [issues](https://github.com/MCantuncer/kick-chat-bot/issues).
