"""Chặn tên miền bằng file hosts (chỉ sửa đoạn của Net Tools, có sao lưu)."""
import os
import re
import shutil

HOSTS = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "drivers", "etc", "hosts")
BEGIN = "# >>> Net Tools block >>>"
END = "# <<< Net Tools block <<<"
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?!-)([a-z0-9-]{1,63}\.)+[a-z]{2,63}$")

# gợi ý nhanh (người dùng tự chọn thêm)
SUGGESTIONS = {
    "Theo dõi quảng cáo phổ biến": ["doubleclick.net", "googleadservices.com",
                                    "googlesyndication.com", "adservice.google.com"],
    "Telemetry Windows": ["vortex.data.microsoft.com", "settings-win.data.microsoft.com",
                          "watson.telemetry.microsoft.com"],
}


def normalize(text):
    """Tách danh sách tên miền hợp lệ (bỏ trùng, bỏ http://, bỏ dòng trống/chú thích)."""
    out, bad = [], []
    for raw in re.split(r"[\s,;]+", text):
        d = raw.strip().lower()
        if not d or d.startswith("#"):
            continue
        d = re.sub(r"^https?://", "", d).split("/")[0]
        if DOMAIN_RE.match(d):
            if d not in out:
                out.append(d)
        else:
            bad.append(raw)
    return out, bad


def split_hosts(text):
    """(phần ngoài khối, danh sách domain trong khối)."""
    outside, inside, in_block = [], [], False
    for line in text.splitlines():
        s = line.strip()
        if s == BEGIN:
            in_block = True
        elif s == END:
            in_block = False
        elif in_block:
            parts = s.split()
            if len(parts) >= 2 and not s.startswith("#"):
                inside.append(parts[1])
        else:
            outside.append(line)
    return outside, inside


def build_hosts(outside, domains):
    body = "\n".join(outside).rstrip("\n")
    if not domains:
        return body + "\n"
    block = [BEGIN] + [f"0.0.0.0 {d}" for d in domains] + [END]
    return body + "\n\n" + "\n".join(block) + "\n"


def read_blocked(path=HOSTS):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return split_hosts(f.read())[1]
    except OSError:
        return []


def write_blocked(domains, path=HOSTS):
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    backup = path + ".nettools.bak"
    if not os.path.exists(backup):
        shutil.copy2(path, backup)
    outside, _ = split_hosts(text)
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(build_hosts(outside, domains))
