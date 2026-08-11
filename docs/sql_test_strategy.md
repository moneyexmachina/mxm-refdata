# PostgreSQL Persistence Testing Strategy

## Purpose

MXM packages use explicit PostgreSQL persistence through Psycopg and plain SQL.

This document defines the common testing strategy for that persistence boundary. Its purpose is to make SQL persistence predictable across MXM packages: the same responsibilities should be tested at the same layer, with the same semantics, without every package inventing a new testing model.

The strategy distinguishes four separate concerns:

1. PostgreSQL connection and transaction management.
2. Schema migration management.
3. Entity-specific SQL persistence adapters.
4. Behaviour against a real PostgreSQL instance.

Higher-level application composition and materialisation tests build on these layers but are not substitutes for them.

---

# 1. Core principle

Test each persistence responsibility at the lowest layer that can prove it correctly.

A fake Psycopg connection is appropriate for proving that an adapter:

- emits the intended SQL shape;
- uses the configured schema;
- passes the correct parameters;
- deterministically orders bulk operations;
- encodes domain values correctly;
- reconstructs domain values correctly;
- rejects malformed persisted state;
- applies the intended identity and conflict policy;
- verifies post-write state; and
- does not control transactions.

A fake database cannot prove PostgreSQL behaviour.

A real PostgreSQL integration test is required to prove:

- DDL validity;
- database constraints;
- foreign keys;
- unique constraints;
- PostgreSQL type behaviour;
- JSONB adaptation;
- actual `ON CONFLICT` behaviour;
- actual rollback behaviour;
- schema isolation; and
- migrations and entity adapters working together.

This distinction is fundamental.

---

# 2. Testing layers

## 2.1 PostgreSQL boundary unit tests

Typical file:

```text
tests/unittests/sql/test_postgres.py
```

These tests own the behaviour of the package's PostgreSQL connection abstraction.

They test:

- accepted connection URL forms;
- URL normalisation;
- rejection of unsupported database schemes;
- schema-name validation;
- default schema selection;
- connection creation;
- successful transaction commit;
- rollback after caller failure;
- rollback after commit failure;
- connection closure;
- failure during rollback or close;
- propagation of the original exception; and
- basic connectivity checks such as `SELECT 1`.

Entity persistence tests must not duplicate this behaviour.

In particular, entity SQL adapters should not be tested for the mechanics of commit, rollback, connection creation or closure. They should only prove that they do not attempt to perform those operations themselves.

---

## 2.2 Migration-runner unit tests

Typical file:

```text
tests/unittests/sql/test_migration_runner.py
```

These tests own migration mechanics.

They test:

- migration filename conventions;
- migration version extraction;
- migration names;
- exact-source checksums;
- required bootstrap migration;
- duplicate migration versions;
- deterministic migration ordering;
- schema placeholder rendering;
- configured-schema quoting;
- migration-ledger parsing;
- malformed ledger state;
- unknown applied migrations;
- checksum mismatches;
- pending migration selection;
- migration SQL execution;
- ledger insertion;
- ordering of multiple pending migrations;
- failure stopping subsequent migrations; and
- idempotent replay when all migrations are already applied.

Entity persistence tests must not test migration mechanics or duplicate DDL assertions already owned here.

---

## 2.3 Entity persistence unit tests

Typical files:

```text
tests/unittests/sql/test_periods.py
tests/unittests/sql/test_futures_products.py
tests/unittests/sql/test_futures_contracts.py
```

These tests exercise one SQL persistence adapter through a scripted Psycopg-like connection.

Their purpose is to test the Python ↔ SQL boundary without requiring PostgreSQL.

They are organised by operation rather than by private helper.

Private codecs and reconstruction helpers should normally be exercised through the public persistence operations.

---

## 2.4 Real PostgreSQL integration tests

Typical location:

```text
tests/integration/sql/
```

These tests use an actual PostgreSQL instance.

For MXM development infrastructure, they should use a disposable schema such as:

```text
<package_schema>_test_<random_suffix>
```

