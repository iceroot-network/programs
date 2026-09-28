import copy
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from bot import GitHub, collect_links, notify_sources, prepare_statement, propose_item, publish, scan, trusted_label
from schema import Invalid, load
from validate import validate, validate_data

REPO = Path(__file__).resolve().parents[1]


class PublicAPI:
    def __init__(self, merged=True, published=True):
        self.merged = merged
        self.published = published
        self.calls = []

    def request(self, path, method="GET", body=None):
        self.calls.append((path, method))
        if "/pulls/" in path:
            return {"merged_at": "2026-08-02T00:00:00Z" if self.merged else None}
        if "/security-advisories/" in path:
            return {"state": "published" if self.published else "draft", "published_at": "2026-08-02T00:00:00Z",
                    "severity": "high", "html_url": "https://github.com/iceroot-network/example/security/advisories/GHSA-cccc-cccc-cccc"}
        raise AssertionError(path)


class Bot(unittest.TestCase):
    def setUp(self):
        self.data, self.config = validate(REPO)
        self.config["maintainer_ids"] = [42]
        self.issue = {"id": 77, "number": 1, "html_url": "https://github.com/iceroot-network/example/pull/1",
                      "user": {"id": 123}, "state": "closed", "pull_request": {},
                      "labels": [{"name": "bounty: tier 3"}, {"name": "bounty: approved"}]}
        self.events = [{"id": i, "event": "labeled", "actor": {"id": 42}, "label": label,
                        "created_at": "2026-08-02T00:00:00Z"} for i, label in enumerate(self.issue["labels"])]
        self.claim = {"id": 9, "user": {"id": 123}, "html_url": self.issue["html_url"] + "#issuecomment-9",
                      "created_at": "2026-08-01T00:00:00Z", "updated_at": "2026-08-01T00:00:00Z",
                      "body": '/bounty claim\n{"related_party":false,"relationship":null,"team_member":false,"advisory":null}'}
        self.approval = {"id": 10, "user": {"id": 42}, "created_at": "2026-08-02T00:00:00Z",
                         "updated_at": "2026-08-02T00:00:00Z", "body": "/bounty approve 123 9"}

    def propose(self, api=None):
        propose_item(api or PublicAPI(), "iceroot-network/example", self.issue,
                     [self.claim, self.approval], self.events, self.data, self.config)

    def security(self):
        self.issue.pop("pull_request")
        self.issue["labels"][0]["name"] = "bounty: high"
        self.issue["labels"].append({"name": "bounty: private report confirmed"})
        self.events.append({"id": 2, "event": "labeled", "actor": {"id": 42},
                            "label": self.issue["labels"][-1], "created_at": "2026-08-02T00:00:00Z"})
        self.claim["body"] = self.claim["body"].replace('"advisory":null', '"advisory":"GHSA-cccc-cccc-cccc"')

    def test_accepted_contribution_creates_shared_id_once(self):
        self.propose()
        validate_data(self.data, self.config)
        self.propose()
        self.assertEqual(list(self.data["entries"]), ["DEV-0001"])
        self.assertEqual(self.data["bounties"]["DEV-0001"]["entry"], "DEV-0001")
        self.assertEqual(self.data["entries"]["DEV-0001"]["status"], "proposed")

    def test_unmerged_contribution_rejected(self):
        with self.assertRaisesRegex(Invalid, "not merged"):
            self.propose(PublicAPI(merged=False))

    def test_untrusted_label_rejected(self):
        self.events[0]["actor"]["id"] = 99
        with self.assertRaisesRegex(Invalid, "trusted severity"):
            self.propose()

    def test_latest_label_actor_controls_trust(self):
        self.events += [{"id": 3, "event": "unlabeled", "actor": {"id": 42}, "label": self.issue["labels"][0], "created_at": "2026-08-03T00:00:00Z"},
                        {"id": 4, "event": "labeled", "actor": {"id": 99}, "label": self.issue["labels"][0], "created_at": "2026-08-03T00:00:01Z"}]
        self.assertFalse(trusted_label(self.issue, self.events, "bounty: tier 3", [42]))

    def test_conflicting_rating_rejected(self):
        self.issue["labels"].append({"name": "bounty: tier 1"})
        with self.assertRaisesRegex(Invalid, "conflicting"):
            self.propose()

    def test_edited_claim_invalidates_approval(self):
        self.claim["updated_at"] = "2026-08-03T00:00:00Z"
        with self.assertRaisesRegex(Invalid, "current claim"):
            self.propose()

    def test_non_author_cannot_redirect_contribution(self):
        self.claim["user"]["id"] = 456
        self.approval["body"] = "/bounty approve 456 9"
        with self.assertRaisesRegex(Invalid, "current claim"):
            self.propose()

    def test_self_declared_team_ineligible(self):
        self.claim["body"] = self.claim["body"].replace('"team_member":false', '"team_member":true')
        with self.assertRaisesRegex(Invalid, "team members"):
            self.propose()

    def test_unpublished_advisory_never_creates_record(self):
        self.security()
        with self.assertRaisesRegex(Invalid, "not published"):
            self.propose(PublicAPI(published=False))
        self.assertEqual(self.data["entries"], {})
        self.assertEqual(self.data["bounties"], {})

    def test_published_advisory_becomes_security_entry(self):
        self.security()
        self.propose()
        validate_data(self.data, self.config)
        self.assertEqual(list(self.data["entries"]), ["SEC-0001"])

    def test_advisory_in_organisation_repository_is_found(self):
        class OrgAdvisory(PublicAPI):
            def request(self, path, method="GET", body=None):
                if path.startswith("/repos/iceroot-network/example/security-advisories/"):
                    self.calls.append((path, method))
                    raise Invalid("GitHub API GET returned 404")
                return super().request(path, method, body)
        self.security()
        api = OrgAdvisory()
        self.propose(api)
        self.assertIn(("/repos/iceroot-network/.github/security-advisories/GHSA-cccc-cccc-cccc", "GET"), api.calls)
        self.assertEqual(list(self.data["entries"]), ["SEC-0001"])

    def test_undocumented_label_is_not_a_rating(self):
        self.issue["labels"][0]["name"] = "bounty: bug"
        with self.assertRaisesRegex(Invalid, "rating labels"):
            self.propose()

    def test_cap_excess_queues_full_reward(self):
        self.config["pools"][1]["bounty_yearly_cap"] = "1"
        self.propose()
        entry = self.data["entries"]["DEV-0001"]
        self.assertEqual(entry["status"], "queued")
        self.assertIsNone(entry["budget_period"])
        self.assertEqual(entry["amount"], "250000000000000000000")

    def test_no_write_token_refuses_remote_writes(self):
        api = GitHub("", writable=True)
        with patch("bot.urlopen") as network, self.assertRaisesRegex(Invalid, "read-only"):
            api.request("/repos/iceroot-network/programs/pulls", "POST", {})
        network.assert_not_called()
        self.assertFalse(publish(api, self.config, {"entries/DEV-0001.json": "{}"}))

    def test_read_token_does_not_enable_writes(self):
        api = GitHub("read-token", writable=False)
        self.assertFalse(api.writable)

    def test_notifications_are_read_only_without_token(self):
        self.assertEqual(notify_sources(GitHub(), [{"source": "unused"}]), 0)

    def test_source_notification_is_idempotent(self):
        class SourceAPI:
            writable = True

            def __init__(self):
                self.comments = []
                self.labels = []
                self.writes = []

            def pages(self, path):
                return self.comments

            def request(self, path, method="GET", body=None):
                if method == "POST":
                    self.writes.append(path)
                    if path.endswith("/comments"):
                        self.comments.append(body)
                    else:
                        self.labels.extend({"name": label} for label in body["labels"])
                    return {}
                return {"private": False, "labels": self.labels}
        api = SourceAPI()
        notification = {"source": self.issue["html_url"], "marker": "DEV-0001-paid", "body": "Recorded payment.", "label": "bounty: paid"}
        self.assertEqual(notify_sources(api, [notification]), 1)
        self.assertEqual(notify_sources(api, [notification]), 0)
        self.assertEqual(len(api.writes), 2)

    def test_notification_cannot_target_another_organization(self):
        api = GitHub("write-token", writable=True)
        with self.assertRaisesRegex(Invalid, "not a public organization issue"):
            notify_sources(api, [{"source": "https://github.com/example/repo/issues/1"}])

    def test_publish_creates_only_a_proposal_branch(self):
        class ProposalAPI:
            writable = True

            def __init__(self):
                self.writes = []

            def pages(self, path, **query):
                return []

            def request(self, path, method="GET", body=None):
                if method != "GET":
                    self.writes.append((path, method, body))
                    return {"sha": "b" * 40}
                if path.endswith("/programs"):
                    return {"default_branch": "dev"}
                if path.endswith("/git/ref/heads/dev"):
                    return {"object": {"sha": "a" * 40}}
                if "/git/commits/" in path:
                    return {"tree": {"sha": "c" * 40}}
                if "/git/matching-refs/" in path:
                    return []
                raise AssertionError(path)
        api = ProposalAPI()
        with patch.dict(os.environ, {"PROGRAMS_COMMIT_NAME": "release", "PROGRAMS_COMMIT_EMAIL": "release@example.com", "GITHUB_SHA": "a" * 40}):
            self.assertTrue(publish(api, self.config, {"entries/DEV-0001.json": "{}\n"}))
        refs = [body["ref"] for path, method, body in api.writes if path.endswith("/git/refs")]
        self.assertEqual(refs, ["refs/heads/bounty-record-updates"])
        self.assertEqual(api.writes[-1][2]["base"], "dev")

    def test_scan_flags_only_merged_outside_pull_requests(self):
        def pull(number, user, merged):
            return {"number": number, "html_url": f"https://github.com/iceroot-network/example/pull/{number}",
                    "user": {"id": user}, "state": "closed", "labels": [],
                    "pull_request": {"merged_at": "2026-08-02T00:00:00Z" if merged else None}}

        class Listing:
            def pages(self, path, **query):
                if path == "/orgs/iceroot-network/repos":
                    return iter([{"full_name": "iceroot-network/example", "private": False}])
                return iter([pull(1, 123, True), pull(2, 123, False), pull(3, 7, True)])

        self.config["team_ids"] = [7]
        notes = scan(Listing(), self.data, self.config, {})
        self.assertEqual(notes, ["https://github.com/iceroot-network/example/pull/1: review whether a bounty label is needed"])

    def test_pagination_reads_later_pages(self):
        api = GitHub()
        with patch.object(api, "request", side_effect=[[{}] * 100, [{"last": True}]]) as request:
            self.assertEqual(len(list(api.pages("/orgs/iceroot-network/repos"))), 101)
        self.assertIn("page=2", request.call_args.args[0])

    def test_pending_link_uses_server_time(self):
        fixture = load(REPO / "bindings/examples/LINK-9999999999-0001.json")
        payload = {k: fixture[k] for k in ("testnet_address", "signed_at", "message", "public_key", "signature")}
        comment = {"id": 1, "user": {"id": 9999999999}, "html_url": "https://example.com/new-link",
                   "created_at": "2030-01-02T00:00:00Z", "updated_at": "2030-01-02T00:00:00Z",
                   "body": "/bounty link\n" + json.dumps(payload)}
        collect_links([comment], self.data)
        binding = self.data["bindings"]["LINK-9999999999-0001"]
        self.assertEqual(binding["effective_at"], "2030-01-09T00:00:00Z")
        self.assertEqual(binding["status"], "pending")
        self.assertIsNone(binding["mainnet"])

    def test_monthly_before_mainnet_contains_no_transfers(self):
        self.propose()
        entry = self.data["entries"]["DEV-0001"]
        entry.update(status="earned", approval={"pull_request": "https://example.com/approval", "at": "2026-08-02T00:00:00Z"})
        prepare_statement(self.data, self.config, "2026-08", "2026-09-01T00:00:00Z")
        statement = self.data["statements"]["MONTH-2026-08"]
        self.assertEqual(statement["earned_entries"], ["DEV-0001"])
        self.assertEqual(statement["transactions"], [])
        validate_data(self.data, self.config)

    def test_monthly_excludes_reserved_and_genesis(self):
        data, config = validate(REPO, True)
        prepare_statement(data, config, "2030-04", "2030-05-01T00:00:00Z")
        self.assertEqual(data["statements"]["MONTH-2030-04"]["transactions"], [])

    def test_monthly_carryover_is_included_once(self):
        data, config = validate(REPO, True)
        data["statements"].clear()
        prepare_statement(data, config, "2030-04", "2030-05-01T00:00:00Z")
        self.assertEqual(len(data["statements"]["MONTH-2030-04"]["transactions"]), 1)
        prepare_statement(data, config, "2030-05", "2030-06-01T00:00:00Z")
        self.assertEqual(len(data["statements"]["MONTH-2030-05"]["transactions"]), 0)

    def test_open_month_rejected(self):
        with self.assertRaisesRegex(Invalid, "has not ended"):
            prepare_statement(self.data, self.config, "2030-05", "2030-05-10T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
