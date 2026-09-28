# Contributing

Propose changes by pull request. Include the program, evidence, amount in base units, eligibility and related-party disclosure. Do not include unpublished vulnerability details, secrets or personal information. Use [private reporting](https://github.com/iceroot-network/.github/security/advisories/new) for vulnerabilities.

Read [the program rules](README.md), [the data format](FORMAT.md) and the relevant folder README. Match each filename to its record id. Accepted bounty metadata and the entry share an id. Retain rejected and cancelled records. Do not change a settled record or silently replace a signed link. Add a new link revision and allow seven days.

Run these offline checks before submitting:

```sh
python3 scripts/validate.py
python3 scripts/validate.py --examples
python3 -m unittest discover -s tests -v
```

For a change to existing history, also run `python3 scripts/validate.py --base <full-base-commit-hash>`. CI runs this comparison on pull requests and pushes where a prior commit exists.

Maintainers check ratings, the first complete report, duplicates and root causes, claim authorship, team exclusion, related-party disclosures, signed links and chain evidence. They review pool and program budgets together. New bot records are proposals. Once the listing merges, record its approval URL and UTC merge time. Approving an entry does not sign a payment. Two pool keys must approve each payment separately in the wallet.

For a monthly run, review and merge the proposed statement, then record its approval and export the unsigned instructions. Check addresses, network, fees, current balance, finality and memo in the signing tool. Record the final transaction receipt afterward. Paid contributions need a `bounty paid` tag and a record link in the validators portal.

Repository settings should require reviewed pull requests and the `validate` check on the default branch. Workflow files alone do not enforce branch protection. Changes to workflows, schemas, scripts, maintainer ids, pool accounts, caps and verification evidence need particular care during review.