rather than creating or dropping databases.

Integration tests may intentionally use the complete runtime infrastructure required to resolve the database connection, including configuration and secret resolution. They are not required to preserve the artificial isolation used by lower-level unit tests.

They must include explicit safety guards ensuring that tests are connected to the expected development database and user before creating or dropping disposable schemas.

---

# 3. Standard entity-adapter unit-test machinery

Each entity SQL test module should use a small scripted connection boundary.

The standard conceptual objects are:

```python
@dataclass(frozen=True)
class Execution:
    operation: Literal["execute", "executemany"]
    query: ExecutableQuery
    parameters: object | None
```

A `FakeCursor` should:

- implement the context-manager protocol;
- record `execute`;
- record `executemany`;
- return scripted rows from `fetchall`.

A `FakeConnection` should:

- return scripted cursors in order;
- maintain one ordered execution log;
- count cursor requests;
- record accidental `commit()` calls; and
- record accidental `rollback()` calls.

Tests should cast the fake connection to the production Psycopg connection type only at the boundary.

The fake does not simulate PostgreSQL.

It records the adapter's requested operations and supplies predetermined result rows.

---

# 4. Do not prematurely share the test fake implementation

The testing **strategy** should be common across MXM packages immediately.

The fake implementation does not yet need to live in a shared package.

Initially, local duplication is preferable because different persistence adapters may reveal requirements that change the shape of the fake.

A shared SQL test utility should only be extracted once several MXM packages are using substantially identical machinery and its stable interface is obvious.

The desired progression is:

```text
common strategy
    ↓
repeated local implementations
    ↓
stable repeated shape
    ↓
shared test utility
```

not:

```text
first implementation
    ↓
premature testing framework
```

---

# 5. Testing read operations

## 5.1 Unfiltered fetch-all operation

For a public operation such as:

```python
fetch_entities(...)
```

test:

- empty database result returns the appropriate empty collection;
- complete persisted rows reconstruct complete domain values;
- configured schema is used;
- deterministic `ORDER BY` is present;
- duplicate persisted identity is rejected; and
- malformed persisted rows are rejected before entering the domain.

The test should verify semantic SQL fragments rather than snapshotting the complete SQL string.

For example:

```python
assert '"refdata_test_abc"."periods"' in query_text
assert "ORDER BY first_date, last_date, period_id" in query_text
```

Do not test indentation, whitespace or irrelevant SQL formatting.

---

## 5.2 Filtered reads

For operations such as:

```python
fetch_entities_by_ids(...)
fetch_entities_by_types(...)
fetch_entities_for_parent(...)
fetch_active_entities(...)
```

test the behaviour specific to the filter.

Where appropriate this includes:

- empty explicit selection returns without database access;
- duplicate filter values are collapsed;
- filter values are deterministically ordered;
- enums are encoded using the agreed representation;
- exact SQL predicate semantics are present;
- inclusive/exclusive boundary semantics are explicit;
- parameters are supplied in the expected order;
- configured schema is used; and
- returned rows reconstruct through the same domain decoder as unfiltered fetches.

Do not duplicate every general reconstruction test for every filtered query.

The common decoder should already be covered by the main fetch tests.

---

# 6. Testing persisted-row decoding

Persisted data is an untrusted boundary even when PostgreSQL normally constrains it.

Entity adapters must reject values that cannot validly enter the domain.

Tests should cover each materially different decoder or invariant rather than every column merely because it exists.

Typical cases include:

- too few columns;
- too many columns;
- text expected but another type returned;
- numeric value expected but another type returned;
- date expected but another type returned;
- unknown enum encoding;
- malformed JSON structure;
- malformed nested JSON values;
- invalid domain identity;
- invalid domain value; and
- invalid semantic relationships between fields.

The purpose is to prove the adapter's reconstruction contract, not to duplicate every possible malformed database value.

---

# 7. Constructing malformed PostgreSQL rows

Test code needs to create rows that would not satisfy the production type model.

Use one explicit test boundary:

