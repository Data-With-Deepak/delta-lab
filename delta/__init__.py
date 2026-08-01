import os

from .client import DeltaClient, DeltaError

__all__ = ["DeltaClient", "DeltaError", "make_client"]


def _load_dotenv(path=".env"):
    """Tiny .env loader so we don't need an extra dependency."""
    if not os.path.exists(path):
        return
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def make_client():
    """Build a DeltaClient from .env / environment variables."""
    # Look for .env in the project root regardless of where the script runs.
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _load_dotenv(os.path.join(here, ".env"))
    return DeltaClient(
        api_key=os.environ.get("DELTA_API_KEY"),
        api_secret=os.environ.get("DELTA_API_SECRET"),
        env=os.environ.get("DELTA_ENV", "prod"),
    )
