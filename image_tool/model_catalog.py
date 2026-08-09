"""Immutable metadata for redistributable offline inference models."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    """Describe one checksummed model and its upstream license."""

    model_id: str
    filename: str
    url: str
    sha256: str
    expected_size: int
    display_key: str
    license_name: str
    license_url: str


MODEL_CATALOG: dict[str, ModelArtifact] = {
    "u2net": ModelArtifact(
        model_id="u2net",
        filename="u2net.onnx",
        url="https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx",
        sha256="8d10d2f3bb75ae3b6d527c77944fc5e7dcd94b29809d47a739a7a728a912b491",
        expected_size=175_997_641,
        display_key="model.u2net",
        license_name="Apache-2.0",
        license_url="https://github.com/xuebinqin/U-2-Net/blob/master/LICENSE",
    ),
    "u2netp": ModelArtifact(
        model_id="u2netp",
        filename="u2netp.onnx",
        url="https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx",
        sha256="309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8",
        expected_size=4_574_861,
        display_key="model.u2netp",
        license_name="Apache-2.0",
        license_url="https://github.com/xuebinqin/U-2-Net/blob/master/LICENSE",
    ),
}
