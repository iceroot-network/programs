#!/usr/bin/env python3
"""Read public bounty activity and propose reviewable records. Never sign or pay."""

import argparse
import copy
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from schema import Invalid, check, instant, load, require
from validate import ROOT, RATES, binding_at, budget_period, validate, validate_data

LABELS = {"bounty: critical": "critical", "bounty: high": "high", "bounty: medium": "medium", "bounty: low": "low",
          "bounty: confirmed bug": "bug", "bounty: tier 1": "tier-1", "bounty: tier 2": "tier-2",
          "bounty: tier 3": "tier-3", "bounty: posted": "posted", "bounty: credit": "credit", "bounty: none": "none"}
# Private reports can be filed through the organisation's .github repository, so a
# published advisory may live there instead of in the affected repository.
ADVISORY_FALLBACK = "iceroot-network/.github"


class GitHub:
    def __init__(self, token="", writable=False):
        self.token = token
        self.writable = bool(token and writable)

    def request(self, path, method="GET", body=None):
        require(path.startswith("/") and not path.startswith("//"), "API path must be relative")
        require(method == "GET" or self.writable, "bot is read-only without PROGRAMS_BOT_TOKEN")
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "iceroot-programs"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request("https://api.github.com" + path, method=method, headers=headers,
                          data=json.dumps(body).encode() if body is not None else None)
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            raise Invalid(f"GitHub API {method} {path.split('?')[0]} returned {error.code}") from None

    def pages(self, path, **query):
        for page in range(1, 10001):
            rows = self.request(path + "?" + urlencode({**query, "per_page": 100, "page": page}))
            require(isinstance(rows, list), "unexpected paginated response")
            yield from rows
            if len(rows) < 100:
                return
        raise Invalid("pagination limit reached; refusing a partial snapshot")


def trusted_label(issue, events, label, maintainers):
    if label not in {x["name"] for x in issue["labels"]}:
        return False
    changes = [e for e in events if e.get("event") in {"labeled", "unlabeled"}
               and e.get("label", {}).get("name") == label]
    changes.sort(key=lambda e: (e["created_at"], e["id"]))
    return bool(changes and changes[-1]["event"] == "labeled"
                and changes[-1].get("actor", {}).get("id") in maintainers)


def command(comment, prefix):
    body = comment.get("body", "").strip()
    if not body.startswith(prefix + "\n"):
        return None
    try:
        result = json.loads(body[len(prefix) + 1:])
    except (ValueError, TypeError):
        raise Invalid(f"invalid command JSON in comment {comment['id']}") from None
    require(isinstance(result, dict), "command must contain a JSON object")
    return result


def approved_claim(comments, maintainers, item_author, security=False):
    claims = [(c, command(c, "/bounty claim")) for c in comments]
    claims = [(c, payload) for c, payload in claims if payload is not None]
    require(bool(claims), "claim comment missing")
    approved = []
    for comment, payload in claims:
        require(set(payload) == {"related_party", "relationship", "team_member", "advisory"}, "unknown or missing claim fields")
        require(type(payload["related_party"]) is bool and type(payload["team_member"]) is bool,
                "claim declarations must be booleans")
        require(payload["relationship"] is None or isinstance(payload["relationship"], str), "invalid relationship")
        require(payload["related_party"] == bool(payload["relationship"] and payload["relationship"].strip()),
                "related-party relationship must be stated")
        require(not payload["team_member"], "team members cannot earn")
        uid = comment["user"]["id"]
        if not security and uid != item_author:
            continue
        approvals = [c for c in comments if c["user"]["id"] in maintainers
                     and c.get("body", "").strip() == f"/bounty approve {uid} {comment['id']}"
                     and instant(c["created_at"]) >= instant(comment["updated_at"])]
        if approvals:
            approved.append((comment, payload))
    require(len(approved) == 1, "exactly one current claim needs maintainer approval")
    return approved[0]


def published_advisory(api, repo, ghsa):
    errors = []
    for source in dict.fromkeys([repo, ADVISORY_FALLBACK]):
        try:
            return api.request(f"/repos/{source}/security-advisories/{ghsa}")
        except Invalid as error:
            errors.append(str(error))
    raise Invalid("advisory not found: " + "; ".join(errors))


