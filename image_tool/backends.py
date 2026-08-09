from __future__ import annotations

import hashlib
import json
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from .config import BackendConfig


TENSORRT_PROVIDER = "TensorrtExecutionProvider"
CUDA_PROVIDER = "CUDAExecutionProvider"
DIRECTML_PROVIDER = "DmlExecutionProvider"
CPU_PROVIDER = "CPUExecutionProvider"


@dataclass(frozen=True, slots=True)
class BackendEvent:
    """One user-visible backend activation or fallback message."""

    level: str
    message: str
    provider: str | None = None


class SessionFactory(Protocol):
    """Factory contract used to isolate ONNX Runtime from backend selection tests."""

    def __call__(
        self,
        model_path: Path,
        session_options: object,
        providers: Sequence[str | tuple[str, dict[str, Any]]],
    ) -> object:
        """Create and return one ONNX inference session."""


class IInferenceBackend(ABC):
    """Abstraction for a single reusable inference backend and ONNX session."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Return the Vietnamese user-facing backend label."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the primary ONNX Runtime execution provider name."""

    @abstractmethod
    def is_available(self, available_providers: set[str]) -> bool:
        """Return whether required providers are present in this runtime."""

    @abstractmethod
    def load(self, model_path: Path) -> None:
        """Create the backend's one reusable session."""

    @abstractmethod
    def infer(self, input_tensor: np.ndarray) -> np.ndarray:
        """Run one inference and return the primary raw model output."""

    @abstractmethod
    def close(self) -> None:
        """Release references to native session resources."""


def _default_session_factory(
    model_path: Path,
    session_options: object,
    providers: Sequence[str | tuple[str, dict[str, Any]]],
) -> object:
    """Create an ONNX Runtime session without importing ORT at module import time."""
    import onnxruntime as ort

    return ort.InferenceSession(str(model_path), sess_options=session_options, providers=list(providers))


class OrtInferenceBackend(IInferenceBackend):
    """Base implementation shared by concrete ONNX Runtime providers."""

    provider = CPU_PROVIDER
    label = "CPU"

    def __init__(self, config: BackendConfig, session_factory: SessionFactory = _default_session_factory) -> None:
        self._config = config
        self._session_factory = session_factory
        self._session: object | None = None
        self._input_name: str | None = None

    @property
    def display_name(self) -> str:
        """Return the Vietnamese user-facing backend label."""
        return self.label

    @property
    def provider_name(self) -> str:
        """Return the primary ONNX Runtime provider name."""
        return self.provider

    def is_available(self, available_providers: set[str]) -> bool:
        """Return whether this provider is available in the installed runtime."""
        return self.provider in available_providers

    def load(self, model_path: Path) -> None:
        """Create one session and cache its input name."""
        if self._session is not None:
            return
        if not model_path.is_file():
            raise FileNotFoundError(f"Không tìm thấy model offline: {model_path}")
        options = self._create_session_options()
        session = self._session_factory(model_path, options, self._providers())
        active = set(getattr(session, "get_providers")())
        if self.provider not in active:
            raise RuntimeError(f"ONNX Runtime không kích hoạt được {self.provider}.")
        inputs = getattr(session, "get_inputs")()
        if not inputs:
            raise RuntimeError("Model ONNX không có input hợp lệ.")
        self._session = session
        self._input_name = inputs[0].name

    def infer(self, input_tensor: np.ndarray) -> np.ndarray:
        """Run the cached session exactly once for one input tensor."""
        if self._session is None or self._input_name is None:
            raise RuntimeError("Backend AI chưa được chuẩn bị.")
        outputs = getattr(self._session, "run")(None, {self._input_name: input_tensor})
        if not outputs or not isinstance(outputs[0], np.ndarray):
            raise RuntimeError("Backend AI trả về output không hợp lệ.")
        return outputs[0]

    def close(self) -> None:
        """Release the only session owned by this backend."""
        self._input_name = None
        self._session = None

    def _create_session_options(self) -> object:
        """Build provider-safe session options."""
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        options.log_severity_level = 3
        return options

    def _providers(self) -> Sequence[str | tuple[str, dict[str, Any]]]:
        """Return provider configuration for session construction."""
        return [self.provider]


