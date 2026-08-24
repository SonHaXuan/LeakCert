from .completion_service import CompletionResult, CompletionService


def __getattr__(name):
    if name == "BackendCompletionService":
        from .backend_model import BackendCompletionService

        return BackendCompletionService
    if name in ("CanaryFineTuner", "FineTuneConfig"):
        from .fine_tuner import CanaryFineTuner, FineTuneConfig

        return {"CanaryFineTuner": CanaryFineTuner, "FineTuneConfig": FineTuneConfig}[
            name
        ]
    raise AttributeError(f"module 'leakcert.model' has no attribute {name!r}")


__all__ = [
    "BackendCompletionService",
    "CanaryFineTuner",
    "CompletionResult",
    "CompletionService",
    "FineTuneConfig",
]
