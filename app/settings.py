"""Process settings: package root, kernel location, output directories, credentials.

Kept dependency-free on purpose. The `.env` reader is short enough to read in one sitting,
which is cheaper than asking a reviewer to install a package before the code will start.
"""
import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).absolute().parent.parent
CORE_ROOT = PACKAGE_ROOT / "h56_core"
RUNS_ROOT = PACKAGE_ROOT / "runs"
RECORDS_ROOT = PACKAGE_ROOT / "records"
ENV_FILE = PACKAGE_ROOT / ".env"

# Identity constants. These are assertions about the shipped bytes, not configuration:
# changing one of them turns selfcheck into a no-op that always agrees with itself.
DECLARATION_PATH = "offline_qualification_v1/SOURCE_MANIFEST.json"
SOURCE_MANIFEST_SHA = "adeca462c152a7ee34c4bdee0f1f9b3833adab6b1aa5ae6e110d2ae58a42c6cb"
ASSET_MANIFEST_SHA = "a6c5461b9bf89f077d2e448c4019dec079555dd06dad0dabfed666efb428a825"
MEMBER_COUNT = 139
MEMBER_BYTES = 582506
TEST_MODULES = ("test_boundary", "test_core_chain", "test_evidence", "test_records")
CREDENTIAL_KEYS = ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET")


class MissingCredentials(RuntimeError):
    """Raised when real mode is requested without the credentials it needs."""

    def __init__(self, names):
        self.names = tuple(names)
        super().__init__("missing credentials: " + ", ".join(self.names))


def load_env_file(path=None):
    """Read KEY=VALUE lines from a .env file into the environment.

    Existing environment variables win: a shell export is a deliberate act by the operator
    and must not be silently overridden by a file. Returns the keys that were read.
    """
    path = Path(path) if path is not None else ENV_FILE
    if not path.is_file():
        return {}
    read = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        read[key] = value
        os.environ.setdefault(key, value)
    return read


def credential(name):
    """Return one credential value, or None. Never logged and never written by this package."""
    value = os.environ.get(name, "").strip()
    return value or None


def require_credentials(names=CREDENTIAL_KEYS):
    """Return the credential mapping, or raise with the missing key names only."""
    missing = [name for name in names if not credential(name)]
    if missing:
        raise MissingCredentials(missing)
    return {name: credential(name) for name in names}


def run_directory(stamp, business):
    """Create and return `runs/<stamp>_<business>`, the only place run output belongs."""
    safe = "".join(ch for ch in str(business) if ch.isalnum() or ch in "-_")[:32] or "run"
    directory = RUNS_ROOT / ("%s_%s" % (stamp, safe))
    directory.mkdir(parents=True, exist_ok=True)
    return directory
