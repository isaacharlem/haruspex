"""Default GPU hourly prices in USD.

These are editable estimates for cost accounting, not market truth. Override
per run via ``gpu_hourly_usd`` at registration; unknown GPU types fall back to
``FALLBACK_GPU_HOURLY_USD``. The SDK ships the same table.
"""

GPU_HOURLY_USD_DEFAULTS: dict[str, float] = {
    "H100": 2.50,
    "H200": 3.20,
    "A100": 1.50,
    "A10G": 0.75,
    "L40S": 0.90,
    "L4": 0.45,
    "V100": 0.60,
    "T4": 0.35,
}

FALLBACK_GPU_HOURLY_USD = 1.00


def default_hourly_usd(gpu_type: str) -> float:
    return GPU_HOURLY_USD_DEFAULTS.get(gpu_type.upper(), FALLBACK_GPU_HOURLY_USD)
