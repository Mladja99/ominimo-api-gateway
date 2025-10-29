"""
Routing engine for determining which model should handle each request.

This module implements different routing strategies including feature-based
routing and A/B testing.
"""

import hashlib
from bisect import bisect
from datetime import date
from pathlib import Path
from typing import Any, Dict

import yaml


class RouterEngine:
    """
    Main routing engine that selects appropriate model based on configured rules.

    Attributes:
        config: Dictionary containing routing configuration from YAML file
    """

    def __init__(self, config_path: str):
        """
        Initialize router with configuration from YAML file.

        Args:
            config_path: Path to the models.yaml configuration file
        """

        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """
        Load configuration from YAML file.
        """

        config_file = Path(self.config_path)

        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        with open(config_file, "r") as f:
            return yaml.safe_load(f)

    def reload_config(self) -> None:
        """Reload configuration from file (useful for live updates)."""
        self.config = self._load_config()

    def route_request(self, payload: Dict[str, Any]) -> str:
        """
        Determine which model should handle the request.

        Args:
            payload: Dictionary containing request data (birthdate, car info, etc.)

        Returns:
            Model ID (e.g., "model-a") to route the request to

        Raises:
            ValueError: If routing rule is invalid or no models are available
        """

        routing_rule = (
            self.config.get("routing_rules", {}).get("default") or "birthdate_even_odd"
        )

        # Apply the configured routing strategy
        if routing_rule == "birthdate_even_odd":
            return self._route_by_birthdate(payload)

        if routing_rule == "postal_code_region":
            return self._route_by_postal_code(payload)

        if routing_rule == "ab_testing_percentage":
            return self._route_by_ab_testing(payload)

        # Fallback to first available model
        return self._get_default_model()

    def _route_by_birthdate(self, payload: Dict[str, Any]) -> str:
        """
        Route based on even/odd day of birth.

        Rule: Even day -> Model A, Odd day -> Model B
        """

        birthdate_str = payload.get("birthdate")

        if isinstance(birthdate_str, str):
            birthdate = date.fromisoformat(birthdate_str)
        else:
            birthdate = birthdate_str

        if birthdate.day % 2 == 0:
            return "model-a"
        else:
            return "model-b"

    def _route_by_postal_code(self, payload: Dict[str, Any]) -> str:
        """
        Route based on postal code region.

        Rule:
        - Postal codes starting with 1-3 -> Model A (North)
        - Postal codes starting with 4-6 -> Model B (Central)
        - Postal codes starting with 7-9 -> Model C (South)
        """

        postal_code = payload.get("postal_code", "")

        # Extract numeric part
        numeric_part = "".join(filter(str.isdigit, postal_code))

        if not numeric_part:
            return self._get_default_model()

        first_digit = int(numeric_part[0])

        if first_digit <= 3:
            return "model-a"
        elif first_digit <= 6:
            return "model-b"
        else:
            return "model-c"

    def _route_by_ab_testing(self, payload: Dict[str, Any]) -> str:
        """
        Deterministic A/B routing with sticky assignment.
        Uses either:
            - ab_testing.distributions: { "model-a": 0.5, "model-b": 0.5 }
                (direct model weights), or
            - ab_testing.variants: { "A": {"target":"model-a","weight":0.5}, ... }
                (variant indirection)
        """

        ab_cfg = self.config.get("ab_testing") or {}
        if not ab_cfg.get("enabled", False):
            return self._get_default_model()

        # Determine unit id for stickiness
        unit_field = ab_cfg.get("unit_field", "postal_code")
        unit_id = str(payload.get(unit_field, "anonymous"))
        experiment_id = ab_cfg.get("experiment_id", "api_routing_default")

        # Build a CDF for weighted pick
        if "variants" in ab_cfg:
            items = [
                (v["target"], float(v.get("weight", 0)))
                for v in ab_cfg["variants"].values()
            ]
        else:
            distributions = ab_cfg.get("distributions") or {}
            items = [(model, float(w)) for model, w in distributions.items()]

        # Normalize and guard against empty/zero weights
        total = sum(w for _, w in items)
        if total <= 0 or not items:
            return self._get_default_model()
        items = [(m, w / total) for m, w in items]

        # Deterministic bucket in [0,1)
        h = hashlib.sha256(f"{experiment_id}:{unit_id}".encode()).hexdigest()
        r = int(h[:15], 16) / float(16**15)

        # CDF pick
        cdf, labels = [], []
        acc = 0.0
        for label, w in items:
            acc += w
            cdf.append(acc)
            labels.append(label)
        idx = bisect(cdf, r)
        choice = labels[idx] if idx < len(labels) else labels[-1]

        # Extra sanity: if chosen model disabled/missing → fallback
        if choice not in self.config.get("models", {}):
            return self._get_default_model()
        if not self.is_model_enabled(choice):
            return self._get_default_model()
        return choice

    def _get_default_model(self) -> str:
        """Get the first enabled model as default fallback."""

        for model_id, config in (self.config.get("models") or {}).items():
            if config.get("enabled", True):
                return model_id

        raise ValueError("No enabled models found in configuration")

    def get_model_config(self, model_id: str) -> Dict[str, Any]:
        """
        Get configuration for a specific model.

        Args:
            model_id: ID of the model (e.g., "model-a")

        Returns:
            Dictionary containing model configuration

        Raises:
            KeyError: If model ID is not found in configuration
        """

        if model_id not in (self.config.get("models") or {}):
            raise KeyError(f"Model '{model_id}' not found in configuration")

        return self.config["models"][model_id]

    def is_model_enabled(self, model_id: str) -> bool:
        """Check if a model is enabled in the configuration."""

        try:
            config = self.get_model_config(model_id)
            return config.get("enabled", True)
        except KeyError:
            return False

    def get_all_models(self) -> Dict[str, Dict[str, Any]]:
        """Get configuration for all models."""

        return self.config.get("models", {})

    def get_routing_rule(self) -> str:
        """Get the currently active routing rule."""

        return (self.config.get("routing_rules", {}) or {}).get(
            "default", "birthdate_even_odd"
        )