def next_id(data, program):
    used = set(data["entries"]) | set(data["bounties"])
    numbers = [int(key.rsplit("-", 1)[1]) for key in used if key.startswith(program + "-")]
    return f"{program}-{max(numbers, default=0) + 1:04d}"


def propose_item(api, repo, issue, comments, events, data, config):
    source = issue["html_url"]
    if any(b["source"] == source for b in data["bounties"].values()):
        return
    maintainers = config["maintainer_ids"]
    declared = [label["name"] for label in issue["labels"] if label["name"] in LABELS]
    require(len(declared) == 1, "conflicting or missing rating labels")
    ratings = [rating for label, rating in LABELS.items() if trusted_label(issue, events, label, maintainers)]
    require(len(ratings) == 1, "exactly one trusted severity or tier label required")
    rating = ratings[0]
    security = rating in {"critical", "high", "medium", "low"}
    kind = "security" if security else "bug" if rating == "bug" else "contribution"
    program = {"security": "SEC", "bug": "BUG", "contribution": "DEV"}[kind]
    duplicate = trusted_label(issue, events, "bounty: duplicate", maintainers)
    claim, payload = approved_claim(comments, maintainers, issue["user"]["id"], security)
    uid = claim["user"]["id"]
    require(uid not in config["team_ids"], "team members cannot earn")
    require(trusted_label(issue, events, "bounty: approved", maintainers) or duplicate,
            "maintainer acceptance label missing")
    if kind == "contribution" and rating not in {"posted", "credit", "none"}:
        require("pull_request" in issue, "contribution reward needs a merged pull request")
    if "pull_request" in issue:
        pull = api.request(f"/repos/{repo}/pulls/{issue['number']}")
        require(pull.get("merged_at"), "pull request is not merged")
    elif not security:
        require(issue["state"] == "closed", "bug or posted task must be closed as accepted")
    advisory = None
    if security:
        require(isinstance(payload["advisory"], str), "public advisory id required")
        require(re.fullmatch(r"GHSA-[23456789cfghjmpqrvwx]{4}-[23456789cfghjmpqrvwx]{4}-[23456789cfghjmpqrvwx]{4}", payload["advisory"]), "invalid advisory id")
        public = published_advisory(api, repo, payload["advisory"])
        require(public.get("state") == "published" and public.get("published_at"), "advisory is not published")
        require(public.get("severity") == rating, "public advisory and label severity disagree")
        require(trusted_label(issue, events, "bounty: private report confirmed", maintainers), "private-first confirmation missing")
        advisory = {"url": public["html_url"], "published_at": public["published_at"], "private_report_confirmed": True}
    else:
        require(payload["advisory"] is None, "nonsecurity claim cannot name an advisory")
    if rating == "posted":
        offers = [c for c in comments if c["user"]["id"] in maintainers
                  and re.fullmatch(r"/bounty offer [1-9][0-9]*", c.get("body", "").strip())
                  and c["created_at"] == c["updated_at"] and c["created_at"] < claim["created_at"]]
        require(len(offers) == 1, "posted task requires one unedited prior maintainer offer")
        amount = int(offers[0]["body"].strip().split()[-1]) * ROOT
        require(amount <= 12500 * ROOT, "posted amount exceeds cap")
    else:
        amount = RATES[rating] * ROOT
    key = next_id(data, program)
    duplicate_of = None
    if duplicate:
        links = [c["body"].strip().split()[-1] for c in comments if c["user"]["id"] in maintainers
                 and re.fullmatch(r"/bounty duplicate https://github.com/iceroot-network/[^\s]+", c.get("body", "").strip())]
        require(len(links) == 1, "duplicate needs a maintainer reference")
        duplicate_of = links[0]
    when = max(claim["updated_at"], advisory["published_at"] if advisory else claim["updated_at"])
    record = {"schema_version": 1, "example": False, "id": key, "recorded_at": when,
              "entry": key if amount and not duplicate else None, "source": source, "github_user_id": uid,
              "kind": kind, "rating": rating, "amount": str(amount),
              "status": "duplicate" if duplicate else "rejected" if rating == "none" else "accepted", "claim_url": claim["html_url"],
              "rating_evidence": source, "related_party": payload["related_party"],
              "relationship": payload["relationship"], "duplicate_of": duplicate_of, "advisory": advisory}
    data["bounties"][key] = record
    if record["entry"]:
        entry = {"schema_version": 1, "example": False, "id": key, "program": program,
                 "title": f"Accepted {kind} item {repo}#{issue['number']}", "github_user_id": uid,
                 "amount": str(amount), "earned_at": when, "budget_period": budget_period(config, instant(when)),
                 "status": "proposed", "related_party": payload["related_party"], "relationship": payload["relationship"],
                 "evidence": [source] + ([advisory["url"]] if advisory else []), "binding": None,
                 "payment": None, "fingerprint": None, "memo": None, "approval": None, "receipt": None}
        data["entries"][key] = entry
        try:
            validate_data(data, config)
        except Invalid as error:
            if "cap exceeded" not in str(error):
                raise
            entry["status"], entry["budget_period"] = "queued", None
            validate_data(data, config)


