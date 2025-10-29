"""
Pydantic models for request/response validation.

This module defines the data structures used for API requests and responses,
including validation rules.
"""

from datetime import date
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator


class PriceRequest(BaseModel):
    """
    Request model for insurance price calculation.

    This model defines and validates the input schema for the `/price` endpoint.
    It ensures that all submitted driver and vehicle information is valid before
    the API Gateway routes the request to the appropriate pricing model.

    ### Attributes
    --------------
    birthdate : date
        Driver's birthdate in ISO 8601 format (`YYYY-MM-DD`).
        Used to calculate driver's age and determine eligibility.
    driver_license_date : date
        Date when the driver's license was issued.
        Used to calculate driving experience.
    car_model : str
        Name of the car model (e.g., "Golf", "Model S").
    car_brand : str
        Manufacturer of the car (e.g., "Volkswagen", "Toyota").
    postal_code : str
        Postal code of the driver's residence.
        Used for geographic routing or A/B testing segmentation.

    ### Validation Rules
    --------------------
    - **Birthdate**:
        - Must be in the past.
        - Driver must be at least 18 years old and not older than 100.
    - **License Date**:
        - Cannot be in the future.
    - **String Fields**:
        - Car model: 1–100 characters.
        - Car brand: 1–50 characters.
        - Postal code: 3–10 characters.

    ### Example
    -----------
    ```json
    {
        "birthdate": "1995-06-15",
        "driver_license_date": "2015-08-20",
        "car_model": "Golf",
        "car_brand": "Volkswagen",
        "postal_code": "1234AC"
    }
    ```
    """

    birthdate: date = Field(
        ...,
        description="Driver's birth date in YYYY-MM-DD format",
        examples=["1995-06-15"],
    )

    driver_license_date: date = Field(
        ...,
        description="Date when driver's license was issued",
        examples=["2015-08-20"],
    )

    car_model: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Car model name",
        examples=["Golf", "Corolla", "Model S"],
    )

    car_brand: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Car brand/manufacturer",
        examples=["Volkswagen", "Toyota", "Tesla"],
    )

    postal_code: str = Field(
        ...,
        min_length=3,
        max_length=10,
        description="Postal code of driver's residence",
        examples=["1234AC", "5678BD"],
    )

    @field_validator("birthdate")
    @classmethod
    def validate_birthdate(cls, v: date) -> date:
        """
        Validate `birthdate`.

        Ensures that:
        - The driver is at least 18 years old.
        - The driver's age does not exceed 100 years.
        - The birthdate is not in the future.

        Raises
        ------
        ValueError
            If any of the above conditions are violated.
        """

        today = date.today()
        age = today.year - v.year - ((today.month, today.day) < (v.month, v.day))

        if age < 18:
            raise ValueError("Driver must be at least 18 years old")
        if age > 100:
            raise ValueError("Invalid birthdate: age exceeds 100 years")
        if v > today:
            raise ValueError("Birthdate cannot be in the future")

        return v

    @field_validator("driver_license_date")
    @classmethod
    def validate_license_date(cls, v: date) -> date:
        """
        Validate `driver_license_date`.

        Ensures that:
        - The license issue date is not in the future.

        Raises
        ------
        ValueError
            If the date is after today's date.
        """

        if v > date.today():
            raise ValueError("Driver license date cannot be in the future")
        return v

    class Config:
        """Pydantic model configuration and schema examples."""

        json_schema_extra = {
            "example": {
                "birthdate": "1995-06-15",
                "driver_license_date": "2015-08-20",
                "car_model": "Golf",
                "car_brand": "Volkswagen",
                "postal_code": "1234AC",
            }
        }


