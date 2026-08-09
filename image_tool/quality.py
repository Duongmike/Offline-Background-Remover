"""Licensed alpha-mask dataset validation and reproducible quality metrics."""
from __future__ import annotations

import argparse
import json
import os
import platform
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Any

import numpy as np
from PIL import Image

from .models import PngCompressionMode, ResizeOptions, SingleImageOptions
from .processing import BatchImageService


@dataclass(frozen=True, slots=True)
class QualityCase:
    """One licensed input, ground-truth alpha mask, and expected prediction name."""

    case_id: str
    category: str
    input_path: Path
    ground_truth_path: Path
    prediction_name: str
    license_name: str
    source: str


@dataclass(frozen=True, slots=True)
class AlphaMetrics:
    """Common normalized alpha and binary-mask metrics."""

    mae: float
    sad: float
    iou: float
    f1: float


def alpha_metrics(predicted: np.ndarray, expected: np.ndarray) -> AlphaMetrics:
    """Calculate normalized MAE/SAD and thresholded IoU/F1 for two alpha masks."""
    if predicted.shape != expected.shape:
        raise ValueError(f"Mask shape mismatch: predicted={predicted.shape}, expected={expected.shape}")
    predicted_float = predicted.astype(np.float32) / 255.0
    expected_float = expected.astype(np.float32) / 255.0
    difference = np.abs(predicted_float - expected_float)
    predicted_binary = predicted >= 128
    expected_binary = expected >= 128
    intersection = int(np.logical_and(predicted_binary, expected_binary).sum())
    union = int(np.logical_or(predicted_binary, expected_binary).sum())
    predicted_count = int(predicted_binary.sum())
    expected_count = int(expected_binary.sum())
    iou = intersection / union if union else 1.0
    denominator = predicted_count + expected_count
    f1 = (2.0 * intersection / denominator) if denominator else 1.0
    return AlphaMetrics(float(difference.mean()), float(difference.sum()), float(iou), float(f1))


def _safe_dataset_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Dataset path escapes its manifest directory: {relative}") from exc
    return path


