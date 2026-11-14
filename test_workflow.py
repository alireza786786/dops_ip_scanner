#!/usr/bin/env python3
# Copyright (c) 2026 alireza786786 (DOPS). All rights reserved. See LICENSE.
"""Validates .github/workflows YAML and simulates the restore/publish shell steps against a local git remote."""
import os, subprocess, sys, tempfile, yaml
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + name)
wf = None
for cand in (os.path.join(ROOT, "scanner.yml"), os.path.join(ROOT, ".github", "workflows", "scanner.yml")):
    if os.path.exists(cand): wf = cand; break
d = yaml.safe_load(open(wf, encoding="utf-8")); on = d.get("on", d.get(True))
check("one cron: a slot every 15 minutes", len(on["schedule"]) == 1 and on["schedule"][0]["cron"] == "7,22,37,52 * * * *")
g = d["env"]["SCAN_MIN_GAP_MIN"]
check("scan gap for schedule + Worker triggers only (manual always scans)", "github.event_name == 'schedule'" in g and "github.event.inputs.from == 'worker'" in g and "'25'" in g and "'0'" in g)
check("workflow_dispatch has a 'from' input defaulting to manual", on["workflow_dispatch"]["inputs"]["from"]["default"] == "manual")
check("first step prints event/cron for diagnosis", "github.event_name" in d["jobs"]["scan-and-publish"]["steps"][0]["run"])
check("manual force_telegram input", "force_telegram" in on["workflow_dispatch"]["inputs"])
check("concurrency group + no cancel", d["concurrency"]["group"] == "cdn-scanner" and d["concurrency"]["cancel-in-progress"] is False)
check("contents: write only", d["permissions"] == {"contents": "write"})
check("telegram interval 170", d["env"]["TG_INTERVAL_MIN"] == "170")
check("TG_FORCE only via github.event.inputs in steps", "TG_FORCE" not in d["env"] and all("github.event.inputs.force_telegram" in s["env"]["TG_FORCE"] for s in d["jobs"]["scan-and-publish"]["steps"] if s.get("env") and "TG_FORCE" in s["env"]))
steps = {s["name"]: s for s in d["jobs"]["scan-and-publish"]["steps"]}
check("timeout set", d["jobs"]["scan-and-publish"]["timeout-minutes"] == 20)
check("fastly runs even if cloudflare fails", "cancelled" in steps["Run Fastly Scanner"]["if"])
URL = "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
R, P = steps["Restore previous outputs from data branch"]["run"], steps["Publish outputs to data branch"]["run"]
check("scripts use the token URL", URL in R and URL in P)
tmp = tempfile.mkdtemp()
sh = lambda cmd, cwd: subprocess.run(["bash", "-c", cmd], cwd=cwd, capture_output=True, text=True)
sh("git init -q --bare remote.git && git init -q -b main work && cd work && git config user.email a@b && git config user.name n && echo hi > f && git add f && git commit -q -m i && git remote add origin ../remote.git && git push -q origin main", tmp)
R, P = R.replace(URL, tmp + "/remote.git"), P.replace(URL, tmp + "/remote.git"); w = tmp + "/work"
r = sh(R, w); check("first run: no data branch handled", "first run" in r.stdout and r.returncode == 0)
sh('echo "1.1.1.1 ping=1ms" > outputs/alive_cloudflare.txt', w); r = sh(P, w)
check("publish creates data branch with outputs/", r.returncode == 0 and "outputs/alive_cloudflare.txt" in sh("git --git-dir=remote.git ls-tree -r --name-only data", tmp).stdout)
sh("rm -rf outputs", w); sh(R, w); check("restore brings files back", "alive_cloudflare.txt" in sh("ls outputs", w).stdout)
check("no change -> no push", "No changes" in sh(P, w).stdout)
sh('echo "2.2.2.2 ping=2ms" >> outputs/alive_cloudflare.txt', w); r = sh(P, w)
check("change -> history stays 1 commit", r.returncode == 0 and sh("git --git-dir=remote.git rev-list --count data", tmp).stdout.strip() == "1")
check("main branch untouched", sh("git --git-dir=remote.git rev-list --count main", tmp).stdout.strip() == "1")
sys.exit(0 if ok else 1)
