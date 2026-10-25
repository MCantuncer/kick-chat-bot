# Fixtures

Chat samples used by regression and integration tests. Every sample is anonymized: usernames, user ids, message ids and channel ids are made up before a sample is committed.

- `pusher_frames.jsonl`: one public chat stream frame per line, covering chat messages, a reply, an emote, an empty message, a ping, a channel event, an unknown event and a duplicate.
- `messy_chat.txt`: one chat message per line, with shouting, emotes, emoji, fancy letters, stacked accents, links and punctuation-only messages.
- `community_chat.txt`: a made-up stream chat of 240 messages in a Turkish community's style, for profile tests.