def load_manifest(path: Path) -> tuple[str, list[QualityCase]]:
    """Load a versioned dataset manifest and enforce attribution on every case."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("Quality dataset schema_version must be 1")
    dataset_license = str(data.get("license", "")).strip()
    if not dataset_license:
        raise ValueError("Quality dataset must declare a license")
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Quality dataset must contain at least one case")
    root = path.parent
    cases: list[QualityCase] = []
    seen: set[str] = set()
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise ValueError("Quality dataset cases must be objects")
        case_id = str(raw.get("id", "")).strip()
        if not case_id or case_id in seen:
            raise ValueError(f"Missing or duplicate quality case id: {case_id!r}")
        seen.add(case_id)
        license_name = str(raw.get("license", dataset_license)).strip()
        source = str(raw.get("source", "")).strip()
        if not license_name or not source:
            raise ValueError(f"Quality case {case_id!r} must include license and source")
        input_path = _safe_dataset_path(root, str(raw.get("input", "")))
        ground_truth_path = _safe_dataset_path(root, str(raw.get("ground_truth", "")))
        if not input_path.is_file() or not ground_truth_path.is_file():
            raise ValueError(f"Quality case {case_id!r} references a missing file")
        cases.append(QualityCase(
            case_id=case_id,
            category=str(raw.get("category", "uncategorized")),
            input_path=input_path,
            ground_truth_path=ground_truth_path,
            prediction_name=str(raw.get("prediction", f"{case_id}.png")),
            license_name=license_name,
            source=source,
        ))
    return str(data.get("name", path.stem)), cases


def _read_alpha(path: Path, ground_truth: bool = False) -> np.ndarray:
    with Image.open(path) as image:
        if ground_truth and image.mode in {"1", "L", "I", "F"}:
            alpha = image.convert("L")
        elif "A" in image.getbands():
            alpha = image.getchannel("A")
        else:
            alpha = image.convert("L")
        try:
            return np.asarray(alpha, dtype=np.uint8).copy()
        finally:
            alpha.close()


def run_predictions(cases: list[QualityCase], directory: Path, model_name: str) -> tuple[str, dict[str, float]]:
    """Generate predictions with one reusable session and return provider/timings."""
    directory.mkdir(parents=True, exist_ok=True)
    service = BatchImageService()
    timings: dict[str, float] = {}
    try:
        for case in cases:
            destination = directory / case.prediction_name
            progress_items = []
            result = service.process_single(
                SingleImageOptions(
                    source_file=case.input_path,
                    output_file=destination,
                    remove_background=True,
                    resize=ResizeOptions(),
                    overwrite=True,
                    model_name=model_name,
                    png_compression=PngCompressionMode.FAST,
                ),
                Event(),
                progress_items.append,
            )
            if result.failed or not destination.is_file():
                detail = progress_items[-1].error if progress_items else "unknown failure"
                raise RuntimeError(f"Prediction failed for {case.case_id}: {detail}")
            timing = progress_items[-1].timings if progress_items else None
            timings[case.case_id] = timing.total_ms if timing is not None else 0.0
        return service.active_provider, timings
    finally:
        service.close()


def evaluate_predictions(dataset_name: str, cases: list[QualityCase], directory: Path) -> dict[str, Any]:
    """Evaluate prediction alpha masks and return case/category/aggregate metrics."""
    records: list[dict[str, Any]] = []
    for case in cases:
        prediction_path = directory / case.prediction_name
        if not prediction_path.is_file():
            raise ValueError(f"Missing prediction for {case.case_id}: {prediction_path}")
        predicted = _read_alpha(prediction_path)
        expected = _read_alpha(case.ground_truth_path, ground_truth=True)
        metrics = alpha_metrics(predicted, expected)
        records.append({
            "id": case.case_id,
            "category": case.category,
            "license": case.license_name,
            "source": case.source,
            **asdict(metrics),
        })
    aggregate = {
        key: float(np.mean([record[key] for record in records]))
        for key in ("mae", "sad", "iou", "f1")
    }
    categories: dict[str, dict[str, float]] = {}
    for category in sorted({record["category"] for record in records}):
        selected = [record for record in records if record["category"] == category]
        categories[category] = {
            key: float(np.mean([record[key] for record in selected]))
            for key in ("mae", "sad", "iou", "f1")
        }
    return {"dataset": dataset_name, "case_count": len(records), "aggregate": aggregate, "categories": categories, "cases": records}


def quality_gate(report: dict[str, Any], thresholds: dict[str, object]) -> list[str]:
    """Return human-readable failures for configured aggregate regression limits."""
    aggregate = report.get("aggregate", {})
    failures: list[str] = []
    checks = (
        ("max_mae", "mae", lambda actual, expected: actual <= expected, "<="),
        ("max_sad", "sad", lambda actual, expected: actual <= expected, "<="),
        ("min_iou", "iou", lambda actual, expected: actual >= expected, ">="),
        ("min_f1", "f1", lambda actual, expected: actual >= expected, ">="),
    )
    for threshold_key, metric_key, predicate, operator in checks:
        if threshold_key not in thresholds:
            continue
        actual = float(aggregate[metric_key])
        expected = float(thresholds[threshold_key])
        if not predicate(actual, expected):
            failures.append(f"{metric_key}={actual:.6f} must be {operator} {expected:.6f}")
    return failures


def write_json_atomic(path: Path, value: object) -> None:
    """Atomically write one UTF-8 JSON report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    """Run an optional model pass followed by deterministic quality evaluation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--run-model", choices=("u2net", "u2netp"))
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        manifest_data = json.loads(arguments.manifest.read_text(encoding="utf-8"))
        dataset_name, cases = load_manifest(arguments.manifest)
        provider = None
        timings: dict[str, float] = {}
        if arguments.run_model:
            provider, timings = run_predictions(cases, arguments.predictions, arguments.run_model)
        report = evaluate_predictions(dataset_name, cases, arguments.predictions)
        report["environment"] = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "model": arguments.run_model,
            "provider": provider,
            "timings_ms": timings,
        }
        thresholds = manifest_data.get("thresholds", {})
        if not isinstance(thresholds, dict):
            raise ValueError("Quality dataset thresholds must be an object")
        failures = quality_gate(report, thresholds)
        report["quality_gate"] = {"thresholds": thresholds, "passed": not failures, "failures": failures}
        write_json_atomic(arguments.output, report)
        print(json.dumps(report["aggregate"], indent=2))
        if failures:
            print("[ERROR] Quality gate failed: " + " | ".join(failures))
            return 1
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"[ERROR] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
