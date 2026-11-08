"""Small explicit domain adapters; adding a type never permits arbitrary code execution."""

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from sibyl.forecasting.contracts import TrainForecast
from sibyl.forecasting.drift import Recalibrate
from sibyl.operations.jobs.contracts import AccountingArguments, NoArguments
from sibyl.strategies.plugins.contracts import PluginBacktest
from sibyl.strategies.research.adaptive.contracts import AdaptiveStudy


@dataclass(frozen=True)
class Handler:
    """A private callable and public input contract; result must be safe for the workspace UI."""

    name: str
    label: str
    description: str
    arguments: type[BaseModel]
    execute: Callable
    restart_safe: bool = True
    repeatable: bool = True
    creation_url: str | None = None
    prepare: Callable | None = None

    def validate(self, arguments):
        try:
            validated = self.arguments.model_validate(arguments).model_dump(mode="json")
        except ValidationError:
            raise ValueError(
                "Choose valid settings for this job type; unsupported fields are not accepted."
            ) from None

        if self.prepare:
            self.prepare(validated)
        return validated

    def public(self):
        return {
            "id": self.name,
            "label": self.label,
            "description": self.description,
            "restart_safe": self.restart_safe,
            "repeatable": self.repeatable,
            "creation_url": self.creation_url,
            "input_schema": self.arguments.model_json_schema(),
        }


def application_handlers(performance, forecasts, workers, strategies=None):
    """Bind owned services without serializing them or any decrypted configuration."""

    def accounting(arguments):
        result = performance.account_books.report(
            account_id=arguments["account_id"],
            environment_filter=arguments["environment"],
            currency=arguments["currency"],
            source=arguments["source"],
        )
        return {
            **{
                key: result[key]
                for key in (
                    "currency",
                    "source",
                    "as_of",
                    "input_fingerprint",
                    "fill_count",
                    "funding_count",
                    "note",
                )
            },
            "reports": [
                {
                    "environment": group["environment"],
                    "items": group["items"][:100],
                    "asset_count": len(group["items"]),
                }
                for group in result["reports"]
            ],
            "asset_evidence_limit": 100,
        }

    def training(arguments):
        body = TrainForecast.model_validate(arguments)
        if body.input_kind != "saved_dataset":
            raise ValueError(
                "Scheduled training requires a pinned saved dataset; live fetches must be configured through the forecast lifecycle."
            )
        result = forecasts.train(body)
        return {
            "model_id": result["model"]["id"],
            "version": result["model"]["version"],
            "url": "/forecast",
            "note": "A local trained model was retained. Cancellation cannot undo a model already committed.",
        }

    handlers = [
        Handler(
            "forecast.recalibrate",
            "Check forecast recalibration policy",
            "Check retained exact-source drift and train a candidate only when its saved revision, new-day threshold and cooldown allow it. No provider fetch or promotion.",
            Recalibrate,
            lambda arguments: forecasts.drift.recalibrate(Recalibrate(**arguments)),
            restart_safe=False,
        ),
        Handler(
            "workspace.health",
            "Workspace health check",
            "Run a bounded read-only SQLite check and retain content-free runtime diagnostics.",
            NoArguments,
            lambda _args: workers.diagnostics.run(),
        ),
        Handler(
            "account.accounting",
            "Retained account accounting",
            "Calculate cross-pair books from already imported fills, funding and price candles.",
            AccountingArguments,
            accounting,
        ),
        Handler(
            "forecast.train",
            "Train a pinned forecast recipe",
            "Fit a local model from a saved immutable daily dataset. Interrupted fitting is not automatically repeated.",
            TrainForecast,
            training,
            restart_safe=False,
            repeatable=False,
        ),
    ]

    if strategies is not None:

        def adaptive(arguments):
            result = strategies.adaptive.run(AdaptiveStudy.model_validate(arguments))
            return {
                "report_id": result["id"],
                "kind": "adaptive_study",
                "research_status": result["status"],
                "url": "/strategies",
            }

        handlers.extend(
            [
                Handler(
                    "strategy.adaptive",
                    "Adaptive strategy research",
                    "Run native optional Optuna distributions on a pinned dataset, with training-only selection and independent chronological tests.",
                    AdaptiveStudy,
                    adaptive,
                    restart_safe=False,
                    repeatable=False,
                    creation_url="/strategies",
                    prepare=strategies.adaptive.validate,
                ),
                Handler(
                    "strategy.plugin",
                    "Pinned custom strategy backtest",
                    "Run an explicitly installed trusted plugin against an immutable dataset. No execution or inference replay.",
                    PluginBacktest,
                    strategies.adaptive.pinned_plugin_run,
                    restart_safe=False,
                    repeatable=False,
                    creation_url="/strategies",
                    prepare=strategies.adaptive.validate_plugin,
                ),
            ]
        )
    return handlers
