from datetime import datetime, timezone


def utc_now_naive() -> datetime:
    """Hora actual en UTC sin tzinfo: misma convención que las columnas DateTime
    (timestamp without time zone) cuyo server_default=func.now() corre en UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_from_timestamp_naive(timestamp: float) -> datetime:
    """Convierte un epoch (p. ej. el claim ``exp`` de un JWT) a UTC naive."""
    return datetime.fromtimestamp(timestamp, timezone.utc).replace(tzinfo=None)
