# Program rewards at genesis

One manifest file per reviewed set of genesis credits. [Schema](../schemas/genesis.schema.json). [Worked example](examples/GENESIS-EXAMPLE.json).

Each credit references a bound pre-mainnet entry, its pool, recipients, amount and payment fingerprint. Genesis has no payout transaction, so a credit has no transaction memo. The manifest SHA-256 is computed as specified in [FORMAT.md](../FORMAT.md). Publish the frozen hash with the genesis materials. Deduct these credits from their program pools' genesis balances.

These manifests describe program rewards, not the full genesis supply allocation. The participation split, cutoff and binding deadline are not decided here. The genesis builder must account separately for participation and the rest of the distribution. An unpublished security advisory cannot have an entry or credit; it waits for a later monthly run. No rule is assumed for bounty rewards still unbound at the deadline.

Generate a draft with `scripts/prepare.py --genesis <id> --cutoff <UTC time> --output <new file>`. Review all bindings and allocations before freezing. A frozen manifest and credited entries are immutable in history checks. Marking a file frozen does not deploy or construct a chain.
