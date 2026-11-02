# Test Cleanup

`value-cleaner test` removes tests, fixtures, snapshots, and test documentation that do not protect against a plausible regression. Scan signals are in brackets.

## Contents

1. Decision rule
2. Evidence
3. Low-value categories
4. Protected risks
5. Actions
6. Suite-level checks
7. Writing replacement tests
8. Test documentation
9. Sources

## 1. Decision rule

A test has value when it detects a plausible production regression or enforces a stable contract that is not already protected more clearly and cheaply elsewhere.

A useful test lets the reviewer complete this sentence:

> If production accidentally changes from **correct behavior A** to **plausible defect B**, this test fails because it observes **stable evidence C**.

A test is a strong deletion candidate when no credible version of that sentence exists and no protected risk applies.

Counterfactual check:

- What small, realistic defect could be introduced while this test still passes?
- What small, realistic defect would make this test fail?
- Is that failure already detected by a clearer, cheaper, or more reliable test?

Existing mutation-test and coverage reports are evidence. Do not introduce a mutation-testing tool unless the user asks, and never decide from a coverage percentage alone.

## 2. Evidence

| Dimension | Strong evidence | Weak evidence |
|---|---|---|
| Regression relevance | Reflects a real failure mode, incident, invariant, or user-visible behavior | Merely executes a line or method |
| Failure sensitivity | A realistic defect changes the assertion result | Assertion is tautological, vague, or derived from the same implementation |
| Uniqueness | Catches a failure not protected elsewhere | Repeats the same behavior at the same or a more expensive layer |
| Contract stability | Observes public output, state, side effect, schema, or explicit invariant | Observes call order, private structure, incidental text, timing, or layout |
| Fidelity | Uses production behavior or a faithful fake at the right boundary | Recreates the implementation with mocks or stubs |
| Reliability | Deterministic with actionable failures | Flaky, timing-sensitive, retry-dependent, or difficult to diagnose |
| Cost | Small setup, focused purpose, reasonable runtime | High fixture cost, broad environment, long runtime, frequent maintenance |

Value is contextual. A costly test can be justified by severe risk; a fast test can still be useless.

## 3. Low-value categories

### 3.1 Tautological or self-fulfilling tests

Signals:

- The expected value is calculated by the same logic as the system under test.
- A stub returns a value and the test only asserts that the same value came back.
- The test asserts that an imported constant equals itself or a copied literal.
- The assertion is always true, checks only that execution reached the end, or cannot fail under realistic defects.

```text
stub(exchange.rate("USD", "EUR")).returns(0.9)
assert converter.rate("USD", "EUR") == 0.9
```

This passes while conversion, rounding, or caching is broken; assert `converter.convert(100, "USD", "EUR") == 90` instead. Likewise, replace `assert MAX_RETRIES == imported_MAX_RETRIES` with a test that the fourth attempt does not start after three failures.

Action: DELETE when no contract is protected; REWRITE when the intended behavior is real but the oracle is invalid.

### 3.2 Implementation-coupled tests

Signals:

- Verifies private methods, internal helper calls, exact call order, temporary data structures, SQL shape, DOM structure, or serialization details not promised to consumers.
- Breaks during a refactor that preserves public behavior.
- Mirrors the current implementation step by step.

Verifying that `normalize_items` and `sum_items` were each called once proves nothing about the result; assert `calculate_total(order_with_discount) == expected_total` instead.

Action: REWRITE around a stable result. DELETE only when another test already protects the result.

Exceptions:

- Call count or order is itself a contract for caching, rate limits, transactions, audit, protocols, performance, or destructive effects.
- Internal representation is a published file format, plugin interface, ABI, schema, or compatibility boundary.

### 3.3 Mock theater and interaction-only tests [mock-only]

Signals:

- Most collaborators of the system under test are mocked.
- Assertions only verify non-state-changing queries such as `get`, `find`, `read`, or validation lookups.
- The test passes even if the code ignores dependency return values or produces the wrong result.
- The mock setup reimplements the production branching logic.
- Log assertions where the record is not an audit, security, compliance, billing, or operator contract.

