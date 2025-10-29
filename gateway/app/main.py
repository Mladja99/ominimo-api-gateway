"""
Main FastAPI application for the Ominimo API Gateway.

This is the entry point for the gateway service that routes insurance
pricing requests to different model versions.
"""

import time
import uuid

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from .config import settings
from .models import (
    ConfigResponse,
    GatewayMetadata,
    HealthResponse,
    PriceRequest,
    PriceResponse,
)
from .observability import setup_observability
from .routing import RouterEngine

# Initialize FastAPI app
app = FastAPI(
    title="Ominimo Pricing Engine API Gateway",
    description="API Gateway for car insurance pricing with intelligent routing",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)
# Expose Prometheus metrics at /metrics
app.mount("/metrics", make_asgi_app())

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
router_engine = RouterEngine(settings.models_config_path)
observability = setup_observability(settings.log_level, settings.log_dir)

ab = router_engine.config.get("ab_testing", {})
expected = None
if ab.get("enabled") and ab.get("distributions"):
    # normalize & set
    expected = {k: float(v) for k, v in ab["distributions"].items()}
    observability.set_expected_distribution(expected)


@app.middleware("http")
async def add_request_id_and_timing(request: Request, call_next):
    """
    Middleware to add request ID and measure processing time.

    Adds X-Request-ID header and X-Process-Time to all responses.
    """

    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{process_time:.3f}"

    return response


@app.post("/price", response_model=PriceResponse, tags=["Pricing"])
async def get_price(request: PriceRequest, req: Request):
    """
    Get insurance price quote.

    Routes the request to an appropriate pricing model based on configured
    routing rules. Returns the calculated price with detailed breakdown.

    Args:
        request: Price request with driver and car information
        req: FastAPI request object (for metadata)

    Returns:
        Price response with calculation details and routing metadata

    Raises:
        HTTPException: If model is unavailable or returns an error
    """

    request_id = req.state.request_id
    model_id = None
    start_time = time.time()

    # Convert request to dict for routing (ensure date strings)
    payload = request.model_dump()
    payload["birthdate"] = request.birthdate.isoformat()
    payload["driver_license_date"] = request.driver_license_date.isoformat()

    # Log incoming request
    client_ip = req.client.host if req.client else None
    observability.log_request(request_id, payload, client_ip)

    try:
        # Determine which model to use
        model_id = router_engine.route_request(payload)
        observability.log_exposure(
            experiment_id=router_engine.config.get("ab_testing", {}).get(
                "experiment_id", "api_routing_default"
            ),
            unit_id=payload.get("postal_code", "anon"),
            model_id=model_id,
        )
        model_config = router_engine.get_model_config(model_id)

        # Check if model is enabled
        if not model_config.get("enabled", True):
            raise HTTPException(
                status_code=503, detail=f"Model {model_id} is currently disabled"
            )

        # Log routing decision
        routing_rule = router_engine.get_routing_rule()
        observability.log_routing_decision(request_id, model_id, routing_rule, payload)

        # Call the selected model
        model_url = model_config["url"]

        async with httpx.AsyncClient(timeout=settings.model_timeout_seconds) as client:
            model_call_start = time.time()
            try:
                response = await client.post(f"{model_url}/predict", json=payload)
                response.raise_for_status()
                result = response.json()
                observability.prom_record_model_call(
                    model_id, True, time.time() - model_call_start
                )
            except Exception:
                observability.prom_record_model_call(
                    model_id, False, time.time() - model_call_start
                )
                raise

        # Validate minimal schema from model
        required_keys = {"price", "breakdown"}
        missing = required_keys - set(result)

        if missing:
            msg = (
                f"Model {model_id} returned invalid schema, missing: {sorted(missing)}"
            )
            observability.log_error(request_id, "ModelSchemaError", msg, model_id)
            raise HTTPException(status_code=502, detail=msg)

        # Calculate total processing time
        process_time = time.time() - start_time

        # Add gateway metadata
        result["gateway_metadata"] = GatewayMetadata(
            model_id=model_id,
            model_version=model_config["version"],
            routing_rule=routing_rule,
            process_time_ms=round(process_time * 1000, 2),
        ).model_dump()

        # Log successful response
        observability.log_model_response(
            request_id, model_id, result.get("price", 0), process_time
        )

        return PriceResponse(**result)

    except httpx.HTTPError as e:
        error_msg = f"Error calling model service: {str(e)}"
        observability.log_error(
            request_id, "HTTPError", error_msg, model_id or "unknown"
        )
        raise HTTPException(status_code=502, detail=error_msg) from e

    except Exception as e:
        error_msg = f"Internal error: {str(e)}"
        observability.log_error(request_id, "InternalError", error_msg)
        raise HTTPException(status_code=500, detail=error_msg) from e


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Check health of gateway and all model services.

    Returns:
        Health status of gateway and all configured models
    """

    model_health = {}

    async with httpx.AsyncClient(timeout=5.0) as client:
        for model_id, config in router_engine.get_all_models().items():
            try:
                response = await client.get(f"{config['url']}/health")
                model_health[model_id] = response.json()
            except Exception as e:
                model_health[model_id] = {"status": "unreachable", "error": str(e)}

    return HealthResponse(gateway="healthy", models=model_health)


@app.get("/config", response_model=ConfigResponse, tags=["Configuration"])
async def get_config():
    """
    View current routing configuration.

    Returns:
        Current configuration including models, routing rules, and A/B testing setup
    """
    return ConfigResponse(
        models=router_engine.config["models"],
        routing_rules=router_engine.config["routing_rules"],
        ab_testing=router_engine.config.get("ab_testing", {}),
    )


@app.post("/config/reload", tags=["Configuration"])
async def reload_config():
    """
    Reload configuration from YAML file.

    Allows updating routing rules without restarting the gateway.

    Returns:
        Success message with new configuration
    """
    try:
        router_engine.reload_config()
        return {
            "message": "Configuration reloaded successfully",
            "routing_rule": router_engine.get_routing_rule(),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to reload configuration: {str(e)}"
        ) from e


@app.get("/", tags=["Info"])
async def root():
    """
    Root endpoint with API information.

    Returns:
        Basic information about the API and available endpoints
    """
    return {
        "service": "Ominimo Pricing Engine API Gateway",
        "version": "1.0.0",
        "status": "operational",
        "endpoints": {
            "price": "POST /price - Get insurance quote",
            "health": "GET /health - Check service health",
            "config": "GET /config - View configuration",
            "docs": "GET /docs - API documentation",
        },
        "routing": {
            "current_rule": router_engine.get_routing_rule(),
            "available_models": list(router_engine.get_all_models().keys()),
        },
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    request_id = getattr(request.state, "request_id", "unknown")
    observability.log_error(request_id, type(exc).__name__, str(exc))

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": str(exc),
            "request_id": request_id,
        },
    )
