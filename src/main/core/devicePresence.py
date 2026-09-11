from datetime import datetime, timezone


def device_is_connected(last_ping, now=None, timeout_seconds=130):
    if last_ping is None:
        return False
    current = now or datetime.now(timezone.utc)
    if last_ping.tzinfo is None:
        last_ping = last_ping.replace(tzinfo=timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return 0 <= (current - last_ping).total_seconds() <= timeout_seconds
