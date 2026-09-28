# IceRoot programs

This repository is the public program list, bounty record, account bindings and monthly payment record for IceRoot. Entries describe what each payment is for. The team reviews entries; each pool's 2-of-3 multisig approves and signs its payments. The bot proposes changes and prepares unsigned payment instructions. It never pays.

Only these five program pool accounts follow this list:

| Pool | Genesis allocation (ROOT) |
| --- | ---: |
| Security and bug bounty pool | 30,000,000 |
| Developer ecosystem pool | 15,000,000 |
| Ecosystem campaigns pool | 10,000,000 |
| Long-term reserve pool | At least 10,000,000 |
| Community and ambassadors pool | 5,000,000 |

The team account and the Development and Ecosystem funds show balances and transfers on the explorer without program entries. The 10,000,000 ROOT testnet and launch participation pool has no pool account: earned shares are direct allocations in the mainnet genesis, and unearned or unbound shares go to the Long-term reserve. How that pool is split is not decided yet, and this repository holds no participation records. Pool addresses and mainnet dates are not published yet. Null values in [config.json](config.json) mean unknown, not an address or a launch announcement.

IceRoot has sold no ROOT. That is a commitment, not something these records or the chain can prove. The protocol does not enforce program spending rules. The documentation site shows this list as a page, and the explorer reads these same files.

## Repository layout

| Directory | Contents |
| --- | --- |
| [programs](programs/README.md) | One definition per program; initially SEC, BUG and DEV |
| [entries](entries/README.md) | One payment entitlement per stable entry id |
| [bounties](bounties/README.md) | Review and claim records, sharing the entry id for accepted rewards |
| [bindings](bindings/README.md) | Signed GitHub-to-testnet links and mainnet binding evidence |
| [statements](statements/README.md) | One monthly statement containing separate unsigned transfers |
| [genesis](genesis/README.md) | Manifests of program rewards allocated at genesis |
| [schemas](schemas/README.md) | JSON Schemas checked without network access |
| [scripts](scripts) | Validator, record bot and payment preparation |
| [tests](tests) | Offline tests and isolated example configuration |

Each data directory has worked examples under `examples/`, marked `"example": true`. They use fictional addresses, signatures, dates and evidence. They never enter live accounting, bot pull requests or payment exports. The three live program definitions authorize no individual reward by themselves.

## Bounty program

Security reports and confirmed bugs draw from the Security and bug bounty pool. Accepted code, documentation and tests draw from the Developer ecosystem pool. Maintainers determine severity, tier, acceptance and duplicates. The bot does not decide any of them.

The following table is **provisional**, in ROOT. The final table will be set once ROOT has an on-chain value. The table is reviewed quarterly. A review does not reduce an earned reward; the table in effect when a report or contribution arrives applies.

| Reward | ROOT |
| --- | ---: |
| Security: Critical | 50,000 |
| Security: High | 12,500 |
| Security: Medium | 2,500 |
| Security: Low | 500 |
| Confirmed bug with no security effect | 250 |
| Contribution: Tier 1 | 2,500 |
| Contribution: Tier 2 | 1,000 |
| Contribution: Tier 3 | 250 |
| Posted bounty | Up to 12,500 |
| Yearly security and bug bounty cap, shared by SEC and BUG | 750,000 |
| Yearly contribution bounty cap | 375,000 |

Critical findings include unauthorized asset creation, theft, signature bypasses or conflicting finalized blocks within the stated fault limits. High findings include network-wide halts, determinism failures or signing something the user did not approve. Medium findings include an inexpensive remote crash of one node or disclosure of private data other than keys. Low findings have limited but demonstrated security effects.

Tier 1 covers major features, subsystems, tools, test suites and substantial refactoring. Tier 2 covers fixes with tests, measured performance improvements and new guides. Tier 3 covers smaller tested fixes, additional tests and substantive documentation corrections. Typos, link fixes, formatting, routine dependency updates and generated files receive credit only. Posted tasks state their amount before work starts. There are no rankings or monthly bonuses.

The pre-mainnet earning period has one cap. After mainnet, yearly periods start at genesis and its anniversaries. Rewards beyond a period's remaining cap are queued at their full amount for the next period, ahead of newer rewards. Queued rewards still count against the program's total budget and pool allocation. Audits, security research and grants need their own programs and budgets; these bounty caps do not set their budgets.

### Scope and eligibility

