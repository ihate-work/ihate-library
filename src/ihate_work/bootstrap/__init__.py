import logging
import os
from datetime import datetime

import dotenv as _dotenv

_dotenv.load_dotenv(override=False)
_log_format = "%(asctime)s %(levelname)s %(threadName)s %(name)s - %(funcName)s: %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=_log_format,
    # datefmt="%Y-%m-%d %H:%M:%S",
)

if IHATE_LOG_DIR := os.environ.get("IHATE_LOG_DIR"):
    if os.path.exists(IHATE_LOG_DIR):
        now = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        pid = os.getpid()
        log_filename = os.path.join(IHATE_LOG_DIR, f"{now}-{pid}.log")
        logging.getLogger().info(f"Logging to {log_filename}")
        file_handler = logging.FileHandler(log_filename)
        file_handler.setFormatter(logging.Formatter(_log_format))
        logging.getLogger().handlers.append(file_handler)

logger = logging.getLogger(__name__)

for info_only in ("httpcore",):
    logging.getLogger(info_only).setLevel(logging.INFO)

for warn_only in ("httpx", "elastic_transport.transport", "LiteLLM"):
    logging.getLogger(warn_only).setLevel(logging.WARN)

# expectation:
# local code should be installed as --editable to make its real path stable
try:
    from ihate_work.llm.litellm import setup_langfuse_otel, setup_litellm_logging

    setup_litellm_logging()
    setup_langfuse_otel()
except ImportError:
    pass

# expectation:
# local code should be installed as --editable to make its real path stable
logger.info("ihate.work.bootstrap done.")
