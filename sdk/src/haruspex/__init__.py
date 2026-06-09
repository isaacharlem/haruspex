"""Haruspex SDK: instrument training runs for live outcome forecasting."""

from haruspex.client import HaruspexClient
from haruspex.errors import HaruspexAPIError, HaruspexConnectionError, HaruspexError
from haruspex.run import Run, init

__version__ = "0.1.0"

__all__ = [
    "HaruspexAPIError",
    "HaruspexClient",
    "HaruspexConnectionError",
    "HaruspexError",
    "Run",
    "init",
]
