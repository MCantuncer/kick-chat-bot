# Fixtures

Chat samples used by regression and integration tests. Every sample is anonymized: usernames, user ids, message ids and channel ids are made up before a sample is committed.

- `pusher_frames.jsonl`: one public chat stream frame per line, covering chat messages, a reply, an emote, an empty message, a ping, a channel event, an unknown event and a duplicate.
