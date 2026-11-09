"""Chronos reads forecast models, held-out evidence and the separate price baseline.

The model chooses typed ProtoLink evidence or help tools; it does not train a
forecast model. Tool descriptions explain their purpose to the reasoning model.
"""

from typing import Annotated

from protolink import Agent, Tool, ToolRejectedError
from pydantic import Field

from sibyl.agents.guides import read_guide
from sibyl.agents.guides.chronos import GUIDES, Topic
from sibyl.agents.utils.common import COMMON_PROMPT, Services, selected
from sibyl.services.markets.analytics import forecast

NAME = "Chronos"
TAGLINE = "Explore what comes next"
DESCRIPTION = (
    "Explain selected trained forecasts, model evaluation and baseline assumptions; guide Forecasting."
)
SYSTEM_PROMPT = (
    "Read the selected model's numerical family, saved feature recipe and notes. Optional causal trend/volatility context does not establish better future accuracy. "
    "For a Huber model, inspect its retained delta, training-only median/MAD scale, convergence/step cap and downweighted residual counts. Downweighting does not establish that an observation is erroneous and does not protect against extreme feature leverage. A step-limit fit is not converged. Training loss and convergence are not held-out accuracy or future coverage; compare naive/drift test errors and empirical bands. "
    "ARIMA is nonseasonal ARIMA(p,1,q) on log prices with drift, fitted natively as ARMA on training-only standardized returns. All horizons share one frozen parameter vector; a native filter uses the latest 90 closes at each origin, without refitting or future smoothing. Inspect actual order, convergence, iterations, native coefficients and held-out price errors. AIC/BIC describe training fit and are comparable only for identical data/scaling; they do not establish predictive accuracy. Degenerate/nonconverged fits are rejected. "
    "Drift compares training returns with later non-overlapping retained observations, using descriptive Jensen–Shannon divergence. Saved policies can retain candidates through local jobs; candidates never replace a model automatically. Missing recent days are not evidence of stability. "
    "Portable imported models are locally refitted research with unverified source origin, never prospective live evidence. Archived models keep saved evidence and existing outcome monitors; they must be restored for new forecasts. Use page_help models/portability for library controls. "
    "Use forecast_outcomes for live prospective scorecards, distinct from historical held-out or rolling evaluations. Missing future or archived targets remain missing; repeated horizon errors and selected forecast runs do not establish reliable future accuracy. "
    "Use rolling_evaluation to inspect selected saved rolling reports or list evaluations for a model. These refit a fixed recipe over earlier windows; they do not evaluate the original saved weights. Disclose per-fold variation, pooled benchmark skill, overlapping targets and repeated-experiment limitations. Never claim a rolling run trained or deployed a production model. "
    "Use page_help for Forecasting controls and setup, forecast_method for conceptual methodology, "
    "and price_forecast for a selected trained result or baseline. Use trained_models and model_report "
    "to inspect registry versions, chronological evaluation, naive/drift benchmarks, calibration and data provenance. "
    "Ask for a model, symbol or horizon when ambiguous. Trained numerical forecast models and "
    "the untrained drift baseline are distinct. Negative skill means the naive benchmark performed better. "
    "Bands and input-shift checks provide research evidence, not guaranteed coverage, calibrated regime detection "
    "or profitable trade probabilities. You can read model evidence but cannot train, refit or save forecasts. "
)


