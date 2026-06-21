from datetime import datetime, timezone

LAST_SEEN_FILE = "last_seen.txt"

def save_last_seen():
    """Saves the current timestamp to the last_seen file."""
    with open(LAST_SEEN_FILE, "w") as f:
        f.write(datetime.now(timezone.utc).isoformat())

def get_last_seen() -> datetime | None:
    """Reads the last_seen timestamp from the file."""
    try:
        with open(LAST_SEEN_FILE, "r") as f:
            return datetime.fromisoformat(f.read().strip())
    except FileNotFoundError:
        return None
