"""Bảng điều khiển: tình trạng tổng quan + thao tác nhanh."""
import customtkinter as ctk

from nettools.core import dns, netinfo
from nettools.ui import theme as T
from nettools.ui.app import Page
from nettools.ui.widgets import Card, InfoRow, LineChart, button, header


class DashboardPage(Page):
    def __init__(self, app):
        super().__init__(app)
        header(self, "Bảng điều khiển", "Tình trạng mạng của bạn trong nháy mắt.")

        hero = Card(self)
        hero.pack(fill="x", padx=24, pady=6)
        top = ctk.CTkFrame(hero.body, fg_color="transparent")
        top.pack(fill="x")
        left = ctk.CTkFrame(top, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        self.state = ctk.CTkLabel(left, text="● Đang kiểm tra...", font=T.font(20, "bold"), anchor="w")
        self.state.pack(fill="x")
        self.state_sub = ctk.CTkLabel(left, text="", font=T.font(12), text_color=T.MUTED, anchor="w")
        self.state_sub.pack(fill="x")
        self.refresh_btn = self.lock(button(top, "↻  Làm mới", self.refresh, "neutral", width=110))
        self.refresh_btn.pack(side="right")
        self.chart = LineChart(hero.body, [("Internet", T.ACCENT), ("Router", T.GOOD)], height=120)
        self.chart.pack(fill="x", pady=(10, 0))

        quick = ctk.CTkFrame(self, fg_color="transparent")
        quick.pack(fill="x", padx=24, pady=6)
        for i, (text, cmd) in enumerate([
            ("⚡  Đo tốc độ", lambda: self.app.show("speed").start()),
            ("⏱  Tìm DNS nhanh nhất", lambda: self.app.show("dns").start_benchmark()),
            ("⛨  Bật VPN", lambda: self.app.show("vpn")),
            ("Xóa cache DNS", lambda: self.app.show("fix").run("flushdns")),
            ("⌕  Kiểm tra website", lambda: self.app.show("diag").open_tab("Website")),
        ]):
            quick.grid_columnconfigure(i, weight=1)
            button(quick, text, cmd, "neutral" if i else "primary", height=40).grid(
                row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0))

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=24, pady=(6, 20))
        grid.grid_columnconfigure((0, 1), weight=1, uniform="c")
        self.rows = {}

        def card(r, c, title, fields, link=None):
            k = Card(grid, title)
            k.grid(row=r, column=c, sticky="nsew", padx=(0, 6) if c == 0 else (6, 0), pady=6)
            for key, label in fields:
                row = InfoRow(k.body, label)
                row.pack(fill="x", pady=2)
                self.rows[key] = row
            if link:
                ctk.CTkButton(k.body, text=link[0], command=link[1], fg_color="transparent",
                              hover_color=T.NAV_HOVER, text_color=T.ACCENT, anchor="e",
                              height=26, font=T.font(12)).pack(fill="x", pady=(6, 0))

        card(0, 0, "Kết nối mạng", [("adapter", "Card mạng"), ("desc", "Thiết bị"),
                                        ("link", "Tốc độ cổng"), ("mac", "Địa chỉ MAC"),
                                        ("ipv4", "IP nội bộ"), ("gateway", "Router (gateway)")],
             ("Sửa lỗi mạng →", lambda: self.app.show("fix")))
        card(0, 1, "Internet", [("pub", "IP công khai"), ("pub6", "IPv6"), ("isp", "Nhà mạng"),
                                    ("loc", "Vị trí"), ("nat", "Loại mạng")],
             ("Chẩn đoán →", lambda: self.app.show("diag")))
        card(1, 0, "⌖  DNS", [("dns", "DNS đang dùng"), ("dns_src", "Nguồn"), ("doh", "Mã hóa (DoH)")],
             ("Đổi DNS →", lambda: self.app.show("dns")))
        card(1, 1, "⛨  VPN", [("vpn", "Trạng thái"), ("mon", "Giám sát kết nối")],
             ("Mở VPN →", lambda: self.app.show("vpn")))

        self.app.sample_listeners.append(self._on_sample)
        self._loaded = False

    def on_show(self):
        self._draw_chart()
        self.rows["vpn"].set(self.app.vpn_text)
        if not self._loaded:
            self._loaded = True
            self.after(300, self.refresh)

    def on_adapter(self, name):
        if self._loaded:
            self.refresh()

    def on_theme(self):
        self.chart.redraw()

    def refresh(self):
        self.state.configure(text="● Đang kiểm tra...", text_color=T.MUTED)
        self.job(self._refresh, self.app.adapter)

    def _refresh(self, alias):
        conf = netinfo.ip_config(alias)
        doh = dns.doh_status(alias)
        self.ui(self._show_local, alias, conf, doh)
        info = netinfo.public_info()
        v6 = netinfo.public_ipv6()
        self.ui(self._show_public, info, v6, conf)

    def _show_local(self, alias, conf, doh):
        a = self.app.adapter_info()
        self.rows["adapter"].set(alias)
        self.rows["desc"].set(a.get("desc"))
        self.rows["link"].set(a.get("speed"))
        self.rows["mac"].set(a.get("mac"))
        self.rows["ipv4"].set(conf.get("ipv4"))
        self.rows["gateway"].set(conf.get("gateway"))
        servers = conf.get("dns", [])
        self.rows["dns"].set(" / ".join(servers[:2]))
        name = dns.preset_of(servers)
        self.rows["dns_src"].set(("Tự động từ nhà mạng (DHCP)" if conf.get("dns_dhcp") else "Tự đặt")
                                 + (f" · {name}" if name else ""))
        self.rows["doh"].set("Đang bật ✔" if doh else "Tắt", T.GOOD if doh else None)
        self.rows["mon"].set("Đang chạy" if self.app.monitor.running else "Đã tắt")
        self.rows["vpn"].set(self.app.vpn_text)

    def _show_public(self, info, v6, conf):
        if "error" in info:
            self.state.configure(text="● Không có kết nối internet", text_color=T.BAD)
            self.state_sub.configure(text="Không liên lạc được máy chủ bên ngoài. Thử trang 'Sửa lỗi mạng'.")
            for k in ("pub", "isp", "loc", "nat"):
                self.rows[k].set("—")
            return
        self.state.configure(text="● Đang kết nối internet", text_color=T.GOOD)
        self.state_sub.configure(text=f"{info.get('isp') or 'Nhà mạng không rõ'} · "
                                      f"{info.get('city', '')}, {info.get('country', '')}")
        self.rows["pub"].set(info.get("ip"))
        self.rows["pub6"].set(v6 or "Không có")
        self.rows["isp"].set(info.get("isp"))
        self.rows["loc"].set(f"{info.get('city', '')}, {info.get('country', '')}".strip(", "))
        kind = netinfo.classify_ip(info.get("ip", ""))
        if kind == "cgnat":
            self.rows["nat"].set("CGNAT (IP dùng chung)", T.OK)
        elif conf.get("ipv4") and conf.get("ipv4") == info.get("ip"):
            self.rows["nat"].set("IP công khai trực tiếp", T.GOOD)
        else:
            self.rows["nat"].set("Sau router (NAT) — xem Chẩn đoán")

    def _on_sample(self, t, gw, net):
        if self.app.current == "dashboard":
            self._draw_chart()

    def _draw_chart(self):
        data = list(self.app.monitor.samples)[-120:]
        self.chart.set_data([[n for _, _, n in data], [g for _, g, _ in data]])