class GatewayMetadata(BaseModel):
    """
    Metadata added by the API Gateway to describe *how* a request
    was routed and processed.

    ### Attributes
    ----------
    model_id : str
        Identifier of the model service that handled the request
        (e.g., "model-a", "model-b", "model-c").
    model_version : str
        Version string of the selected model (e.g., "v0.1.0").
    routing_rule : str
        Name of the routing rule used for the decision
        (e.g., "ab_testing_percentage", "birthdate_even_odd").
    process_time_ms : float | None
        End-to-end processing time measured by the gateway in **milliseconds**
        (includes routing + downstream call). Optional.
    """

    model_id: str = Field(
        ...,
        description="ID of the model service that processed the request (e.g., 'model-a').",
        examples=["model-a", "model-b", "model-c"],
    )
    model_version: str = Field(
        ...,
        description="Version string of the selected model.",
        examples=["v0.1.0"],
    )
    routing_rule: str = Field(
        ...,
        description="Routing rule applied for this request.",
        examples=["ab_testing_percentage", "birthdate_even_odd", "postal_code_region"],
    )
    process_time_ms: Optional[float] = Field(
        None,
        description="Total gateway processing time in milliseconds.",
        examples=[123.45],
    )

    class Config:
        """Pydantic configuration and example for OpenAPI."""

        json_schema_extra = {
            "example": {
                "model_id": "model-b",
                "model_version": "v0.1.0",
                "routing_rule": "ab_testing_percentage",
                "process_time_ms": 87.23,
            }
        }


class PriceResponse(BaseModel):
    """
    Unified response returned by the API Gateway.

    Combines the **model service output** (price, currency, metadata, breakdown)
    with **gateway metadata** describing routing and timing.

    ### Attributes
    ----------
    model_name : str
        Human-readable name of the model (supplied by the model service).
    price : float
        Calculated annual insurance price.
    currency : str
        ISO currency code (default: "EUR").
    breakdown : dict[str, Any]
        Key–value details of the price computation (e.g., base, age_factor, risk_load).
    metadata : dict[str, Any]
        Any additional model-specific information you choose to return.
    gateway_metadata : GatewayMetadata | None
        Metadata added by the gateway (selected model, rule, processing time).
    """

    model_name: str = Field(
        ...,
        description="Human-readable name of the pricing model that produced this result.",
        examples=["Model B - Experience Based Pricing"],
    )
    price: float = Field(
        ...,
        description="Calculated annual insurance price.",
        examples=[1234.56],
    )
    currency: str = Field(
        default="EUR",
        description="Currency code for the price.",
        examples=["EUR"],
    )
    breakdown: Dict[str, Any] = Field(
        default_factory=dict,
        description="Detailed breakdown of the price calculation.",
        examples=[{"base": 900.0, "experience_factor": 1.2, "risk_load": 120.0}],
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional model-specific metadata returned by the model service.",
        examples=[{"engine": "B", "features_used": ["age", "experience", "brand"]}],
    )
    gateway_metadata: Optional[GatewayMetadata] = Field(
        None,
        description="Routing/timing metadata added by the API Gateway.",
    )

    class Config:
        """Pydantic configuration and example for OpenAPI."""

        json_schema_extra = {
            "example": {
                "model_name": "Model B - Experience Based Pricing",
                "price": 1234.56,
                "currency": "EUR",
                "breakdown": {
                    "base": 900.0,
                    "experience_factor": 1.2,
                    "risk_load": 120.0,
                },
                "metadata": {
                    "engine": "B",
                    "features_used": ["age", "experience", "brand"],
                },
                "gateway_metadata": {
                    "model_id": "model-b",
                    "model_version": "v0.1.0",
                    "routing_rule": "ab_testing_percentage",
                    "process_time_ms": 87.23,
                },
            }
        }


