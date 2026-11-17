"""Đo tốc độ đường truyền + lịch sử."""
import time

import customtkinter as ctk

from nettools.core import netinfo, speed
from nettools.core.system import open_path, popen
from nettools.ui import theme as T
from nettools.ui.app import Page
from nettools.ui.widgets import Card, LineChart, Table, Tile, button, header


class SpeedPage(Page):
    def __init__(self, app):
        super().__init__(app)
        header(self, "Đo tốc độ", "Đo Ping, Jitter, mất gói, Download và Upload qua máy chủ Cloudflare gần nhất.")

        ctl = Card(self)
        ctl.pack(fill="x", padx=24, pady=6)
        row = ctk.CTkFrame(ctl.body, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(row, text="Ping tới:", font=T.font(13)).pack(side="left")
        self.host = ctk.CTkComboBox(row, values=speed.PING_HOSTS, width=170)
        self.host.set(self.app.settings["ping_host"])
        self.host.pack(side="left", padx=8)
        ctk.CTkLabel(row, text="Đơn vị:", font=T.font(13)).pack(side="left", padx=(16, 0))
        self.unit = ctk.CTkSegmentedButton(row, values=list(speed.UNITS), command=self._unit_changed)
        self.unit.set(self.app.settings["unit"])
        self.unit.pack(side="left", padx=8)
        self.start_btn = self.lock(button(row, "▶  Bắt đầu đo", self.start, width=160, height=38))
        self.start_btn.pack(side="right")
        self.info = ctk.CTkLabel(ctl.body, text="IP: —   ·   Nhà mạng: —   ·   Vị trí: —",
                                 font=T.font(12), text_color=T.MUTED, anchor="w")
        self.info.pack(fill="x", pady=(10, 0))

        tiles = ctk.CTkFrame(self, fg_color="transparent")
        tiles.pack(fill="x", padx=24, pady=6)
        self.tiles = {}
        for i, (key, title) in enumerate([("ping", "Ping"), ("jitter", "Jitter"), ("loss", "Mất gói"),
                                          ("down", "Download"), ("up", "Upload")]):
            tiles.grid_columnconfigure(i, weight=1, uniform="t")
            t = Tile(tiles, title)
            t.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0))
            self.tiles[key] = t
        self.speeds = {}

        prog = ctk.CTkFrame(self, fg_color="transparent")
        prog.pack(fill="x", padx=24, pady=(4, 6))
        self.stage = ctk.CTkLabel(prog, text="Bấm 'Bắt đầu đo' để kiểm tra đường truyền.", font=T.font(12),
                                  text_color=T.MUTED, anchor="w")
        self.stage.pack(fill="x")
        self.progress = ctk.CTkProgressBar(prog, height=8)
        self.progress.set(0)
        self.progress.pack(fill="x", pady=4)

        mid = ctk.CTkFrame(self, fg_color="transparent")
        mid.pack(fill="x", padx=24, pady=6)
        mid.grid_columnconfigure(0, weight=2, uniform="m")
        mid.grid_columnconfigure(1, weight=3, uniform="m")
        vc = Card(mid, "Đường truyền này dùng được cho")
        vc.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.verdict_labels = []
        for _ in range(3):
            lb = ctk.CTkLabel(vc.body, text="—", font=T.font(13), anchor="w", justify="left", wraplength=300)
            lb.pack(fill="x", pady=3)
            self.verdict_labels.append(lb)
        hc = Card(mid, "Lịch sử Download / Upload (Mbps)")
        hc.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.chart = LineChart(hc.body, [("Download", T.ACCENT), ("Upload", T.GOOD)], height=150, unit="Mbps")
        self.chart.pack(fill="x")

        tc = Card(self, "Các lần đo gần đây")
        tc.pack(fill="x", padx=24, pady=(6, 20))
        self.table = Table(tc.body, [("time", "Thời gian", 150, "w"), ("ping", "Ping (ms)", 90, "center"),
                                     ("jitter", "Jitter", 80, "center"), ("loss", "Mất gói", 80, "center"),
                                     ("down", "Download", 110, "center"), ("up", "Upload", 110, "center"),
                                     ("isp", "Nhà mạng", 180, "w")], height=6)
        self.table.pack(fill="x")
        button(tc.body, "Mở file lịch sử (CSV)", lambda: open_path(speed.history_path()), "neutral",
               width=200).pack(anchor="e", pady=(8, 0))
        self._load_history()

    # ---------------------------------------------------------------- lịch sử
    def _load_history(self):
        rows = speed.load_history()
        tail = rows[-30:]
        self.chart.set_data([[r["down"] for r in tail], [r["up"] for r in tail]],
                            [tail[0]["time"][5:16], tail[-1]["time"][5:16]] if len(tail) > 1 else None)
        fmt = lambda v, f="{:.0f}": "—" if v is None else f.format(v)  # noqa: E731
        show = [{"time": r["time"], "ping": fmt(r["ping"]), "jitter": fmt(r["jitter"], "{:.1f}"),
                 "loss": fmt(r["loss"], "{:.0f}%"), "down": fmt(r["down"], "{:.1f}"),
                 "up": fmt(r["up"], "{:.1f}"), "isp": r.get("isp", "")} for r in reversed(rows[-50:])]
        self.table.set_rows(show)

    def on_theme(self):
        self.chart.redraw()

    # ---------------------------------------------------------------- đo
    def _unit_changed(self, unit):
        self.app.settings["unit"] = unit
        for key, mbps in self.speeds.items():
            self._set_speed(key, mbps)

    def _set_speed(self, key, mbps, final=True):
        self.speeds[key] = mbps
        self.tiles[key].set(speed.fmt_speed(mbps, self.unit.get()),
                            speed.quality(key, mbps) if final else None)

    def _stage(self, text, value=None):
        self.stage.configure(text=text)
        if value is not None:
            self.progress.set(max(0.0, min(1.0, value)))

    def start(self):
        host = self.host.get().strip()
        if not speed.valid_host(host):
            self._stage("IP/Host không hợp lệ.")
            return
        self.app.settings["ping_host"] = host
        self.speeds.clear()
        for t in self.tiles.values():
            t.set("…")
        for lb in self.verdict_labels:
            lb.configure(text="Đang đo...", text_color=T.MUTED)
        self.job(self._run, host)

    def _run(self, host):
        self.ui(self._stage, "Đang lấy thông tin mạng...", 0)
        info = netinfo.public_info()
        if "error" in info:
            self.ui(self.info.configure, text=f"Không lấy được thông tin IP ({info['error'][:60]})")
        else:
            self.ui(self.info.configure, text=f"IP: {info['ip']}   ·   Nhà mạng: {info['isp'] or '?'}   ·   "
                                              f"Vị trí: {info['city']}, {info['country']}")

        proc = popen(["ping", "-n", str(speed.PING_COUNT), "-w", "1000", host])
        lines = []
        for line in proc.stdout:
            if line.strip():
                lines.append(line)
                self.ui(self._stage, f"Đang ping {host}...  {line.strip()[:70]}", (len(lines) - 1) / speed.PING_COUNT)
        proc.wait()
        ping, jitter, loss = speed.parse_ping("".join(lines))
        self.ui(self.tiles["ping"].set, "Lỗi" if ping is None else f"{ping:.0f} ms", speed.quality("ping", ping))
        self.ui(self.tiles["jitter"].set, "Lỗi" if jitter is None else f"{jitter:.1f} ms",
                speed.quality("jitter", jitter))
        self.ui(self.tiles["loss"].set, f"{loss:.0f} %", speed.quality("loss", loss))

        down = up = 0.0
        self.ui(self._stage, "Đang đo Download...", 0)
        try:
            down = speed.measure_download(lambda m, f: self.ui(self._live, "down", m, f))
            self.ui(self._set_speed, "down", down)
        except Exception as e:  # noqa: BLE001
            self.ui(self.tiles["down"].set, "Lỗi", "bad")
            self.app.ui(self.app.log, f"Download lỗi: {e}", "error")
        self.ui(self._stage, "Đang đo Upload...", 0)
        try:
            up = speed.measure_upload(lambda m, f: self.ui(self._live, "up", m, f))
            self.ui(self._set_speed, "up", up)
        except Exception as e:  # noqa: BLE001
            self.ui(self.tiles["up"].set, "Lỗi", "bad")
            self.app.ui(self.app.log, f"Upload lỗi: {e}", "error")

        self.ui(self._show_verdict, speed.verdict(ping, jitter, loss, down, up))
        speed.save_history({"time": time.strftime("%Y-%m-%d %H:%M"), "ping": "" if ping is None else round(ping, 1),
                            "jitter": "" if jitter is None else round(jitter, 1), "loss": round(loss, 1),
                            "down": round(down, 2), "up": round(up, 2), "host": host, "isp": info.get("isp", "")})
        self.ui(self._load_history)
        self.ui(self._stage, "Hoàn tất. Kết quả đã được lưu vào lịch sử.", 1)
        self.app.ui(self.app.log, f"Đo tốc độ: ping {ping or 0:.0f} ms, down {down:.1f} Mbps, up {up:.1f} Mbps")

    def _live(self, key, mbps, frac):
        self._set_speed(key, mbps, final=False)
        self.progress.set(min(1.0, frac))

    def _show_verdict(self, results):
        for lb, (ok, name, need) in zip(self.verdict_labels, results):
            lb.configure(text=f"{'✅' if ok else '❌'}  {name}" + (f"\n      {need}" if need else ""),
                         text_color=T.TEXT if ok else T.MUTED)
