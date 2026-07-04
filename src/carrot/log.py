import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

logging.basicConfig(
    level=logging.CRITICAL,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    filename=PROJECT_ROOT / "log.log",
    filemode="w",
)
logging.getLogger("carrot").setLevel(logging.DEBUG)


logger = logging.getLogger("carrot")
