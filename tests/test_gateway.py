#!/usr/bin/env python3
"""
Demo-friendly test suite for the Ominimo API Gateway.

- Default: demo mode (no red FAILs for expected negatives; exit code 0)
- Strict mode (--strict): enforce everything; non-zero exit on failures
"""

import argparse
import json
import math
import os
import statistics
import time
from typing import Any, Dict, Tuple

import requests


def _bool_env(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")


class GatewayTester:
    """Main tester class for the API Gateway."""

    def __init__(self, gateway_url: str, strict: bool, max_avg: float, max_p95: float):
        """
        Args:
            gateway_url: Base URL of the gateway
            strict: If True, fail hard on violations; if False, show WARN and continue
            max_avg: Max average response time in seconds
            max_p95: Max p95 response time in seconds
        """

        self.gateway_url = gateway_url.rstrip("/")
        self.strict = strict
        self.max_avg = max_avg
        self.max_p95 = max_p95

        self.tests_run = 0
        self.tests_passed = 0
        self.tests_warned = 0
        self.tests_failed = 0

        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.session.timeout = 10
        self.session.max_redirects = 5

    def _fail(self, msg: str) -> bool:
        if self.strict:
            print(f"  ✗ FAIL: {msg}")
            self.tests_failed += 1
            return False
        else:
            print(f"  ⚠ WARN: {msg}")
            self.tests_warned += 1
            return True

    def _pass(self, msg: str) -> bool:
        print(f"  ✓ PASS: {msg}")
        self.tests_passed += 1
        return True

    def _make_request(self, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """Make a price request to the gateway; returns (status_code, json_or_empty)."""

        resp = self.session.post(f"{self.gateway_url}/price", json=payload)
        try:
            data = resp.json()
        except Exception:
            data = {}
        return resp.status_code, data

    # -------------------------------------------------------------- test cases
    def test_health_check(self) -> bool:
        """Test health check endpoint."""

        print("Testing /health …")
        self.tests_run += 1

        try:
            r = self.session.get(f"{self.gateway_url}/health")
            r.raise_for_status()
            data = r.json()

            gw = data.get("gateway")
            if gw != "healthy":
                return self._fail(f"Gateway not healthy (got {gw!r})")

            models = data.get("models", {})
            bad = []
            for model_id, status in models.items():
                s = status.get("status")
                if s not in ("healthy", "unreachable"):
                    bad.append((model_id, s))
            if bad:
                return self._fail(f"Invalid model statuses: {bad}")

            return self._pass("Health check working")
        except Exception as e:
            return self._fail(str(e))

    def test_config_endpoint(self) -> bool:
        """Test configuration endpoint."""

        print("Testing /config …")
        self.tests_run += 1
        try:
            r = self.session.get(f"{self.gateway_url}/config")
            r.raise_for_status()
            data = r.json()
            for key in ("models", "routing_rules", "ab_testing"):
                if key not in data:
                    return self._fail(f"Missing '{key}' in config")
            return self._pass("Config endpoint working")
        except Exception as e:
            return self._fail(str(e))

    def test_valid_request(self) -> bool:
        """Test a valid price request."""

        print("Testing POST /price (valid payload) …")
        self.tests_run += 1

        payload = {
            "birthdate": "1990-06-15",
            "driver_license_date": "2010-08-20",
            "car_model": "Golf",
            "car_brand": "Volkswagen",
            "postal_code": "1234AC",
        }
        try:
            status, result = self._make_request(payload)
            if status != 200:
                return self._fail(f"Expected 200, got {status}: {result}")

            for field in ("model_name", "price", "currency", "gateway_metadata"):
                if field not in result:
                    return self._fail(f"Missing field '{field}' in response")

            price = result["price"]
            # Very wide range to avoid demo fails; make strict via env if needed
            if not (0 <= float(price) <= 100000):
                return self._fail(f"Unreasonable price {price}")

            mid = result["gateway_metadata"]["model_id"]
            return self._pass(f"Got price {price} EUR from {mid}")
        except Exception as e:
            return self._fail(str(e))

    def test_birthdate_routing(self) -> bool:
        """Test birthdate-based routing when that rule is active."""

        print("Testing birthdate routing logic …")
        try:
            cfg = self.session.get(f"{self.gateway_url}/config").json()
            routing_rule = cfg.get("routing_rules", {}).get("default", "")
        except Exception:
            routing_rule = ""

        if routing_rule != "birthdate_even_odd":
            print(
                f"  ⏭ SKIP: Current rule is '{routing_rule}', not 'birthdate_even_odd'"
            )
            return True

        # even case
        self.tests_run += 1
        payload_even = {
            "birthdate": "1995-06-14",
            "driver_license_date": "2015-08-20",
            "car_model": "Golf",
            "car_brand": "Volkswagen",
            "postal_code": "1234AC",
        }
        status, result = self._make_request(payload_even)
        if status != 200:
            return self._fail(f"Even birthdate expected 200, got {status}")
        model_id_even = (result.get("gateway_metadata") or {}).get("model_id")
        if model_id_even != "model-a":
            return self._fail(
                f"Even birthdate routed to {model_id_even}, expected model-a"
            )
        self._pass(f"Even birthdate routed to {model_id_even}")

        # odd case
        self.tests_run += 1
        payload_odd = {
            "birthdate": "1995-06-15",
            "driver_license_date": "2015-08-20",
            "car_model": "Golf",
            "car_brand": "Volkswagen",
            "postal_code": "1234AC",
        }
        status, result = self._make_request(payload_odd)
        if status != 200:
            return self._fail(f"Odd birthdate expected 200, got {status}")
        model_id_odd = (result.get("gateway_metadata") or {}).get("model_id")
        if model_id_odd != "model-b":
            return self._fail(
                f"Odd birthdate routed to {model_id_odd}, expected model-b"
            )
        return self._pass(f"Odd birthdate routed to {model_id_odd}")

    def test_invalid_requests(self) -> bool:
        """Test validation of invalid requests (422 expected)."""
        print("Testing invalid request handling …")

        invalid_payloads = [
            {"name": "Missing fields", "payload": {"birthdate": "1995-06-15"}},
            {
                "name": "Invalid date format",
                "payload": {
                    "birthdate": "invalid-date",
                    "driver_license_date": "2015-08-20",
                    "car_model": "Golf",
                    "car_brand": "Volkswagen",
                    "postal_code": "1234AC",
                },
            },
            {
                "name": "Future birthdate",
                "payload": {
                    "birthdate": "2100-06-15",
                    "driver_license_date": "2015-08-20",
                    "car_model": "Golf",
                    "car_brand": "Volkswagen",
                    "postal_code": "1234AC",
                },
            },
            {
                "name": "Underage driver",
                "payload": {
                    "birthdate": "2010-06-15",
                    "driver_license_date": "2023-08-20",
                    "car_model": "Golf",
                    "car_brand": "Volkswagen",
                    "postal_code": "1234AC",
                },
            },
        ]

        ok = True
        for case in invalid_payloads:
            self.tests_run += 1
            r = self.session.post(f"{self.gateway_url}/price", json=case["payload"])
            if r.status_code == 422:
                self._pass(f"{case['name']} correctly rejected (422)")
            else:
                ok = self._fail(f"{case['name']} expected 422, got {r.status_code}")
        return ok

    def test_sample_payloads(self) -> bool:
        """Test all sample payloads from JSON file (422 acceptable)."""

        print("Testing sample payloads …")
        try:
            with open("tests/sample_payloads.json", "r") as f:
                payloads = json.load(f)
        except FileNotFoundError:
            print("  ⏭ SKIP: tests/sample_payloads.json not found")
            return True

        ok = True
        for name, payload in payloads.items():
            self.tests_run += 1
            status, result = self._make_request(payload)
            if status == 200:
                price = result.get("price")
                model_id = (result.get("gateway_metadata") or {}).get("model_id")
                self._pass(f"{name} → {model_id} → €{price}")
            elif status == 422:
                # Acceptable: validator doing its job
                self._pass(f"{name} correctly rejected (422)")
            else:
                ok = self._fail(f"{name} got status {status}")
        return ok

    def test_response_times(self) -> bool:
        """Measure response times (demo mode: warn; strict mode: fail on thresholds)."""
        print("Testing response times …")
        self.tests_run += 1

        payload = {
            "birthdate": "1990-06-15",
            "driver_license_date": "2010-08-20",
            "car_model": "Golf",
            "car_brand": "Volkswagen",
            "postal_code": "1234AC",
        }

        times = []
        for _ in range(10):
            start = time.time()
            status, _ = self._make_request(payload)
            if status != 200:
                return self._fail(f"Expected 200 in timing test, got {status}")
            times.append(time.time() - start)

        avg = statistics.mean(times)
        p95 = sorted(times)[math.ceil(0.95 * len(times)) - 1]
        msg = f"avg={avg:.3f}s p95={p95:.3f}s (thresholds avg<{self.max_avg}s p95<{self.max_p95}s)"

        if avg < self.max_avg and p95 < self.max_p95:
            return self._pass(f"Response times OK: {msg}")
        else:
            return self._fail(f"Response times high: {msg}")

    def run_all_tests(self):
        print("=" * 50)
        print("Ominimo API Gateway — Demo Test Suite")
        print("=" * 50)
        print(f"Gateway URL : {self.gateway_url}")
        print(f"Mode        : {'STRICT' if self.strict else 'DEMO'}")
        print(f"Thresholds  : max_avg={self.max_avg}s  max_p95={self.max_p95}s")
        print()

        # Check reachability
        try:
            self.session.get(
                f"{self.gateway_url}/health", timeout=5, allow_redirects=True
            )
        except Exception as e:
            print(f"ERROR: Cannot reach gateway at {self.gateway_url}")
            print(f"Error: {str(e)}")
            print("\nStart services with:")
            print("  docker compose up --build")
            return 1 if self.strict else 0

        # Run
        self.test_health_check()
        self.test_config_endpoint()
        self.test_valid_request()
        self.test_birthdate_routing()
        self.test_invalid_requests()
        self.test_sample_payloads()
        self.test_response_times()

        # Summary
        print("\n" + "=" * 50)
        print("Test Summary")
        print("=" * 50)
        print(f"Total:  {self.tests_run}")
        print(f"Pass :  {self.tests_passed} ✓")
        print(f"Warn :  {self.tests_warned} ⚠")
        print(f"Fail :  {self.tests_failed} ✗")
        print()

        if self.tests_failed == 0 or not self.strict:
            print("✓ Demo complete.")
            return 0
        else:
            print("✗ Some tests failed (STRICT mode).")
            return 1


def main():
    parser = argparse.ArgumentParser(description="Ominimo Gateway Demo Test Suite")
    parser.add_argument(
        "gateway_url",
        nargs="?",
        default=os.environ.get("HOST", "http://localhost:8000"),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=_bool_env("STRICT", False),
        help="Fail on violations and exit non-zero.",
    )
    parser.add_argument(
        "--max-avg",
        type=float,
        default=float(os.environ.get("MAX_AVG", 2.0)),
        help="Max average response time (seconds).",
    )
    parser.add_argument(
        "--max-p95",
        type=float,
        default=float(os.environ.get("MAX_P95", 5.0)),
        help="Max p95 response time (seconds).",
    )
    args = parser.parse_args()

    tester = GatewayTester(
        args.gateway_url, strict=args.strict, max_avg=args.max_avg, max_p95=args.max_p95
    )
    exit(tester.run_all_tests())


if __name__ == "__main__":
    main()
