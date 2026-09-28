# Schemas

Each data kind uses a JSON Schema with version `2020-12`. `config.schema.json` checks pool and bot configuration. Every field is explicit; unknown fields are rejected. Schemas provide structural constraints; `scripts/validate.py` adds cross-record accounting, memo, address checksum, history and binding rules.

The offline standard-library schema checker supports the vocabulary used here: objects, arrays, primitive types, required fields, closed properties, enums, constants, local references, alternatives, patterns, lengths, integer bounds, unique items and UTC timestamps. It is not a general-purpose JSON Schema implementation. Unsupported keywords fail closed. It never fetches `$id`, `$schema` or external references. Standard JSON Schema tooling can also consume these files, but the repository validator remains necessary for accounting checks.

All examples run as one isolated dataset. `tests/example-config.json` supplies its fictional pool addresses and dates; it is never used by the live bot or payment export.
