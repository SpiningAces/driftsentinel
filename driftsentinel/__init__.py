"""Drift Sentinel — watch your OpenAPI spec for the gap between what it says and what your API does.

Public API:
  - compute_adi(results, weights, caps) -> dict
  - ADI_DEFAULTS: default weights and caps for the Drift Score

Run via CLI:
  driftsentinel audit ./openapi.yaml --url https://api.example.com
  driftsentinel verify ./out/report.pdf
"""
from .cli import compute_adi, load_adi_config, ADI_DEFAULTS

__version__ = "0.0.1"
__all__ = ["compute_adi", "load_adi_config", "ADI_DEFAULTS", "__version__"]
