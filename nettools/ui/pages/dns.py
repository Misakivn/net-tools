"""Đổi DNS, kiểm tra, benchmark, DNS mã hóa (DoH)."""
import ipaddress
import socket
import time

import customtkinter as ctk

from nettools.core import dns, speed
from nettools.ui import theme as T
from nettools.ui.app import Page
from nettools.ui.widgets import Card, InfoRow, LogBox, Table, button, header


class DnsPage(Page):
    def __init__(self, app):
        super().__init__(app)
        header(self, "DNS", "DNS là 'danh bạ' của internet. DNS nhanh giúp web mở nhanh hơn; "
                            "DNS mã hóa (DoH) giúp nhà mạng không đọc được bạn vào trang nào.")

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=6)
        top.grid_columnconfigure(0, weight=2, uniform="d")
        top.grid_columnconfigure(1, weight=3, uniform="d")

        cur = Card(top, "DNS hiện tại")
        cur.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.rows = {k: InfoRow(cur.body, lbl) for k, lbl in
                     [("adapter", "Card mạng"), ("dns", "Đang dùng"), ("src", "Nguồn"), ("doh", "Mã hóa DoH")]}
        for r in self.rows.values():
            r.pack(fill="x", pady=2)
        self.check_btn = self.lock(button(cur.body, "⌕  Kiểm tra DNS hiện tại", self.check, "neutral"))
        self.check_btn.pack(fill="x", pady=(10, 0))

        chg = Card(top, "Đổi DNS")
        chg.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.preset = ctk.CTkOptionMenu(chg.body, values=list(dns.PRESETS), command=self._preset_changed,
                                        dynamic_resizing=False, font=T.font(13))
        self.preset.pack(fill="x")
        self.desc = ctk.CTkLabel(chg.body, text="", font=T.font(12), text_color=T.MUTED, anchor="w")
        self.desc.pack(fill="x", pady=(4, 6))
        row = ctk.CTkFrame(chg.body, fg_color="transparent")
        row.pack(fill="x")
        self.primary = ctk.CTkEntry(row, placeholder_text="DNS chính, vd 1.1.1.1")
        self.primary.pack(side="left", fill="x", expand=True)
        self.secondary = ctk.CTkEntry(row, placeholder_text="DNS phụ, vd 1.0.0.1")
        self.secondary.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self.doh_var = ctk.BooleanVar(value=False)
        self.doh_switch = ctk.CTkSwitch(chg.body, text="Bật mã hóa DNS (DoH) — chỉ Cloudflare, Google, Quad9, AdGuard",
                                        variable=self.doh_var, font=T.font(12))
        self.doh_switch.pack(anchor="w", pady=(10, 4))
        brow = ctk.CTkFrame(chg.body, fg_color="transparent")
        brow.pack(fill="x", pady=(6, 0))
        self.apply_btn = self.lock(button(brow, "✔  Áp dụng", self.apply, width=130))
        self.apply_btn.pack(side="left")
        self.dhcp_btn = self.lock(button(brow, "Về mặc định (DHCP)", lambda: self.apply(dhcp=True), "neutral"))
        self.dhcp_btn.pack(side="left", padx=8)

        bc = Card(self, "Tìm DNS nhanh nhất", "Đo thời gian trả lời của từng DNS từ mạng của bạn (5 truy vấn mỗi DNS).")
        bc.pack(fill="x", padx=24, pady=6)
        brow = ctk.CTkFrame(bc.body, fg_color="transparent")
        brow.pack(fill="x", pady=(0, 8))
        self.bench_btn = self.lock(button(brow, "⏱  Chạy benchmark", self.start_benchmark, width=170))
        self.bench_btn.pack(side="left")
        self.best_btn = button(brow, "", self._apply_best, width=260)
        self.best = None
        self.table = Table(bc.body, [("name", "DNS", 200, "w"), ("ip", "Địa chỉ", 150, "center"),
                                     ("ms", "Thời gian", 110, "center"), ("rate", "Đánh giá", 120, "center"),
                                     ("doh", "Hỗ trợ DoH", 100, "center")], height=8)
        self.table.pack(fill="x")

        lc = Card(self, "Kết quả")
        lc.pack(fill="x", padx=24, pady=(6, 20))
        self.out = LogBox(lc.body, height=150)
        self.out.pack(fill="x")

        self.preset.set("Cloudflare")
        self._preset_changed("Cloudflare")
        self._loaded = False

    # ---------------------------------------------------------------- hiển thị
    def on_show(self):
        if not self._loaded:
            self._loaded = True
            self.reload()

    def on_adapter(self, name):
        self.reload()

    def reload(self):
        alias = self.app.adapter
        self.rows["adapter"].set(alias)

        def work():
            from nettools.core import netinfo
            conf = netinfo.ip_config(alias)
            doh = dns.doh_status(alias)
            self.ui(self._show_current, conf, doh)
        self.app.bg(work)

    def _show_current(self, conf, doh):
        servers = conf.get("dns", [])
        self.rows["dns"].set(" / ".join(servers[:2]) or "—")
        name = dns.preset_of(servers)
        self.rows["src"].set(("DHCP (nhà mạng)" if conf.get("dns_dhcp") else "Tự đặt") + (f" · {name}" if name else ""))
        self.rows["doh"].set("Đang bật · " + ", ".join(doh) if doh else "Tắt", T.GOOD if doh else None)
        self.doh_var.set(bool(doh))

    def _preset_changed(self, name):
        servers, desc = dns.PRESETS[name]
        self.desc.configure(text=desc)
        if name != dns.CUSTOM:
            for entry, value in zip((self.primary, self.secondary), servers or ("", "")):
                entry.delete(0, "end")
                if value:
                    entry.insert(0, value)
        state = "normal" if dns.doh_supported(list(servers)) or name == dns.CUSTOM else "disabled"
        self.doh_switch.configure(state=state)
        if state == "disabled":
            self.doh_var.set(False)

    def _servers(self):
        servers = [s for s in (self.primary.get().strip(), self.secondary.get().strip()) if s]
        for s in servers:
            ipaddress.IPv4Address(s)
        return servers

    # ---------------------------------------------------------------- áp dụng
    def apply(self, dhcp=False):
        alias = self.app.adapter
        if not alias:
            self.out.write("Chưa chọn card mạng (chọn ở góc dưới bên trái).")
            return
        if dhcp or self.preset.get() == dns.DHCP:
            servers = []
        else:
            try:
                servers = self._servers()
            except ValueError as e:
                self.out.write(f"Địa chỉ DNS không hợp lệ: {e}")
                return
            if not servers:
                self.out.write("Chưa nhập địa chỉ DNS.")
                return
        want_doh = bool(servers) and self.doh_var.get()
        if want_doh and not dns.doh_supported(servers):
            self.out.write("DNS này không hỗ trợ DoH trên Windows — sẽ áp dụng không mã hóa.")
            want_doh = False
        self.job(self._apply, alias, servers, want_doh,
                 done=lambda: (self.reload(), self.app.refresh_ipconf()))

    def _apply(self, alias, servers, want_doh):
        label = " / ".join(servers) if servers else "DHCP (tự động)"
        self.ui(self.out.write, f"Đang đổi DNS của '{alias}' sang {label}...")
        rc, out = dns.set_dns(alias, servers)
        if rc != 0:
            self.ui(self.out.write, f"✖ Đổi DNS THẤT BẠI (mã {rc}): {out}")
            self.app.ui(self.app.log, f"Đổi DNS thất bại: {out[:120]}", "error")
            return
        if want_doh:
            rc, out = dns.doh_enable(alias, servers)
            self.ui(self.out.write, "Đã bật DNS mã hóa (DoH)." if rc == 0 else f"✖ Bật DoH lỗi: {out}")
        else:
            dns.doh_disable(alias)
        self.ui(self.out.write, f"✔ Đã áp dụng DNS {label} và xóa cache DNS.")
        self.app.ui(self.app.log, f"Đã đổi DNS '{alias}' → {label}" + (" (DoH)" if want_doh else ""))

    def quick_apply(self, name):
        """Dùng từ menu khay hệ thống."""
        self.preset.set(name)
        self._preset_changed(name)
        self.apply(dhcp=name == dns.DHCP)

    # ---------------------------------------------------------------- kiểm tra
    def check(self):
        self.job(self._check, self.app.adapter, list(self.app.ipconf.get("dns", [])))

    def _check(self, alias, servers):
        w = lambda s: self.ui(self.out.write, s)  # noqa: E731
        w(f"— Kiểm tra DNS của '{alias}': {' / '.join(servers) or '(không có)'}")
        for host in ("google.com", "yahoo.co.jp", "github.com"):
            t = time.perf_counter()
            try:
                ip = socket.gethostbyname(host)
                w(f"  ✔ {host:<12} → {ip:<16} {(time.perf_counter() - t) * 1000:6.0f} ms (qua DNS máy)")
            except OSError as e:
                w(f"  ✖ {host:<12} không phân giải được: {e}")
        for s in servers[:2]:
            ms = dns.latency(s, 3)
            w(f"  DNS {s:<16} trả lời trực tiếp: " + ("không phản hồi" if ms is None else f"{ms:.0f} ms"))
        w("Nếu cả 3 tên miền đều ✔ là DNS đang hoạt động bình thường.")

    # ---------------------------------------------------------------- benchmark
    def start_benchmark(self):
        targets = [(n, s[0]) for n, (s, _) in dns.PRESETS.items() if s]
        current = [s for s in self.app.ipconf.get("dns", []) if s not in {ip for _, ip in targets}]
        if current:
            targets.insert(0, ("DNS hiện tại (nhà mạng)", current[0]))
        try:
            custom = self._servers()
        except ValueError:
            custom = []
        if custom and custom[0] not in {ip for _, ip in targets}:
            targets.append(("Tùy chỉnh", custom[0]))
        self.table.set_rows([])
        self.best_btn.pack_forget()
        self.job(self._benchmark, targets)

    def _benchmark(self, targets):
        self.ui(self.out.write, "Đang benchmark DNS...")
        results = []
        for name, ip in targets:
            ms = dns.latency(ip, 5)
            results.append((name, ip, ms))
            rate = "Không phản hồi" if ms is None else speed.quality("ping", ms / 1.5)
            self.ui(self.table.add_row, {"name": name, "ip": ip, "ms": "—" if ms is None else f"{ms:.1f} ms",
                                         "rate": {"good": "Rất nhanh", "ok": "Bình thường", "bad": "Chậm"}.get(rate, rate),
                                         "doh": "✔" if ip in dns.DOH_TEMPLATES else ""},
                    rate if ms is not None else "bad")
        ok = [r for r in results if r[2] is not None and r[0] in dns.PRESETS]
        if ok:
            self.best = min(ok, key=lambda r: r[2])
            self.ui(self._show_best)
        else:
            self.ui(self.out.write, "Không DNS nào phản hồi (UDP cổng 53 có thể bị chặn trên mạng này).")

    def _show_best(self):
        name, ip, ms = self.best
        self.best_btn.configure(text=f"⚡ Áp dụng nhanh nhất: {name} ({ms:.0f} ms)")
        self.best_btn.pack(side="left", padx=8)
        self.out.write(f"★ Nhanh nhất: {name} ({ip}) — {ms:.1f} ms")

    def _apply_best(self):
        if self.best:
            self.quick_apply(self.best[0])