Public iceroot-network repositories that deliver IceRoot software, tools or documentation are in scope. A repository joins when it becomes public. The default branch and latest release count. The reference repository `solar-core-ref` is excluded unless the same flaw affects IceRoot. Third-party bugs count only when exploitable through IceRoot's use of that dependency; report upstream first. Forks run by other projects, limits the whitepaper states, scanner output without a reproduction, social engineering, physical attacks, volumetric denial of service and attacks that need a stolen key, a compromised computer or a malicious browser extension are outside the program.

Anyone with a GitHub account may earn except the team. Validators and related parties may earn at the same rates. The team includes people paid for IceRoot work, pool or fund key holders and bounty raters. Contracted work is paid under its contract, without an additional bounty. A related party is a person or project related to the IceRoot team, Monolythium and LYTH included. A related party's claim states the relationship, and its reward is marked as related-party in the record. Holding LYTH or running an independent validator does not by itself make someone a related party. Reviewers check declarations; an automated check cannot discover undisclosed relationships.

The first complete, reproducible report of a root cause is eligible. Duplicates, including earlier recorded findings, earn nothing. One root cause earns one reward; reporting a security flaw and writing its fix does not earn two rewards. Split pull requests are rated as one contribution. Repeated reports without a working reproduction may lead to exclusion. Maintainers explain ratings and allow one request for a second review. A contribution that was paid a bounty carries a `bounty paid` tag on the validators portal, with a link to its record here.

### Report, claim and bind

1. **Security:** [report privately first](https://github.com/iceroot-network/.github/security/advisories/new). A private security report is a condition of a security bounty. Do not create a public claim, record or payment until the advisory is published. Ordinary bugs use a public issue; contributions use a pull request.
2. Supply a working reproduction or complete the contribution. After acceptance, post the [claim comment](BOT.md#claim-comments) from your GitHub account. Declare team membership and related-party relationships. Maintainers confirm the claim and assign its rating. Earnings use the permanent numeric GitHub account id, not a changeable username.
3. Post the [signed account link](bindings/README.md). A new or changed GitHub-to-testnet link takes effect after seven days. Keep old link records. Maintainers verify the post author, exact message, signature and derived account before approving it.
4. From the linked testnet account, send the participation binding transaction with memo `iceroot:bind:v1 <mainnet address>`. The latest valid binding before the announced deadline counts. The deadline is not published yet. Testnet balances never carry over.
5. Eligible rewards earned before mainnet, with a published advisory where applicable and a verified binding, become explicit mainnet genesis allocations. They are liquid from block 1. A security report still unpublished at the genesis cutoff is listed after publication and paid in a monthly run after mainnet. What happens to bounty rewards still unbound at the deadline is **not decided yet**. Do not assume that the participation pool's rule for unbound shares applies to them.

After mainnet the team pays approved rewards by hand once a month from each pool's 2-of-3 multisig, one transaction per entry, with its memo. How a new earner links a payout account after mainnet is not published yet. A pasted payout address is never accepted as proof.

### Proposals and approval

Anyone can propose a program or entry by pull request. Maintainers review scope, evidence, amount, eligibility, related-party disclosure and available budget. A team member merges the listing. Set approval evidence to the merged pull request and its UTC merge time in a follow-up record update. A bot proposal is not itself approval.

An entry must be listed and approved before payment, and payment details must match. **There is no waiting period before payment.** The seven-day account-link rule is separate. Payment preparation refuses missing pool addresses, unverified bindings, over-budget rewards, duplicate payouts and mismatched memos. Signers also check the real chain balance, fees and finality, which an offline validator cannot know. After finality, record the transaction id, height, time and memo. Never delete or reuse an id, including a cancelled one.

The memo is `iceroot:pay:v1 <entry id> <64-character fingerprint>`. [FORMAT.md](FORMAT.md) defines its exact bytes and the payment fingerprint. No signing keys live here. Public history, reviewed merges and on-chain fingerprints provide the audit trail.

## Local checks and automation

Python 3.11 or later is sufficient. No packages, network or wallet keys are needed for validation or tests.

```sh
python3 scripts/validate.py
python3 scripts/validate.py --examples
python3 -m unittest discover -s tests -v
python3 scripts/bot.py --offline --month 2026-08 --output bot-output
```

Pull requests and pushes run the checks. Hourly and manual bot runs read public GitHub activity; monthly runs prepare statements. Without `PROGRAMS_BOT_TOKEN`, the bot writes only downloadable review artifacts. With a configured token it can propose a pull request. [BOT.md](BOT.md) describes setup, labels, commands, permissions and the remaining SDK and wallet integrations. [SECURITY.md](SECURITY.md) states the reporting and disclosure policy.