```text
stub(user_store.find(42)).returns(active_user)
service.activate(42)
verify(user_store.find(42)).called_once()
```

This proves a lookup happened, not that activation worked; assert `user_store.get(42).status == ACTIVE` instead.

Action: REWRITE to assert output, state, persisted effect, emitted event, or a state-changing external command. Prefer a real lightweight dependency or maintained fake when practical.

Exceptions:

- A state-changing command is the only observable boundary, such as sending a message or charging a provider. `verify(payment_gateway.charge).called_once_with(order.total, idempotency_key)` is valid when charging exactly once is the contract and a real gateway cannot be used safely; also assert the resulting state.
- A query count protects an explicit cache or performance requirement.
- A rare failure path can only be induced safely through a test double.

### 3.4 Duplicate or equivalent tests [duplicate-body, large-parametrize]

Signals:

- Several cases use values from the same equivalence class and fail for the same reason.
- Unit, integration, and end-to-end suites repeat the same exhaustive matrix.
- A historical regression test duplicates a newer, clearer test without preserving incident context or a distinct boundary.
- Generated cases add volume without adding failure modes.

`for age in 21..99: assert allowed(age)` becomes `assert not allowed(20)` and `assert allowed(21)`, plus a representative value only when a distinct rule needs one. Across layers, keep the exhaustive cases at the business-rule layer, a few API contract cases, and one or two critical browser journeys, without a fixed ratio.

Action: MERGE into representative partitions or keep the cheapest clear protection. Preserve separate tests for different behaviors, risks, platforms, protocols, or failure mechanisms.

### 3.5 Coverage padding and impossible scenarios

Trace malformed input from the actual entry point to the tested function. A schema declaration or static type alone does not prove runtime enforcement: check the parser or validator, alternate callers, and public or plugin entry points. Keep rejection tests at the boundary that owns validation; inner layers need not repeat the same matrix after the guarantee is established.

For example, when an API parser rejects a missing required field before calling a private service, test rejection through that parser and valid behavior through the service. A test that bypasses the parser to inject the same missing field into the service may add no supported-behavior protection. If the service is independently callable by plugins, its own validation contract may still require that test.

Do not modify production validation just to make a test removable. If reachability is unclear, choose INVESTIGATE.

Signals:

- The test exists only to execute a line, catch block, or branch with no plausible production path.
- Inputs are rejected by upstream schema, type, parser, or invariant before reaching the unit.
- Assertions are weak because the goal is coverage rather than behavior.
- The test targets defensive code that cannot be exercised in the supported runtime and has no compatibility requirement.

Action: DELETE or REWRITE around a real contract.

Exception: fault injection can be valuable for recovery, corruption, partial failure, or hard-to-reproduce operational risks.

### 3.6 Incidental snapshots and golden files [large-snapshot, orphan-snapshot]

Signals:

- A large snapshot changes for harmless whitespace, ordering, timestamps, generated IDs, metadata, or unrelated UI sections.
- Reviewers routinely update snapshots without inspecting semantic differences.
- The snapshot duplicates precise assertions already present.
- Most of the captured output is outside the behavior under test.

When a full-page snapshot exists only for the suspended-account banner, assert the banner's role and message instead.

Action: REWRITE to a narrow semantic snapshot or explicit properties; MERGE duplicate snapshots; DELETE snapshots with no distinct protection.

Exceptions: complete output can be the contract for compilers, formatters, code generators, renderers, schemas, AST transforms, migrations, and compatibility fixtures.

### 3.7 Weak, absent, or misleading assertions [no-assertion, weak-assertion]

Signals:

- No assertion and no expected side effect, such as a bare `parse(valid_input)`.
- Only checks `not null`, `true`, status success, or collection non-emptiness when correctness requires more, such as `assert search("invoice") is not None`.
- Asserts logs, metrics, or tracing that are not an operational or audit contract.
- The test name promises behavior the assertion does not verify.

Action: REWRITE if the scenario matters, asserting only the properties relevant to the behavior; otherwise DELETE.

Exception: "does not throw" or smoke checks can be valid when successful construction or execution is the explicit contract.

