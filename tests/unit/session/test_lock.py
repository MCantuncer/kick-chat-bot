import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from kick_commenter.session.lock import ChannelBusyError, ChannelLock, LockInfo

NOW = datetime(2026, 10, 25, tzinfo=UTC)


def info(pid: int, bot: str = "golfwangtr") -> LockInfo:
    return LockInfo(pid=pid, bot=bot, started_at=NOW)


def test_lock_is_held_while_inside_and_released_after(tmp_path: Path) -> None:
    lock = ChannelLock(tmp_path / "locks", "thetoxicparty", info(os.getpid()))

    with lock:
        assert lock.path.exists()
        assert LockInfo.model_validate_json(lock.path.read_text()).bot == "golfwangtr"

    assert not lock.path.exists()


def test_second_session_in_same_channel_is_refused(tmp_path: Path) -> None:
    running = ChannelLock(tmp_path, "thetoxicparty", info(os.getppid(), bot="first"))
    running.acquire()

    with pytest.raises(ChannelBusyError, match="bot first") as caught:
        ChannelLock(tmp_path, "thetoxicparty", info(os.getpid(), bot="second")).acquire()

    assert caught.value.holder.bot == "first"
    assert running.path.exists()


def test_other_channels_are_independent(tmp_path: Path) -> None:
    ChannelLock(tmp_path, "one", info(os.getppid())).acquire()

    ChannelLock(tmp_path, "two", info(os.getpid())).acquire()

    assert (tmp_path / "two.lock").exists()


def test_lock_left_by_a_crashed_session_is_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ChannelLock(tmp_path, "thetoxicparty", info(999_999, bot="crashed")).acquire()
    monkeypatch.setattr("psutil.pid_exists", lambda pid: pid != 999_999)

    lock = ChannelLock(tmp_path, "thetoxicparty", info(os.getpid(), bot="fresh"))
    lock.acquire()

    assert LockInfo.model_validate_json(lock.path.read_text()).bot == "fresh"


def test_unreadable_lock_file_is_treated_as_stale(tmp_path: Path) -> None:
    (tmp_path / "thetoxicparty.lock").write_text("not json")

    ChannelLock(tmp_path, "thetoxicparty", info(os.getpid())).acquire()

    assert LockInfo.model_validate_json((tmp_path / "thetoxicparty.lock").read_text())


def test_release_leaves_another_sessions_lock_alone(tmp_path: Path) -> None:
    ChannelLock(tmp_path, "thetoxicparty", info(os.getppid(), bot="other")).acquire()

    ChannelLock(tmp_path, "thetoxicparty", info(os.getpid())).release()

    assert (tmp_path / "thetoxicparty.lock").exists()