def create_agent(services: Services, **runtime) -> Agent:
    """Register this specialist's evidence and help tools on a native Agent.

    Args:
        services: Workspace domain services; credentials stay in their owners.
        **runtime: AgentGroup configuration, including the lazy model factory,
            native state, worker defaults and context policy.

    Returns:
        An unstarted Agent. Static guides run inline; domain reads inherit the
        runtime's execution policy (bounded threads in Sibyl). AgentGroup owns
        startup and shutdown.
    """
    market = services.market

    def price_forecast(
        symbol: str | None = None,
        horizon: Annotated[int | None, Field(ge=1, le=30)] = None,
        model_id: Annotated[str | None, Field(pattern=r"^[a-f0-9]{32}$")] = None,
    ) -> dict:
        """Read the selected trained forecast, or a labeled statistical baseline when no model is
        selected. Supply exact source/pair/horizon or follow the page. Distinguish fitted evaluation
        from future uncertainty; interval coverage is empirical, not a guarantee. Never trains a
        model.
        """
        explicit_model = model_id is not None
        identity = selected("forecast_model_id", model_id)
        if identity:
            if not services.forecasts:
                raise ValueError("Trained forecasting is unavailable in this workspace.")
            try:
                model = services.forecasts.detail(identity)["model"]
            except LookupError as exc:
                raise ToolRejectedError(
                    "That trained model version is not retained in this workspace.",
                    code="forecast_model_not_found",
                    suggestion="Call trained_models() to find saved versions, or explain that the selected version is missing. Never silently replace it with the untrained baseline.",
                ) from exc
            symbol = symbol or (
                model["symbol"] if explicit_model else selected("symbol", None, model["symbol"])
            )
            horizon = horizon or (
                min(14, model["parameters"]["max_horizon"])
                if explicit_model
                else selected("horizon", None, min(14, model["parameters"]["max_horizon"]))
            )
            if symbol != model["symbol"]:
                raise ValueError("The selected trained model uses a different market. Choose its exact pair.")
            run_id = (
                selected("forecast_run_id", None)
                if not explicit_model or identity == selected("forecast_model_id", None)
                else None
            )
            return services.forecasts.preview(identity, horizon, run_id=run_id)
        symbol = selected("symbol", symbol, "BTC/USDT")
        horizon = selected("horizon", horizon, 14)
        if not 1 <= horizon <= 30:
            raise ValueError("Forecast horizon must be between 1 and 30 days.")
        with market.snapshot(selected("market_source", None, None)):
            return {
                "symbol": symbol,
                "source": market.source,
                **forecast(market.candles(symbol, 180), horizon),
            }

    def forecast_outcomes(model_id: str | None = None, run_id: str | None = None) -> dict:
        """Read retained real-time forecast-vs-outcome evaluations for the selected model and source.
        Returns observed horizons, errors, interval coverage, missing/stale candles and samples.
        Missing outcomes are not zero errors. Never fetches prices, fits or promotes a model.
        """
        identity = selected("forecast_model_id", model_id)
        run = selected("forecast_run_id", run_id) if model_id is None else run_id
        if not services.forecasts or not identity:
            raise ToolRejectedError("Select a trained model first.", code="forecast_model_required")
        try:
            result = (
                services.forecasts.forward.detail(run) if run else services.forecasts.forward.list(identity)
            )
        except LookupError as exc:
            raise ToolRejectedError(
                "That tracked forecast is not retained.",
                code="forecast_tracking_not_found",
                suggestion="Read the model's tracking list for current IDs.",
            ) from exc
        if run and result["model_id"] != identity:
            raise ToolRejectedError(
                "This tracked output belongs to another model.", code="forecast_tracking_not_found"
            )
        if not run:
            all_items = result["items"]
            result = {
                **result,
                "total": len(all_items),
                "limit": 20,
                "items": [
                    {
                        key: item[key]
                        for key in (
                            "id",
                            "accepted_at",
                            "status",
                            "observed",
                            "pending",
                            "metrics",
                            "naive",
                            "coverage_pct",
                            "mae_skill_vs_naive_pct",
                        )
                    }
                    for item in all_items[:20]
                ],
            }
        return {"kind": "forecast_outcomes", **result, "url": f"/forecast?tab=models&model={identity}"}

    def forecast_method() -> dict:
        """Explain trained autoregressive forecasts and the separate statistical baseline.

        Use for questions about forecast methodology or whether a model has been
        trained. Returns the implemented assumptions and calibration limitations.
        """
        return {
            "method": "Trained direct ridge, fixed-scale Huber, native nonseasonal ARIMA(p,1,q) or a small tanh neural network; the untrained log-return baseline is separate",
            "training": "Frozen daily input and chronological 60/20/20 train/calibration/test partitions. Ridge/Huber/neural fit per horizon with purged targets. ARIMA fits one return model on the training partition, fixes parameters, then filters exactly 90 observed closes per origin; calibration/test targets crossing their boundaries are purged.",
            "trained_intervals": "Nominal 90% bands from calibration log errors; held-out coverage is reported and future coverage is not guaranteed.",
            "horizon_days": {"ridge": [1, 30], "huber": [1, 30], "small_neural": [1, 14], "arima": [1, 14]},
            "baseline_intervals": "Approximate 95% theoretical bands from constant historical drift/volatility, without empirical calibration.",
            "interpretation": "Neither model's bands are probabilities of profitable trades.",
        }

    def trained_models(include_archived: bool = False) -> dict:
        """List saved Chronos model versions, their exact markets, datasets and training settings.

        Use to find a model ID before inspecting its evaluation or a retained forecast.
        Set include_archived to find hidden retained versions. Imported versions carry
        unverified source labels even after local refitting. Returns the local registry only; does not train, fetch prices or select a model for the user.
        """
        rows = services.forecasts.list(include_archived)["items"] if services.forecasts else []
        return {
            "items": [
                {
                    key: row.get(key)
                    for key in (
                        "id",
                        "label",
                        "version",
                        "symbol",
                        "source",
                        "environment",
                        "parameters",
                        "archived",
                        "imported_from",
                    )
                }
                for row in rows[:20]
            ],
            "total": len(rows),
            "limit": 20,
        }

    def model_report(model_id: str | None = None) -> dict:
        """Inspect a trained model's test errors, naive/drift benchmarks and interval coverage.

        Omit model_id to use the Forecasting page selection. Returns dataset/source
        provenance, version, training/calibration/test dates, metrics, actual Huber/neural/ARIMA training diagnostics and interpretation notes. Huber residual weights are not labels of incorrect market data; inspect convergence separately from held-out skill.
        """
        identity = selected("forecast_model_id", model_id)
        if not identity or not services.forecasts:
            raise ToolRejectedError(
                "No trained model is selected.",
                code="forecast_model_required",
                suggestion="Use trained_models() for saved versions or guide the user to Forecasting. An empty registry is not a trained forecast.",
            )
        try:
            report = services.forecasts.detail(identity)
        except LookupError as exc:
            raise ToolRejectedError(
                "That trained model version is not retained in this workspace.",
                code="forecast_model_not_found",
                suggestion="Use trained_models() for current model IDs; do not invent a version or substitute the baseline.",
            ) from exc
        evidence = {key: value for key, value in report.items() if key not in {"test_trace", "outputs"}}
        drift = services.forecasts.drift.state(identity)
        evidence["drift"] = {key: drift[key] for key in ("revision", "policy", "assessment", "note")}
        evidence["recalibration_candidates"] = [
            {
                key: row[key]
                for key in ("status", "created_at", "candidate_id", "candidate_version")
                if key in row
            }
            for row in drift["history"][:5]
        ]
        return evidence

    def rolling_evaluation(
        model_id: Annotated[str | None, Field(pattern=r"^[a-f0-9]{32}$")] = None,
        evaluation_id: Annotated[str | None, Field(pattern=r"^[a-f0-9]{32}$")] = None,
    ) -> dict:
        """Read a saved chronological forecast evaluation and its independent folds. Omit evaluation_id
        for the page selection. Returns source pins, training/test boundaries, model/baseline errors
        and interval coverage. Repeated research can overfit; this tool never runs training.
        """
        identity = selected("forecast_model_id", model_id)
        report_id = evaluation_id or (
            selected("forecast_evaluation_id", None)
            if model_id is None or model_id == selected("forecast_model_id", None)
            else None
        )
        if not services.forecasts or not identity and not report_id:
            raise ToolRejectedError(
                "Choose a saved model or rolling evaluation first.",
                code="forecast_model_required",
                suggestion="Use trained_models() or open Forecasting → Trained models.",
            )
        try:
            if not report_id:
                return {
                    "kind": "rolling_evaluations",
                    "model_id": identity,
                    **services.forecasts.evaluations.list(identity),
                }
            report = services.forecasts.evaluations.detail(report_id)
        except LookupError as exc:
            raise ToolRejectedError(
                "That model or rolling evaluation is no longer retained.",
                code="forecast_evaluation_not_found",
                suggestion="List rolling_evaluation(model_id=...) for retained reports. Never substitute a different evaluation or baseline.",
            ) from exc
        if identity and report["model_id"] != identity:
            raise ToolRejectedError(
                "The evaluation belongs to a different model version.",
                code="forecast_evaluation_not_found",
                suggestion="Choose an evaluation retained for the selected model version.",
            )
        return {
            "kind": "rolling_evaluation",
            "report": {
                **services.forecasts.evaluations.header(report),
                "notes": report["result"]["notes"],
                "folds": [
                    {
                        "index": fold["index"],
                        "partitions": fold["partitions"],
                        "evaluation": {
                            key: value for key, value in fold["evaluation"].items() if key != "trace"
                        },
                    }
                    for fold in report["result"]["folds"]
                ],
            },
        }

    def page_help(topic: Topic = "overview") -> dict:
        """Explain Forecasting controls, input requirements, baseline intervals or model availability.

        Choose a topic for concrete instructions and an in-app link. Use overview for orientation.
        """
        return read_guide(GUIDES, topic)

    agent = Agent(
        name="sibyl-chronos",
        description=DESCRIPTION,
        tools=[
            price_forecast,
            Tool.from_callable(forecast_method, sync_execution="inline"),
            Tool.from_callable(page_help, sync_execution="inline"),
            trained_models,
            model_report,
            rolling_evaluation,
            forecast_outcomes,
        ],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent
