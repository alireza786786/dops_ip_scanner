#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, subprocess

def main():
    while True:
        print("\n" + "="*50 + "\n🌐 DOPS IP Scanner\n" + "="*50)
        print("1️⃣  Cloudflare Scanner\n2️⃣  Fastly Scanner\n3️⃣  Test Telegram Sender\n0️⃣  Exit")
        c = input("\nSelect (0-3): ").strip()
        if c == "0": sys.exit(0)
        elif c == "1": subprocess.run([sys.executable, "start.py"])
        elif c == "2": subprocess.run([sys.executable, "fastly.py"])
        elif c == "3": subprocess.run([sys.executable, "sender.py"])

if __name__ == "__main__":
    main()
