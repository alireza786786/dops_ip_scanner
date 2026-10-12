#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time, socket
from typing import List, Tuple

# لیست DNS سرورهای معتبر داخلی ایران
IRAN_RESOLVERS = [
    ("رادار گیم ۱", "10.202.10.10"),
    ("رادار گیم ۲", "10.202.10.11"),
    ("سرویس ۴۰۳", "10.202.10.202"),
    ("بگذر ۱", "185.55.226.26"),
    ("بگذر ۲", "185.55.225.25"),
    ("شکن ۱", "178.22.122.100"),
    ("شکن ۲", "185.51.200.2"),
    ("الکترو", "78.157.42.100"),
    ("همراه اول", "208.67.222.222"),
    ("ایرانسل", "109.69.8.51"),
    ("مخابرات ۱", "8.8.8.8"),
    ("مخابرات ۲", "4.2.2.4")
]

def test_udp_dns(ip: str, timeout: float = 1.5) -> Tuple[bool, float]:
    """تست باز بودن پورت ۵۳ برای تونل"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    # پکت ساده استاندارد DNS
    dummy_query = b"\xaa\xaa\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x03www\x06google\x03com\x00\x00\x01\x00\x01"
    t0 = time.time()
    try:
        s.sendto(dummy_query, (ip, 53))
        data, _ = s.recvfrom(512)
        latency = (time.time() - t0) * 1000
        return True, round(latency, 1)
    except Exception:
        return False, 9999
    finally:
        s.close()

def main():
    print("\n🔍 در حال اسکن ریزالورهای فعال داخلی برای تونل DNSTT...")
    print("=" * 50)
    alive = []
    for name, ip in IRAN_RESOLVERS:
        ok, lat = test_udp_dns(ip)
        if ok:
            alive.append((name, ip, lat))
            print(f" ✅ {name:<15} {ip:<16} ⚡ {lat}ms")
        else:
            print(f" ❌ {name:<15} {ip:<16} مسدود/بسته")
    
    alive.sort(key=lambda x: x[2])
    print("=" * 50)
    if alive:
        best_name, best_ip, best_lat = alive[0]
        print(f"\n🏆 بهترین سرور برای تونل: {best_name} ({best_ip})")
        print("\nدستور اتصال نمونه:")
        print(f"dnstt-client -udp {best_ip}:53 -pubkey-file server.pub <دامنه-شما> 127.0.0.1:7000\n")
    else:
        print("⚠️ هیچ سرور بازی پیدا نشد.")

if __name__ == "__main__":
    main()
