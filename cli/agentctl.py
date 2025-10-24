from __future__ import annotations
import argparse, json, os, sys, time
from typing import Any
import httpx

API_URL = os.getenv("API_URL","http://localhost:8080")
API_KEY = os.getenv("API_KEY","dev-local")

def cmd_submit(args):
    with open(args.file,"r") as f:
        payload = json.load(f)
    headers = {"X-API-Key": API_KEY}
    r = httpx.post(f"{API_URL}/v1/tasks", json=payload, headers=headers, timeout=30.0)
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2))

def cmd_status(args):
    r = httpx.get(f"{API_URL}/v1/tasks/{args.id}")
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2))

def cmd_cancel(args):
    headers = {"X-API-Key": API_KEY}
    r = httpx.post(f"{API_URL}/v1/tasks/{args.id}/cancel", headers=headers, timeout=30.0)
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2))

def cmd_feedback(args):
    with open(args.file,"r") as f:
        payload = json.load(f)
    headers = {"X-API-Key": API_KEY}
    r = httpx.post(f"{API_URL}/v1/feedback", json=payload, headers=headers, timeout=30.0)
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2))

def main():
    p = argparse.ArgumentParser(prog="agentctl", description="Control the Multi-Agent Code System API")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("submit", help="Submit a task JSON")
    sp.add_argument("file")
    sp.set_defaults(func=cmd_submit)

    sp = sub.add_parser("status", help="Get task status by id")
    sp.add_argument("id")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("cancel", help="Cancel a task by id")
    sp.add_argument("id")
    sp.set_defaults(func=cmd_cancel)

    sp = sub.add_parser("feedback", help="Submit feedback JSON")
    sp.add_argument("file")
    sp.set_defaults(func=cmd_feedback)

    args = p.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
