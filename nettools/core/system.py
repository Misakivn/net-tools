"""Lớp nền: chạy lệnh, PowerShell, quyền Admin, thư mục dữ liệu, chống mở 2 lần."""
import ctypes
import json
import os
import subprocess
import sys

from nettools import APP_ID

IS_WINDOWS = sys.platform == "win32"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ENCODING = "oem" if IS_WINDOWS else "utf-8"


def run(cmd, timeout=60):
    """Chạy lệnh ẩn cửa sổ, trả (returncode, output). Không bao giờ ném lỗi."""
    try:
        p = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL, text=True,
                           encoding=ENCODING, errors="replace", timeout=timeout,
                           creationflags=NO_WINDOW)
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
    except FileNotFoundError:
        return 127, f"Không tìm thấy chương trình: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "Hết thời gian chờ lệnh."
    except OSError as e:
        return 1, str(e)


def popen(cmd):
    """Mở tiến trình đọc output theo dòng (dùng cho ping/tracert/openvpn)."""
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, text=True, encoding=ENCODING,
                            errors="replace", creationflags=NO_WINDOW)


def powershell(script, timeout=60):
    # Ép output UTF-8 để tên card mạng tiếng Nhật/Việt không bị lỗi font
    prefix = "[Console]::OutputEncoding=[Text.Encoding]::UTF8;$ProgressPreference='SilentlyContinue';"
    try:
        p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                            "Bypass", "-Command", prefix + script],
                           capture_output=True, stdin=subprocess.DEVNULL, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           creationflags=NO_WINDOW)
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
    except FileNotFoundError:
        return 127, "Không tìm thấy PowerShell."
    except subprocess.TimeoutExpired:
        return 124, "PowerShell hết thời gian chờ."


def ps_json(script, timeout=60):
    """Chạy script PowerShell kết thúc bằng ConvertTo-Json; trả list dict (rỗng nếu lỗi)."""
    rc, out = powershell(f"{script} | ConvertTo-Json -Depth 4 -Compress", timeout)
    if rc != 0 or not out:
        return []
    starts = [i for i in (out.find("{"), out.find("[")) if i >= 0]
    if not starts:
        return []
    try:
        data = json.loads(out[min(starts):])
    except ValueError:
        return []
    return data if isinstance(data, list) else [data]


def ps_quote(text):
    """Đặt chuỗi vào nháy đơn PowerShell an toàn."""
    return "'" + str(text).replace("'", "''") + "'"


def is_admin():
    if not IS_WINDOWS:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def relaunch_as_admin():
    """Mở lại chính app qua UAC. Trả True nếu đã gửi yêu cầu."""
    if not IS_WINDOWS:
        return False
    if getattr(sys, "frozen", False):
        exe, args = sys.executable, sys.argv[1:]
    else:
        exe, args = sys.executable, ["-m", "nettools"] + sys.argv[1:]
    r = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe,
                                            subprocess.list2cmdline(args), os.getcwd(), 1)
    return r > 32


def launch_command():
    """(exe, args, workdir) để chạy lại app, dùng cho khởi động cùng Windows."""
    if getattr(sys, "frozen", False):
        return sys.executable, "--tray", os.path.dirname(sys.executable)
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pythonw if os.path.exists(pythonw) else sys.executable
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return exe, "-m nettools --tray", os.path.dirname(root)


def data_dir(*parts):
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    path = os.path.join(base, APP_ID, *parts)
    os.makedirs(path, exist_ok=True)
    return path


def resource_path(*parts):
    """Đường dẫn file đi kèm app (chạy được cả khi đã đóng gói PyInstaller)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
    return os.path.join(base, *parts)


def open_path(path):
    if IS_WINDOWS:
        os.startfile(path)  # noqa: S606 - mở thư mục/file của chính app


_mutex = None


def _k32():
    """kernel32 với kiểu HANDLE đúng 64-bit."""
    k32 = ctypes.windll.kernel32
    vp = ctypes.c_void_p
    k32.CreateMutexW.restype = vp
    k32.CreateEventW.restype = vp
    k32.OpenEventW.restype = vp
    k32.WaitForSingleObject.argtypes = [vp, ctypes.c_uint32]
    k32.SetEvent.argtypes = [vp]
    k32.CloseHandle.argtypes = [vp]
    return k32


def single_instance():
    """True nếu đây là bản đang chạy duy nhất."""
    global _mutex
    if not IS_WINDOWS:
        return True
    k32 = _k32()
    _mutex = k32.CreateMutexW(None, False, f"Local\\{APP_ID}_Mutex")
    return k32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


SHOW_EVENT = f"Local\\{APP_ID}_Show"


def wait_show_requests(callback):
    """Luồng nền: mỗi khi bản thứ 2 được mở, gọi callback() để hiện cửa sổ bản đang chạy."""
    if not IS_WINDOWS:
        return
    import threading
    k32 = _k32()
    handle = k32.CreateEventW(None, False, False, SHOW_EVENT)

    def loop():
        while k32.WaitForSingleObject(handle, 0xFFFFFFFF) == 0:
            callback()
    threading.Thread(target=loop, daemon=True).start()


def request_show():
    """Gọi từ bản thứ 2: nhờ bản đang chạy hiện cửa sổ lên."""
    if not IS_WINDOWS:
        return False
    k32 = _k32()
    handle = k32.OpenEventW(0x0002, False, SHOW_EVENT)  # EVENT_MODIFY_STATE
    if not handle:
        return False
    k32.SetEvent(handle)
    k32.CloseHandle(handle)
    return True
