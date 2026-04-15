import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = PROJECT_ROOT / "config"
LEGACY_RUNTIME_DIR = PROJECT_ROOT / "runtime"
LEGACY_STATE_DIR = LEGACY_RUNTIME_DIR / "state"
LEGACY_DB_PATH = LEGACY_STATE_DIR / "networking.db"

ARI_ROOT = Path(os.environ.get("ARI_HOME", str(Path.home() / "ARI"))).expanduser()
ARI_STATE_DIR = ARI_ROOT / "state"
LOGS_DIR = ARI_ROOT / "logs"
ARTIFACTS_DIR = ARI_ROOT / "artifacts"
MODULES_DIR = ARI_ROOT / "modules"
NETWORKING_MODULE_DIR = MODULES_DIR / "networking-crm"
STATE_DIR = NETWORKING_MODULE_DIR / "state"
DB_PATH = STATE_DIR / "networking.db"
SCHEMA_PATH = CONFIG_DIR / "schema.sql"


def ari_path(*parts: str) -> Path:
    return ARI_ROOT.joinpath(*parts)
