import logging
import time

from app.config.settings import get_settings
from app.core.logging import setup_logging

logger = logging.getLogger("brokerbridge.worker")


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("worker_started env=%s", settings.app_env)
    while True:
        logger.info("worker_heartbeat")
        time.sleep(30)


if __name__ == "__main__":
    main()
