"""
Create logger instance.
"""

import logging
import os
from typing import Optional


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Function for creating logger instance.

    :arg name: Name of logger, default is pulled from __name__ variable.
    :return: Returns instanced logger
    """

    log_dir = os.getenv("LOG_DIR", "./logs")
    log_level = os.getenv("LOG_LEVEL", "INFO")

    os.makedirs(log_dir, exist_ok=True)

    filename = os.path.join(log_dir, "logs.log")

    logging.basicConfig(
        level=log_level,
        format="[%(asctime)s] %(name)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(filename=filename, mode="a"),
            logging.StreamHandler(),
        ],
    )

    return logging.getLogger(name if name is not None else __name__)
