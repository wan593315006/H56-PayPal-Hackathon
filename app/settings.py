"""Process settings: package root, kernel location, output directories, credentials.

Kept dependency-free on purpose. Two rules govern this module, because both were violated
by an earlier version and both are cheap to enforce once and for all:

* a path this module returns is always inside `runs/`, and it is created exclusively —
  a second attempt for the same stamp fails instead of silently reusing the directory and
  mixing two runs' evidence;
* only the keys named below may enter the environment from a file. Anything else is an
  error, not something to load quietly.
"""
import datetime
import os
import re
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
# Every key a .env file may define. The list is closed: an unknown key is refused rather
# than injected, so a typo cannot become a silently-ignored setting or a smuggle channel.
ALLOWED_ENV_KEYS = CREDENTIAL_KEYS + ("PAYPAL_ENVIRONMENT",)
ENV_FILE_MAX_BYTES = 65536

# Variables a child interpreter needs in order to start on Windows, and nothing else.
# Deliberately an allowlist: an inherited environment is how a credential reaches a
# subprocess that never asked for one.
CHILD_ENV_KEYS = ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH")

_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}")
_STAMP = re.compile(r"[0-9]{8}T[0-9]{6}Z")


class SettingsError(RuntimeError):
    """Base class: every refusal here is a configuration error, not a runtime accident."""


class MissingCredentials(SettingsError):
    def __init__(self, names):
        self.names = tuple(names)
        super().__init__("missing credentials: " + ", ".join(self.names))


class EnvFileError(SettingsError):
    def __init__(self, code, detail=""):
        self.code = code
        super().__init__(code + (": " + str(detail) if detail else ""))


class RunPathError(SettingsError):
    def __init__(self, code, detail=""):
        self.code = code
        super().__init__(code + (": " + str(detail) if detail else ""))


def utc_stamp(moment=None):
    """The only accepted shape of a run stamp: 20261103T021741Z."""
    return (moment or datetime.datetime.utcnow()).strftime("%Y%m%dT%H%M%SZ")


def read_env_file(path=None):
    """Parse and validate a .env file. Pure: the process environment is not touched.

    Refusals are explicit for all three cases that used to slip through: a key outside
    ALLOWED_ENV_KEYS, a key defined twice, and a line that is neither blank, a comment nor
    KEY=VALUE. Returns an ordered mapping of validated values.
    """
    path = Path(path) if path is not None else ENV_FILE
    if not path.is_file():
        return {}
    size = path.stat().st_size
    if size > ENV_FILE_MAX_BYTES:
        raise EnvFileError("ENV_FILE_TOO_LARGE", size)
    values = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise EnvFileError("ENV_LINE_MALFORMED", "line %d" % number)
        key, _, value = line.partition("=")
        key = key.strip()
        if key not in ALLOWED_ENV_KEYS:
            raise EnvFileError("ENV_KEY_NOT_ALLOWED", key or "line %d" % number)
        if key in values:
            raise EnvFileError("ENV_KEY_DUPLICATED", key)
        values[key] = value.strip().strip('"').strip("'")
    return values


def apply_env_file(path=None):
    """Validate a .env file, then set only its allowed keys.

    Existing environment variables still win: a shell export is a deliberate act and must
    not be silently overridden by a file. Returns the validated mapping.
    """
    values = read_env_file(path)
    for key, value in values.items():
        assert key in ALLOWED_ENV_KEYS
        os.environ.setdefault(key, value)
    return values


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


def subprocess_environment():
    """The minimal environment for a child interpreter: allowlist, no credentials.

    `-E` stops Python from reading its own environment configuration; it does not remove
    PAYPAL_CLIENT_ID from the process environment. That is this function's job.
    """
    environment = {key: os.environ[key] for key in CHILD_ENV_KEYS if os.environ.get(key)}
    environment["PYTHONIOENCODING"] = "utf-8"
    leaked = sorted(set(environment) & set(ALLOWED_ENV_KEYS))
    if leaked:
        raise SettingsError("CHILD_ENV_WOULD_LEAK", ", ".join(leaked))
    return environment


def _stamp(value):
    if type(value) is not str or not _STAMP.fullmatch(value):
        raise RunPathError("STAMP_INVALID", value)
    return value


def _label(value, what):
    if type(value) is not str or not _LABEL.fullmatch(value):
        raise RunPathError(what + "_INVALID", value)
    return value


def _inside_runs(directory):
    """Belt and braces: the joined path must sit directly under `runs/`."""
    root = RUNS_ROOT.absolute()
    candidate = directory.absolute()
    if candidate.parent != root:
        raise RunPathError("RUN_PATH_ESCAPES_RUNS", str(directory))
    return candidate


def run_directory(stamp, business):
    """Create and return `runs/<stamp>_<business>` exclusively.

    Both components are validated against a closed shape, so neither can carry a
    separator, a drive, a dot segment or a trailing dot. Creation never reuses an existing
    directory: two runs that share a stamp would otherwise share their evidence.
    """
    name = "%s_%s" % (_stamp(stamp), _label(business, "BUSINESS"))
    directory = _inside_runs(RUNS_ROOT / name)
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        directory.mkdir(parents=False, exist_ok=False)
    except FileExistsError:
        raise RunPathError("RUN_DIRECTORY_ALREADY_EXISTS", name) from None
    return directory


def existing_run_directory(stamp, business):
    """Return an existing run directory without creating anything.

    Recovery reads the evidence a previous run left behind; it must never manufacture a
    fresh, empty directory that looks like that run.
    """
    name = "%s_%s" % (_stamp(stamp), _label(business, "BUSINESS"))
    directory = _inside_runs(RUNS_ROOT / name)
    if not directory.is_dir():
        raise RunPathError("RUN_DIRECTORY_MISSING", name)
    return directory
