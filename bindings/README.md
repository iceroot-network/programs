# Bindings

One `LINK-<numeric GitHub id>-<revision>.json` file records one signed link. [Schema](../schemas/binding.schema.json). [Worked example](examples/LINK-9999999999-0001.json).

Post from the GitHub account that earned the reward. Use exactly this message, with a UTC timestamp and no final newline:

```text
IceRoot GitHub link v1
GitHub user id: <numeric id>
Account: <testnet address>
Date: <YYYY-MM-DDTHH:MM:SSZ>
```

Sign the exact message using the account's message-signing API and domain, not a transaction signature. Post a new, unedited comment on a bounty-labelled item:

```text
/bounty link
{"testnet_address":"<testnet address>","signed_at":"<UTC signature time>","message":"<exact message with JSON newline escapes>","public_key":"<public key>","signature":"<message signature>"}
```

The message timestamp must match `signed_at` and must not be later than the GitHub post's recorded creation time. The seven-day wait starts from GitHub's publication time, not the signed timestamp. The bot never rewrites a signed message.

`posted_at` is the public post time; `effective_at` is exactly seven days later. New and changed links both wait seven days. A changed link gets a new id and points to `previous`; keep the old record. A pending change blocks preparation from a stale link until reviewed. Revoked links have a `revoked_at` time and cannot be used for payments at or after it. Older settled payments retain their historical binding evidence.

The bot imports links as `pending`. A reviewer must verify authorship, exact message, signature and derived testnet address and record evidence before `verified`. The example signature is fictional and demonstrates structure only. [BOT.md](../BOT.md#binding-verification-boundary) states the current verification limitation.

After the effective time, an ordinary testnet transaction from that account binds the mainnet address with `iceroot:bind:v1 <mainnet address>`. The `mainnet` field records its address, transaction id, UTC time, exact memo and evidence. Review its signature, sender and finality. The latest valid transaction before the announced deadline counts. The deadline is not published yet. Rewards without a verified binding stay unpaid; the disposition of bounty rewards unbound at the deadline is not decided yet.
