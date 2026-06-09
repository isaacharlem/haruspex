"""Synthetic training-run generator: the demo and a living integration test.

It speaks only the public API through the public SDK.
"""

from haruspex.simulate.generators import PROFILES, GeneratedRun, generate

__all__ = ["PROFILES", "GeneratedRun", "generate"]
