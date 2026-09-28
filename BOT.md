# Bounty bot operations

The Python bot reads public GitHub repositories, labels, label-event actors and claim comments. It proposes entries, bounty records, pending bindings and monthly statements. It never rates work, signs transactions, submits transfers, reads wallet keys or consumes draft advisories. Untrusted comment text is parsed as data, never evaluated as code. Only the default branch can run the scheduled write job.

## Setup

1. Merge this repository's initial contents and enable Actions. Configure reviewed pull requests and the `validate` check for the default branch. Put numeric maintainer GitHub ids and known team ids in `config.json`, through review. Empty maintainer ids intentionally mean no trusted ratings.
2. Install the labels below on the public repositories. The collector discovers public, non-archived, non-fork repositories in `iceroot-network`; `solar-core-ref` is excluded. No repository count is assumed.
3. For pull request creation, set the secret **`PROGRAMS_BOT_TOKEN`** to an organization-approved fine-grained token. Grant contents write and pull requests write on `programs`, and issues and pull requests write on source repositories for courtesy comments and display labels. Public advisory reads must also be available. The scheduled job uses `--notify` to greet first-time contributors and synchronize reviewed reward and binding notices. Omit `--notify` and grant only source read permissions to disable those source writes. The bot never changes portal pages.
4. A GitHub App installation token with equivalent permissions can replace the token. Mint a short-lived token in a trusted workflow step and pass it as `PROGRAMS_BOT_TOKEN`. The supplied workflow does not store or mint an App private key. Set repository variables `PROGRAMS_COMMIT_NAME` and `PROGRAMS_COMMIT_EMAIL` to the project's approved commit identity. Dates use UTC; commit messages have no trailers.
5. Publish real pool addresses, mainnet time and binding deadline in `config.json` when decided. Do not substitute example values. Check actual balances and fees outside this offline record before signing.

Without `PROGRAMS_BOT_TOKEN`, scheduled and manual runs use the read-only `GITHUB_TOKEN` for public reads and save downloadable artifacts. No remote write occurs, even with `--write`. Outside Actions, authenticated public reads can use `GITHUB_TOKEN`, or run without a token subject to GitHub's lower rate limit. API errors stop the run instead of treating a partial scan as complete. No live GitHub run is needed for tests.

