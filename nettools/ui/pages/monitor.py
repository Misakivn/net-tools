"""Giám sát kết nối liên tục + nhật ký rớt mạng."""
import time

import customtkinter as ctk

from nettools.core import speed
from nettools.core.monitor import Monitor
from nettools.core.system import open_path
from nettools.ui import theme as T
from nettools.ui.app import Page
from nettools.ui.widgets import Card, LineChart, Table, Tile, button, header

INTERVALS = {"1 giây": 1, "3 giây": 3, "5 giây": 5, "10 giây": 10}


class MonitorPage(Page):
    def __init__(self, app):
        super().__init__(app)
        header(self, "Giám sát kết nối",
               "Ping router và internet liên tục, tự ghi lại mỗi lần rớt mạng và nguyên nhân. "
               "Dùng làm bằng chứng khi báo lỗi cho ban quản lý tòa nhà hoặc nhà mạng.")

        ctl = Card(self)
        ctl.pack(fill="x", padx=24, pady=6)
        row = ctk.CTkFrame(ctl.body, fg_color="transparent")
        row.pack(fill="x")
        self.toggle_btn = button(row, "", self.toggle, width=150, height=38)
        self.toggle_btn.pack(side="left")
        ctk.CTkLabel(row, text="Ping internet tới:", font=T.font(13)).pack(side="left", padx=(16, 6))
        self.host = ctk.CTkComboBox(row, values=["1.1.1.1", "8.8.8.8", "9.9.9.9", "google.com"], width=150,
                                    command=self._host_changed)
        self.host.set(self.app.monitor.host)
        self.host.pack(side="left")
        ctk.CTkLabel(row, text="Mỗi:", font=T.font(13)).pack(side="left", padx=(16, 6))
        self.interval = ctk.CTkSegmentedButton(row, values=list(INTERVALS), command=self._interval_changed)
        cur = next((k for k, v in INTERVALS.items() if v == self.app.monitor.interval), "3 giây")
        self.interval.set(cur)
        self.interval.pack(side="left")
        self.gw_label = ctk.CTkLabel(ctl.body, text="", font=T.font(12), text_color=T.MUTED, anchor="w")
        self.gw_label.pack(fill="x", pady=(8, 0))

        tiles = ctk.CTkFrame(self, fg_color="transparent")
        tiles.pack(fill="x", padx=24, pady=6)
        self.tiles = {}
        for i, (key, title) in enumerate([("gw", "Router"), ("net", "Internet"), ("loss", "Mất gói (5 phút)"),
                                          ("uptime", "Thời gian có mạng"), ("count", "Số lần rớt")]):
            tiles.grid_columnconfigure(i, weight=1, uniform="t")
            t = Tile(tiles, title, size=22)
            t.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0))
            self.tiles[key] = t

        cc = Card(self, "Độ trễ theo thời gian (vạch đỏ = mất gói)")
        cc.pack(fill="x", padx=24, pady=6)
        self.chart = LineChart(cc.body, [("Internet", T.ACCENT), ("Router", T.GOOD)], height=200)
        self.chart.pack(fill="x")

        oc = Card(self, "Nhật ký rớt mạng")
        oc.pack(fill="x", padx=24, pady=(6, 20))
        self.table = Table(oc.body, [("start", "Bắt đầu", 170, "center"), ("end", "Kết thúc", 170, "center"),
                                     ("seconds", "Số giây", 80, "center"),
                                     ("cause", "Nguyên nhân dự đoán", 380, "w")], height=6)
        self.table.pack(fill="x")
        brow = ctk.CTkFrame(oc.body, fg_color="transparent")
        brow.pack(fill="x", pady=(8, 0))
        button(brow, "Sao chép báo cáo", self.copy_report, "neutral", width=170).pack(side="right")
        button(brow, "Mở file CSV", lambda: open_path(Monitor.log_path()), "neutral",
               width=140).pack(side="right", padx=6)

        self.app.sample_listeners.append(self._on_sample)
        self._last_draw = 0
        self._refresh_btn()
        self._load_outages()

    def on_show(self):
        self._refresh_btn()
        self._load_outages()
        self._draw()

    def on_theme(self):
        self.chart.redraw()

    def toggle(self):
        m = self.app.monitor
        if m.running:
            m.stop()
            self.app.log("Đã tắt giám sát kết nối.")
        else:
            m.start()
            self.app.log("Đã bật giám sát kết nối.")
        self.after(200, self._refresh_btn)

    def start(self):
        if not self.app.monitor.running:
            self.toggle()

    def _refresh_btn(self):
        running = self.app.monitor.running and not self.app.monitor._stop.is_set()
        self.toggle_btn.configure(text="■  Dừng giám sát" if running else "▶  Bắt đầu giám sát",
                                  fg_color=T.DANGER if running else T.ACCENT,
                                  hover_color=T.DANGER_HOVER if running else T.ACCENT_HOVER)
        gw = self.app.monitor.gateway
        self.gw_label.configure(text=f"Router (gateway) của card '{self.app.adapter}': {gw}" if gw
                                else "Chưa xác định router — chỉ ping internet.")

    def _host_changed(self, host):
        host = host.strip()
        if speed.valid_host(host):
            self.app.monitor.host = host
            self.app.settings["monitor_host"] = host

    def _interval_changed(self, label):
        self.app.monitor.interval = INTERVALS[label]
        self.app.settings["monitor_interval"] = INTERVALS[label]

    def on_adapter(self, name):
        self.after(1500, self._refresh_btn)

    def _on_sample(self, t, gw, net):
        if self.app.current != "monitor":
            return
        self._draw()

    def _draw(self):
        m = self.app.monitor
        data = list(m.samples)[-200:]
        if data:
            _, gw, net = data[-1]
            self.tiles["gw"].set("—" if not m.gateway else ("Mất" if gw is None else f"{gw:.0f} ms"),
                                 speed.quality("ping", gw) if m.gateway else None)
            self.tiles["net"].set("Mất" if net is None else f"{net:.0f} ms", speed.quality("ping", net))
        window = max(1, int(300 / max(m.interval, 1)))
        st = m.stats(window)
        all_st = m.stats()
        if st["loss"] is not None:
            self.tiles["loss"].set(f"{st['loss']:.1f} %", speed.quality("loss", st["loss"]))
            self.tiles["uptime"].set(f"{all_st['uptime']:.1f} %",
                                     "good" if all_st["uptime"] > 99.5 else "ok" if all_st["uptime"] > 97 else "bad",
                                     note=f"{len(m.samples)} mẫu")
        self.tiles["count"].set(str(len(Monitor.load_outages(1000))), note="tổng đã ghi")
        labels = None
        if len(data) > 1:
            labels = [time.strftime("%H:%M:%S", time.localtime(data[0][0])),
                      time.strftime("%H:%M:%S", time.localtime(data[-1][0]))]
        self.chart.set_data([[n for _, _, n in data], [g for _, g, _ in data]], labels)

    def _load_outages(self):
        rows = list(reversed(Monitor.load_outages()))
        self.table.set_rows(rows, ["bad"] * len(rows))

    def on_outage(self):
        self._load_outages()

    def copy_report(self):
        rows = Monitor.load_outages(1000)
        st = self.app.monitor.stats()
        lines = ["BÁO CÁO TÌNH TRẠNG MẠNG (Net Tools)",
                 f"Thời điểm: {time.strftime('%Y-%m-%d %H:%M')}",
                 f"Số lần rớt mạng đã ghi: {len(rows)}"]
        if st["avg"] is not None:
            lines.append(f"Phiên hiện tại: ping trung bình {st['avg']:.0f} ms, mất gói {st['loss']:.1f}%")
        lines.append("")
        lines += [f"- {r['start']} → {r['end']} ({r['seconds']} giây): {r['cause']}" for r in rows[-30:]]
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self.app.log("Đã sao chép báo cáo rớt mạng vào clipboard — dán vào email/tin nhắn được ngay.")
