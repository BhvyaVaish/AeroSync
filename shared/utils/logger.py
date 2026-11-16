"""
AeroSync Structured Logger

Provides a module-aware logger factory with structured output.
Log level is controlled by the LOG_LEVEL environment variable.

Usage:
    from shared.utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Server started", extra={"port": 8000})
"""

import logging
import logging.config
import os
import sys
from pathlib import Path

import yaml


_initialized = False


def _setup_logging() -> None:
    """
    Initialize logging from YAML config file.
    Falls back to basic config if YAML file is not found.
    """
    global _initialized
    if _initialized:
        return

    log_level = os.getenv("LOG_LEVEL", "DEBUG").upper()
    
    # Try to load YAML config
    config_paths = [
        Path(__file__).resolve().parent.parent.parent / "config" / "logging_config.yaml",
        Path.cwd() / "config" / "logging_config.yaml",
    ]
    
    config_loaded = False
    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    config = yaml.safe_load(f)
                
                # Override log level from environment
                if "loggers" in config and "aerosync" in config["loggers"]:
                    config["loggers"]["aerosync"]["level"] = log_level
                
                logging.config.dictConfig(config)
                config_loaded = True
                break
            except Exception:
                pass
    
    if not config_loaded:
        # Fallback to basic structured config
        logging.basicConfig(
            level=getattr(logging, log_level, logging.DEBUG),
            format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
            stream=sys.stdout,
        )
    
    _initialized = True


def setup_logging(level=None) -> None:
    """Public wrapper to initialize logging."""
    _setup_logging()
    if level is not None:
        if isinstance(level, int):
            level = logging.getLevelName(level)
        set_log_level(str(level))


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger for the given module.
    
    All loggers are children of the 'aerosync' root logger for
    consistent formatting and handler configuration.
    
    Args:
        name: The module name, typically __name__.
        
    Returns:
        logging.Logger: A configured logger instance.
    """
    _setup_logging()
    
    # Ensure all app loggers are under the 'aerosync' namespace
    if not name.startswith("aerosync"):
        logger_name = f"aerosync.{name}"
    else:
        logger_name = name
    
    return logging.getLogger(logger_name)


def set_log_level(level: str) -> None:
    """
    Dynamically change the log level at runtime.
    
    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    numeric_level = getattr(logging, level.upper(), logging.DEBUG)
    logger = logging.getLogger("aerosync")
    logger.setLevel(numeric_level)
    for handler in logger.handlers:
        handler.setLevel(numeric_level)
