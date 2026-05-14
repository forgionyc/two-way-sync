from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return current UTC time as a timezone-naive datetime.

    SQLAlchemy `DateTime` columns in this project are timezone-naive. Using
    `datetime.utcnow()` is deprecated in Python 3.12+; this helper preserves the
    same shape (naive UTC) while using the non-deprecated API.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