### 3.8 Testing the language, framework, or dependency

Signals:

- Verifies standard-library sorting, framework routing, ORM persistence, dependency behavior, or generated boilerplate without project-specific configuration or adaptation, such as `save(entity)` followed by `assert database_contains(entity)` on an uncustomized ORM.
- Tests a third-party library through mocks rather than the project's integration contract.
- Getter and setter round trips with no logic in between.

Action: DELETE pure dependency tests. KEEP project configuration, adapters, compatibility assumptions, and integration boundaries that can realistically break, and accessors that validate, normalize, authorize, lazy-load, emit events, or map compatibility.

### 3.9 Dead, undiscovered, or obsolete tests [skipped, unused-fixture, unreferenced-fixture]

Signals:

- File naming or configuration prevents runner discovery.
- The target code, feature flag, platform, or endpoint no longer exists.
- A test is permanently skipped, commented out, or quarantined with no owner or exit condition, such as `skip("sometimes fails in CI")`. A leftover `.only` silently skips the rest of the file.
- Fixtures and snapshots have no references.

Action: DELETE after confirming the content is not intentional documentation, a migration fixture, a compliance artifact, or a tracked defect. When the behavior still matters, restore execution instead: fix synchronization or isolation, quarantine with an owner and exit condition, or replace it with a deterministic narrower test.

### 3.10 Flaky or nondeterministic tests [sleep]

Signals:

- Arbitrary sleeps, wall-clock assumptions, uncontrolled randomness, shared state, network dependence, unstable ordering, race-prone polling, or repeated reruns.
- Failures give little diagnostic value and are routinely ignored.

Action: REWRITE first when the behavior is valuable; a flaky test may expose a real race or operational defect. Quarantine only with an owner and exit condition. DELETE only when the protected behavior is covered elsewhere or no longer matters.

### 3.11 Over-broad end-to-end tests

Signals:

- Many cases repeat expensive login, provisioning, or environment setup to test narrow rules.
- A shared upstream failure causes unrelated scenarios to fail.
- Failures do not identify the broken component.
- The same rule is fully protected at a faster boundary and the broad test adds no integration assurance.

Action: keep a small set of critical journeys and move exhaustive business-rule matrices to narrower tests. Do not enforce a universal test-pyramid ratio.

### 3.12 Low-value generated tests

Signals:

- AI or generators produce one test per syntax branch, literal, field, or method regardless of risk.
- Cases differ cosmetically but exercise identical behavior.
- Expected values were copied from current output without a contract.
- Generated tests lock down accidental implementation choices and make refactoring expensive.

Action: group by behavior and failure mode, and keep the minimum representative set of normal, boundary, and error cases. Each retained case names the regression it protects.

## 4. Protected risks

Do not delete tests in these areas without evidence of equivalent surviving protection; they may still need rewriting, consolidation, or relocation:

- authentication, authorization, privacy, security, abuse prevention, or audit trails;
- money, billing, tax, quotas, and accounting;
- destructive changes, migrations, backup, recovery, and data integrity;
- concurrency, retries, idempotency, ordering, caching, and distributed failure;
- public APIs, protocols, schemas, serialization, file formats, compatibility, and plugin contracts;
- incident regressions, legal obligations, safety, and availability-critical behavior.

A narrow-looking assertion can carry one of these: `assert deserialize(old_version_fixture).customer_id == expected_id` protects backward compatibility.

## 5. Actions

- **KEEP**: protects a stable contract or credible failure mode, is not meaningfully duplicated, and costs in proportion to its risk.
- **REWRITE**: the scenario has value, but the oracle is poor or the test is implementation-coupled, over-mocked, flaky, too broad, or tied to an incidental snapshot.
- **MERGE**: several cases protect the same behavior and failure mechanism. Keep representative normal, boundary, and failure partitions.
- **DELETE**: at least one of these is well supported and no protected risk applies: no plausible defect is detected; the assertion cannot distinguish correct from incorrect behavior; an equal or stronger test protects the same failure; the test is dead, undiscovered, or targets removed behavior; it documents an implementation choice with no unique value.
- **INVESTIGATE**: the contract, runner path, consumer, incident history, or risk cannot be established. Report it instead of deleting it.