def collect_links(comments, data):
    for comment in comments:
        payload = command(comment, "/bounty link")
        if payload is None:
            continue
        require(set(payload) == {"testnet_address", "signed_at", "message", "public_key", "signature"}, "unknown or missing link fields")
        uid = comment["user"]["id"]
        require(comment["created_at"] == comment["updated_at"], "edited link post requires a new post")
        if any(b["post_url"] == comment["html_url"] for b in data["bindings"].values()):
            continue
        previous = sorted([b for b in data["bindings"].values() if b["github_user_id"] == uid], key=lambda b: b["posted_at"])
        number = max((int(b["id"].split("-")[-1]) for b in previous), default=0) + 1
        key = f"LINK-{uid}-{number:04d}"
        data["bindings"][key] = {"schema_version": 1, "example": False, "id": key, "github_user_id": uid,
            "previous": previous[-1]["id"] if previous else None, "posted_at": comment["created_at"],
            "effective_at": (instant(comment["created_at"]) + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "post_url": comment["html_url"], "post_author_id": uid, **payload, "status": "pending",
            "verification": None, "mainnet": None, "revoked_at": None}


def scan(api, data, config, schemas, notifications=None):
    notes = []
    for repository in api.pages("/orgs/iceroot-network/repos", type="public"):
        if repository.get("private") is not False or repository.get("archived") or repository.get("fork"):
            continue
        repo = repository["full_name"]
        if repo == "iceroot-network/solar-core-ref":
            continue
        require(re.fullmatch(r"iceroot-network/[A-Za-z0-9_.-]+", repo), "unexpected repository")
        for issue in api.pages(f"/repos/{repo}/issues", state="all", sort="created", direction="asc"):
            if (notifications is not None and "pull_request" in issue and issue.get("state") == "open"
                    and issue.get("author_association") == "FIRST_TIME_CONTRIBUTOR"):
                notifications.append({"source": issue["html_url"], "marker": "welcome-v1",
                    "body": "Contribution rewards follow https://github.com/iceroot-network/programs. Read the claim and signed account-link steps before requesting a reward.", "label": None})
            if not any(label["name"].startswith("bounty:") for label in issue["labels"]):
                merged = (issue.get("pull_request") or {}).get("merged_at")
                if merged and issue["user"]["id"] not in config["team_ids"]:
                    notes.append(f"{issue['html_url']}: review whether a bounty label is needed")
                continue
            comments = list(api.pages(f"/repos/{repo}/issues/{issue['number']}/comments"))
            events = list(api.pages(f"/repos/{repo}/issues/{issue['number']}/events"))
            candidate = copy.deepcopy(data)
            try:
                collect_links(comments, candidate)
                propose_item(api, repo, issue, comments, events, candidate, config)
                for folder in ("entries", "bounties", "bindings"):
                    for value in candidate[folder].values():
                        check(value, schemas[folder])
                validate_data(candidate, config)
            except (Invalid, KeyError, TypeError, ValueError) as error:
                notes.append(f"{issue['html_url']}: {error}")
                continue
            data.clear()
            data.update(candidate)
    return notes


def record_notifications(data):
    result = []
    for bounty in data["bounties"].values():
        entry = data["entries"].get(bounty["entry"])
        if not entry or not entry["approval"] or entry["status"] in {"cancelled", "queued", "proposed"}:
            continue
        settled = entry["status"] in {"paid", "credited"}
        state = entry["status"]
        body = (f"Bounty {bounty['rating']}: {int(entry['amount']) // ROOT:,} ROOT. "
                f"Record: https://github.com/iceroot-network/programs/blob/prod/bounties/{entry['id']}.json. "
                f"Recorded status: {state}." + (" Bounty paid." if settled else " Payment requires the reviewed binding and payout process."))
        result.append({"source": bounty["source"], "marker": f"{entry['id']}-{state}", "body": body,
                       "label": "bounty: paid" if settled else "bounty: awaiting binding" if entry["payment"] is None else None})
        for binding in data["bindings"].values():
            if binding["github_user_id"] == entry["github_user_id"] and binding["status"] == "pending":
                result.append({"source": bounty["source"], "marker": binding["id"], "label": None,
                    "body": f"A new account link is pending review: {binding['post_url']}. Its seven-day wait ends at {binding['effective_at']}. Review an unexpected change before any payment."})
    return result


def notify_sources(api, notifications):
    if not api.writable:
        return 0
    sent = 0
    for notification in notifications:
        match = re.fullmatch(r"https://github.com/(iceroot-network/[A-Za-z0-9_.-]+)/(?:issues|pull)/([1-9][0-9]*)", notification["source"])
        require(match is not None, "notification source is not a public organization issue")
        repo, number = match.groups()
        require(api.request(f"/repos/{repo}").get("private") is False, "source repository is no longer public")
        prefix = f"/repos/{repo}/issues/{number}"
        marker = f"<!-- iceroot-programs:{notification['marker']} -->"
        comments = list(api.pages(prefix + "/comments"))
        # Matching the marker makes reruns idempotent. A copied marker can suppress a
        # courtesy notification, but cannot authorize a reward or payment.
        if not any(marker in c.get("body", "") for c in comments):
            api.request(prefix + "/comments", "POST", {"body": marker + "\n" + notification["body"]})
            sent += 1
        if notification["label"]:
            issue = api.request(prefix)
            if notification["label"] not in {label["name"] for label in issue["labels"]}:
                api.request(prefix + "/labels", "POST", {"labels": [notification["label"]]})
    return sent


def prepare_statement(data, config, month, prepared_at):
    require(re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month), "invalid statement month")
    cutoff = datetime.strptime(month, "%Y-%m").replace(tzinfo=timezone.utc)
    cutoff = (cutoff.replace(day=28) + timedelta(days=4)).replace(day=1)
    require(instant(prepared_at) >= cutoff, "statement month has not ended")
    key = "MONTH-" + month
    if key in data["statements"]:
        return
    existing = {tx["entry"] for s in data["statements"].values() for tx in s["transactions"]}
    genesis = {c["entry"] for g in data["genesis"].values() for c in g["credits"]}
    transactions, earned = [], []
    for entry in sorted(data["entries"].values(), key=lambda e: (e["earned_at"], e["id"])):
        if not entry["approval"] or instant(entry["approval"]["at"]) >= cutoff:
            continue
        if entry["earned_at"].startswith(month):
            earned.append(entry["id"])
        if (not config["mainnet_at"] or entry["status"] != "approved" or entry["id"] in existing | genesis):
            continue
        if entry["binding"]:
            try:
                binding_at(data["bindings"][entry["binding"]], entry["github_user_id"], prepared_at, data["bindings"], config)
            except Invalid:
                continue
        if entry["budget_period"] != budget_period(config, instant(prepared_at)):
            continue
        transactions.append({"entry": entry["id"], "pool": data["programs"][entry["program"]]["pool"],
                             **{k: entry[k] for k in ("payment", "fingerprint", "memo", "amount", "related_party")}})
    data["statements"][key] = {"schema_version": 1, "example": False, "id": key, "month": month,
        "prepared_at": prepared_at, "status": "proposed", "approval": None, "transactions": transactions,
        "earned_entries": earned, "credit_only": [b["id"] for b in data["bounties"].values()
            if b["status"] == "accepted" and int(b["amount"]) == 0 and b["recorded_at"].startswith(month)]}


