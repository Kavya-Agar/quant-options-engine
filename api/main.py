"""
Options Pricing Engine — FastAPI Backend (Phase 4)
==================================================
Run from the project root:
    uvicorn api.main:app --reload --port 8000

Interactive docs: http://localhost:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import chain, price, planner

app = FastAPI(
    title="Options Pricing Engine",
    description=(
        "Black-Scholes pricing, all five Greeks, and Brent's-method implied volatility "
        "computed against live options chains from yfinance. Includes AI-powered strategy planner."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(price.router, prefix="/api", tags=["pricing"])
app.include_router(chain.router, prefix="/api", tags=["chain"])
app.include_router(planner.router, prefix="/api", tags=["planner"])


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