class HealthResponse(BaseModel):
    """
    Standard health-check response returned by `/health`.

    Reports the status of the **API Gateway** itself and every configured
    model service (A, B, C …).

    ### Attributes
    ----------
    gateway : str
        Overall health of the gateway process.
        Usually `"healthy"` if the service is reachable.
    models : dict[str, dict[str, str]]
        Mapping of model ID → small JSON object describing that model’s
        health (status, optional error message, version info, etc.).
    """

    gateway: str = Field(
        ...,
        description="Overall health of the gateway service (e.g. 'healthy').",
        examples=["healthy"],
    )
    models: Dict[str, Dict[str, str]] = Field(
        ...,
        description="Per-model health status objects keyed by model ID.",
        examples=[
            {
                "model-a": {"status": "healthy"},
                "model-b": {"status": "unreachable", "error": "Connection refused"},
            }
        ],
    )

    class Config:
        json_schema_extra = {
            "example": {
                "gateway": "healthy",
                "models": {
                    "model-a": {"status": "healthy"},
                    "model-b": {"status": "unreachable", "error": "Connection refused"},
                },
            }
        }


class ConfigResponse(BaseModel):
    """
    Response model for `/config`.

    Returns the current configuration loaded by the **RouterEngine**,
    including available models, routing rules, and A/B-testing settings.

    ### Attributes
    ----------
    models : dict[str, Any]
        Configuration block for every registered model service.
    routing_rules : dict[str, Any]
        Currently active routing rule(s) and any alternative options.
    ab_testing : dict[str, Any]
        Details of the active A/B-testing experiment (weights, unit field, etc.).
    """

    models: Dict[str, Any] = Field(
        ...,
        description="Dictionary of configured models with metadata and URLs.",
        examples=[
            {
                "model-a": {
                    "url": "http://model-a-api:8000",
                    "version": "v0.1.0",
                    "enabled": True,
                }
            }
        ],
    )
    routing_rules: Dict[str, Any] = Field(
        ...,
        description="Routing rule configuration (default rule and list of available rules).",
        examples=[
            {
                "default": "ab_testing_percentage",
                "available_rules": ["birthdate_even_odd"],
            }
        ],
    )
    ab_testing: Dict[str, Any] = Field(
        ...,
        description="A/B-testing configuration (enabled flag, distributions, etc.).",
        examples=[
            {
                "enabled": True,
                "experiment_id": "api_routing_2025_10",
                "unit_field": "postal_code",
                "distributions": {"model-a": 0.33, "model-b": 0.33, "model-c": 0.34},
            }
        ],
    )

    class Config:
        json_schema_extra = {
            "example": {
                "models": {
                    "model-a": {
                        "url": "http://model-a-api:8000",
                        "version": "v0.1.0",
                        "enabled": True,
                    }
                },
                "routing_rules": {
                    "default": "ab_testing_percentage",
                    "available_rules": [
                        "birthdate_even_odd",
                        "postal_code_region",
                        "ab_testing_percentage",
                    ],
                },
                "ab_testing": {
                    "enabled": True,
                    "experiment_id": "api_routing_2025_10",
                    "unit_field": "postal_code",
                    "distributions": {
                        "model-a": 0.33,
                        "model-b": 0.33,
                        "model-c": 0.34,
                    },
                },
            }
        }


class ErrorResponse(BaseModel):
    """
    Standardized error payload returned by the API Gateway.

    Used for consistent error handling across endpoints and during downstream
    model-service failures.

    ### Attributes
    ----------
    error : str
        Short error category (e.g., `"HTTPError"`, `"InternalError"`).
    detail : str
        Human-readable explanation of the problem.
    model_id : str | None
        ID of the model where the error occurred (if applicable).
    """

    error: str = Field(
        ...,
        description="Short error type or category.",
        examples=["HTTPError", "InternalError"],
    )
    detail: str = Field(
        ...,
        description="Detailed error message explaining the failure.",
        examples=["Connection timed out while calling model-b service."],
    )
    model_id: str | None = Field(
        None,
        description="ID of the model involved in the error, if any.",
        examples=["model-b"],
    )

    class Config:
        json_schema_extra = {
            "example": {
                "error": "HTTPError",
                "detail": "Model service returned status 502 Bad Gateway.",
                "model_id": "model-b",
            }
        }