def publish(api, config, updates):
    if not api.writable or not updates:
        return False
    name, email = os.getenv("PROGRAMS_COMMIT_NAME"), os.getenv("PROGRAMS_COMMIT_EMAIL")
    require(name and email, "write mode needs PROGRAMS_COMMIT_NAME and PROGRAMS_COMMIT_EMAIL")
    prefix = f"/repos/{config['repository']}"
    repository = api.request(prefix)
    base = repository["default_branch"]
    head = api.request(f"{prefix}/git/ref/heads/{base}")["object"]["sha"]
    require(head == os.environ.get("GITHUB_SHA"), "default branch advanced; rerun before proposing updates")
    branch = "bounty-record-updates"
    pulls = list(api.pages(f"{prefix}/pulls", state="open", head=f"iceroot-network:{branch}"))
    if pulls:
        print("An update pull request is open; retaining this run as an artifact for review.")
        return False
    commit = api.request(f"{prefix}/git/commits/{head}")
    tree = api.request(f"{prefix}/git/trees", "POST", {"base_tree": commit["tree"]["sha"], "tree": [
        {"path": path, "mode": "100644", "type": "blob", "content": content} for path, content in sorted(updates.items())]})
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    identity = {"name": name, "email": email, "date": timestamp}
    created = api.request(f"{prefix}/git/commits", "POST", {"message": "Update bounty records and statements",
        "tree": tree["sha"], "parents": [head], "author": identity, "committer": identity})
    refs = api.request(f"{prefix}/git/matching-refs/heads/{branch}")
    if any(ref["ref"] == f"refs/heads/{branch}" for ref in refs):
        api.request(f"{prefix}/git/refs/heads/{branch}", "PATCH", {"sha": created["sha"], "force": True})
    else:
        api.request(f"{prefix}/git/refs", "POST", {"ref": f"refs/heads/{branch}", "sha": created["sha"]})
    api.request(f"{prefix}/pulls", "POST", {"title": "Update bounty records and statements", "head": branch, "base": base,
        "body": "Review claims, ratings, eligibility, bindings and reserved budgets. New entries are proposals. Statements contain unsigned payment instructions. This workflow does not pay."})
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("bot-output"))
    parser.add_argument("--month", help="closed UTC month, YYYY-MM")
    parser.add_argument("--write", action="store_true", help="open a pull request when a write token is present")
    parser.add_argument("--notify", action="store_true", help="also synchronize public source comments and display labels")
    parser.add_argument("--offline", action="store_true", help="prepare a statement from local records only")
    args = parser.parse_args()
    try:
        data, config = validate(args.root)
        before = copy.deepcopy(data)
        token = os.getenv("PROGRAMS_BOT_TOKEN", "")
        api = GitHub(token or os.getenv("GITHUB_TOKEN", ""), writable=bool(token and args.write and not args.offline))
        schemas = {folder: load(args.root / "schemas" / f"{kind}.schema.json")
                   for folder, kind in (("entries", "entry"), ("bounties", "bounty"), ("bindings", "binding"))}
        notifications = []
        notes = [] if args.offline else scan(api, data, config, schemas, notifications)
        notifications.extend(record_notifications(before))
        if args.month:
            prepare_statement(data, config, args.month, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        validate_data(data, config)
        updates = {}
        for folder, records in data.items():
            for key, value in records.items():
                if before[folder].get(key) != value:
                    updates[f"{folder}/{key}.json"] = json.dumps(value, indent=2) + "\n"
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "review.json").write_text(json.dumps({"read_only": not api.writable, "notes": notes,
                                                          "updates": sorted(updates), "notifications": notifications}, indent=2) + "\n")
        for path, content in updates.items():
            dest = args.output / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        opened = publish(api, config, updates)
        if args.notify:
            notify_sources(api, notifications)
        print(f"Prepared {len(updates)} record updates and {len(notes)} review notes. Pull request opened: {opened}.")
        return 0
    except (Invalid, OSError, ValueError, KeyError) as error:
        print(f"Bot stopped: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
