from os import environ
from threading import Lock

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_setup_lock = Lock()
_setup_done = False


def setup_otel(fallback_to_console=False):
    """
    Setup otel providers for traces, metrics, and logs.
    Must only be called once.

    If OTEL_EXPORTER_OTLP_ENDPOINT is set, uses OTLP exporters.
    Otherwise, falls back to console exporters if fallback_to_console is True.
    """
    global _setup_done
    with _setup_lock:
        if _setup_done:
            raise RuntimeError("setup_otel() must only be called once")
        _setup_done = True

    use_otlp = bool(environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"))

    if use_otlp:
        _setup_otel_otlp()
    elif fallback_to_console:
        _setup_otel_console()


def _setup_otel_otlp():
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    # Traces
    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    # Metrics
    reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    metrics.set_meter_provider(MeterProvider(metric_readers=[reader]))

    # Logs
    logger_provider = LoggerProvider()
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    set_logger_provider(logger_provider)


def _setup_otel_console():
    from opentelemetry.sdk._logs.export import ConsoleLogExporter
    from opentelemetry.sdk.metrics.export import ConsoleMetricExporter
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter

    # Traces
    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)

    # Metrics
    reader = PeriodicExportingMetricReader(ConsoleMetricExporter())
    metrics.set_meter_provider(MeterProvider(metric_readers=[reader]))

    # Logs
    logger_provider = LoggerProvider()
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(ConsoleLogExporter())
    )
    set_logger_provider(logger_provider)
