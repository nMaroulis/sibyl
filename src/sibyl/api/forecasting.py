"""Explicit trained-forecast research controls and read-only saved evidence."""

from fastapi import APIRouter, Depends, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from sibyl.api.routes import S
from sibyl.api.uploads import bounded_body
from sibyl.forecasting.bundles import MAX_BUNDLE
from sibyl.forecasting.contracts import ArchiveModel, ForecastRequest, RollingEvaluationRequest, TrainForecast
from sibyl.forecasting.forward import ForwardAction


def private_evidence(response: Response):
    """Keep workspace research and saved model outputs out of shared caches."""
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/api/v1/forecast-models", tags=["Chronos"], dependencies=[Depends(private_evidence)]
)


@router.get("")
def registry(s: S, include_archived: bool = False):
    """Read model-version metadata; no training or provider requests."""
    return s.forecasts.list(include_archived)


@router.post("", status_code=201)
def train_model(body: TrainForecast, s: S):
    """Capture reviewed input, fit coefficients and retain independent test evidence."""
    return s.forecasts.train(body)


@router.get("/outputs/{identity}")
def output(identity: str, s: S):
    """Read one exact saved forecast with its original observation window."""
    return s.forecasts.output(identity)


@router.get("/evaluations/{evaluation_id}")
def rolling_report(evaluation_id: str, s: S):
    """Read/export an exact saved rolling evaluation without rerunning it."""
    return s.forecasts.evaluations.detail(evaluation_id)


@router.get("/{identity}/evaluations")
def rolling_history(identity: str, s: S):
    """Read retained evaluation headers for the selected model version."""
    return s.forecasts.evaluations.list(identity)


@router.post("/{identity}/evaluations", status_code=201)
def rolling_evaluate(identity: str, body: RollingEvaluationRequest, s: S):
    """Explicitly refit the saved recipe over earlier windows and retain later test evidence."""
    return s.forecasts.evaluations.run(identity, body)


@router.post("/import", status_code=201)
async def import_model(request: Request, s: S):
    """Read a bounded JSON bundle, refit its recipe offline and label its source as unverified imported research."""
    content = await bounded_body(request, MAX_BUNDLE)
    return await run_in_threadpool(s.forecasts.bundles.import_bundle, content)


@router.get("/{identity}/bundle")
def bundle(identity: str, s: S):
    """Export the trained recipe, recorded evidence and full immutable daily input in portable JSON."""
    return s.forecasts.bundles.export(identity)


@router.post("/{identity}/archive")
def archive(identity: str, body: ArchiveModel, s: S):
    """Archive/restore a model without deleting outputs, evaluations or stopping outcome monitors."""
    return s.forecasts.archive(identity, body.archived, body.revision)


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


@router.get("/{identity}/tracking")
def tracked(identity: str, s: S):
    """Read prospective outcomes for this exact model, without provider requests."""
    return s.forecasts.forward.list(identity)


@router.post("/outputs/{identity}/track", status_code=201)
def track(identity: str, s: S):
    """Retain a current-feed forecast for prospective outcome tracking."""
    return s.forecasts.forward.enroll(identity)


@router.get("/outputs/{identity}/tracking")
def tracking(identity: str, s: S):
    """Read/export original predictions and dated observed actuals."""
    return s.forecasts.forward.detail(identity)


@router.post("/outputs/{identity}/tracking/action")
def tracking_action(identity: str, body: ForwardAction, s: S):
    """Pause/resume outcome tracking without modifying a forecast or model."""
    return s.forecasts.forward.action(identity, body)


@router.post("/outputs/{identity}/tracking/check")
def check_tracking(identity: str, s: S, refresh: bool = False):
    """Check the local archive, or explicitly refresh a matching current source page."""
    return s.forecasts.forward.evaluate(identity, refresh=refresh)


@router.delete("/outputs/{identity}/tracking")
def forget_tracking(identity: str, s: S, revision: int = Query(ge=1)):
    """Remove tracked actuals after explicit review; do not delete the original forecast."""
    return s.forecasts.forward.forget(identity, revision)