## 6. Suite-level checks

A suite of individually reasonable tests can still be over-tested. Look for:

- exhaustive matrices repeated at several layers;
- runtime dominated by low-risk scenarios;
- fixtures and helpers more complex than the production behavior;
- refactors that require widespread test rewrites without behavior changes;
- high failure noise, growing quarantine, or ignored CI results;
- tests organized around methods and files rather than behaviors and risks.

## 7. Writing replacement tests

- Exercise the production implementation and keep expected values independent of its algorithm. Patch process-wide globals only when no local seam exists.
- Keep simple setup inline. Extract a helper when it is reused, isolates complex setup, or names a meaningful operation; do not build fixtures for hypothetical cases.
- Add a test only for meaningful behavior, a relevant failure path, or a known regression, and name the protection it adds. Low-impact, reversible changes do not automatically need new tests.
- Before expanding scope for a speculative race or security edge case, explain the concrete failure, its likelihood, and the maintenance cost, and get the user's agreement.
- Do not change production behavior as part of test cleanup unless the user asks for a fix.

## 8. Test documentation

Keep what helps someone run, diagnose, or evolve the suite: verified commands, required environments and test data, CI gates and triage paths, reasons for unusual boundaries or fakes, and gaps with an owner and exit condition.

Remove static coverage numbers and pasted test output, catalogs of every test file, generic framework tutorials, completed or ownerless "tests to add" lists, and manual matrices nobody runs. `scripts/scan.py docs` finds stale status tables, TODOs, and broken links in test documents.

A cleaned set answers, without duplication: how to run the right tests, how to diagnose common failures, which level owns which risk, which constraints are non-obvious, and where active gaps are tracked.

## 9. Sources

Repository evidence takes precedence over these.

- Test behavior rather than implementation, and organize by behavior rather than method: [Testing on the Toilet, 2013-08](https://testing.googleblog.com/2013/08/testing-on-toilet-test-behavior-not.html), [2014-04](https://testing.googleblog.com/2014/04/testing-on-toilet-test-behaviors-not.html), [Software Engineering at Google, ch. 12](https://abseil.io/resources/swe-book/html/ch12.html).
- Prefer state and outcomes over incidental interactions: [SWE Book ch. 12](https://abseil.io/resources/swe-book/html/ch12.html), [Testing Blog, 2017-12](https://testing.googleblog.com/2017/12/).
- Fidelity before mock convenience: [2024-02](https://testing.googleblog.com/2024/02/increase-test-fidelity-by-avoiding-mocks.html).
- Resilient, expressive assertions: [2024-04](https://testing.googleblog.com/2024/04/how-i-learned-to-stop-writing-brittle.html), [2014-03](https://testing.googleblog.com/2014/03/testing-on-toilet-what-makes-good-test.html).
- Coverage is evidence, not the objective: [2020-08](https://testing.googleblog.com/2020/08/code-coverage-best-practices.html).
- Flakiness damages trust but may reveal real defects: [2016-05](https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html), [2021-03](https://testing.googleblog.com/2021/03/test-flakiness-one-of-main-challenges.html).
- Broad tests should earn their cost: [2015-04](https://testing.googleblog.com/2015/04/just-say-no-to-more-end-to-end-tests.html), [Martin Fowler, Test Pyramid](https://martinfowler.com/bliki/TestPyramid.html).
- Minimal inputs, meaningful assertions: [Microsoft unit testing best practices](https://learn.microsoft.com/dotnet/core/testing/unit-testing-best-practices).
- One-time boundary validation, restraint with single-use helpers, and agreement before speculative complexity: [OpenCode AGENTS.md](https://github.com/anomalyco/opencode/blob/dev/AGENTS.md), reviewed 2026-10-27 ([MIT](https://github.com/anomalyco/opencode/blob/dev/LICENSE)). Its Bun commands, package paths, globalThis restriction, and formatting conventions are repository-specific and were not adopted. The stop-after-sufficient-checks rule and the low-impact-change guidance are local preferences.
