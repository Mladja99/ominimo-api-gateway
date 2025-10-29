"""
Observability module for logging, metrics, and monitoring.

This module handles all logging and tracking of requests, responses,
and system health.
"""

import logging
import time
from collections import Counter as LocalCounter
from pathlib import Path
from typing import Any, Dict, Optional

from prometheus_client import Counter, Histogram

from .logger import get_logger


class ObservabilityManager:
    """
    Manager for logging and metrics collection.

    Handles structured logging of requests, routing decisions, and errors.
    """

    def __init__(self, log_level: str = "INFO", log_dir: str = "/logs"):
        """
        Initialize observability manager.

        Args:
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
            log_dir: Directory to store log files
        """

        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Setup loggers
        self.gateway_logger = self._setup_logger("gateway", log_level)
        self.routing_logger = self._setup_logger("routing", log_level)
        self.metrics_logger = self._setup_logger("metrics", log_level)

        # --- Exposure/SRM state ---
        # exposure counts are kept per experiment+model (e.g., "exp:api...|model:model-a")
        self._exposures: LocalCounter[str] = LocalCounter()
        self._last_srm_log_ts: float = 0.0
        self._srm_log_interval_sec: int = 60  # throttle SRM logs
        self._expected_distribution: Optional[Dict[str, float]] = (
            None  # model_id -> weight in [0,1]
        )

        # --- Prometheus metrics ---
        # Per-model request/latency/error
        self._m_requests = Counter(
            "gateway_model_requests_total",
            "Total requests routed to a model",
            ["model"],
        )
        self._m_errors = Counter(
            "gateway_model_errors_total", "Total errors when calling a model", ["model"]
        )
        self._m_latency = Histogram(
            "gateway_model_latency_seconds", "Model call latency in seconds", ["model"]
        )
        # Exposures (A/B routing assignments)
        self._m_exposures = Counter(
            "gateway_exposures_total",
            "Experiment exposures by model",
            ["experiment", "model"],
        )

    def set_expected_distribution(self, expected: Dict[str, float]) -> None:
        """
        Set the expected model traffic proportions for SRM checks.

        Example:
            expected = {"model-a": 0.33, "model-b": 0.33, "model-c": 0.34}
        """

        total = sum(float(w) for w in expected.values())
        if total <= 0:
            # disable if invalid
            self._expected_distribution = None
            self.routing_logger.warning("SRM disabled: expected distribution sum <= 0")
            return
        # normalize to sum=1
        self._expected_distribution = {m: float(w) / total for m, w in expected.items()}
        self.routing_logger.info(
            f"SRM expected distribution set: {self._expected_distribution}"
        )

    def _setup_logger(self, name: str, level: str) -> logging.Logger:
        """
        Set up a logger with file and console handlers.
        """

        logger = get_logger(name)

        # Avoid duplicate handlers
        if logger.handlers:
            return logger

        # File handler
        file_handler = logging.FileHandler(self.log_dir / f"{name}.log")
        file_handler.setLevel(getattr(logging, level.upper()))

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, level.upper()))

        # Formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        return logger

    def log_request(
        self, request_id: str, payload: Dict[str, Any], client_ip: Optional[str] = None
    ) -> None:
        """
        Log incoming request.

        Args:
            request_id: Unique identifier for the request
            payload: Request payload
            client_ip: Client IP address
        """

        self.gateway_logger.info(
            f"Request {request_id} received from {client_ip or 'unknown'}: "
            f"birthdate={payload.get('birthdate')}, "
            f"car={payload.get('car_brand')} {payload.get('car_model')}"
        )

    def log_routing_decision(
        self, request_id: str, model_id: str, routing_rule: str, payload: Dict[str, Any]
    ) -> None:
        """
        Log routing decision.

        Args:
            request_id: Unique identifier for the request
            model_id: ID of selected model
            routing_rule: Routing rule that was applied
            payload: Request payload
        """

        self.routing_logger.info(
            f"Request {request_id} routed to {model_id} "
            f"using rule '{routing_rule}' "
            f"(postal_code={payload.get('postal_code')})"
        )

    def log_exposure(self, experiment_id: str, unit_id: str, model_id: str) -> None:
        """
        Log an exposure (user/request assigned to a model variant) and
        run a throttled SRM (sample ratio mismatch) check.

        Args:
            experiment_id: Experiment identifier (e.g., "api_routing_2025_10")
            unit_id: Sticky unit id used for bucketing (e.g., postal_code/user_id)
            model_id: Chosen model id (e.g., "model-a")
        """

        # Structured exposure line for later parsing
        self.metrics_logger.info(
            f"exposure experiment={experiment_id} unit={unit_id} model={model_id}"
        )

        # Count exposure for SRM aggregation
        key = f"exp:{experiment_id}|model:{model_id}"
        self._exposures[key] += 1

        # Periodically emit SRM diagnostics
        self._maybe_log_srm(experiment_id)

        # Prometheus counter (NEW)
        self.prom_record_exposure(experiment_id, model_id)

    def _maybe_log_srm(self, experiment_id: str) -> None:
        """
        Periodically compute a simple chi-square goodness-of-fit vs. expected distribution
        and log a warning if mismatch is statistically suspicious.

        Notes:
            - Requires self._expected_distribution to be set (model -> expected share).
            - Only logs if we have >= 50 exposures for the experiment (avoid noise).
            - df = k-1 (k = number of models present in counts ∩ expected)
              We warn at p < 0.05 approx thresholds.
        """

        if not self._expected_distribution:
            return

        now = time.time()
        if now - self._last_srm_log_ts < self._srm_log_interval_sec:
            return
        self._last_srm_log_ts = now

        # Aggregate counts for this experiment
        counts: Dict[str, int] = {}
        total = 0
        prefix = f"exp:{experiment_id}|model:"
        for key, c in self._exposures.items():
            if key.startswith(prefix):
                model = key.split("|model:")[1]
                counts[model] = counts.get(model, 0) + c
                total += c

        if total < 50:
            return  # wait for a bit more data

        # Restrict to models we have expectations for
        observed = {m: counts.get(m, 0) for m in self._expected_distribution.keys()}
        k = sum(1 for m in observed if self._expected_distribution.get(m, 0) > 0)
        if k < 2:
            return  # not meaningful

        # Chi-square statistic
        chi2 = 0.0
        for m, obs in observed.items():
            p = self._expected_distribution.get(m, 0.0)
            exp = total * p
            if exp > 0:
                chi2 += (obs - exp) ** 2 / exp

        # Rough threshold for p<0.05 by k (df = k-1)
        # k=2 -> 3.84; k=3 -> 5.99; k=4 -> 7.81 (approx)
        thresholds = {2: 3.84, 3: 5.99, 4: 7.81, 5: 9.49}
        df = max(1, k - 1)
        threshold = thresholds.get(
            k, 3.84 + 2.0 * (df - 1)
        )  # crude growth for larger k
        suspicious = chi2 > threshold

        self.routing_logger.info(
            f"SRM exp={experiment_id} total={total} counts={observed} "
            f"expected={self._expected_distribution} chi2={chi2:.2f} df={df} suspicious={suspicious}"
        )
        if suspicious:
            self.routing_logger.warning(
                f"SRM suspected for exp={experiment_id}: chi2={chi2:.2f} > {threshold:.2f}"
            )

    def log_model_response(
        self, request_id: str, model_id: str, price: float, processing_time: float
    ) -> None:
        """
        Log model response.

        Args:
            request_id: Unique identifier for the request
            model_id: ID of the model
            price: Calculated price
            processing_time: Processing time in seconds
        """

        self.gateway_logger.info(
            f"Request {request_id} completed by {model_id}: "
            f"price={price:.2f} EUR, time={processing_time:.3f}s"
        )

        # Also log to metrics
        self.metrics_logger.info(
            f"model={model_id}, price={price:.2f}, time_ms={processing_time * 1000:.2f}"
        )

    def log_error(
        self,
        request_id: str,
        error_type: str,
        error_message: str,
        model_id: Optional[str] = None,
    ) -> None:
        """
        Log error.

        Args:
            request_id: Unique identifier for the request
            error_type: Type of error
            error_message: Detailed error message
            model_id: ID of model if error occurred in model call
        """

        self.gateway_logger.error(
            f"Request {request_id} failed: {error_type} - {error_message} "
            f"(model={model_id or 'gateway'})"
        )

    def get_metrics_summary(self) -> Dict[str, Any]:
        """
        Get summary of collected metrics.

        This is a placeholder for future implementation of metrics aggregation.

        Returns:
            Dictionary containing metrics summary
        """

        return {
            "total_requests": "See logs for details",
            "requests_per_model": "See logs for details",
            "average_response_time": "See logs for details",
        }

    def prom_record_model_call(
        self, model_id: str, success: bool, latency_s: float
    ) -> None:
        """Record a single downstream model call into Prometheus."""

        self._m_requests.labels(model=model_id).inc()
        self._m_latency.labels(model=model_id).observe(latency_s)
        if not success:
            self._m_errors.labels(model=model_id).inc()

    def prom_record_exposure(self, experiment_id: str, model_id: str) -> None:
        """Increment exposure counter for SRM/traffic distribution."""

        self._m_exposures.labels(experiment=experiment_id, model=model_id).inc()


# Global observability manager instance
_observability_manager: Optional[ObservabilityManager] = None


def setup_observability(
    log_level: str = "INFO", log_dir: str = "./logs"
) -> ObservabilityManager:
    """
    Setup and return global observability manager.

    Args:
        log_level: Logging level
        log_dir: Directory for log files

    Returns:
        Observability manager instance
    """

    global _observability_manager
    if _observability_manager is None:
        _observability_manager = ObservabilityManager(log_level, log_dir)
    return _observability_manager


def get_observability() -> ObservabilityManager:
    """Get the global observability manager instance."""

    if _observability_manager is None:
        raise RuntimeError(
            "Observability not initialized. Call setup_observability() first."
        )
    return _observability_manager