class TensorRTCudaFp16Backend(OrtInferenceBackend):
    """TensorRT backend with CUDA fallback for unsupported graph nodes."""

    provider = TENSORRT_PROVIDER
    label = "GPU TensorRT / CUDA FP16"

    def is_available(self, available_providers: set[str]) -> bool:
        """Require both TensorRT and CUDA providers in the installed runtime."""
        return (
            self._config.enable_tensorrt_fp16
            and TENSORRT_PROVIDER in available_providers
            and CUDA_PROVIDER in available_providers
        )

    def load(self, model_path: Path) -> None:
        """Load TensorRT FP16 only after a model-hash-bound alpha quality check."""
        if not self._fp16_quality_approved(model_path):
            raise RuntimeError("FP16 chưa có benchmark alpha hợp lệ cho đúng SHA256 model này")
        super().load(model_path)

    def _providers(self) -> Sequence[str | tuple[str, dict[str, Any]]]:
        cache = self._config.tensorrt_cache_directory
        trt_options = {
            "trt_fp16_enable": True,
            "trt_max_workspace_size": self._config.tensorrt_workspace_bytes,
            "trt_engine_cache_enable": bool(cache),
        }
        if cache is not None:
            cache.mkdir(parents=True, exist_ok=True)
            trt_options["trt_engine_cache_path"] = str(cache)
        cuda_options = {"gpu_mem_limit": self._config.gpu_memory_limit_bytes, "arena_extend_strategy": "kSameAsRequested"}
        return [(TENSORRT_PROVIDER, trt_options), (CUDA_PROVIDER, cuda_options)]

    def _fp16_quality_approved(self, model_path: Path) -> bool:
        """Only enable FP16 when a benchmark manifest explicitly approves it."""
        manifest = self._config.fp16_quality_manifest or model_path.with_suffix(".fp16-quality.json")
        if not manifest.is_file():
            return False
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            return (
                bool(data.get("approved"))
                and data.get("model_sha256") == sha256_file(model_path)
                and float(data.get("alpha_mae", 999.0)) <= float(data.get("max_alpha_mae", 1.0))
            )
        except (OSError, ValueError, TypeError):
            return False


class CudaExecutionBackend(OrtInferenceBackend):
    """CUDA backend configured to remain safe on a 4 GB GPU."""

    provider = CUDA_PROVIDER
    label = "GPU CUDA"

    def _providers(self) -> Sequence[str | tuple[str, dict[str, Any]]]:
        return [(CUDA_PROVIDER, {"gpu_mem_limit": self._config.gpu_memory_limit_bytes, "arena_extend_strategy": "kSameAsRequested"})]


class DirectMLExecutionBackend(OrtInferenceBackend):
    """DirectML backend for NVIDIA, AMD, and Intel GPUs on Windows."""

    provider = DIRECTML_PROVIDER
    label = "GPU DirectML"

    def _create_session_options(self) -> object:
        import onnxruntime as ort

        options = super()._create_session_options()
        options.enable_mem_pattern = False
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        return options


class CpuExecutionBackend(OrtInferenceBackend):
    """Portable CPU fallback backend."""

    provider = CPU_PROVIDER
    label = "CPU fallback"

    def _create_session_options(self) -> object:
        options = super()._create_session_options()
        options.intra_op_num_threads = self._config.cpu_threads
        options.inter_op_num_threads = 1
        return options


BackendFactory = Callable[[], IInferenceBackend]


def backend_priority() -> tuple[str, ...]:
    """Return the required automatic backend priority order."""
    return (TENSORRT_PROVIDER, CUDA_PROVIDER, DIRECTML_PROVIDER, CPU_PROVIDER)


def detect_available_providers() -> set[str]:
    """Return installed ONNX providers, falling back to CPU on import failure."""
    try:
        import onnxruntime as ort

        return set(ort.get_available_providers())
    except (ImportError, OSError):
        return {CPU_PROVIDER}


