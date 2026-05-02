import base64
import os

import ihate_work.o11y as o11y

logger, *_ = o11y.get_o11y(__name__)


def setup_langfuse_otel(validate=False):
    LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
    LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
    LANGFUSE_HOST = os.getenv("LANGFUSE_HOST")
    if LANGFUSE_SECRET_KEY and LANGFUSE_PUBLIC_KEY and LANGFUSE_HOST:
        LANGFUSE_AUTH = base64.b64encode(
            f"{os.environ.get('LANGFUSE_PUBLIC_KEY')}:{os.environ.get('LANGFUSE_SECRET_KEY')}".encode()
        ).decode()
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = LANGFUSE_HOST + "/api/public/otel"
        os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization=Basic {LANGFUSE_AUTH}"
        # Verify connection
        if validate:
            from langfuse import get_client

            langfuse_client = get_client()
            if langfuse_client.auth_check():
                logger.info("Langfuse client is authenticated and ready!")
            else:
                logger.warning("Authentication failed. Please check your credentials and host.")
        else:
            logger.info("Langfuse client check skipped.")
    else:
        logger.info("Langfuse credentials not set. Skipping setup.")
