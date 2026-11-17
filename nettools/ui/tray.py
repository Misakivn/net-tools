"""Icon ở khay hệ thống (cạnh đồng hồ): mở app, đổi DNS nhanh, bật/tắt giám sát, thoát."""
import pystray

from nettools import APP_NAME
from nettools.core import dns
from nettools.ui.icon import make_icon


class Tray:
    def __init__(self, app):
        self.app = app
        self._status = None
        self.icon = pystray.Icon("NetTools", make_icon(64), APP_NAME, menu=self._menu())
        self.icon.run_detached()

    def _menu(self):
        app = self.app
        M = pystray.MenuItem

        def dns_item(name):
            return M(name, lambda *_: app.ui(app.page("dns").quick_apply, name))

        presets = [dns_item(n) for n in dns.PRESETS if n != dns.CUSTOM]
        return pystray.Menu(
            M(f"Mở {APP_NAME}", lambda *_: app.ui(app.show_window), default=True),
            pystray.Menu.SEPARATOR,
            M("Đo tốc độ", lambda *_: app.ui(self._open, "speed", "start")),
            M("Đổi DNS nhanh", pystray.Menu(*presets)),
            M("Ngắt VPN", lambda *_: app.ui(app.page("vpn").disconnect)),
            M("Giám sát kết nối", lambda *_: app.ui(self._toggle_monitor),
              checked=lambda item: app.monitor.running),
            pystray.Menu.SEPARATOR,
            M("Thoát", lambda *_: app.ui(app.quit_app)),
        )

    def _open(self, key, action=None):
        self.app.show_window()
        page = self.app.show(key)
        if action == "start":
            page.start()

    def _toggle_monitor(self):
        page = self.app.page("monitor")
        page.toggle()

    def set_status(self, status):
        """None | 'bad' | 'vpn' — chấm màu trên icon."""
        if status != self._status:
            self._status = status
            self.icon.icon = make_icon(64, status)

    def notify(self, title, msg):
        try:
            self.icon.notify(msg, title)
        except Exception:  # noqa: BLE001 - một số hệ thống không hỗ trợ thông báo
            pass

    def stop(self):
        try:
            self.icon.stop()
        except Exception:  # noqa: BLE001
            pass
