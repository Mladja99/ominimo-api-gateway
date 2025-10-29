from fastapi import FastAPI
from pydantic import BaseModel
from datetime import date
import time
import random
import logging

try:
    from model_a import ModelA

    model = ModelA()
except ImportError:
    model = None

app = FastAPI(title="Model A API", version="1.0.0")
logger = logging.getLogger(__name__)


class PriceRequest(BaseModel):
    birthdate: date
    driver_license_date: date
    car_model: str
    car_brand: str
    postal_code: str


@app.post("/predict")
async def predict(request: PriceRequest):
    if model:
        result = model.calculate_price(
            birthdate=request.birthdate,
            driver_license_date=request.driver_license_date,
            car_model=request.car_model,
            car_brand=request.car_brand,
            postal_code=request.postal_code
        )
    else:
        # Fallback mock response
        result = {
            "model_name": "Model A",
            "price": random.uniform(500, 1000),
            "currency": "EUR",
            "breakdown": {},
            "metadata": {}
        }

    logger.info(f"Prediction generated: {result['price']} EUR")
    return result


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "model": "Model A",
        "version": "1.0.0"
    }