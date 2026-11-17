"""Điểm khởi chạy: python -m nettools [--tray] [--no-admin]."""
import sys


def main():
    from nettools.core.system import IS_WINDOWS, is_admin, relaunch_as_admin, request_show, single_instance

    if IS_WINDOWS:
        try:  # chữ sắc nét trên màn hình độ phân giải cao
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
        if not is_admin() and "--no-admin" not in sys.argv and relaunch_as_admin():
            return
    if not single_instance():
        request_show()  # bản đang chạy (có thể đang ẩn ở khay) sẽ tự hiện cửa sổ
        return

    from nettools.ui.app import App
    App(start_hidden="--tray" in sys.argv).mainloop()


if __name__ == "__main__":
    main()