The workflow runs at minute 17 hourly and at 00:37 UTC on the first of the month. Scheduled workflows use the default branch and may be delayed or disabled after inactivity; use a manual run when needed. See [GitHub's scheduling documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule). Manual runs accept an optional closed UTC month. Overlapping runs are serialized. An existing bot pull request is preserved for review; new changes remain in the artifact until it is resolved. The bot verifies that its checkout still matches the default branch before publishing.

## Labels

Maintainers apply exactly one rating label:

| Kind | Labels |
| --- | --- |
| Security | `bounty: critical`, `bounty: high`, `bounty: medium`, `bounty: low` |
| Ordinary bug | `bounty: confirmed bug` |
| Contribution | `bounty: tier 1`, `bounty: tier 2`, `bounty: tier 3`, `bounty: posted`, `bounty: credit`, `bounty: none` |

Also create `bounty: approved`, `bounty: duplicate`, `bounty: private report confirmed`, `bounty: awaiting binding` and `bounty: paid`. The last two are display labels, added by notifications from reviewed records. The collector checks the latest application or removal event for each trusted rating and acceptance label against the configured numeric maintainer ids. GitHub's [issue event API](https://docs.github.com/en/rest/issues/events) supplies that history. A label alone, applied by an unlisted account, cannot accept a reward.

For security, create the public tracking issue only **after** advisory publication. Match its severity label to the published advisory and add `bounty: private report confirmed` after checking that the original report was private. Private intake and the mapping from report to public claimant are reviewed by maintainers. The bot fetches only the explicitly named public advisory, from the tracking issue's repository or, failing that, from the organisation's `.github` repository, where private reports can also be filed. It checks the advisory's published state and severity and never copies its body. It cannot discover unpublished security rewards. [Repository advisory API](https://docs.github.com/en/rest/security-advisories/repository-advisories).

## Claim comments

The contributor posts exactly this command followed by one JSON object, without a code fence:

```text
/bounty claim
{"related_party":false,"relationship":null,"team_member":false,"advisory":null}
```

Related claimants set `related_party` to `true` and describe the relationship. A published security claim puts its `GHSA-...` id in `advisory`. Do not paste an address into a claim.

A listed maintainer confirms the exact account and comment:

```text
/bounty approve <numeric GitHub user id> <claim comment id>
```

The approval must be created after the claim's last edit. There must be exactly one approved current claim. For ordinary bugs and contributions, the claim author must also be the issue or pull request author. For public security tracking, the maintainer explicitly confirms the original private reporter. Add the trusted acceptance and rating labels. Contributions must be merged pull requests, except posted tasks and credit-only records; ordinary bugs and posted issue tasks must be closed. Acceptance and reproduction evidence still need human review.

For a posted task, a listed maintainer writes an unedited `/bounty offer <whole ROOT amount>` comment before the claim. Reviewers must also establish that the offer preceded work, since a claim timestamp alone cannot prove when work started. The amount cannot exceed 12,500 ROOT. To record a duplicate, use `bounty: duplicate` and one maintainer comment `/bounty duplicate <public original URL>`. The duplicate reserves an id but earns no entitlement. Related symptoms and split pull requests must be linked during review; the bot cannot infer a shared root cause.

For links, post `/bounty link` followed by the JSON fields in [bindings/README.md](bindings/README.md) on a bounty-labelled item. Each post must be new and unedited. The bot stores it as pending, verifies the numeric post author against the link data, and calculates the seven-day effective time. Existing source items are not awarded twice. Existing accepted records are never silently repriced when labels change.

## Review and payment

Bot output under `bot-output/` includes proposed JSON files and `review.json` with items that need attention. It flags merged pull requests from outside the team that have no bounty label, and rejected or incomplete claims. New entries start as `proposed`, or `queued` if the shared yearly cap is exhausted. The bot does not merge its own pull request or promote a proposal to approval. A reviewer records the merged listing URL and time, then sets `earned`, `bound` or `approved` as appropriate. Reviewed bindings are attached by updating the entry's payment details, fingerprint and memo together.

For the previous month, the bot includes approved unpaid entries and eligible carryovers, oldest first. Before mainnet, statements record earnings and credit-only items without transfer instructions. After mainnet, only entries assigned to the current budget period, with a usable binding, enter transactions. Items already in a statement or genesis manifest are excluded. Promote queued items through review, oldest first, before newer work in the next period. An existing statement is preserved instead of being overwritten.

```sh
python3 scripts/bot.py --offline --month 2026-08 --output bot-output
python3 scripts/bot.py --month 2026-08 --output bot-output
python3 scripts/bot.py --write --month 2026-08 --output bot-output
```

After the monthly statement merges, record its approval evidence and set its status to `approved`. Export it for the signers:

```sh
python3 scripts/prepare.py --statement MONTH-2030-03 --output payment-output/transfers.json
```

That command is illustrative and refuses absent or unapproved records. The output is a set of **unsigned transfer instructions**, one per entry with its exact memo. It is not serialized chain transaction bytes and has no invented nonce, fee or network hash. Wallet import support for this format still needs integration. Signers must construct or import the transfers with the current wallet, check every field and use two of the pool's three keys. There is no additional payment waiting period.

After finality, reviewers add the actual receipt to each entry, set entry and bounty status to `paid`, and update the statement. The indexer endpoint and finalized transaction response contract are not published here, so the bot does not claim to verify or mark payments automatically. With `--notify`, it reflects the merged receipt records in source comments and the `bounty: paid` label. Notification markers make reruns idempotent. The validators portal still needs its own `bounty paid` links integration.

To prepare a draft program-reward genesis manifest from reviewed bound entries:

```sh
python3 scripts/prepare.py --genesis GENESIS-MAINNET --cutoff <published-UTC-cutoff> --output payment-output/genesis.json
```

The cutoff is not decided here. Frozen manifests require published mainnet and binding dates. This manifest is input for review and the genesis builder, not a command that launches a chain.

## Binding verification boundary

The available SDK address and message APIs do not yet supply the required public-testnet post-quantum binding verifier. The collector therefore never automatically marks a signature valid. A reviewer must verify the exact signed message, public key and derived address with a conforming SDK, check the GitHub author, then record verification evidence. Mainnet binding evidence must show the finalized transaction, its linked sender, exact memo, order and timestamp. Record a replacement binding transaction only after reviewing the latest valid transaction before the deadline. The offline validator enforces the recorded seven-day rule and payment consistency; it does not substitute for these cryptographic checks.

Automated signature verification, chain receipt ingestion, wallet import and portal updates remain integration work. Pending bindings cannot produce payments. This keeps collection and review usable while those interfaces are completed.
