#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, subprocess

def main():
    while True:
        print("\n" + "="*50 + "\n🌐 DOPS IP Scanner\n" + "="*50)
        print("1️⃣  Cloudflare Scanner (اسکن کامل)")
        print("2️⃣  Fastly Scanner (اسکن کامل)")
        print("3️⃣  📱 تست زنده روی اینترنت گوشی (سریع)")
        print("4️⃣  Test Telegram Sender")
        print("0️⃣  Exit")
        c = input("\nSelect (0-4): ").strip()
        if c == "0": sys.exit(0)
        elif c == "1": subprocess.run([sys.executable, "start.py"])
        elif c == "2": subprocess.run([sys.executable, "fastly.py"])
        elif c == "3": subprocess.run([sys.executable, "test_local.py"])
        elif c == "4": subprocess.run([sys.executable, "sender.py"])

if __name__ == "__main__":
    main()