class InferenceBackendManager:
    """Select, reuse, serialize, and safely fall back between inference backends."""

    def __init__(
        self,
        model_directory: Path,
        config: BackendConfig | None = None,
        available_providers: set[str] | None = None,
        factories: Sequence[BackendFactory] | None = None,
        on_event: Callable[[BackendEvent], None] | None = None,
    ) -> None:
        self._model_directory = model_directory
        self._config = config or BackendConfig()
        self._available = available_providers if available_providers is not None else detect_available_providers()
        self._on_event = on_event
        self._lock = threading.RLock()
        self._shutdown_requested = threading.Event()
        self._active: IInferenceBackend | None = None
        self._model_name: str | None = None
        self._candidate_index = -1
        self._factories = list(factories) if factories is not None else [
            lambda: TensorRTCudaFp16Backend(self._config),
            lambda: CudaExecutionBackend(self._config),
            lambda: DirectMLExecutionBackend(self._config),
            lambda: CpuExecutionBackend(self._config),
        ]

    @property
    def active_provider(self) -> str:
        """Return the active provider or a not-yet-ready label."""
        with self._lock:
            return self._active.provider_name if self._active is not None else "Chưa khởi tạo"

    @property
    def active_display_name(self) -> str:
        """Return the active user-facing backend label."""
        with self._lock:
            return self._active.display_name if self._active is not None else "Đang chuẩn bị AI"

    def prepare(self, model_name: str) -> str:
        """Load exactly one session for the selected model and return its provider."""
        with self._lock:
            if self._shutdown_requested.is_set():
                raise RuntimeError("Ứng dụng đang đóng; không thể nạp AI.")
            if self._active is not None and self._model_name == model_name:
                return self._active.provider_name
            self._close_active()
            self._model_name = model_name
            self._candidate_index = -1
            self._activate_next(model_name, None)
            assert self._active is not None
            return self._active.provider_name

    def infer(self, model_name: str, input_tensor: np.ndarray) -> tuple[np.ndarray, str]:
        """Run serialized inference and fall back after a provider failure."""
        with self._lock:
            self.prepare(model_name)
            while True:
                assert self._active is not None
                try:
                    return self._active.infer(input_tensor), self._active.provider_name
                except Exception as exc:
                    failed = self._active.display_name
                    failed_provider = self._active.provider_name
                    self._emit("warning", f"{failed} lỗi khi inference: {exc}. Đang fallback an toàn.", failed_provider)
                    self._close_active()
                    self._activate_next(model_name, exc)

    def request_shutdown(self) -> None:
        """Signal background preload to dispose a session instead of publishing it."""
        self._shutdown_requested.set()

    def close(self) -> None:
        """Stop future loads and release the active session."""
        self._shutdown_requested.set()
        with self._lock:
            self._close_active()

    def _activate_next(self, model_name: str, previous_error: Exception | None) -> None:
        model_path = self._model_directory / f"{model_name}.onnx"
        errors: list[str] = []
        while self._candidate_index + 1 < len(self._factories):
            self._candidate_index += 1
            backend = self._factories[self._candidate_index]()
            if not backend.is_available(self._available):
                self._emit(
                    "info",
                    f"Bỏ qua {backend.display_name}: provider/dependency không có trong runtime này.",
                    None,
                )
                continue
            try:
                backend.load(model_path)
                if self._shutdown_requested.is_set():
                    backend.close()
                    raise RuntimeError("Ứng dụng đang đóng.")
                self._active = backend
                self._emit("info", f"Đã kích hoạt {backend.display_name}.", backend.provider_name)
                return
            except Exception as exc:
                backend.close()
                errors.append(f"{backend.display_name}: {exc}")
                self._emit("warning", f"Không thể dùng {backend.display_name}: {exc}. Đang thử backend tiếp theo.", backend.provider_name)
        prefix = f"Backend trước đó lỗi: {previous_error}. " if previous_error is not None else ""
        raise RuntimeError(prefix + "Không có backend AI khả dụng. " + " | ".join(errors))

    def _close_active(self) -> None:
        if self._active is not None:
            self._active.close()
            self._active = None

    def _emit(self, level: str, message: str, provider: str | None) -> None:
        if self._on_event is not None:
            self._on_event(BackendEvent(level, message, provider))


def sha256_file(path: Path) -> str:
    """Return the SHA256 digest of a model or release artifact."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
