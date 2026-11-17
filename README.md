# Net Tools

Bộ công cụ mạng cho Windows 10/11, giao diện tiếng Việt. Gộp và nâng cấp từ hai app cũ **NetCheck** (đo tốc độ) và **Đổi DNS**.

![icon](assets/icon.png)

## Tính năng

| Nhóm | Trang | Làm được gì |
|---|---|---|
| Tổng quan | **Bảng điều khiển** | Card mạng, IP nội bộ/công khai, nhà mạng, DNS, VPN, biểu đồ độ trễ, nút thao tác nhanh |
| Hiệu năng | **Đo tốc độ** | Ping, Jitter, mất gói, Download, Upload (Cloudflare), đánh giá cho game/4K/họp online, lịch sử + biểu đồ |
| | **Giám sát kết nối** | Ping router + internet liên tục, tự ghi lại mỗi lần rớt mạng và đoán nguyên nhân, sao chép báo cáo |
| Kết nối | **DNS** | Cloudflare, Google, NTT, IIJ, Quad9, AdGuard, tùy chỉnh; kiểm tra DNS; benchmark và áp dụng DNS nhanh nhất; DNS mã hóa (DoH) |
| | **VPN** | Nhập file WireGuard `.conf` / OpenVPN `.ovpn`; máy chủ miễn phí VPN Gate; Cloudflare WARP; kiểm tra IP và rò rỉ DNS |
| Công cụ | **Chẩn đoán** | Traceroute và phát hiện CGNAT/double NAT, kiểm tra website, kiểm tra cổng, dò MTU |
| | **Sửa lỗi mạng** | Xóa cache DNS, xin lại IP, khởi động lại card mạng, xóa ARP, tắt proxy, reset Winsock, reset TCP/IP |
| | **Chặn tên miền** | Chặn web bằng file hosts (chỉ sửa đoạn của Net Tools, có sao lưu) |
| Hệ thống | **Nhật ký / Cài đặt** | Giao diện sáng/tối, khởi động cùng Windows, icon ở khay hệ thống, thông báo rớt mạng |

Icon ở khay hệ thống (cạnh đồng hồ) cho phép mở app, đo tốc độ, đổi DNS nhanh, ngắt VPN và bật/tắt giám sát. Chấm đỏ trên icon nghĩa là đang mất mạng, chấm xanh lá nghĩa là đang bật VPN.

### VPN cần cài phần mềm chính chủ (miễn phí)
- **WireGuard** cho file `.conf`: https://www.wireguard.com/install/
- **OpenVPN Community** cho file `.ovpn` và VPN Gate: https://openvpn.net/community-downloads/
- **Cloudflare WARP**: https://one.one.one.one/

> VPN Gate là dự án học thuật của Đại học Tsukuba. Máy chủ do tình nguyện viên chạy, nên đừng đăng nhập tài khoản quan trọng khi dùng.

## Tải về
Vào tab **Actions** → lần build mới nhất → tải **NetTools** trong mục Artifacts. Nếu có bản phát hành, xem mục **Releases**.

## Chạy và build từ mã nguồn (VS Code)
```powershell
git clone https://github.com/Misakivn/net-tools.git
cd net-tools
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m nettools        # chạy app (tự xin quyền Admin)
.\.venv\Scripts\python.exe -m pytest -q       # kiểm thử
powershell -ExecutionPolicy Bypass -File .\build.ps1   # build -> dist\NetTools.exe
```
Trong VS Code: **F5** để chạy, **Ctrl+Shift+B** để build.

### Phát hành phiên bản mới
1. Sửa `__version__` trong `nettools/__init__.py`.
2. Commit, rồi `git tag v1.0.1` và `git push --tags`.
3. GitHub Actions tự build và đính kèm `NetTools.exe` vào Release.

## Cấu trúc
```
nettools/
  core/      logic thuần (không phụ thuộc giao diện): speed, dns, vpn, diag, monitor, fix, hosts, autostart
  ui/        giao diện customtkinter: app.py (khung), widgets.py, tray.py, pages/*
tests/       pytest cho phần core + ui_smoke.py (chạy giao diện với dữ liệu giả)
scripts/     tạo icon, thông tin phiên bản
```
Dữ liệu người dùng (cài đặt, lịch sử đo, nhật ký rớt mạng, hồ sơ VPN) nằm ở `%APPDATA%\NetTools`.