```python
def _row(
    *values: object,
) -> PostgresRow:
    return tuple(values)
```

or the equivalent required by the package's `PostgresRow` type.

For narrow rows, malformed cases can be constructed directly.

For wide rows, prefer:

1. construct one valid persisted row;
2. copy it into `list[object]`;
3. replace only the values relevant to the test; and
4. convert it back through `_row()`.

For example:

```python
def _row_with_values(
    row: PostgresRow,
    replacements: dict[int, object],
) -> PostgresRow:
    values: list[object] = list(row)

    for index, value in replacements.items():
        if index < 0 or index >= len(values):
            raise AssertionError(
                "Test row replacement index is out of range: "
                f"index={index}, row_length={len(values)}"
            )

        values[index] = value

    return _row(*values)
```

This prevents malformed test construction from accidentally changing the row shape.

For particularly wide rows, construct the malformed row inside the test rather than doing significant runtime construction inside `pytest.mark.parametrize` at module-import time.

---

# 8. Testing immutable/idempotent inserts

Most MXM operational reference and state entities use immutable-by-identity insertion semantics.

The standard contract is:

```text
identity absent
    → insert

identity present with identical state
    → accept idempotent replay

identity present with different state
    → conflict
```

The SQL implementation normally uses:

```sql
ON CONFLICT (<identity>) DO NOTHING
```

followed by explicit readback and equality verification.

Tests should cover:

### Input normalisation

- empty input returns without database access;
- repeated identical domain values collapse to one write;
- conflicting values for the same identity fail before database access;
- domain/persistence invariants fail before database access where applicable.

### SQL encoding

- rows are emitted in deterministic identity order;
- configured schema is used;
- the intended `ON CONFLICT` clause is present;
- all representative domain values are encoded correctly;
- enums use the agreed enum representation;
- dates remain dates;
- nested JSON is wrapped using the expected Psycopg JSON adapter.

### Post-write verification

- matching persisted state is accepted;
- conflicting persisted state raises the entity conflict error;
- missing persisted state raises the entity persistence error;
- validation includes every unique requested identity;
- validation uses the configured schema.

Do not add two tests merely to express the same successful idempotent-replay condition.

---

# 9. Testing mutable UPSERT state

Some persisted state is intentionally mutable.

Examples include provenance or other metadata whose operational identity remains stable while its descriptive state may evolve.

The contract is then different:

```text
identity absent
    → insert

identity present
    → explicitly update mutable fields
```

Unit tests should prove the intended SQL:

```sql
ON CONFLICT (<identity>)
DO UPDATE SET ...
```

and should assert representative update assignments.

For example:

```text
source_digest = EXCLUDED.source_digest
source_revision = EXCLUDED.source_revision
updated_at = EXCLUDED.updated_at
```

The fake-database unit test must not pretend to prove that PostgreSQL actually changed an existing row.

That behaviour belongs in the real PostgreSQL integration suite.

Post-write verification should still ensure that the returned persisted state exactly matches the requested final state.

---

# 10. Composite identities and secondary uniqueness

Some tables have more than one meaningful uniqueness rule.

For example, an entity may have:

- a primary identity; and
- a separate semantic position or source-path uniqueness constraint.

Tests should reflect the real domain semantics.

Input normalisation should reject conflicts detectable without contacting the database.

Persisted-row reconstruction should reject contradictory result sets even if the database schema would normally prevent them.

Actual database enforcement of `PRIMARY KEY`, `UNIQUE` and `FOREIGN KEY` constraints remains an integration-test responsibility.

---

# 11. Determinism

Persistence operations should be deterministic wherever their semantics do not require otherwise.

Unit tests should therefore verify deterministic:

- bulk-write ordering;
- parameter-array ordering;
- fetch ordering; and
- identity normalisation.

Do not rely on:

- input sequence accidents;
- Python set ordering; or
- unspecified PostgreSQL row ordering.

Determinism makes tests reproducible, logs inspectable and materialisation behaviour easier to reason about.

---

