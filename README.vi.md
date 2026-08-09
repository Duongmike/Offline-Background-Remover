# Xóa Nền AI Offline

[![CI](https://github.com/Duongmike/Offline-Background-Remover/actions/workflows/ci.yml/badge.svg)](https://github.com/Duongmike/Offline-Background-Remover/actions/workflows/ci.yml)
[![Bản phát hành mới nhất](https://img.shields.io/github/v/release/Duongmike/Offline-Background-Remover?display_name=tag)](https://github.com/Duongmike/Offline-Background-Remover/releases/latest)
[![Lượt tải](https://img.shields.io/github/downloads/Duongmike/Offline-Background-Remover/total)](https://github.com/Duongmike/Offline-Background-Remover/releases)
[![Giấy phép: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[English](README.md) · **Tiếng Việt**

Xóa Nền AI Offline là ứng dụng desktop Windows để xóa nền AI, tách nền theo
màu nâng cao, xử lý hàng loạt và resize ảnh. Ảnh chỉ được xử lý trên máy của
người dùng, không tải lên dịch vụ bên ngoài.

> **Bản hiện tại:** v1.5.2. Dự án đang được phát triển tích cực; toàn bộ workflow
> hỗ trợ English và Tiếng Việt, đồng thời lưu lựa chọn ngôn ngữ của người dùng.

![Giao diện Offline Background Remover](ui_preview.png)

## Tính năng

- Xử lý một ảnh hoặc cả folder và giữ nguyên cấu trúc folder con.
- Ba chiến lược xóa nền: AI tự động, theo màu nâng cao và Hybrid AI + màu.
- Preview ảnh gốc/kết quả ở chế độ một ảnh trước khi mở file đã tạo.
- Nhiều mẫu nền, overlay mask, cọ Giữ lại/Xóa thêm, Undo/Redo 20 lệnh.
- Chuyển toàn bộ workflow và tên ứng dụng hiển thị bằng nút gọn `EN | VI` trên
  header mà không cần mở lại app.
- Kiểm tra, tải và sửa model đã ghim SHA256 bằng Model Manager chạy nền.
- Giao diện AI mặc định gọn; bộ điều khiển màu chỉ mở ở chế độ Theo màu/Hybrid
  và hiển thị ô màu trực quan cạnh mã hex của từng mẫu.
- Resize theo phần trăm, khung W × H hoặc giới hạn cạnh dài.
- Preload AI trong background, cancellation, back-pressure và atomic save.
- Bản phân phối Windows dùng DirectML → CPU fallback. Adapter CUDA/TensorRT chỉ
  được bật khi có runtime tương thích và benchmark phần cứng tái lập được.
- Chạy hoàn toàn offline sau lần cài đặt model đầu tiên.

## Tải và cài đặt trên Windows

Tải bộ cài đã được kiểm tra tại **[GitHub Releases](https://github.com/Duongmike/Offline-Background-Remover/releases/latest)**:

1. Tải `KhongBietGiDungNoi_Setup_1.5.2.exe` và `SHA256SUMS.txt`.
2. Có thể xác minh bộ cài trước khi chạy:

   ```powershell
   (Get-FileHash .\KhongBietGiDungNoi_Setup_1.5.2.exe -Algorithm SHA256).Hash
   Get-Content .\SHA256SUMS.txt
   ```

3. Chạy bộ cài; bản đóng gói không yêu cầu cài Python.

Installer đã gồm model U²-Net được ghim phiên bản và DirectML runtime nên có thể
xử lý ảnh offline ngay sau khi cài. Internet chỉ cần khi tải Release hoặc sửa model
từ Model Manager. Ứng dụng không upload ảnh của người dùng.

## Chọn chế độ xóa nền

- **AI tự động:** lựa chọn đầu tiên cho người, sản phẩm hoặc ảnh có chủ thể chính rõ.
- **Theo màu nâng cao:** phù hợp nền tương đối đồng nhất; có thể lấy nhiều mẫu nền
  và chỉnh bảo vệ cạnh khi màu vật thể gần giống màu nền.
- **Hybrid AI + màu:** kết hợp cấu trúc AI với các màu đã lấy mẫu cho ảnh studio
  hoặc ảnh sản phẩm khó.
- **Cọ Giữ lại/Xóa thêm:** sửa vùng mask nhỏ với Undo/Redo 20 bước khi kết quả tự
  động chưa đủ sạch.

## Kiến trúc

```text
Giao diện desktop
    │
    ▼
BatchImageService
    │
    ├── AI tự động ─────────┐
    ├── Theo màu nâng cao ──┼──► bounded pipeline ─► atomic PNG output
    └── Hybrid AI + màu ────┘
             │
             ▼
InferenceBackendManager
    └── runtime phân phối: DirectML → CPU
```

Pipeline giới hạn tối đa bốn ảnh full-resolution đang xử lý và chỉ giữ một ONNX
session tại một thời điểm. GPU inference được serialize để không nhân bản model
hoặc VRAM.

## Chạy từ source

Yêu cầu Windows 10 trở lên và Python 3.10 hoặc 3.11 64-bit.

```powershell
git clone https://github.com/Duongmike/Offline-Background-Remover.git
cd Offline-Background-Remover
setup.bat
run.bat
```

`setup.bat` tạo `.venv`, cài dependencies, tải model U²-Net và kiểm tra SHA256.
Sau khi setup xong, app không cần Internet để xử lý ảnh. Model Manager trong app
có thể kiểm tra hoặc sửa các model đã ghim mà không khóa Tkinter UI.

## Test và build

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
build.bat
build_installer.bat
```

Binary sinh ra không được commit vào Git. Installer chính thức và file checksum
sẽ được phát hành tại [GitHub Releases](https://github.com/Duongmike/Offline-Background-Remover/releases).

Maintainer có thể chạy workflow Release thủ công để dry-run build mà không phát
hành. Khi push tag `vMAJOR.MINOR.PATCH`, workflow chỉ tạo GitHub Release nếu tag
khớp phiên bản canonical, toàn bộ test đạt, packaged self-test, UI smoke test,
installer build và kiểm tra checksum đều thành công.

## Benchmark

```powershell
.venv\Scripts\python.exe -m image_tool.benchmark --model u2net --repeats 3 --output benchmarks\after_local.json
```

Xem phương pháp đo, environment, stage timings và giới hạn của kết quả tại
[báo cáo benchmark](benchmarks/BENCHMARK_REPORT_1.4.0.md). Dự án không tuyên bố
phần trăm chất lượng khi chưa có bộ dữ liệu ground-truth được gắn nhãn.

## Quality regression

Repo chứa tám fixture alpha synthetic CC0 có thể tái tạo. Bộ này dùng để kiểm tra
evaluator và quality gate trong CI, không phải bằng chứng chất lượng ảnh thực tế.

```powershell
.venv\Scripts\python.exe -m image_tool.quality `
  --manifest quality_dataset\starter\manifest.json `
  --predictions quality_results\starter-u2netp `
  --run-model u2netp `
  --output quality_results\starter-u2netp.json
```

Report ghi MAE, SAD, IoU, F1, provider, platform và timing từng case. Đọc
[hướng dẫn quality dataset](quality_dataset/README.md) trước khi thêm ảnh thật.

## Roadmap

- [x] Giao diện English và Tiếng Việt, lưu lựa chọn ngôn ngữ
- [x] Quy trình phát hành theo tag có thể tái tạo
- [ ] Bộ dữ liệu regression chất lượng ảnh lớn hơn
- [ ] Benchmark trên nhiều GPU và phần cứng hơn
- [x] Model Manager có kiểm tra SHA256
- [ ] Điểm mở rộng rõ ràng cho removal backend mới

## Đóng góp

Bug report, tài liệu, test, bản dịch, benchmark và pull request có phạm vi rõ
ràng đều được chào đón. Đọc [CONTRIBUTING.md](CONTRIBUTING.md) trước khi bắt đầu.
Lỗ hổng bảo mật cần được báo cáo riêng theo [SECURITY.md](SECURITY.md).

Source của ứng dụng dùng [MIT License](LICENSE). Model và dependencies giữ
license riêng; xem [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
