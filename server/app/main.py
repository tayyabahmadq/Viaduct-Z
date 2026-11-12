"""Viaduct Pay API."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from . import __version__
from .config import get_settings
from .db import Base, engine
from .routers import accounts, assistant, payments, peers, tokens, topups
from .seed import seed_if_empty

Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if get_settings().seed_on_start:
        seed_if_empty()
    yield


app = FastAPI(
    title="Viaduct Pay API",
    version=__version__,
    description="Demo credit ledger. No KYC, no real money.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(accounts.router)
app.include_router(payments.router)
app.include_router(peers.router)
app.include_router(tokens.router)
app.include_router(topups.router)
app.include_router(assistant.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "viaduct-ledger", "version": __version__}


@app.get("/")
def root() -> dict:
    return {
        "service": "viaduct-ledger",
        "docs": "/docs",
        "health": "/health",
        "api": "/api/v1",
    }


@app.get("/paypal/return", response_class=HTMLResponse, include_in_schema=False)
def paypal_return() -> str:
    """Where PayPal's approval page sends the browser back to."""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Viaduct Pay</title>"
        "<style>body{font-family:system-ui;margin:0;display:grid;place-items:center;"
        "height:100vh;background:#F8FAFC;color:#0B1220}main{text-align:center;padding:24px}"
        "</style></head><body><main><h1>PayPal approval received</h1>"
        "<p>Return to the Viaduct Pay app and tap <strong>I approved — capture</strong>.</p>"
        "</main></body></html>"
    )
