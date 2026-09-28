# Record and payment format

Version 1 uses UTF-8 JSON, one file per record. Each filename equals its `id` with a `.json` suffix. Unknown fields and duplicate JSON keys are rejected. All amounts are unsigned decimal **strings of integer base units**. `1 ROOT = 1000000000000000000` base units. No floats, signs, exponent notation, leading zeroes or decimal points are accepted. A payable amount is positive. Timestamps use UTC seconds, `YYYY-MM-DDTHH:MM:SSZ`.

## Ids and accounting

Program codes contain 3 to 6 capital letters. Entry ids are `<CODE>-<number>` with at least four digits, for example `DEV-0001`. Retain cancelled entries and rejected bounty records so ids cannot be reused. A bounty record for an accepted reward references the entry with **the same id**. It is workflow metadata for that entitlement, not another allocation. Unaccepted and credit-only bounty records reserve an id without creating an entry.

All entries except cancelled entries reserve total program budget and pool allocation. All except cancelled or queued entries reserve their assigned yearly cap. A queued entry has a null `budget_period`, retains its full amount and cannot be paid. Programs have individual caps; bounty programs also share the paying pool's bounty cap. Moving work between SEC and BUG does not evade the security pool cap.

`pre-mainnet` is the single period before genesis. `year-1` starts at mainnet genesis, followed by annual anniversaries. A February 29 anniversary falls on February 28 in a non-leap year. Queued rewards need a reviewed period assignment before payment. Statement preparation includes approved carryovers, oldest first, once their period and binding are valid. There is no automatic cap increase.

Entry states are `proposed`, `earned`, `bound`, `approved`, `paid`, `credited`, `queued` and `cancelled`. An unbound earning has no `payment`, `fingerprint`, `memo` or `binding`. A verified mainnet binding and published pool account allow payment details to be set. `bound` is ready for a genesis manifest; `approved` is ready for a monthly transfer. `paid` requires a final transaction receipt; `credited` requires a genesis manifest. Approvals reference the merged listing pull request and its merge time. They are review evidence, not cryptographic attestations.

## Fingerprint

SHA-256 hashes the UTF-8 bytes of this line, **without a trailing newline**:

```text
iceroot-entry:v1|<id>|<pool account address>|<address>=<base units>,<address>=<base units>,...|<0 or 1>
```

Recipient order is the entry's order. Addresses are canonical lowercase Bech32m mainnet addresses. The final digit is `1` for a related-party entry and `0` otherwise. A relationship description is required for a marked entry. The digest is 64 lowercase hexadecimal characters. Title, evidence, status and the relationship's wording are outside the fingerprint. Changing addresses, amounts, their order, the pool account or related-party mark changes it.

The memo is ASCII, with exactly one space between fields:

```text
iceroot:pay:v1 <entry id> <fingerprint>
```

Its UTF-8 representation must fit 255 bytes. Every transaction pays one complete entry. Up to 256 distinct recipients can share that entry. For phased work, create one entry per payment. This format does not yet encode time-locked tranche schedules; do not substitute an ordinary transfer for one. Fees are separate from recipient amounts and are checked by signers against the actual pool balance.

For the worked example [DEV-0001](entries/examples/DEV-0001.json), the preimage is:

```text
iceroot-entry:v1|DEV-0001|example-developer-pool|example-mainnet-account=250000000000000000000|1
```

Its checked fingerprint and memo are in that file. Example strings are deliberately invalid live addresses.

## Statements and genesis

A monthly statement contains separate unsigned transfer instructions. Its `payment`, `amount`, `fingerprint`, `memo` and related-party flag exactly match the referenced entry. A payment appears in only one statement or genesis manifest. Proposed statements reserve their entries against duplication, but require a merged approval before export. Existing statements are never silently regenerated.

Genesis credits have no payout transaction or payment memo. The manifest repeats the entry's recipients, amount, pool and payment fingerprint. Deduct each program pool's credited total from that pool's genesis allocation. These manifests cover program rewards only. They are not the complete chain genesis: participation, team allocations and the rest of the distribution belong in the genesis builder's full allocation list. Participation amounts and dates are not invented here.

To hash a manifest, remove its `sha256` field, sort object keys, preserve array order, serialize compact JSON with literal UTF-8 characters and no whitespace or trailing newline, and hash those bytes with SHA-256. All numeric values here are integers or decimal strings. The `sha256` field is lowercase hex. This encoding is specified by `manifest_hash` in the validator and the worked example. A frozen manifest and settled records are immutable against the base revision in CI.

The offline checks verify structure, arithmetic, recorded times and cross-references. They do not contact GitHub or the chain, prove relationship declarations, authenticate a reviewer, verify post-quantum signatures or prove finality. Those evidence checks are required during review. [BOT.md](BOT.md) describes what the public GitHub collector verifies and what still needs a reviewer.
