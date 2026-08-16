# Xóa Nền AI Offline

[![CI](https://github.com/Duongmike/Offline-Background-Remover/actions/workflows/ci.yml/badge.svg)](https://github.com/Duongmike/Offline-Background-Remover/actions/workflows/ci.yml)
[![Bản phát hành mới nhất](https://img.shields.io/github/v/release/Duongmike/Offline-Background-Remover?display_name=tag)](https://github.com/Duongmike/Offline-Background-Remover/releases/latest)
[![Lượt tải](https://img.shields.io/github/downloads/Duongmike/Offline-Background-Remover/total)](https://github.com/Duongmike/Offline-Background-Remover/releases)
[![Giấy phép: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10–3.11](https://img.shields.io/badge/Python-3.10%E2%80%933.11-blue.svg)](https://www.python.org/)

[English](README.md) · **Tiếng Việt**

Xóa Nền AI Offline là ứng dụng desktop Windows dùng AI để xóa nền, tách màu nâng cao, xử lý hàng loạt và resize ảnh. Ảnh chỉ được xử lý trên máy của người dùng; ứng dụng không tải lên dịch vụ bên ngoài.

> **Bản hiện tại:** v1.5.3. Dự án đang được phát triển tích cực; toàn bộ quy trình hỗ trợ English và Tiếng Việt, đồng thời lưu giữ lựa chọn ngôn ngữ.

![Giao diện Xóa Nền AI Offline](ui_preview.png)

## Tính năng chính

- Xử lý một ảnh hoặc cả thư mục và giữ nguyên cấu trúc thư mục con.
- Ba chiến lược xóa nền: AI tự động, tách màu nâng cao và lai AI + màu.
- Xem trước ảnh gốc/kết quả ở chế độ đơn ảnh trước khi mở file đã tạo.
- Nhiều mẫu nền, lớp phủ mask, cọ Giữ lại/Xóa bỏ, hoàn tác/làm lại 20 bước.
- Chuyển toàn bộ quy trình và tên ứng dụng bằng nút `EN | VI` trên header mà không cần khởi động lại.
- Kiểm tra, tải xuống và sửa model đã ghim SHA256 bằng Model Manager chạy nền.
- Giao diện AI mặc định gọn; điều khiển màu chỉ mở ở chế độ tách màu/Lai và hiển thị ô màu trực quan cạnh mã hex.
- Resize theo phần trăm, khung W×H hoặc giới hạn cạnh dài.
- Tải AI nền, hủy bỏ, kiểm soát áp lực và lưu nguyên tử.
- Bản Windows dùng DirectML → CPU fallback. Adapter CUDA/TensorRT chỉ bật khi có runtime tương thích và benchmark phần cứng.
- Chạy hoàn toàn offline sau khi model đã được cài đặt.

## Tải xuống cho Windows

Tải bộ cài đã kiểm tra từ **[GitHub Releases](https://github.com/Duongmike/Offline-Background-Remover/releases/latest)**:

1. Tải `OfflineBackgroundRemover_Setup_1.5.3.exe` và `SHA256SUMS.txt`.
2. Có thể xác minh bộ cài trước khi chạy:

   ```powershell
   (Get-FileHash .\OfflineBackgroundRemover_Setup_1.5.3.exe -Algorithm SHA256).Hash
   Get-Content .\SHA256SUMS.txt
   ```

3. Chạy bộ cài. Python không cần thiết cho bản đóng gói.

Bộ cài gồm model U²-Net đã ghim và DirectML runtime nên có thể xử lý ảnh offline ngay sau khi cài. Internet chỉ cần khi tải release hoặc sửa model từ Model Manager. Ứng dụng không tải ảnh người dùng lên bất kỳ đâu.

## Chọn chế độ xóa nền

- **AI tự động:** lựa chọn tốt nhất cho người, sản phẩm hoặc ảnh có chủ thể chính rõ ràng.
- **Tách màu nâng cao:** phù hợp nền tương đối đồng nhất; lấy nhiều mẫu nền và chỉnh bảo vệ cạnh khi màu vật thể gần giống nền.
- **Lai AI + màu:** kết hợp cấu trúc AI với các màu đã mẫu cho ảnh studio hoặc sản phẩm khó.
- **Cọ Giữ lại/Xóa bỏ:** sửa vùng mask nhỏ với hoàn tác/làm lại 20 bước khi tách tự động chưa đủ.

## Kiến trúc

```text
Giao diện Desktop
    │
    ▼
BatchImageService
    │
    ├── AI tự động ─────────┐
    ├── Tách màu nâng cao ──┼──► pipeline có kiểm soát ─► output PNG nguyên tử
    └── Lai AI + màu ───────┘
             │
             ▼
InferenceBackendManager
    └── runtime đã phân phối: DirectML → CPU
```

Pipeline giữ tối đa bốn ảnh full-resolution đang xử lý và chỉ sở hữu một ONNX session tại một thời điểm. Suy luận GPU được tuần tự hóa để không nhân bản model hay VRAM.

## Chạy từ source

Yêu cầu:

- Windows 10 trở lên, 64-bit
- Python 3.10 hoặc 3.11, 64-bit
- Internet chỉ cần trong lần setup đầu tiên cho dependencies và model AI

```powershell
git clone https://github.com/Duongmike/Offline-Background-Remover.git
cd Offline-Background-Remover
setup.bat
run.bat
```

`setup.bat` tạo `.venv`, cài dependencies runtime, tải model U²-Net và xác minh SHA256. Xử lý sau đó là offline. Model Manager trong app có thể kiểm tra hoặc sửa cùng artifacts đã ghim mà không khóa thread Tkinter.

## Kiểm thử

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Bộ test kiểm thử resize, đường dẫn Unicode, output nguyên tử, hủy bỏ, hàng đợi có kiểm soát, fallback provider, giữ alpha PNG, tách màu nâng cao, lệnh mask thủ công, tính nhất quán localization, cài đặt nguyên tử, toàn vẹn model, chỉ số chất lượng và tương đương backend cũ.

## Đánh giá chất lượng hồi quy

Repo chứa tám fixture alpha synthetic CC0 có thể tái tạo. Bộ này dùng để kiểm tra pipeline đánh giá và quality gate trong CI, không phải bằng chứng chất lượng ảnh thực tế.

```powershell
.venv\Scripts\python.exe -m image_tool.quality `
  --manifest quality_dataset\starter\manifest.json `
  --predictions quality_results\starter-u2netp `
  --run-model u2netp `
  --output quality_results\starter-u2netp.json
```

Báo cáo ghi MAE, SAD, IoU, F1, provider, platform và thời gian từng case. Xem [hướng dẫn quality dataset](quality_dataset/README.md) trước khi thêm ảnh thật.

## Xây dựng bộ cài Windows

Cài đặt [Inno Setup 6](https://jrsoftware.org/isinfo.php), sau đó chạy:

```powershell
build.bat
build_installer.bat
```

Ứng dụng và installer đã xây dựng không được commit vào Git. Binary phát hành thuộc về [GitHub Releases](https://github.com/Duongmike/Offline-Background-Remover/releases) kèm checksum SHA256.

Maintainer có thể chạy workflow Release thủ công như build dry-run. Tag khớp `vMAJOR.MINOR.PATCH` chỉ phát hành khi tag khớp phiên bản chính thức, tất cả test đạt, self-test đóng gói, UI smoke test, build installer và xác minh checksum đều thành công.

## Benchmark

```powershell
.venv\Scripts\python.exe -m image_tool.benchmark --model u2net --repeats 3 --output benchmarks\after_local.json
```

Xem [báo cáo benchmark](benchmarks/BENCHMARK_REPORT_1.4.0.md) để biết phương pháp đo, môi trường, thời gian từng giai đoạn và giới hạn kết quả. Dự án không tuyên bố phần trăm chất lượng khi chưa có bộ dữ liệu ground-truth được gắn nhãn.

## Lộ trình

- [x] English và Tiếng Việt, lưu giữ lựa chọn ngôn ngữ
- [x] Quy trình phát hành theo tag có thể tái tạo
- [ ] Bộ dữ liệu hồi quy chất lượng ảnh lớn hơn
- [ ] Benchmark trên nhiều GPU và phần cứng hơn
- [x] Model Manager có xác minh SHA256
- [ ] Điểm mở rộng rõ ràng cho backend xóa mới

## Đóng góp và bảo mật

Bug report, tài liệu, test, bản dịch, benchmark và pull request có phạm vi rõ ràng đều được chào đón. Đọc [CONTRIBUTING.md](CONTRIBUTING.md) trước khi bắt đầu. Báo cáo lỗ hổng bảo mật theo cách riêng được mô tả trong [SECURITY.md](SECURITY.md).

## Giấy phép và attribution model

Mã nguồn ứng dụng phát hành theo [MIT License](LICENSE). Model và packages bên thứ ba giữ giấy phép riêng; xem [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