# 12. Schema isolation

Every entity SQL operation accepting a schema argument should have at least one focused unit test proving that the configured schema is used.

The test should also ensure that the operation does not silently address `public`.

Example:

```python
assert '"refdata_test_abc"."futures_products"' in query_text
assert '"public"."futures_products"' not in query_text
```

Actual isolation between two real PostgreSQL schemas belongs in integration tests.

---

# 13. Transaction ownership

Entity SQL persistence modules do not own transactions.

Their public operations receive a caller-owned connection.

At least one test per entity module should exercise representative writes and assert:

```python
assert connection.commit_calls == 0
assert connection.rollback_calls == 0
```

This is an ownership test, not a transaction-lifecycle test.

Commit and rollback semantics belong exclusively to the PostgreSQL boundary tests.

This separation is what allows a higher-level materialisation operation to combine many entity writes into one atomic transaction.

---

# 14. What entity unit tests deliberately do not prove

Entity fake-database tests must not claim to prove:

- that table DDL is valid PostgreSQL;
- that a table or column actually exists;
- that a foreign key works;
- that a `CHECK` constraint works;
- that a uniqueness constraint works;
- that PostgreSQL accepts a Python parameter type;
- that JSONB adaptation works against PostgreSQL;
- that `ON CONFLICT` behaves as expected on the server;
- that an UPDATE really changed a persisted row;
- that transaction rollback restored prior database state; or
- that schema isolation works on an actual server.

These are integration-test responsibilities.

---

# 15. Real PostgreSQL integration-test contract

Integration tests should migrate a disposable schema using the production migration runner.

They should then exercise the actual persistence functions against that schema.

A representative integration suite should prove:

### Migration

The complete packaged migration set can create the schema from nothing.

### Round trip

A domain value can be inserted and fetched back identically.

### Idempotent replay

An immutable entity can be inserted twice without changing its persisted value.

### Conflict behaviour

Where the adapter deliberately performs post-write conflict detection, conflicting requested state is detected.

### UPSERT behaviour

For mutable state, persisted state A can actually become requested state B.

### Foreign keys

Rows referencing missing parent identities are rejected by PostgreSQL.

### Unique constraints

Secondary uniqueness rules are enforced by PostgreSQL.

### Check constraints

Important database-level invariants are enforced by PostgreSQL.

### PostgreSQL types

JSONB, dates, numeric values and other PostgreSQL-specific representations adapt successfully through Psycopg.

### Schema isolation

Operations against one disposable schema do not affect another.

### Transaction rollback

A deliberately failed multi-operation transaction leaves no partial state behind.

---

# 16. Integration-test safety

Real PostgreSQL tests must fail closed.

Before destructive schema operations, verify the expected development environment.

Typical guards include:

```text
application      expected package/application
environment      dev
machine          expected development host
substrate        expected local substrate
database         expected development database
database user    expected development role
schema           disposable test-schema prefix
```

Tests may drop only their own disposable schema.

They must never drop the database.

---

# 17. Materialisation tests are a separate layer

A materialisation operation combines persistence adapters into an application-level transaction.

Its tests should prove behaviour such as:

```text
generate desired state
    ↓
BEGIN
    persist entity A
    persist entity B
    persist entity C
    persist entity D
COMMIT
```

and:

```text
conflict anywhere
    ↓
ROLLBACK entire materialisation
```

This behaviour should not be pushed down into individual entity persistence tests.

Entity adapters prove local persistence semantics.

Materialisation proves orchestration and atomicity across entities.

---

# 18. Query-layer tests are a separate layer

The SQL layer should provide table-local persistence operations.

Higher-level query operations may compose these operations to answer domain questions involving multiple persisted entities.

Tests for such composition belong in the query layer.

For example:

```text
SQL layer
    fetch periods
    fetch contracts
    fetch products

query layer
    contracts of a given period type
    product + contract view
    domain lookup semantics
```

Do not introduce joins or application-specific lookup policy into the entity persistence adapter merely because a higher-level query will eventually need the information.

