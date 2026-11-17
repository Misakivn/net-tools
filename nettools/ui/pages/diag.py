"""Chẩn đoán: traceroute + NAT/CGNAT, kiểm tra website, kiểm tra cổng, dò MTU."""
import customtkinter as ctk

from nettools.core import diag, speed
from nettools.core.system import run
from nettools.ui import theme as T
from nettools.ui.app import Page
from nettools.ui.widgets import LogBox, Table, button, header

KIND_VI = {"private": "Mạng nội bộ", "cgnat": "CGNAT nhà mạng", "public": "Internet", "loopback": "Máy này", "": ""}


class DiagPage(Page):
    def __init__(self, app):
        super().__init__(app)
        header(self, "Chẩn đoán", "Tìm xem mạng chậm/lỗi ở đâu: trong nhà, ở tòa nhà, nhà mạng hay phía website.")
        self.tabs = ctk.CTkTabview(self, height=560, fg_color=T.CARD, segmented_button_selected_color=T.ACCENT,
                                   border_width=1, border_color=T.BORDER, corner_radius=12)
        self.tabs.pack(fill="both", expand=True, padx=24, pady=(6, 20))
        self._build_trace(self.tabs.add("Traceroute"))
        self._build_web(self.tabs.add("Website"))
        self._build_port(self.tabs.add("Kiểm tra cổng"))
        self._build_mtu(self.tabs.add("MTU"))

    def open_tab(self, name):
        self.tabs.set(name)

    @staticmethod
    def _desc(tab, text):
        ctk.CTkLabel(tab, text=text, font=T.font(12), text_color=T.MUTED, anchor="w", justify="left",
                     wraplength=800).pack(fill="x", padx=8, pady=(6, 8))

    # ---------------------------------------------------------------- traceroute
    def _build_trace(self, tab):
        self._desc(tab, "Hiển thị từng chặng gói tin đi qua. Độ trễ tăng vọt ở chặng nào thì chỗ đó là nút thắt. "
                        "Đồng thời cho biết mạng có bị CGNAT / double NAT không (quan trọng nếu muốn tự host server).")
        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(fill="x", padx=8)
        self.t_host = ctk.CTkComboBox(row, values=["1.1.1.1", "8.8.8.8", "google.com", "yahoo.co.jp"], width=200)
        self.t_host.set("1.1.1.1")
        self.t_host.pack(side="left")
        self.lock(button(row, "▶  Chạy traceroute", self.trace, width=160)).pack(side="left", padx=8)
        self.t_table = Table(tab, [("hop", "Chặng", 60, "center"), ("ip", "Địa chỉ", 200, "w"),
                                   ("kind", "Vị trí", 150, "center"), ("t1", "Lần 1", 80, "center"),
                                   ("t2", "Lần 2", 80, "center"), ("t3", "Lần 3", 80, "center"),
                                   ("avg", "Trung bình", 100, "center")], height=11)
        self.t_table.pack(fill="both", expand=True, padx=8, pady=8)
        self.t_summary = ctk.CTkLabel(tab, text="", font=T.font(13), anchor="w", justify="left", wraplength=800)
        self.t_summary.pack(fill="x", padx=8, pady=(0, 6))

    def trace(self):
        host = self.t_host.get().strip()
        if not speed.valid_host(host):
            self.t_summary.configure(text="Host không hợp lệ.")
            return
        self.t_table.set_rows([])
        self.t_summary.configure(text="Đang dò đường (có thể mất tới 1 phút)...", text_color=T.MUTED)
        self.job(self._trace, host)

    def _trace(self, host):
        def on_hop(hop, times, ip, kind):
            ok = [t for t in times if t is not None]
            avg = sum(ok) / len(ok) if ok else None
            fmt = lambda t: "*" if t is None else f"{t} ms"  # noqa: E731
            self.ui(self.t_table.add_row, {"hop": hop, "ip": ip or "(không trả lời)", "kind": KIND_VI.get(kind, ""),
                                           "t1": fmt(times[0]), "t2": fmt(times[1]), "t3": fmt(times[2]),
                                           "avg": "—" if avg is None else f"{avg:.0f} ms"},
                    "" if avg is None else speed.quality("ping", avg))
        hops = diag.traceroute(host, on_hop)
        kind, text = diag.nat_summary(hops)
        jump = self._biggest_jump(hops)
        if jump:
            text += f"\nĐộ trễ tăng mạnh nhất ở chặng {jump[0]} (+{jump[1]:.0f} ms) — {KIND_VI.get(jump[2], '')}."
        self.ui(self.t_summary.configure, text=text, text_color=T.OK if kind in ("cgnat", "double") else T.TEXT)

    @staticmethod
    def _biggest_jump(hops):
        prev, best = 0, None
        for hop, times, ip, kind in hops:
            ok = [t for t in times if t is not None]
            if not ok:
                continue
            avg = sum(ok) / len(ok)
            if best is None or avg - prev > best[1]:
                best = (hop, avg - prev, kind)
            prev = avg
        return best if best and best[1] >= 15 else None

    # ---------------------------------------------------------------- website
    def _build_web(self, tab):
        self._desc(tab, "Biết website bị sập với mọi người hay chỉ với bạn: so sánh DNS của máy với Cloudflare "
                        "và thử tải trang.")
        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(fill="x", padx=8)
        self.w_url = ctk.CTkEntry(row, placeholder_text="vd: youtube.com", width=360)
        self.w_url.pack(side="left")
        self.w_url.bind("<Return>", lambda e: self.web())
        self.lock(button(row, "▶  Kiểm tra", self.web, width=120)).pack(side="left", padx=8)
        self.w_out = LogBox(tab, height=360)
        self.w_out.pack(fill="both", expand=True, padx=8, pady=8)

    def web(self):
        url = self.w_url.get().strip()
        if not url:
            return
        self.job(self._web, url)

    def _web(self, url):
        try:
            for line in diag.website_check(url):
                self.ui(self.w_out.write, line)
        except ValueError as e:
            self.ui(self.w_out.write, str(e))
        self.ui(self.w_out.write, "", False)

    # ---------------------------------------------------------------- port
    def _build_port(self, tab):
        self._desc(tab, "Thử kết nối TCP tới một máy chủ:cổng — biết dịch vụ có chạy không hay mạng đang chặn cổng đó "
                        "(ví dụ mạng tòa nhà chặn cổng game).")
        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(fill="x", padx=8)
        self.p_host = ctk.CTkEntry(row, placeholder_text="Máy chủ, vd google.com", width=260)
        self.p_host.pack(side="left")
        self.p_port = ctk.CTkEntry(row, placeholder_text="Cổng", width=90)
        self.p_port.pack(side="left", padx=8)
        self.p_common = ctk.CTkOptionMenu(row, values=[f"{k} ({v})" for k, v in diag.COMMON_PORTS.items()],
                                          command=self._pick_port, width=170)
        self.p_common.set("Cổng phổ biến")
        self.p_common.pack(side="left")
        self.lock(button(row, "▶  Kiểm tra", self.port, width=120)).pack(side="left", padx=8)
        self.p_out = LogBox(tab, height=360)
        self.p_out.pack(fill="both", expand=True, padx=8, pady=8)

    def _pick_port(self, label):
        self.p_port.delete(0, "end")
        self.p_port.insert(0, label.split("(")[-1].rstrip(")"))

    def port(self):
        host, port = self.p_host.get().strip(), self.p_port.get().strip()
        if not speed.valid_host(host) or not port.isdigit() or not 0 < int(port) < 65536:
            self.p_out.write("Nhập máy chủ và cổng (1–65535) hợp lệ.")
            return
        self.job(self._port, host, int(port))

    def _port(self, host, port):
        ok, ms, msg = diag.tcp_check(host, port)
        self.ui(self.p_out.write, f"{'✔' if ok else '✖'} {host}:{port} — {msg}" + (f" ({ms:.0f} ms)" if ms else ""))

    # ---------------------------------------------------------------- MTU
    def _build_mtu(self, tab):
        self._desc(tab, "MTU là kích thước gói tin lớn nhất đi được mà không bị chia nhỏ. MTU sai gây lag game, "
                        "web tải dở dang (hay gặp khi dùng VPN/PPPoE). Mặc định Windows là 1500.")
        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(fill="x", padx=8)
        self.m_host = ctk.CTkComboBox(row, values=["1.1.1.1", "8.8.8.8", "google.com"], width=200)
        self.m_host.set("1.1.1.1")
        self.m_host.pack(side="left")
        self.lock(button(row, "▶  Dò MTU", self.mtu, width=120)).pack(side="left", padx=8)
        self.m_apply = button(row, "", self.apply_mtu, "neutral", width=220)
        self.m_result = ctk.CTkLabel(tab, text="", font=T.font(16, "bold"), anchor="w", justify="left", wraplength=800)
        self.m_result.pack(fill="x", padx=8, pady=12)
        self.m_value = None

    def mtu(self):
        host = self.m_host.get().strip()
        if not speed.valid_host(host):
            return
        self.m_apply.pack_forget()
        self.m_result.configure(text="Đang dò...", text_color=T.MUTED)
        self.job(self._mtu, host)

    def _mtu(self, host):
        value = diag.find_mtu(host, lambda s: self.ui(self.m_result.configure, text=f"Đang thử gói {s + 28} byte..."))
        self.ui(self._show_mtu, value)

    def _show_mtu(self, value):
        self.m_value = value
        if value is None:
            self.m_result.configure(text="Không ping được máy chủ — không dò được MTU.", text_color=T.BAD)
        elif value >= 1500:
            self.m_result.configure(text=f"MTU tối ưu: {value} — đã tốt nhất, không cần chỉnh.", text_color=T.GOOD)
        else:
            self.m_result.configure(text=f"MTU tối ưu: {value} (thấp hơn 1500). Đặt MTU = {value} cho card "
                                         f"'{self.app.adapter}' có thể giảm lag.", text_color=T.OK)
            self.m_apply.configure(text=f"Áp dụng MTU {value} cho card")
            self.m_apply.pack(side="left", padx=8)

    def apply_mtu(self):
        alias, value = self.app.adapter, self.m_value
        if not alias or not value:
            return
        if not self.app.confirm("Đổi MTU", f"Đặt MTU = {value} cho card '{alias}'?\n"
                                           "Muốn trả lại mặc định thì dò lại và đặt 1500."):
            return
        rc, out = run(["netsh", "interface", "ipv4", "set", "subinterface", alias, f"mtu={value}",
                       "store=persistent"])
        self.app.log(f"Đổi MTU '{alias}' = {value}: " + ("thành công" if rc == 0 else out), "info" if rc == 0 else "error")
