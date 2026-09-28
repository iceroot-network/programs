# Entries

One `<CODE>-<number>.json` file represents one payment entitlement. [Schema](../schemas/entry.schema.json). [Monthly payment example](examples/DEV-0001.json). [Genesis credit example](examples/DEV-0002.json).

Record the program, exact amount, evidence, earning time, budget period and related-party declaration. An accepted bounty references its permanent numeric GitHub account. The corresponding bounty file uses this same id and is not counted twice. Keep cancelled entries.

Before binding, payment, fingerprint, memo and binding id are null. After verification, set the pool address, ordered recipient amounts, binding reference, fingerprint and memo together. [FORMAT.md](../FORMAT.md) defines their bytes and states. Record the merged listing approval before setting `earned`, `bound` or `approved`. A transaction receipt belongs only on a paid entry. Never use example addresses for a live entry.
