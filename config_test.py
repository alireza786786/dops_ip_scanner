#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 alireza786786 (DOPS). All rights reserved. See LICENSE.
"""Real end-to-end test of clean IPs THROUGH YOUR OWN CONFIG (experimental; needs the `xray` binary, e.g. in Termux).

For every (config, IP) pair it: writes a temporary Xray config whose server address is the IP (SNI/Host stay your domain),
starts Xray with a local SOCKS5 inbound, fetches a small URL through it and measures the time, then stops Xray.
This answers the question a browser cannot: "does this IP actually carry MY config?".

  python config_test.py --config 'vless://...' --ips-file outputs/alive_cloudflare.txt --top 20
  python config_test.py --configs-file my_configs.txt --ips 104.16.1.1,104.17.2.2 --jobs 2 --out result.json

Supported: vless / vmess / trojan over tcp, ws, grpc, httpupgrade with tls or none. Reality is refused (it does not use a CDN).
Run it on the network you want to test (no VPN on). Requires Python 3.9+ and Xray-core in PATH (or --xray).
"""
import argparse, base64, json, os, queue, re, shutil, socket, ssl, struct, subprocess, sys, tempfile, threading, time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, unquote, urlsplit

DEFAULT_URL = "http://cp.cloudflare.com/generate_204"
OK_STATUS = (200, 204, 301, 302)


class Unsupported(Exception):
    pass


# ------------------------------------------------------------------ link parsing
_LINK = re.compile(r"^(vless|trojan)://([^@/?#]*)@(\[[^\]]+\]|[^:/?#]+):(\d+)([^?#]*)(?:\?([^#]*))?(?:#(.*))?$")


def _b64(s):
    s = s.strip().replace("-", "+").replace("_", "/")
    return base64.b64decode(s + "=" * (-len(s) % 4))


def is_ip(h):
    try:
        socket.inet_pton(socket.AF_INET, h); return True
    except OSError:
        pass
    try:
        socket.inet_pton(socket.AF_INET6, h); return True
    except OSError:
        return False


def parse_link(link):
    link = link.strip()
    if link.lower().startswith("vmess://"):
        try:
            j = json.loads(_b64(link[8:].split("#")[0]).decode("utf-8"))
        except Exception as e:
            raise Unsupported(f"vmess link is not valid base64 JSON ({e})")
        return {"proto": "vmess", "id": j.get("id", ""), "host": str(j.get("add", "")), "port": int(j.get("port", 443)), "net": (j.get("net") or "tcp").lower(),
                "security": "tls" if j.get("tls") == "tls" else "", "sni": j.get("sni") or "", "hostHeader": j.get("host") or "", "path": j.get("path") or "",
                "serviceName": j.get("path") or "", "fp": j.get("fp") or "", "alpn": j.get("alpn") or "", "allowInsecure": False, "aid": int(j.get("aid") or 0),
                "scy": j.get("scy") or "auto", "flow": "", "tag": j.get("ps") or ""}
    m = _LINK.match(link)
    if not m:
        raise Unsupported("only vless://, vmess:// and trojan:// links are supported")
    proto, auth, host, port, _, query, tag = m.groups()
    q = {k: v[0] for k, v in parse_qs(query or "", keep_blank_values=True).items()}
    return {"proto": proto, "id": unquote(auth), "host": host.strip("[]"), "port": int(port), "net": (q.get("type") or "tcp").lower(),
            "security": q.get("security") or ("tls" if proto == "trojan" else ""), "sni": q.get("sni") or "", "hostHeader": q.get("host") or "", "path": q.get("path") or "",
            "serviceName": q.get("serviceName") or "", "fp": q.get("fp") or "", "alpn": q.get("alpn") or "", "allowInsecure": q.get("allowInsecure") == "1",
            "aid": 0, "scy": "auto", "flow": q.get("flow") or "", "tag": unquote(tag or "")}


