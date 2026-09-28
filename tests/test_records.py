import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from schema import Invalid, check, instant, load
from validate import (ROOT, address, binding_at, budget_period, fingerprint, history,
                      manifest_hash, memo, validate, validate_data)
from prepare import export_statement, genesis_manifest

REPO = Path(__file__).resolve().parents[1]


class Records(unittest.TestCase):
    def setUp(self):
        self.data, self.config = validate(REPO, True)
        self.entry = self.data["entries"]["DEV-0001"]
        self.binding = self.data["bindings"]["LINK-9999999999-0001"]

    def invalid(self, pattern):
        with self.assertRaisesRegex(Invalid, pattern):
            validate_data(self.data, self.config, True)

    def test_live_and_example_datasets(self):
        data, config = validate(REPO)
        self.assertEqual(len(data["programs"]), 3)
        self.assertEqual(len(data["entries"]), 0)
        self.assertTrue(all(p["address"] is None for p in config["pools"]))

    def test_fixed_fingerprint_vector(self):
        preimage = b"iceroot-entry:v1|DEV-0001|example-developer-pool|example-mainnet-account=250000000000000000000|1"
        self.assertEqual(fingerprint(self.entry), hashlib.sha256(preimage).hexdigest())
        old = self.entry["fingerprint"]
        self.entry["title"] = "Corrected public title"
        self.assertEqual(fingerprint(self.entry), old)

    def test_noninteger_amounts(self):
        schema = load(REPO / "schemas/entry.schema.json")
        for value in [1, 1.0, True, "-1", "1.1", "1e18", "01", "+1", "0", "1\n"]:
            with self.subTest(value=value), self.assertRaises(Invalid):
                entry = copy.deepcopy(self.entry)
                entry["amount"] = value
                check(entry, schema)

    def test_unknown_fields(self):
        self.entry["extra"] = 1
        with self.assertRaisesRegex(Invalid, "unknown fields"):
            check(self.entry, load(REPO / "schemas/entry.schema.json"))

    def test_schema_fails_closed(self):
        with self.assertRaisesRegex(Invalid, "unsupported schema keywords"):
            check("anything", {"unknownKeyword": True})

    def test_duplicate_json_key(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "record.json"
            path.write_text('{"id":1,"id":2}')
            with self.assertRaisesRegex(Invalid, "duplicate JSON key"):
                load(path)

    def test_program_budget(self):
        self.data["programs"]["DEV"]["budget"] = str(499 * ROOT)
        self.invalid("program budget exceeded")

    def test_program_yearly_cap(self):
        self.data["programs"]["DEV"]["yearly_cap"] = str(249 * ROOT)
        self.invalid("yearly cap exceeded")

    def test_pool_total(self):
        self.config["pools"][1]["allocation"] = str(499 * ROOT)
        self.invalid("pool allocation exceeded")

    def test_shared_pool_cap_cannot_be_split_between_programs(self):
        data, config = validate(REPO)
        config["pools"][0]["bounty_yearly_cap"] = str(600 * ROOT)
        for code in ("SEC", "BUG"):
            data["programs"][code]["bounty"] = True
            rating, amount = ("low", 500) if code == "SEC" else ("bug", 250)
            key = code + "-0001"
            entry = copy.deepcopy(self.entry)
            entry.update(id=key, program=code, amount=str(amount * ROOT), status="proposed", payment=None,
                         fingerprint=None, memo=None, binding=None, approval=None, budget_period="pre-mainnet")
            data["entries"][key] = entry
            bounty = copy.deepcopy(self.data["bounties"]["DEV-0001"])
            bounty.update(id=key, entry=key, source=f"https://example.com/{code}", rating=rating,
                          amount=entry["amount"], kind="security" if code == "SEC" else "bug")
            data["bounties"][key] = bounty
        with self.assertRaisesRegex(Invalid, "shared yearly bounty cap exceeded"):
            validate_data(data, config)

    def test_related_party_disclosure(self):
        self.entry["relationship"] = None
        self.invalid("related-party mark")

    def test_memo_fingerprint_mismatch(self):
        self.entry["fingerprint"] = "0" * 64
        self.invalid("fingerprint mismatch")

    def test_memo_exact_spaces(self):
        self.entry["memo"] += " "
        self.invalid("memo mismatch")

    def test_recipient_total(self):
        self.entry["payment"]["recipients"][0]["amount"] = "1"
        self.invalid("recipient total mismatch")

    def test_wrong_pool(self):
        self.entry["payment"]["pool_address"] = "example-security-pool"
        self.invalid("wrong pool account")

    def test_early_effective_time(self):
        self.binding["effective_at"] = "2030-01-07T23:59:59Z"
        self.invalid("exactly seven days")

    def test_early_binding_transaction(self):
        self.binding["mainnet"]["at"] = "2030-01-07T23:59:59Z"
        self.invalid("transaction precedes seven-day wait")

    def test_binding_boundary(self):
        binding_at(self.binding, 9999999999, "2030-01-08T00:00:00Z", self.data["bindings"], self.config)
        with self.assertRaisesRegex(Invalid, "seven-day wait ended"):
            binding_at(self.binding, 9999999999, "2030-01-07T23:59:59Z", self.data["bindings"], self.config)

    def test_changed_link_requires_full_wait(self):
        changed = copy.deepcopy(self.binding)
        changed.update(id="LINK-9999999999-0002", previous=self.binding["id"], posted_at="2030-03-30T00:00:00Z",
                       signed_at="2030-03-30T00:00:00Z", effective_at="2030-04-06T00:00:00Z",
                       mainnet=None, verification=None, status="pending")
        changed["message"] = changed["message"].replace("2030-01-01", "2030-03-30")
        self.data["bindings"][changed["id"]] = changed
        self.invalid("newer account link")

    def test_wrong_post_author(self):
        self.binding["post_author_id"] = 1234568
        self.invalid("different author")

    def test_backdated_signed_time_cannot_reduce_wait(self):
        self.binding["signed_at"] = "2029-12-01T00:00:00Z"
        self.binding["message"] = self.binding["message"].replace("2030-01-01", "2029-12-01")
        validate_data(self.data, self.config, True)
        self.binding["effective_at"] = "2029-12-08T00:00:00Z"
        self.invalid("exactly seven days")

    def test_wrong_binding_memo(self):
        self.binding["mainnet"]["memo"] = "iceroot:bind:v1 example-another-account"
        self.invalid("wrong binding memo")

    def test_unverified_binding_cannot_pay(self):
        self.binding["status"] = "pending"
        self.invalid("binding unverified")

    def test_statement_cannot_repeat_payout(self):
        second = copy.deepcopy(self.data["statements"]["MONTH-2030-03"])
        second.update(id="MONTH-2030-04", month="2030-04", prepared_at="2030-05-01T00:00:00Z")
        self.data["statements"][second["id"]] = second
        self.invalid("repeated across payment statements")

    def test_prelaunch_no_transfer(self):
        self.config["mainnet_at"] = None
        self.invalid("cannot prepare transfers before mainnet")

    def test_statement_wrong_payment(self):
        self.data["statements"]["MONTH-2030-03"]["transactions"][0]["amount"] = "1"
        self.invalid("statement payment mismatch")

    def test_wrong_year_cannot_bypass_cap(self):
        self.entry["budget_period"] = "year-2"
        self.invalid("wrong yearly budget period")

    def test_payment_cannot_predate_statement_approval(self):
        statement = self.data["statements"]["MONTH-2030-03"]
        statement.update(status="approved", approval={"pull_request": "https://example.com/approval", "at": "2030-04-02T00:00:00Z"})
        self.entry.update(status="paid", receipt={"transaction_id": "2" * 64, "height": 1,
                          "confirmed_at": "2030-04-01T00:00:00Z", "memo": self.entry["memo"]})
        self.data["bounties"]["DEV-0001"]["status"] = "paid"
        self.invalid("receipt predates statement approval")

    def test_credited_reward_needs_frozen_manifest(self):
        self.data["entries"]["DEV-0002"]["status"] = "credited"
        self.data["bounties"]["DEV-0002"]["status"] = "credited"
        self.invalid("missing from frozen genesis manifest")

    def test_revocation_preserves_history_but_stops_new_payment(self):
        self.binding.update(status="revoked", revoked_at="2030-04-03T00:00:00Z")
        validate_data(self.data, self.config, True)
        with self.assertRaisesRegex(Invalid, "not verified at payment time"):
            binding_at(self.binding, 9999999999, "2030-04-03T00:00:00Z", self.data["bindings"], self.config)

    def test_genesis_hash(self):
        self.data["genesis"]["GENESIS-EXAMPLE"]["sha256"] = "0" * 64
        self.invalid("manifest hash mismatch")

    def test_genesis_and_monthly_no_double_payment(self):
        manifest = self.data["genesis"]["GENESIS-EXAMPLE"]
        manifest["credits"][0]["entry"] = "DEV-0001"
        manifest["sha256"] = manifest_hash(manifest)
        self.invalid("duplicate genesis or monthly allocation")

    def test_team_excluded(self):
        self.config["team_ids"] = [9999999999]
        self.invalid("team members cannot earn")

    def test_bounty_rates_enforced(self):
        self.data["bounties"]["DEV-0001"]["rating"] = "tier-2"
        self.invalid("amount differs from provisional table")

    def test_proposed_statement_cannot_export(self):
        with self.assertRaisesRegex(Invalid, "must be approved"):
            export_statement(self.data, self.config, "MONTH-2030-03", "2030-04-02T00:00:00Z")

    def test_approved_export_is_unsigned(self):
        statement = self.data["statements"]["MONTH-2030-03"]
        statement.update(status="approved", approval={"pull_request": "https://example.com/approval", "at": "2030-04-01T00:00:00Z"})
        exported = export_statement(self.data, self.config, statement["id"], "2030-04-02T00:00:00Z")
        self.assertEqual(exported["transactions"][0]["memo"], memo(self.entry))
        self.assertNotIn("signature", json.dumps(exported))

    def test_export_stops_at_year_boundary(self):
        statement = self.data["statements"]["MONTH-2030-03"]
        statement.update(status="approved", approval={"pull_request": "https://example.com/approval", "at": "2030-04-01T00:00:00Z"})
        with self.assertRaisesRegex(Invalid, "budget period changed"):
            export_statement(self.data, self.config, statement["id"], "2031-03-01T00:00:00Z")

    def test_period_anniversaries(self):
        self.assertEqual(budget_period(self.config, instant("2030-02-28T23:59:59Z")), "pre-mainnet")
        self.assertEqual(budget_period(self.config, instant("2030-03-01T00:00:00Z")), "year-1")
        self.assertEqual(budget_period(self.config, instant("2031-03-01T00:00:00Z")), "year-2")

    def test_fake_address_rejected_live(self):
        with self.assertRaises(Invalid):
            address("example-mainnet-account", "ice")

    def test_history_retains_ids(self):
        old = self.entry
        with patch("validate.subprocess.check_output", side_effect=["entries/DEV-0001.json\n", json.dumps(old)]):
            del self.data["entries"]["DEV-0001"]
            with self.assertRaisesRegex(Invalid, "historical id removed"):
                history(REPO, "a" * 40, self.data)

    def test_history_settled_records_immutable(self):
        old = copy.deepcopy(self.entry)
        old["status"] = "paid"
        with patch("validate.subprocess.check_output", side_effect=["entries/DEV-0001.json\n", json.dumps(old)]):
            with self.assertRaisesRegex(Invalid, "settled record changed"):
                history(REPO, "a" * 40, self.data)

    def test_history_link_change_needs_new_revision(self):
        old = copy.deepcopy(self.binding)
        self.binding["testnet_address"] = "example-changed-account"
        with patch("validate.subprocess.check_output", side_effect=[f"bindings/{old['id']}.json\n", json.dumps(old)]):
            with self.assertRaisesRegex(Invalid, "new record and seven-day wait"):
                history(REPO, "a" * 40, self.data)


if __name__ == "__main__":
    unittest.main()
