#!/usr/bin/env python3
"""Find out exactly why the Forge is not producing creatures.

Runs the real Forge code against your real model, one stage at a time, and
says which stage breaks. It writes nothing to your data files.

    python3 tools/forge_doctor.py
    python3 tools/forge_doctor.py --model qwen3.8:27b-mlx
    python3 tools/forge_doctor.py --all-models      # try every model you have
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import forge  # noqa: E402

OK, BAD, WARN, INFO = "  OK  ", " FAIL ", " WARN ", "      "
LINE = "-" * 74


def head(title):
    print(f"\n{LINE}\n{title}\n{LINE}")


def post(endpoint, body, timeout=180):
    req = urllib.request.Request(endpoint.rstrip("/") + "/api/generate",
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    started = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8")), time.time() - started


def stage_reachable(endpoint):
    head("1. Is Ollama there, and what does it have?")
    try:
        with urllib.request.urlopen(endpoint.rstrip("/") + "/api/tags", timeout=10) as r:
            models = json.loads(r.read().decode("utf-8")).get("models", [])
    except Exception as exc:
        print(f"{BAD} cannot reach {endpoint}: {exc}")
        print(f"{INFO} start it with:  ollama serve")
        return None
    print(f"{OK} {endpoint} answered with {len(models)} model(s)")
    for m in models:
        print(f"{INFO}   {m['name']:<34} {round(m.get('size', 0) / 1e9, 1)} GB")
    return [m["name"] for m in models]


def stage_thinking(endpoint, model):
    """Does this model answer in `response`, or bury it in `thinking`?"""
    head(f"2. Where does {model} put its answer?")
    body = {"model": model, "prompt": 'Return one JSON object: {"ok":true}',
            "format": "json", "stream": False}
    try:
        blob, secs = post(endpoint, body, timeout=120)
    except Exception as exc:
        print(f"{BAD} the request failed: {exc}")
        return None
    resp = (blob.get("response") or "").strip()
    think = (blob.get("thinking") or "").strip()
    print(f"{INFO} took {secs:.1f}s, {blob.get('eval_count', 0)} tokens")
    print(f"{INFO} response: {resp[:70]!r}")
    print(f"{INFO} thinking: {think[:70]!r}")
    if resp:
        print(f"{OK} answers in `response` — the normal case")
        return "response"
    if think:
        print(f"{WARN} answers in `thinking`, leaving `response` empty")
        print(f"{INFO} this is a reasoning model. The Forge now reads `thinking`")
        print(f"{INFO} as a fallback, so this is handled — but see stage 3.")
        return "thinking"
    print(f"{BAD} both fields are empty. This model returned nothing usable.")
    return "empty"


def stage_think_off(endpoint, model):
    """Can we turn reasoning off, so the model stops burning tokens on it?"""
    head("3. Can reasoning be switched off?")
    body = {"model": model, "prompt": 'Return one JSON object: {"ok":true}',
            "format": "json", "stream": False, "think": False}
    try:
        blob, secs = post(endpoint, body, timeout=120)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:160]
        except Exception:
            pass
        print(f"{WARN} Ollama refused `think:false` ({exc.code})")
        print(f"{INFO} {detail}")
        print(f"{INFO} the Forge drops the field automatically on this error.")
        return False
    except Exception as exc:
        print(f"{BAD} request failed: {exc}")
        return False
    resp = (blob.get("response") or "").strip()
    think = (blob.get("thinking") or "").strip()
    if resp and not think:
        print(f"{OK} `think:false` works — answer moved into `response` ({secs:.1f}s)")
        return True
    if think:
        print(f"{WARN} accepted but the model still reasoned. Harmless: the")
        print(f"{INFO} fallback reads `thinking`. Costs you some speed.")
        return True
    print(f"{WARN} accepted, but nothing came back.")
    return True


def stage_schema(endpoint, model):
    """Grammar-constrained decoding: supported, and at what speed?"""
    head("4. Does schema-constrained output work, and is it worth it?")
    schema = json.load(open(os.path.join(ROOT, "schemas", "monster.schema.json")))
    body = {"model": model, "prompt": "Invent one small forest creature.",
            "format": schema, "stream": False, "think": False}
    try:
        blob, secs = post(endpoint, body, timeout=forge.SCHEMA_TIMEOUT)
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"{WARN} no usable answer within {forge.SCHEMA_TIMEOUT}s: {exc}")
        print(f"{INFO} untick 'Use the exact game data shape'. repair_record()")
        print(f"{INFO} fills in whatever the schema would have forced.")
        return False
    except Exception as exc:
        print(f"{WARN} refused: {exc}")
        return False
    text = (blob.get("response") or "").strip() or (blob.get("thinking") or "").strip()
    print(f"{INFO} {secs:.1f}s, {blob.get('eval_count', 0)} tokens")
    if secs > 60:
        print(f"{WARN} that is slow. Untick 'Use the exact game data shape'.")
    else:
        print(f"{OK} schema mode works at a usable speed")
    return bool(text)


def stage_real(endpoint, model, use_schema):
    """The actual monster prompt, through the actual Forge code."""
    head("5. Forge one real creature, end to end")
    ask = {"level": 5, "rarity": "Common", "type": "Nature", "role": "Striker",
           "tone": "grim", "brief": "something that lives in flooded stacks and eats paper"}
    system, user = forge.build_prompt("monster", ask)
    schema = None
    if use_schema:
        schema = json.load(open(os.path.join(ROOT, "schemas", "monster.schema.json")))
    print(f"{INFO} prompt is {len(system) + len(user)} chars; generating...")
    started = time.time()
    try:
        blob = forge.ollama_generate(endpoint, model, system, user, 0.9, schema=schema)
    except Exception as exc:
        print(f"{BAD} generation failed: {exc}")
        return False
    secs = time.time() - started
    resp = (blob.get("response") or "").strip()
    think = (blob.get("thinking") or "").strip()
    raw = resp or think
    print(f"{INFO} {secs:.1f}s, {blob.get('eval_count', 0)} tokens, "
          f"answer arrived in `{'response' if resp else 'thinking' if think else 'nothing'}`")
    if not raw:
        print(f"{BAD} the model returned nothing at all.")
        return False
    print(f"{INFO} first 160 chars: {raw[:160]!r}")

    try:
        record = forge.coerce_json(raw)
    except Exception as exc:
        print(f"{BAD} could not find JSON in the reply: {exc}")
        print(f"{INFO} full reply below so we can see what it did:\n")
        print(raw[:2500])
        return False
    print(f"{OK} parsed JSON with {len(record)} top-level fields")

    record, notes = forge.repair_record("monster", record)
    if notes:
        print(f"{INFO} repaired {len(notes)} thing(s):")
        for n in notes[:12]:
            print(f"{INFO}   - {n}")
    report = forge.check("monster", record)
    if report["errors"]:
        print(f"{BAD} still invalid after repair:")
        for e in report["errors"]:
            print(f"{INFO}   - {e}")
        return False
    print(f"{OK} validates clean")

    stats = record.get("base_stats", {})
    types = record.get("types", {})
    print(f"{INFO} {record.get('name')} — {record.get('rarity')} {types.get('primary')}"
          f"/{types.get('secondary')} — BST {sum(stats.values())} {stats}")

    forge.apply_portrait_seed(record)
    forge.write_visual_assets("monster", record)
    png = os.path.join(ROOT, "assets", "V2", "monsters", f"{record['id']}.png")
    if os.path.isfile(png):
        print(f"{OK} sprite written: assets/V2/monsters/{record['id']}.png "
              f"({os.path.getsize(png)} bytes)")
        os.remove(png)          # this is a test; leave no trace
    else:
        print(f"{BAD} no sprite was written for {record['id']}")
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://localhost:11434")
    ap.add_argument("--model", default=None)
    ap.add_argument("--all-models", action="store_true")
    args = ap.parse_args()

    print("VOIDCALLER FORGE DOCTOR")
    print(f"repo: {ROOT}")

    available = stage_reachable(args.endpoint)
    if not available:
        return 1

    targets = available if args.all_models else [args.model or available[0]]
    results = {}
    for model in targets:
        if model not in available:
            print(f"\n{BAD} {model} is not installed. Have: {', '.join(available)}")
            continue
        where = stage_thinking(args.endpoint, model)
        if where == "empty":
            results[model] = "returns nothing"
            continue
        stage_think_off(args.endpoint, model)
        schema_ok = stage_schema(args.endpoint, model)
        good = stage_real(args.endpoint, model, use_schema=schema_ok)
        results[model] = "WORKS" if good else "fails at generation"

    head("VERDICT")
    for model, verdict in results.items():
        mark = OK if verdict == "WORKS" else BAD
        print(f"{mark} {model:<34} {verdict}")
    if any(v == "WORKS" for v in results.values()):
        best = [m for m, v in results.items() if v == "WORKS"][0]
        print(f"\n{INFO} Set the Forge's model box to: {best}")
        print(f"{INFO} Then forge one creature to confirm, before doing a batch.")
    else:
        print(f"\n{INFO} Nothing worked. Send this whole output over and we'll")
        print(f"{INFO} fix it from what it says.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
