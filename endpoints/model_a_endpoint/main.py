import logging
import os
from datetime import date
from typing import Any, Dict

from fastapi import FastAPI
from pydantic import BaseModel, Field

try:
    from model_a import ModelA

    model = ModelA()
except ImportError as e:
    raise ImportError(f"Model package not available: {e}.")

app = FastAPI(
    title="Model A API",
    version="0.1.0",
    description="Age-focused car insurance pricing model",
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("./logs/model-a.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class PriceRequest(BaseModel):
    """Request model for price prediction."""

    birthdate: date = Field(..., description="Driver's birth date")
    driver_license_date: date = Field(..., description="License issue date")
    car_model: str = Field(..., description="Car model")
    car_brand: str = Field(..., description="Car brand")
    postal_code: str = Field(..., description="Postal code")


@app.post("/predict")
async def predict(request: PriceRequest):
    result = model.calculate_price(
        birthdate=request.birthdate,
        driver_license_date=request.driver_license_date,
        car_model=request.car_model,
        car_brand=request.car_brand,
        postal_code=request.postal_code,
    )

    logger.info(f"Prediction generated: {result['price']} EUR")
    return result


@app.get("/health")
async def health():
    return {"status": "healthy", "model": model.name, "version": "0.1.0"}


@app.get("/")
async def root() -> Dict[str, Any]:
    """
    Root endpoint with service information.

    Returns:
        Service metadata and available endpoints
    """

    return {
        "service": "Model A API",
        "description": "Age-based car insurance pricing model",
        "version": "0.1.0",
        "model_available": model.name,
        "endpoints": {
            "predict": "POST /predict",
            "health": "GET /health",
            "docs": "GET /docs",
        },
    }
