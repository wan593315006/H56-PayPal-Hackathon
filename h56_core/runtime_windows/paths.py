"""One relocatable product; data and successor code are separate roots."""
from pathlib import Path

RUNTIME_ROOT = Path(__file__).absolute().parent
PRODUCT_ROOT = RUNTIME_ROOT.parent
COMPONENT_ROOT = PRODUCT_ROOT / 'runtime_binding_v1_20261024'
DATA_ROOT = COMPONENT_ROOT / 'engineering'
PRIVATE_ROOT = RUNTIME_ROOT / '.local'
