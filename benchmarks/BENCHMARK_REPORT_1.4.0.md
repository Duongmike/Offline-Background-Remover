# Báo cáo benchmark 1.4.0

Ngày đo: 2026-08-08. Máy đo: Windows 10, Intel Core i5-11400H, RAM 16 GB, NVIDIA RTX 3050 Ti Laptop 4 GB, ONNX Runtime 1.23.0. Runtime đóng gói hiện có `DmlExecutionProvider` và `CPUExecutionProvider`; CUDA/TensorRT không có trong environment này nên không có số liệu CUDA/TensorRT và không tuyên bố tăng tốc cho hai backend đó.

## Pipeline

Phiên bản 1.3.1:

```text
UI worker
  -> Decode + EXIF
  -> rembg: preprocess -> ONNX -> mask/composite
  -> Resize
  -> PNG level 6
  -> Temp file -> atomic replace
```

Phiên bản 1.4.0:

```text
Bounded source queue
  -> 2 Decode/Preprocess CPU workers
  -> bounded inference queue
  -> 1 backend / 1 ONNX session / serialized inference
  -> bounded encode queue
  -> 2 Postprocess/Encode CPU workers
  -> Temp file -> atomic replace
```

`max_inflight_images=4`, mỗi queue có capacity 2. Không dùng multiprocessing và không tạo nhiều GPU session.

## Warm single-image stages (median 3 lần, ms)

| Kích thước | Bản | Decode | Preprocess | Inference | Postprocess | Encode/save | Tổng stage |
|---:|---|---:|---:|---:|---:|---:|---:|
| 512 | 1.3.1 | 1.67 | 6.52 | 30.74 | 4.41 | 5.94 | 49.13 |
| 512 | 1.4.0 | 2.35 | 5.05 | 28.55 | 4.31 | 5.96 | 47.85 |
| 1024 | 1.3.1 | 4.78 | 13.38 | 28.38 | 15.06 | 19.64 | 88.56 |
| 1024 | 1.4.0 | 5.30 | 14.97 | 28.11 | 15.29 | 21.43 | 85.53 |
| 2048 | 1.3.1 | 14.96 | 39.35 | 28.33 | 52.13 | 73.55 | 206.95 |
| 2048 | 1.4.0 | 20.28 | 44.89 | 28.12 | 62.41 | 74.66 | 232.64 |

Kết luận: warm inference gần như không đổi vì vẫn là cùng model U²-Net/DirectML. Một ảnh 512/1024 nhanh hơn nhẹ trong lần đo này; một ảnh 2048 chậm hơn 12,4%, vì vậy không tuyên bố single-image 2048 nhanh hơn. Preload làm phần model load/warm-up diễn ra khi UI vẫn thao tác được.

## Cold start và tài nguyên

| Chỉ số | 1.3.1 | 1.4.0 |
|---|---:|---:|
| Model load quan sát (ms) | 1088.69 | 768.04 |
| Ready -> output đầu 512 (ms) | 1159.93 | 835.47 |
| RAM sau load (MB) | 443.88 | 335.28 |
| RAM peak (MB) | 496.37 | 380.27 |
| VRAM peak (MB) | 699 | 699 |

Cold load chịu ảnh hưởng cache Windows/driver (một lần baseline khác là 855,35 ms). Số liệu trên là lần chạy được lưu trong JSON, không dùng để khẳng định mọi máy đều giảm cùng tỷ lệ. Lợi ích người dùng ổn định hơn là preload background: UI không bị khóa và thao tác đầu tiên tái sử dụng session đã warm.

## Batch warm, 8 ảnh

| Kích thước | 1.3.1 tuần tự, PNG 6 | 1.4.0 pipeline, PNG 6 | Speedup pipeline | 1.4.0 pipeline, PNG 1 | Speedup mặc định |
|---:|---:|---:|---:|---:|---:|
| 512 | 383.37 ms | 261.42 ms | 1.47x | 243.06 ms | 1.58x |
| 1024 | 691.39 ms | 292.98 ms | 2.36x | 274.48 ms | 2.52x |
| 2048 | 1753.24 ms | 741.38 ms | 2.36x | 720.16 ms | 2.43x |

So sánh PNG 6 với PNG 6 chứng minh pipeline có lợi độc lập với profile nén. Alpha MAE giữa output mới và cũ chỉ 0,00001-0,00003 trên thang 0-255.

## PNG 2048 RGBA

Benchmark xen kẽ 10 lần/profile trên ảnh RGBA 2048 tương đương:

| Profile | Level | Median | Kích thước mẫu | Alpha |
|---|---:|---:|---:|---|
| Nhanh | 1 | 37.82 ms | 194,913 B | Chính xác |
| Cân bằng | 6 | 40.83 ms | 42,575 B | Chính xác |
| File nhỏ | 9 | 81.45 ms | 35,841 B | Chính xác |

Trade-off: Nhanh giảm vài mili giây nhưng file mẫu lớn hơn khoảng 4,6 lần so với Cân bằng. File nhỏ tiết kiệm thêm khoảng 16% so với Cân bằng nhưng encode gần gấp đôi. Cả ba đều PNG lossless và giữ alpha chính xác.