def build_xray_config(info, ip, socks_port):
    """Xray JSON whose outbound dials `ip` while SNI/Host keep the original domain."""
    net, sec = info["net"], info["security"]
    if sec == "reality":
        raise Unsupported("Reality does not use a CDN, so a clean IP is meaningless for it")
    if net not in ("tcp", "ws", "grpc", "httpupgrade"):
        raise Unsupported(f"transport '{net}' is not supported")
    if sec not in ("", "none", "tls"):
        raise Unsupported(f"security '{sec}' is not supported")
    domain = info["host"] if info["host"] and not is_ip(info["host"]) else ""
    sni = info["sni"] or info["hostHeader"] or domain
    stream = {"network": net, "security": "tls" if sec == "tls" else "none"}
    if sec == "tls":
        tls = {"allowInsecure": bool(info["allowInsecure"])}
        if sni:
            tls["serverName"] = sni
        if info["fp"]:
            tls["fingerprint"] = info["fp"]
        if info["alpn"]:
            tls["alpn"] = [a for a in info["alpn"].split(",") if a]
        stream["tlsSettings"] = tls
    host_hdr = info["hostHeader"] or sni
    if net == "ws":
        stream["wsSettings"] = {"path": info["path"] or "/", "headers": {"Host": host_hdr} if host_hdr else {}}
    elif net == "httpupgrade":
        stream["httpupgradeSettings"] = {"path": info["path"] or "/", "host": host_hdr}
    elif net == "grpc":
        stream["grpcSettings"] = {"serviceName": info["serviceName"]}
    if info["proto"] == "vless":
        out = {"protocol": "vless", "settings": {"vnext": [{"address": ip, "port": info["port"], "users": [{"id": info["id"], "encryption": "none", "flow": info["flow"]}]}]}}
    elif info["proto"] == "vmess":
        out = {"protocol": "vmess", "settings": {"vnext": [{"address": ip, "port": info["port"], "users": [{"id": info["id"], "alterId": info["aid"], "security": info["scy"]}]}]}}
    else:
        out = {"protocol": "trojan", "settings": {"servers": [{"address": ip, "port": info["port"], "password": info["id"]}]}}
    out.update({"tag": "proxy", "streamSettings": stream})
    return {"log": {"loglevel": "warning"}, "inbounds": [{"tag": "in", "listen": "127.0.0.1", "port": socks_port, "protocol": "socks", "settings": {"udp": False, "auth": "noauth"}}], "outbounds": [out]}


# ------------------------------------------------------------------ SOCKS5 client (stdlib)
def _recv(s, n):
    buf = b""
    while len(buf) < n:
        c = s.recv(n - len(buf))
        if not c:
            raise ConnectionError("proxy closed the connection")
        buf += c
    return buf


def fetch_via_socks(port, url, timeout=8.0):
    """GET `url` through the SOCKS5 proxy on 127.0.0.1:port -> (status, milliseconds)."""
    u = urlsplit(url); https = u.scheme == "https"; host = u.hostname; dport = u.port or (443 if https else 80)
    t0 = time.perf_counter(); s = socket.create_connection(("127.0.0.1", port), timeout=timeout); s.settimeout(timeout)
    try:
        s.sendall(b"\x05\x01\x00")
        if _recv(s, 2) != b"\x05\x00":
            raise ConnectionError("SOCKS5 negotiation failed")
        hb = host.encode("idna")
        s.sendall(b"\x05\x01\x00\x03" + bytes([len(hb)]) + hb + struct.pack(">H", dport))
        ver, rep, _, atyp = _recv(s, 4)
        if rep != 0:
            raise ConnectionError(f"proxy could not connect (SOCKS reply {rep})")
        _recv(s, {1: 4, 4: 16}.get(atyp, 0) + 2) if atyp != 3 else _recv(s, _recv(s, 1)[0] + 2)
        conn = ssl.create_default_context().wrap_socket(s, server_hostname=host) if https else s
        path = (u.path or "/") + (("?" + u.query) if u.query else "")
        conn.sendall(f"GET {path} HTTP/1.1\r\nHost: {u.netloc}\r\nUser-Agent: dops-config-test\r\nConnection: close\r\n\r\n".encode())
        head = b""
        while b"\r\n" not in head and len(head) < 4096:
            c = conn.recv(1024)
            if not c:
                break
            head += c
        m = re.match(rb"HTTP/1\.[01] (\d{3})", head)
        if not m:
            raise ConnectionError("no HTTP response through the proxy")
        return int(m.group(1)), (time.perf_counter() - t0) * 1000
    finally:
        try:
            s.close()
        except OSError:
            pass


