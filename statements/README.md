# Monthly statements

One `MONTH-YYYY-MM.json` file per closed UTC month. [Schema](../schemas/statement.schema.json). [Worked example](examples/MONTH-2030-03.json).

`earned_entries` records listed earnings; `credit_only` records unpaid recognition. `transactions` contains separate unsigned payment instructions, each referencing one approved entry with matching pool, ordered recipients, amount, fingerprint, related-party flag and memo. Before mainnet it must be empty. There is no waiting period after listing approval, apart from the separate seven-day account-link rule.

Review and merge a proposed statement, then record its approval evidence and set `approved` before exporting with `scripts/prepare.py`. Statements reserve entries against duplicate preparation. Include unpaid carryovers once eligible; never include a genesis credit a second time. Confirm actual transfers and record receipts before setting `paid`. If a proposed transaction will no longer be paid, remove it through review before another statement can reserve it. Settled statements remain unchanged.
