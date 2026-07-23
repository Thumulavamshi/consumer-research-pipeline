"""Utils module.

Shared helpers (config loading, logging setup) and path defaults used
across pipeline modules, so each stage doesn't redefine its own copy.
"""

import logging
from pathlib import Path
from typing import Any, Dict

import yaml
from rich.logging import RichHandler

DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_RAW_DIR = Path("data/raw")
DEFAULT_LOG_PATH = Path("logs/pipeline.log")


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """Load and parse the pipeline's YAML configuration file."""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def setup_logging(log_path: Path = DEFAULT_LOG_PATH) -> None:
    """Configure root logging to write to both the console (via rich) and a log file.

    Safe to call multiple times; only the first call installs handlers.
    """
    if logging.getLogger().handlers:
        return

    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    console_handler = RichHandler(show_path=False, markup=False)
    console_handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))

    logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