# ------------------------------------------------------------------ Xray process
def _xray_cmds(xray, cfg, test=False):
    base = [xray, "run"] + (["-test"] if test else []) + ["-config", cfg]
    legacy = [xray] + (["-test"] if test else []) + ["-config", cfg]
    return base, legacy


def validate_with_xray(xray, cfg_dict):
    """Ask Xray itself to validate a config (catches schema mistakes before the batch starts). Returns (ok, message)."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(cfg_dict, f); path = f.name
    try:
        last = ""
        for cmd in _xray_cmds(xray, path, test=True):
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            except (OSError, subprocess.TimeoutExpired) as e:
                last = str(e); continue
            if r.returncode == 0:
                return True, ""
            last = (r.stderr or r.stdout).strip()[-400:]
        return False, last
    finally:
        os.unlink(path)


def _wait_port(port, proc, timeout=4.0):
    end = time.time() + timeout
    while time.time() < end:
        if proc.poll() is not None:
            return False
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close(); return True
        except OSError:
            time.sleep(0.1)
    return False


def test_pair(xray, info, ip, port, url, timeout):
    """One (config, IP) test -> dict(ip, ok, ms, status, error)."""
    res = {"ip": ip, "ok": False, "ms": None, "status": None, "error": ""}
    try:
        cfg = build_xray_config(info, ip, port)
    except Unsupported as e:
        res["error"] = f"unsupported: {e}"; return res
    fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
    proc = None
    try:
        with open(path, "w") as f:
            json.dump(cfg, f)
        proc = subprocess.Popen(_xray_cmds(xray, path)[0], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if not _wait_port(port, proc):
            err = ""
            if proc.poll() is not None:
                try:
                    err = proc.stderr.read().decode("utf-8", "replace").strip()[-200:]
                except Exception:
                    pass
            res["error"] = "xray did not start" + (f": {err}" if err else ""); return res
        status, ms = fetch_via_socks(port, url, timeout)
        res.update(status=status, ms=round(ms, 1), ok=status in OK_STATUS)
        if not res["ok"]:
            res["error"] = f"HTTP {status}"
    except Exception as e:
        res["error"] = f"{type(e).__name__}: {e}"[:160]
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait()
            if proc.stderr:
                proc.stderr.close()
        try:
            os.unlink(path)
        except OSError:
            pass
    return res


def run_batch(xray, links, ips, url=DEFAULT_URL, jobs=2, base_port=19080, timeout=8.0, progress=None):
    ports = queue.Queue()
    for i in range(jobs):
        ports.put(base_port + i)
    infos = []
    for l in links:
        try:
            infos.append((l, parse_link(l)))
        except Unsupported as e:
            infos.append((l, e))
    work = [(l, inf, ip) for l, inf in infos for ip in ips]
    out, lock = [], threading.Lock()

    def one(item):
        link, inf, ip = item
        if isinstance(inf, Unsupported):
            r = {"ip": ip, "ok": False, "ms": None, "status": None, "error": f"unsupported: {inf}"}
        else:
            p = ports.get()
            try:
                r = test_pair(xray, inf, ip, p, url, timeout)
            finally:
                ports.put(p)
        r["config"] = (inf.get("tag") or inf.get("host") or "config") if isinstance(inf, dict) else "config"
        with lock:
            out.append(r)
            if progress:
                progress(r, len(out), len(work))
        return r

    with ThreadPoolExecutor(max_workers=jobs) as ex:
        list(ex.map(one, work))
    return sorted(out, key=lambda r: (not r["ok"], r["ms"] if r["ms"] is not None else 1e12))


def load_ips(args):
    ips = []
    if args.ips:
        ips += [x.strip() for x in args.ips.split(",") if x.strip()]
    if args.ips_file:
        with open(args.ips_file, encoding="utf-8") as f:
            ips += [ln.split()[0] for ln in f if ln.strip() and is_ip(ln.split()[0])]
    seen, out = set(), []
    for ip in ips:
        if is_ip(ip) and ip not in seen:
            seen.add(ip); out.append(ip)
    return out[: args.top] if args.top else out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Test clean IPs through your own config using Xray (experimental)")
    ap.add_argument("--config", action="append", default=[], help="a vless/vmess/trojan link (repeatable)")
    ap.add_argument("--configs-file", help="file with one link per line")
    ap.add_argument("--ips", default="", help="comma-separated IPs")
    ap.add_argument("--ips-file", help="file whose lines start with an IP (e.g. outputs/alive_cloudflare.txt)")
    ap.add_argument("--top", type=int, default=20, help="test only the first N IPs (0 = all)")
    ap.add_argument("--xray", default=os.environ.get("XRAY_BIN", "xray"), help="path of the xray binary")
    ap.add_argument("--url", default=DEFAULT_URL); ap.add_argument("--jobs", type=int, default=2); ap.add_argument("--base-port", type=int, default=19080)
    ap.add_argument("--timeout", type=float, default=8.0); ap.add_argument("--out", help="write the full result as JSON")
    ap.add_argument("--no-validate", action="store_true", help="skip the `xray -test` validation")
    a = ap.parse_args(argv)
    links = list(a.config)
    if a.configs_file:
        with open(a.configs_file, encoding="utf-8") as f:
            links += [ln.strip() for ln in f if ln.strip() and "://" in ln]
    ips = load_ips(a)
    if not links or not ips:
        print("❌ حداقل یک کانفیگ (--config) و یک آی‌پی (--ips یا --ips-file) لازم است."); return 2
    if not shutil.which(a.xray) and not os.path.isfile(a.xray):
        print(f"❌ فایل xray پیدا نشد ({a.xray}). در Termux: نصب Xray-core و قرار دادن در PATH، یا --xray /مسیر/xray"); return 2
    if not a.no_validate:
        for l in links:
            try:
                good, msg = validate_with_xray(a.xray, build_xray_config(parse_link(l), ips[0], a.base_port))
            except Unsupported:
                continue
            if not good:
                print(f"❌ Xray ساختار کانفیگ ساخته‌شده را نپذیرفت؛ این ابزار آزمایشی است. پیام Xray:\n{msg}"); return 2
            break
    print(f"🔬 تست {len(ips)} آی‌پی × {len(links)} کانفیگ از مسیر Xray (آزمایشی)...")
    res = run_batch(a.xray, links, ips, a.url, a.jobs, a.base_port, a.timeout, progress=lambda r, i, n: print(f"  [{i}/{n}] {r['ip']:<40} {'✅ ' + str(r['ms']) + 'ms' if r['ok'] else '❌ ' + r['error']}"))
    good = [r for r in res if r["ok"]]
    print(f"\n📊 {len(good)} از {len(res)} ترکیب واقعاً کار کرد ({round(100 * len(good) / len(res)) if res else 0}٪)")
    for i, r in enumerate(good[:5], 1):
        print(f" {i}. {r['ip']:<40} ⚡ {r['ms']}ms")
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump({"tested_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "url": a.url, "results": res}, f, ensure_ascii=False, indent=1)
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
