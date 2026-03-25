from __future__ import annotations

import logging
from typing import Any

from schemas.common import ObservationContext


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_info(
    logger: logging.Logger,
    message: str,
    context: ObservationContext,
    **extra: Any,
) -> None:
    suffix = " ".join(f"{key}={value}" for key, value in {**context.as_log_fields(), **extra}.items())
    logger.info("%s | %s", message, suffix)
