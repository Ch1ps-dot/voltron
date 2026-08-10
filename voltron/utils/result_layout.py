"""Canonical paths for diagnostics saved with one Voltron run."""

from pathlib import Path


def diagnostics_path(
    results_path: Path,
    category: str,
    filename: str,
) -> Path:
    """Return one diagnostics artifact path without creating it."""
    return Path(results_path) / 'diagnostics' / category / filename