---

# 19. Test names should describe contracts

Prefer names such as:

```text
test_insert_periods_rejects_conflicting_duplicate_input
test_fetch_futures_products_rejects_duplicate_database_identity
test_upsert_futures_product_sources_uses_update_conflict_clause
test_period_operations_do_not_control_transactions
```

The name should describe externally observable persistence behaviour.

Avoid tests whose primary purpose is to exercise a private helper by name.

---

# 20. Standard checklist for a new entity persistence module

For every new entity module, review the following checklist.

| Area | Required consideration |
|---|---|
| Fetch all | Empty result |
| Fetch all | Domain reconstruction |
| Fetch all | Configured schema |
| Fetch all | Deterministic ordering |
| Fetch all | Duplicate persisted identity |
| Decode | Wrong row shape |
| Decode | Representative scalar type errors |
| Decode | Enum decoding |
| Decode | Domain invariants |
| Filtered reads | Empty-selection behaviour |
| Filtered reads | Parameter normalisation |
| Filtered reads | Predicate semantics |
| Filtered reads | Ordering |
| Insert/upsert | Empty input |
| Insert/upsert | Duplicate input collapse |
| Insert/upsert | Conflicting input |
| Insert/upsert | Deterministic parameter ordering |
| Insert/upsert | Configured schema |
| Insert/upsert | Conflict clause |
| Insert/upsert | Domain encoding |
| Verification | Matching persisted state |
| Verification | Missing persisted state |
| Verification | Conflicting persisted state |
| Verification | All affected identities checked |
| Ownership | No commit |
| Ownership | No rollback |
| Integration | Real round trip |
| Integration | Real constraints |
| Integration | Real conflict/upsert behaviour |
| Integration | Real rollback |
| Integration | Schema isolation |

Not every row applies to every table.

A test should exist because the persistence contract requires it, not because the checklist demands mechanical test-count symmetry.

---

# 21. Applying the strategy to `futures_contracts`

The `futures_contracts` adapter should therefore receive unit coverage for:

```text
fetch_futures_contracts
    empty result
    reconstruction
    configured schema
    semantic ordering
    duplicate contract_id
    malformed rows
    invalid currency
    invalid unit
    invalid contract identity
    invalid lifecycle

fetch_futures_contracts_by_ids
    empty selection
    duplicate collapse
    deterministic ID parameters
    expected ANY predicate
    configured schema
    reconstruction

fetch_futures_contracts_for_product
    product parameter
    expected equality predicate
    configured schema
    semantic ordering
    reconstruction

fetch_active_futures_contracts
    inclusive first_day_of_interest boundary
    inclusive last_trading_day boundary
    no-product-filter SQL
    explicit product-filter SQL
    empty explicit product set returns early
    duplicate product IDs collapse
    deterministic product-ID parameters
    semantic ordering
    reconstruction

insert_futures_contracts
    empty input
    identical duplicate collapse
    conflicting duplicate rejection
    invalid contract invariants before SQL
    deterministic contract-ID ordering
    configured schema
    ON CONFLICT (contract_id) DO NOTHING
    exact domain encoding
    matching readback accepted
    conflicting readback rejected
    missing readback rejected
    all unique contract IDs verified

module ownership
    no commit
    no rollback
```

Real PostgreSQL integration coverage should later prove:

```text
futures_contracts foreign key → futures_products
futures_contracts foreign key → periods
actual idempotent ON CONFLICT behaviour
actual data round trip
date handling
database constraints
schema isolation
rollback as part of full refdata materialisation
```

---

# 22. Governing rule

The governing rule for MXM PostgreSQL tests is:

> Unit tests prove what our Python persistence adapter asks PostgreSQL to do and how it interprets PostgreSQL results. Integration tests prove what PostgreSQL actually does.

Keeping that boundary explicit gives MXM fast deterministic unit tests without replacing the database with a mock fiction, while retaining a small number of high-value real-PostgreSQL tests for the behaviour only PostgreSQL can prove.
