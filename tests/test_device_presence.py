from datetime import datetime, timedelta, timezone

import pytest

from src.main.core.devicePresence import device_is_connected


@pytest.mark.parametrize("age,expected", [(None, False), (-1, False), (0, True), (129, True), (131, False)])
def test_presence_requires_recent_telemetry(age, expected):
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    last = None if age is None else now - timedelta(seconds=age)
    assert device_is_connected(last, now) is expected


def test_database_naive_timestamp_is_utc():
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    assert device_is_connected(now.replace(tzinfo=None), now)
    assert not device_is_connected(now - timedelta(seconds=11), now, timeout_seconds=10)
