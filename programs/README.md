# Programs

One `<CODE>.json` file defines each program. [Schema](../schemas/program.schema.json). [Worked example](examples/DEV.json).

`id` is a permanent 3 to 6 letter code. `pool` references one of the five accounts in `config.json`. `budget` is the total commitment ceiling in base units; `yearly_cap` is an additional per-period ceiling or null. The pool's shared bounty cap applies to programs with `bounty: true`. An open program is not approval of any entry. Pool account addresses remain null until published.

The live SEC and BUG definitions share the security pool allocation and cap. Their budgets are not additive allocations of new funds; aggregate entries must also fit the pool. DEV covers accepted contributions. Other programs need reviewed definitions before entries can use them.

Examples are isolated from live programs and may reuse their codes.
