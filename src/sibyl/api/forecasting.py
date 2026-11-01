"""Explicit trained-forecast research controls and read-only saved evidence."""

from fastapi import APIRouter, Depends, Query, Response

from sibyl.api.routes import S
from sibyl.forecasting.contracts import ForecastRequest, TrainForecast


def private_evidence(response: Response):
    """Keep workspace research and saved model outputs out of shared caches."""
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/api/v1/forecast-models", tags=["Chronos"], dependencies=[Depends(private_evidence)]
)


@router.get("")
def registry(s: S):
    """Read model-version metadata; no training or provider requests."""
    return s.forecasts.list()


@router.post("", status_code=201)
def train_model(body: TrainForecast, s: S):
    """Capture reviewed input, fit coefficients and retain independent test evidence."""
    return s.forecasts.train(body)


@router.get("/outputs/{identity}")
def output(identity: str, s: S):
    """Read one exact saved forecast with its original observation window."""
    return s.forecasts.output(identity)


@router.get("/{identity}")
def detail(identity: str, s: S, horizon: int | None = Query(None, ge=1, le=30)):
    """Read evaluation metrics and the selected held-out test trace."""
    return s.forecasts.detail(identity, horizon)


@router.get("/{identity}/export")
def export(identity: str, s: S):
    """Export a JSON-only model artifact and complete evaluation evidence."""
    return s.forecasts.export(identity)


@router.post("/{identity}/rerun", status_code=201)
def rerun(identity: str, s: S):
    """Fit a new version from original frozen inputs without a provider read."""
    return s.forecasts.rerun(identity)


@router.post("/{identity}/forecasts", status_code=201)
def forecast(identity: str, body: ForecastRequest, s: S):
    """Retain predictions using saved input or explicitly refreshed matching daily observations."""
    return s.forecasts.forecast(identity, body)
