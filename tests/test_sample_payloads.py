import json
import os

import httpx
import pytest

HOST = os.environ.get("HOST", "http://localhost:8000")
SAMPLES_PATH = os.environ.get("SAMPLES", "tests/sample_payloads.json")


@pytest.fixture(scope="session")
def client():
    return httpx.Client(base_url=HOST, timeout=10.0)


@pytest.fixture(scope="session")
def samples():
    with open(SAMPLES_PATH, "r") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def routing_mode(client):
    # Ask the gateway which rule is active so tests adapt automatically
    r = client.get("/config")
    r.raise_for_status()
    cfg = r.json()
    return (cfg.get("routing_rules") or {}).get("default", "")


def _post_price(client, payload):
    r = client.post("/price", json=payload)
    return r, (
        r.json()
        if r.headers.get("content-type", "").startswith("application/json")
        else {}
    )


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert "gateway" in body and body["gateway"] == "healthy"


def test_all_sample_payloads_status_codes(client, samples):
    """
    Every payload should return 200, except those starting with 'invalid_' which should 422.
    """
    for key, payload in samples.items():
        r = client.post("/price", json=payload)
        if key.startswith("invalid_"):
            assert (
                r.status_code == 422
            ), f"{key} expected 422, got {r.status_code} ({r.text})"
        else:
            assert (
                r.status_code == 200
            ), f"{key} expected 200, got {r.status_code} ({r.text})"


@pytest.mark.parametrize(
    "even_key,odd_key",
    [
        ("even_birthdate_model_a", "odd_birthdate_model_b"),
    ],
)
def test_birthdate_even_odd_rule_if_enabled(
    client, samples, routing_mode, even_key, odd_key
):
    """
    Only runs strict assertions if routing rule is 'birthdate_even_odd'.
    Otherwise it's a no-op (still ensures the endpoint works).
    """
    # Ensure endpoints respond
    r_even, body_even = _post_price(client, samples[even_key])
    r_odd, body_odd = _post_price(client, samples[odd_key])
    assert r_even.status_code == 200, f"{even_key} failed: {r_even.text}"
    assert r_odd.status_code == 200, f"{odd_key} failed: {r_odd.text}"

    if routing_mode == "birthdate_even_odd":
        m_even = (body_even.get("gateway_metadata") or {}).get("model_id")
        m_odd = (body_odd.get("gateway_metadata") or {}).get("model_id")
        assert m_even == "model-a", f"Expected even → model-a, got {m_even}"
        assert m_odd == "model-b", f"Expected odd → model-b, got {m_odd}"


def test_ab_distribution_if_enabled(client, samples, routing_mode, request):
    """
    If 'ab_testing_percentage' is active, send many requests with RANDOM unit_ids
    (postal_code) so we sample the full hash space and approximate the configured
    distribution (33/33/34). Also verify stickiness for a few fixed unit_ids.
    """

    if routing_mode != "ab_testing_percentage":
        pytest.skip(
            "A/B distribution check skipped: routing rule is not ab_testing_percentage"
        )

    import random
    from collections import Counter

    # 1) Distribution check with random unit_ids (broad sampling)
    N = 600  # decent sample size
    counts = Counter()

    base_payload = {
        "birthdate": "1991-03-11",
        "driver_license_date": "2011-04-01",
        "car_model": "Yaris",
        "car_brand": "Toyota",
    }

    for _ in range(N):
        pc = str(random.randint(10000, 99999))  # random unit_id each time
        payload = dict(base_payload, postal_code=pc)
        r = client.post("/price", json=payload)
        assert r.status_code == 200, f"Random ab request failed: {r.text}"
        model = (r.json().get("gateway_metadata") or {}).get("model_id")
        assert model in {"model-a", "model-b", "model-c"}
        counts[model] += 1

    total = sum(counts.values())
    shares = {m: counts[m] / total for m in ("model-a", "model-b", "model-c")}
    request.node.ab_counts = counts

    # Relaxed bounds (± ~10–13% absolute) to avoid flakiness
    assert (
        0.20 <= shares["model-a"] <= 0.45
    ), f"model-a share {shares['model-a']:.3f} out of bounds; counts={counts}"
    assert (
        0.20 <= shares["model-b"] <= 0.45
    ), f"model-b share {shares['model-b']:.3f} out of bounds; counts={counts}"
    assert (
        0.20 <= shares["model-c"] <= 0.50
    ), f"model-c share {shares['model-c']:.3f} out of bounds; counts={counts}"

    # Stickiness check: same unit_id should always map to same model
    fixed_ids = ["11000", "22000", "33000", "44000", "55000"]
    for unit in fixed_ids:
        seen = set()
        payload = dict(base_payload, postal_code=unit)
        for _ in range(10):
            r = client.post("/price", json=payload)
            assert r.status_code == 200
            model = (r.json().get("gateway_metadata") or {}).get("model_id")
            seen.add(model)
        assert len(seen) == 1, f"Non-sticky assignment for unit_id={unit}: got {seen}"


def test_metrics_endpoint_exposes_prometheus_counters(client):
    r = client.get("/metrics", follow_redirects=True)
    assert r.status_code == 200
    text = r.text
    assert "gateway_model_requests_total" in text or "gateway_exposures_total" in text
