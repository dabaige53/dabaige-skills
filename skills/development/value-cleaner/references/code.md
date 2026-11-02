# Code Cleanup

`value-cleaner code` removes production logic that no caller, input, or supported behavior needs. Scan signals are in brackets.

## Decision rule

> Which caller or supported input reaches this code, and what breaks without it?

Answer from the real call paths: entry points, the boundary that validates input, and alternate callers such as plugins, CLIs, jobs, string-based dispatch, and decorators that register handlers.

## Candidates

### Validation repeated inside a guaranteed boundary [repeated-guard]

A type or schema declaration alone does not show runtime enforcement; trace malformed input from each entry point to the function. When every path passes through a boundary that already rejects the input, the inner check protects nothing.

```text
def handle(request):
    order = parse_order(request.body)   # rejects a missing customer_id
    return create_order(order)

def create_order(order):
    if order.customer_id is None:
        raise ValueError("customer_id required")
    ...
```

Remove the inner check when `create_order` is reachable only through `parse_order`. Keep it when plugins or other entry points call `create_order` directly, or when it checks something the boundary does not.

### Logic with no callers [unreferenced, test-only, commented-code]

Functions, classes, branches, flags, and parameters that nothing reaches: no call site, a flag that is always off, a parameter every caller passes the same value for, a branch for a platform the project no longer supports, commented-out code. Code reached only by its own tests is dead too; delete those tests with it.

Before removing, search the whole repository, including templates, configuration, and string-based dispatch. Exported names of a published library may have external callers; treat them as public API.

### Abstractions for hypothetical needs [single-implementation]

Interfaces or abstract classes with one implementation, factories that return one class, strategy or plugin layers with one strategy, configuration knobs nobody sets, wrappers that only forward calls.

```text
class ExporterFactory:          # one implementation, one caller
    def create(self, kind):
        return CsvExporter()
```

Call `CsvExporter()` directly and add the factory when a second exporter exists. Keep an abstraction that is a published extension point, a seam the tests actually use, or a boundary to an external system that is being swapped.

### Fallbacks that hide errors [broad-except]

Broad catches that swallow, return a default, or log and continue; defaults for values that should never be missing; retries with no limit or stated reason.

```text
try:
    rate = fetch_rate(currency)
except Exception:
    rate = 1.0
```

An outage becomes silently wrong prices. Let the error surface, or handle the specific failure the caller can act on. Keep documented degraded modes, best-effort cleanup, and top-level handlers that report and exit.

## Keep

- Validation at the boundary that owns external input.
- Error handling for failures that can occur in the supported runtime.
- Business limits, idempotency guards, and checks that keep data consistent.
- Checks protecting security, money, data integrity, concurrency, public contracts, or an incident fix, unless a named surviving check covers them.
- Code kept for compatibility with a named consumer, version, or format.

## Removing

- Do not change supported behavior unless the user asks. A cleanup that changes outputs, errors, or side effects is a behavior change; report it instead of making it.
- Remove the whole unit: the code and its now-unused imports, constants, configuration, tests that only exercised it, and docs that described it.
