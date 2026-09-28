#!/usr/bin/env python3
"""Validate schemas, accounting, bindings and unsigned payment instructions offline."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

from schema import Invalid, check, instant, load, require

ROOT = 10**18
KINDS = {"programs": "program", "entries": "entry", "bindings": "binding",
         "bounties": "bounty", "statements": "statement", "genesis": "genesis"}
RATES = {"critical": 50000, "high": 12500, "medium": 2500, "low": 500,
         "bug": 250, "tier-1": 2500, "tier-2": 1000, "tier-3": 250,
         "credit": 0, "none": 0}


def fingerprint(entry):
    payment = entry["payment"]
    recipients = ",".join(f"{r['address']}={r['amount']}" for r in payment["recipients"])
    line = f"iceroot-entry:v1|{entry['id']}|{payment['pool_address']}|{recipients}|{int(entry['related_party'])}"
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def memo(entry):
    return f"iceroot:pay:v1 {entry['id']} {fingerprint(entry)}"


def manifest_hash(manifest):
    payload = {key: value for key, value in manifest.items() if key != "sha256"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def budget_period(config, now):
    if not config["mainnet_at"] or now < instant(config["mainnet_at"]):
        return "pre-mainnet"
    launch = instant(config["mainnet_at"])
    years = now.year - launch.year
    try:
        anniversary = launch.replace(year=now.year)
    except ValueError:
        anniversary = launch.replace(year=now.year, day=28)
    return f"year-{years + int(now >= anniversary)}"


def address(value, prefix, example=False):
    if example and value.startswith("example-"):
        return
    require(value.startswith(prefix + "1") and len(value) == len(prefix) + 59,
            "wrong address network or length")
    alphabet = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
    try:
        data = [alphabet.index(c) for c in value[len(prefix) + 1:]]
    except ValueError as error:
        raise Invalid("invalid address character") from error
    expanded = [ord(c) >> 5 for c in prefix] + [0] + [ord(c) & 31 for c in prefix]
    checksum = 1
    for number in expanded + data:
        top = checksum >> 25
        checksum = ((checksum & 0x1ffffff) << 5) ^ number
        for i, generator in enumerate((0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3)):
            if (top >> i) & 1:
                checksum ^= generator
    require(checksum == 0x2bc830a3, "invalid Bech32m checksum")
    require(data[-7] & 15 == 0, "noncanonical address padding")


def read_records(root, examples=False):
    result = {}
    for folder, kind in KINDS.items():
        records = {}
        schema = load(root / "schemas" / f"{kind}.schema.json")
        for path in sorted((root / folder).rglob("*.json")):
            relative = path.relative_to(root / folder).parts
            is_example = "examples" in relative
            if examples != is_example:
                continue
            require(len(relative) == (2 if examples else 1), "records must be directly in their data or examples directory")
            value = load(path)
            check(value, schema, str(path.relative_to(root)))
            require(value["example"] == examples, f"{path.name}: example flag disagrees with directory")
            require(path.stem == value["id"], f"{path.name}: filename must equal id")
            require(value["id"] not in records, f"duplicate id: {value['id']}")
            records[value["id"]] = value
        result[folder] = records
    return result


def binding_at(binding, user, at, bindings, config):
    when = instant(at)
    require(binding["github_user_id"] == user, "binding belongs to another GitHub account")
    usable = binding["status"] == "verified" or (binding["status"] == "revoked" and binding["revoked_at"]
                                                 and when < instant(binding["revoked_at"]))
    require(usable and binding["verification"], "binding is not verified at payment time")
    require(instant(binding["effective_at"]) <= when, "binding used before seven-day wait ended")
    require(instant(binding["verification"]["at"]) <= when, "binding used before verification")
    require(binding["mainnet"] is not None, "mainnet binding missing")
    require(instant(binding["mainnet"]["at"]) <= when, "binding transaction is later than payment")
    for other in bindings.values():
        if other["github_user_id"] == user and instant(binding["posted_at"]) < instant(other["posted_at"]) <= when:
            raise Invalid("a newer account link requires review before payment")
    if config["binding_deadline"]:
        require(instant(binding["mainnet"]["at"]) <= instant(config["binding_deadline"]),
                "binding transaction is after the recorded deadline")


def validate_data(data, config, examples=False):
    pools = {p["id"]: p for p in config["pools"]}
    require(len(pools) == 5 and set(pools) == {"security", "developer", "campaigns", "reserve", "community"},
            "only the five program pools belong in the list")
    programs, entries, bindings, bounties, statements, manifests = (data[k] for k in KINDS)
    identifiers = set()
    for folder, records in data.items():
        if folder == "bounties":
            continue
        for key in records:
            require(key not in identifiers, f"id reused across kinds: {key}")
            identifiers.add(key)
    for bounty in bounties.values():
        require(bounty["id"] not in identifiers or bounty["entry"] == bounty["id"] in entries,
                "bounty id must reserve or reference one entry")
    for program in programs.values():
        require(program["pool"] in pools, "program references an unknown pool")
    for pool in pools.values():
        if pool["address"]:
            address(pool["address"], "ice", examples)
    published_addresses = [p["address"] for p in pools.values() if p["address"]]
    require(len(published_addresses) == len(set(published_addresses)), "pool accounts must be distinct")
    by_user = defaultdict(list)
    for binding in bindings.values():
        require(binding["id"].split("-")[1] == str(binding["github_user_id"]), "link id and account disagree")
        require(binding["github_user_id"] == binding["post_author_id"], "signed post has a different author")
        require(instant(binding["effective_at"]) == instant(binding["posted_at"]) + timedelta(days=7),
                "new or changed links require exactly seven days")
        address(binding["testnet_address"], "tice", examples)
        require(instant(binding["signed_at"]) <= instant(binding["posted_at"]), "signed time is after publication")
        expected = (f"IceRoot GitHub link v1\nGitHub user id: {binding['github_user_id']}\n"
                    f"Account: {binding['testnet_address']}\nDate: {binding['signed_at']}")
        require(binding["message"] == expected, "signed message does not match binding details")
        if binding["status"] in {"verified", "revoked"}:
            require(binding["verification"] is not None, "verified binding needs verification evidence")
            require(instant(binding["verification"]["at"]) >= instant(binding["posted_at"]), "verification predates post")
        if binding["status"] == "revoked":
            require(binding["revoked_at"] is not None and instant(binding["revoked_at"]) >= instant(binding["posted_at"]),
                    "revoked link needs a valid revocation time")
        else:
            require(binding["revoked_at"] is None, "unexpected revocation time")
        if binding["mainnet"]:
            mainnet = binding["mainnet"]
            address(mainnet["address"], "ice", examples)
            require(mainnet["memo"] == f"iceroot:bind:v1 {mainnet['address']}", "wrong binding memo")
            require(instant(mainnet["at"]) >= instant(binding["effective_at"]), "binding transaction precedes seven-day wait")
        by_user[binding["github_user_id"]].append(binding)
    for links in by_user.values():
        links.sort(key=lambda b: b["posted_at"])
        for i, binding in enumerate(links):
            require(binding["previous"] == (links[i-1]["id"] if i else None), "broken account link history")
            if i:
                require(binding["posted_at"] > links[i-1]["posted_at"], "account links have the same timestamp")

    totals, caps, pool_totals, pool_caps = (defaultdict(int) for _ in range(4))
    for entry in entries.values():
        key = entry["id"]
        require(entry["program"] in programs, f"{key}: unknown program")
        require(key.rsplit("-", 1)[0] == entry["program"], f"{key}: wrong program prefix")
        program = programs[entry["program"]]
        pool = pools[program["pool"]]
        require(entry["related_party"] == bool(entry["relationship"] and entry["relationship"].strip()),
                f"{key}: related-party mark and relationship disagree")
        if program["bounty"]:
            require(entry["github_user_id"] is not None, f"{key}: bounty needs numeric GitHub account")
            require(entry["github_user_id"] not in config["team_ids"], f"{key}: team members cannot earn bounties")
            require(key in bounties and bounties[key]["entry"] == key, f"{key}: bounty record missing")
        amount = int(entry["amount"])
        if entry["status"] != "cancelled":
            totals[program["id"]] += amount
            pool_totals[pool["id"]] += amount
            if entry["status"] != "queued":
                require(entry["budget_period"] is not None, f"{key}: budget period missing")
                caps[program["id"], entry["budget_period"]] += amount
                if program["bounty"]:
                    pool_caps[pool["id"], entry["budget_period"]] += amount
        if entry["status"] == "queued":
            require(entry["budget_period"] is None, f"{key}: queued entry cannot reserve a yearly cap")
        if entry["payment"]:
            require(entry["payment"]["pool_address"] == pool["address"], f"{key}: wrong pool account")
            address(entry["payment"]["pool_address"], "ice", examples)
            recipients = entry["payment"]["recipients"]
            require(sum(int(r["amount"]) for r in recipients) == amount, f"{key}: recipient total mismatch")
            require(len({r["address"] for r in recipients}) == len(recipients), f"{key}: repeated recipient")
            for recipient in recipients:
                address(recipient["address"], "ice", examples)
            require(entry["fingerprint"] == fingerprint(entry), f"{key}: fingerprint mismatch")
            require(entry["memo"] == memo(entry) and len(entry["memo"].encode()) <= 255, f"{key}: memo mismatch or too long")
            if program["bounty"]:
                require(entry["binding"] in bindings, f"{key}: unknown binding")
                binding = bindings[entry["binding"]]
                require(binding["mainnet"] is not None and binding["status"] in {"verified", "revoked"}, f"{key}: binding unverified")
                require(binding["github_user_id"] == entry["github_user_id"], f"{key}: wrong binding user")
                require(len(recipients) == 1 and recipients[0]["address"] == binding["mainnet"]["address"],
                        f"{key}: payout address differs from binding")
        else:
            require(entry["fingerprint"] is None and entry["memo"] is None and entry["binding"] is None,
                    f"{key}: unbound entry cannot carry payment metadata")
        if entry["status"] in {"bound", "approved", "paid", "credited"}:
            require(entry["payment"] is not None, f"{key}: payable entry has no payment")
        if entry["status"] in {"earned", "bound", "approved", "paid", "credited"}:
            require(entry["approval"] is not None, f"{key}: approval evidence required")
            require(instant(entry["approval"]["at"]) >= instant(entry["earned_at"]), f"{key}: approval predates earning")
        if entry["status"] == "paid":
            require(entry["receipt"] is not None and entry["receipt"]["memo"] == entry["memo"], f"{key}: receipt missing or wrong memo")
        else:
            require(entry["receipt"] is None, f"{key}: unexpected receipt")
    for code, total in totals.items():
        require(total <= int(programs[code]["budget"]), f"{code}: program budget exceeded")
    for (code, period), total in caps.items():
        limit = programs[code]["yearly_cap"]
        require(limit is None or total <= int(limit), f"{code} {period}: yearly cap exceeded")
    for pool, total in pool_totals.items():
        require(total <= int(pools[pool]["allocation"]), f"{pool}: pool allocation exceeded")
    for (pool, period), total in pool_caps.items():
        limit = pools[pool]["bounty_yearly_cap"]
        require(limit is None or total <= int(limit), f"{pool} {period}: shared yearly bounty cap exceeded")

    sources = set()
    for bounty in bounties.values():
        require(bounty["source"] not in sources, "source has more than one bounty record")
        sources.add(bounty["source"])
        require(bounty["related_party"] == bool(bounty["relationship"] and bounty["relationship"].strip()),
                "bounty related-party disclosure missing")
        rating = bounty["rating"]
        allowed = {"security": {"critical", "high", "medium", "low"}, "bug": {"bug"},
                   "contribution": {"tier-1", "tier-2", "tier-3", "posted", "credit", "none"}}
        require(rating in allowed[bounty["kind"]], "rating does not match bounty kind")
        if rating == "posted":
            require(0 < int(bounty["amount"]) <= 12500 * ROOT, "posted bounty exceeds limit")
        else:
            require(int(bounty["amount"]) == RATES[rating] * ROOT, "amount differs from provisional table")
        if bounty["kind"] == "security":
            require(bounty["advisory"] is not None and bounty["advisory"]["private_report_confirmed"],
                    "security reward needs a published advisory and private-first confirmation")
        else:
            require(bounty["advisory"] is None, "unexpected advisory")
        require((bounty["status"] == "duplicate") == (bounty["duplicate_of"] is not None), "duplicate reference missing or unexpected")
        if bounty["entry"]:
            require(bounty["entry"] == bounty["id"] in entries, "bounty and entry must share one id")
            entry = entries[bounty["entry"]]
            for field in ("amount", "github_user_id", "related_party", "relationship"):
                require(entry[field] == bounty[field], f"bounty and entry disagree: {field}")
            require(entry["program"] == {"security": "SEC", "bug": "BUG", "contribution": "DEV"}[bounty["kind"]], "wrong bounty pool program")
            require(bounty["status"] in {"accepted", "paid", "credited"}, "unaccepted bounty has an entry")
            if bounty["status"] in {"paid", "credited"} or entry["status"] in {"paid", "credited"}:
                require(bounty["status"] == entry["status"], "bounty and entry settlement states disagree")
            if bounty["kind"] == "security":
                require(bounty["advisory"]["url"] in entry["evidence"], "entry must link the public advisory")
        elif bounty["status"] in {"accepted", "paid", "credited"}:
            require(int(bounty["amount"]) == 0, "accepted payable bounty has no entry")

    assigned = set()
    receipts = set()
    for statement in statements.values():
        require(statement["id"] == "MONTH-" + statement["month"], "statement id disagrees with month")
        require(statement["prepared_at"][:7] > statement["month"], "statement month has not ended")
        if statement["status"] != "proposed":
            require(statement["approval"] is not None, "statement approval missing")
        if statement["approval"]:
            require(instant(statement["approval"]["at"]) >= instant(statement["prepared_at"]),
                    "statement approval predates preparation")
        for key in statement["earned_entries"]:
            require(key in entries, "unknown earned entry in statement")
        for key in statement["credit_only"]:
            require(key in bounties and int(bounties[key]["amount"]) == 0, "invalid credit-only item")
        for tx in statement["transactions"]:
            key = tx["entry"]
            require(config["mainnet_at"] is not None, "cannot prepare transfers before mainnet")
            require(key in entries and key not in assigned, "entry repeated across payment statements")
            assigned.add(key)
            entry = entries[key]
            require(entry["status"] in {"approved", "paid"}, "statement contains an unapproved entry")
            require(tx["pool"] == programs[entry["program"]]["pool"], "statement pool mismatch")
            for field in ("payment", "fingerprint", "memo", "amount", "related_party"):
                require(tx[field] == entry[field], f"statement payment mismatch: {field}")
            require(instant(entry["approval"]["at"]) <= instant(statement["prepared_at"]), "statement predates listing approval")
            require(instant(statement["prepared_at"]) >= instant(config["mainnet_at"]), "statement predates mainnet")
            if entry["binding"]:
                binding_at(bindings[entry["binding"]], entry["github_user_id"], statement["prepared_at"], bindings, config)
            require(entry["budget_period"] == budget_period(config, instant(statement["prepared_at"])),
                    "statement payment uses the wrong yearly budget period")
            if statement["status"] == "paid":
                require(entry["status"] == "paid", "paid statement contains unpaid entry")
            if entry["status"] == "paid":
                require(statement["status"] in {"approved", "paid"} and statement["approval"],
                        "paid entry requires an approved statement")
                require(instant(entry["receipt"]["confirmed_at"]) >= instant(statement["approval"]["at"]),
                        "receipt predates statement approval")
                require(entry["receipt"]["transaction_id"] not in receipts, "transaction receipt reused for multiple entries")
                receipts.add(entry["receipt"]["transaction_id"])
    credited = set()
    frozen_credits = set()
    for manifest in manifests.values():
        require(manifest["sha256"] == manifest_hash(manifest), "genesis manifest hash mismatch")
        for credit in manifest["credits"]:
            key = credit["entry"]
            require(key in entries and key not in credited and key not in assigned, "duplicate genesis or monthly allocation")
            credited.add(key)
            entry = entries[key]
            require(entry["status"] in {"bound", "credited"}, "genesis entry is not bound")
            require(entry["budget_period"] == "pre-mainnet", "genesis credit uses wrong budget period")
            require(credit["pool"] == programs[entry["program"]]["pool"], "genesis pool mismatch")
            require(credit["amount"] == entry["amount"] and credit["fingerprint"] == entry["fingerprint"]
                    and credit["recipients"] == entry["payment"]["recipients"], "genesis payment mismatch")
            require(instant(entry["approval"]["at"]) <= instant(manifest["cutoff"]), "genesis cutoff precedes approval")
            binding_at(bindings[entry["binding"]], entry["github_user_id"], manifest["cutoff"], bindings, config)
            if manifest["status"] == "frozen":
                require(config["binding_deadline"] is not None and config["mainnet_at"] is not None,
                        "genesis dates must be published before freezing")
                require(instant(manifest["cutoff"]) <= instant(config["mainnet_at"]), "genesis cutoff is after mainnet")
                frozen_credits.add(key)
    for entry in entries.values():
        if entry["status"] == "credited":
            require(entry["id"] in frozen_credits, "credited entry missing from frozen genesis manifest")
        if entry["status"] == "paid":
            require(entry["id"] in assigned, "paid entry missing from monthly statement")
            require(config["mainnet_at"] and instant(entry["receipt"]["confirmed_at"]) >= instant(config["mainnet_at"]),
                    "payment confirmed before mainnet")
            if entry["binding"]:
                binding_at(bindings[entry["binding"]], entry["github_user_id"], entry["receipt"]["confirmed_at"], bindings, config)
            require(entry["budget_period"] == budget_period(config, instant(entry["receipt"]["confirmed_at"])),
                    "receipt falls outside the reserved yearly budget period")


def validate(root, examples=False):
    config = load(root / "config.json")
    check(config, load(root / "schemas/config.schema.json"), "config.json")
    if examples:
        config = load(root / "tests/example-config.json")
        check(config, load(root / "schemas/config.schema.json"), "example config")
    data = read_records(root, examples)
    validate_data(data, config, examples)
    return data, config


def history(root, base, data):
    require(re.fullmatch(r"[0-9a-f]{40}", base) is not None, "base must be a full commit hash")
    paths = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", base], cwd=root, text=True).splitlines()
    for path in paths:
        parts = Path(path).parts
        if len(parts) != 2 or parts[0] not in KINDS or not path.endswith(".json"):
            continue
        old = json.loads(subprocess.check_output(["git", "show", f"{base}:{path}"], cwd=root, text=True))
        current = data[parts[0]].get(old["id"])
        require(current is not None, f"historical id removed: {old['id']}; retain cancelled records")
        if parts[0] == "bindings":
            for key in old.keys() - {"status", "verification", "mainnet", "revoked_at"}:
                require(old[key] == current[key], "changed link requires a new record and seven-day wait")
        if old.get("status") in {"paid", "credited", "frozen"}:
            require(old == current, f"settled record changed: {old['id']}")
        if parts[0] == "bounties":
            require(old["source"] == current["source"] and old["github_user_id"] == current["github_user_id"],
                    "bounty id reused for different work or recipient")
        if parts[0] == "entries":
            for key in ("program", "github_user_id", "earned_at"):
                require(old[key] == current[key], "entry id reused")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--examples", action="store_true")
    parser.add_argument("--base", help="compare immutable records with this commit hash")
    args = parser.parse_args()
    try:
        data, _ = validate(args.root, args.examples)
        if args.base:
            history(args.root, args.base, data)
        print(f"Validated {sum(map(len, data.values()))} {'example' if args.examples else 'live'} records.")
    except (Invalid, ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
