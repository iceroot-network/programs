#!/usr/bin/env python3
"""Export approved unsigned instructions or prepare a draft genesis manifest."""

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from schema import Invalid, instant, require
from validate import binding_at, budget_period, manifest_hash, validate, validate_data


def export_statement(data, config, key, now):
    require(key in data["statements"], "unknown statement")
    statement = data["statements"][key]
    require(statement["status"] == "approved" and statement["approval"], "statement must be approved before export")
    require(instant(statement["approval"]["at"]) <= instant(now), "statement approval is in the future")
    for tx in statement["transactions"]:
        entry = data["entries"][tx["entry"]]
        require(entry["status"] == "approved", "entry has already settled or lost approval")
        require(entry["budget_period"] == budget_period(config, instant(now)), "yearly budget period changed; review before export")
        if entry["binding"]:
            binding_at(data["bindings"][entry["binding"]], entry["github_user_id"], now, data["bindings"], config)
    return {"format": "iceroot-unsigned-payments-v1", "statement": key,
            "transactions": copy.deepcopy(statement["transactions"])}


def genesis_manifest(data, config, key, cutoff):
    require(not data["genesis"], "a genesis manifest already exists; review it instead of replacing it")
    result = {"schema_version": 1, "example": False, "id": key, "status": "draft", "cutoff": cutoff,
              "credits": [], "sha256": ""}
    for entry in sorted(data["entries"].values(), key=lambda e: e["id"]):
        if entry["status"] != "bound" or entry["budget_period"] != "pre-mainnet":
            continue
        binding_at(data["bindings"][entry["binding"]], entry["github_user_id"], cutoff, data["bindings"], config)
        require(instant(entry["approval"]["at"]) <= instant(cutoff), "entry approval is after cutoff")
        result["credits"].append({"entry": entry["id"], "pool": data["programs"][entry["program"]]["pool"],
                                  "recipients": entry["payment"]["recipients"], "amount": entry["amount"],
                                  "fingerprint": entry["fingerprint"]})
    result["sha256"] = manifest_hash(result)
    candidate = copy.deepcopy(data)
    candidate["genesis"][key] = result
    validate_data(candidate, config)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--statement")
    group.add_argument("--genesis", help="new manifest id, for example GENESIS-MAINNET")
    parser.add_argument("--cutoff", help="published UTC genesis credit cutoff")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        data, config = validate(args.root)
        if args.statement:
            result = export_statement(data, config, args.statement, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        else:
            require(args.cutoff is not None, "genesis preparation needs a cutoff")
            from schema import check, load
            result = genesis_manifest(data, config, args.genesis, args.cutoff)
            check(result, load(args.root / "schemas/genesis.schema.json"))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
            handle.write("\n")
        print("Prepared unsigned instructions for review.")
        return 0
    except (Invalid, OSError, ValueError, KeyError) as error:
        print(f"Preparation stopped: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
