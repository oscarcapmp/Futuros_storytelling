from datetime import datetime, timezone
from zoneinfo import ZoneInfo


BOGOTA_TZ = ZoneInfo("America/Bogota")


def now_bogota_iso() -> str:
    """Return current time in Bogota timezone as ISO string."""
    return datetime.now(timezone.utc).astimezone(BOGOTA_TZ).isoformat()


def to_bogota_iso(dt_or_iso) -> str:
    """Convert datetime or ISO string to Bogota timezone ISO string."""
    if isinstance(dt_or_iso, str):
        dt_obj = datetime.fromisoformat(dt_or_iso)
    else:
        dt_obj = dt_or_iso

    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=timezone.utc)

    return dt_obj.astimezone(BOGOTA_TZ).isoformat()
