# Bounty record

One file per report or contribution, named by its reserved entry id. [Schema](../schemas/bounty.schema.json). [Worked example](examples/DEV-0001.json).

Store the public source, numeric claimant id, maintainer rating evidence, claim URL, recorded time, amount, related-party disclosure and review status. Accepted payable records reference an entry with the same id and amount. Credit-only records appear in their recorded month's statement. Rejected and duplicate records have no entry. A duplicate names the original public source and receives no entitlement even though its rating amount is retained for context.

Security records require a published advisory and confirmation that the report was private first. Do not put unpublished reports, severity hints or reserved security payments in a public file. Preserve ids and source identity. Mark final rewards `paid` or `credited` alongside the matching entry; the validators portal can use the id as its `bounty paid` record link.
