"""Sửa lỗi mạng 1 click."""
from nettools.core.system import powershell, ps_quote, run

# key -> (tiêu đề, mô tả, cần xác nhận?, cảnh báo)
ACTIONS = {
    "flushdns": ("Xóa cache DNS", "Sửa lỗi vào web sai trang, web vừa đổi máy chủ.", False, ""),
    "renew": ("Xin lại địa chỉ IP", "Release/Renew IP từ router. Mạng sẽ mất vài giây.", True,
              "Mạng của card này sẽ mất kết nối vài giây."),
    "restart": ("Khởi động lại card mạng", "Tắt rồi bật card — như rút/cắm lại dây mạng.", True,
                "Mạng sẽ mất khoảng 5–10 giây."),
    "arp": ("Xóa bảng ARP", "Sửa lỗi không tìm thấy router/thiết bị trong mạng LAN.", False, ""),
    "proxy": ("Tắt proxy hệ thống", "Gỡ proxy do app lạ/virus cài vào làm mất mạng.", True,
              "Nếu bạn đang cố ý dùng proxy, nó sẽ bị tắt."),
    "winsock": ("Reset Winsock", "Sửa lỗi mạng do phần mềm lạ cài vào. Cần khởi động lại máy.", True,
                "Cần KHỞI ĐỘNG LẠI máy sau khi chạy. Một số VPN/phần mềm mạng có thể phải cài lại."),
    "ipreset": ("Reset TCP/IP", "Đưa cấu hình TCP/IP về mặc định. Cần khởi động lại máy.", True,
                "Cần KHỞI ĐỘNG LẠI máy. IP/DNS tự đặt tay có thể bị xóa."),
}


def run_action(key, alias=""):
    """Chạy 1 thao tác; trả list (lệnh, rc, output)."""
    a = ps_quote(alias) if alias else None
    if key == "flushdns":
        cmds = [["ipconfig", "/flushdns"]]
    elif key == "renew":
        cmds = ([["ipconfig", "/release", alias], ["ipconfig", "/renew", alias]] if alias
                else [["ipconfig", "/release"], ["ipconfig", "/renew"]])
    elif key == "arp":
        cmds = [["netsh", "interface", "ip", "delete", "arpcache"]]
    elif key == "winsock":
        cmds = [["netsh", "winsock", "reset"]]
    elif key == "ipreset":
        cmds = [["netsh", "int", "ip", "reset"]]
    elif key == "restart":
        if not a:
            return [("Restart-NetAdapter", 1, "Chưa chọn card mạng.")]
        rc, out = powershell(f"Restart-NetAdapter -Name {a} -Confirm:$false", timeout=60)
        return [("Restart-NetAdapter " + alias, rc, out or "OK")]
    elif key == "proxy":
        rc, out = powershell(
            "Set-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings' "
            "-Name ProxyEnable -Value 0; netsh winhttp reset proxy")
        return [("Tắt proxy", rc, out or "OK")]
    else:
        return [(key, 1, "Không rõ thao tác")]
    results = []
    for c in cmds:
        rc, out = run(c, timeout=90)
        results.append((" ".join(c), rc, out))
    return results
