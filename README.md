# Chain Observer v1.3

**A rule-based Python prototype for tracking claims across transformations and checking explicitly declared property integrity.**

Chain Observer records claims, their epistemic status, transformation lineage, property snapshots, and the results of declared preservation or constraint checks. It is designed as a small, inspectable demonstrator—not as a general-purpose semantic understanding or truth-verification system.

## What it does

- Maintains a registry of claims with epistemic labels: `[R]`, `[K]`, `[I]`, `[H]`, `[U]`.
- Requires a source reference and matching verification attestation when a claim is registered or transitioned to `[R]`.
- Records transformations, including input/output claim IDs, operation, actor, conditions, timestamps, and property snapshots.
- Evaluates explicit property rules:
  - `preserve`: the selected property must remain equal (numeric values may use a declared tolerance).
  - `constraint`: the output property must satisfy a declared comparator and expected value.
- Reports checks as `PASS`, `VIOLATION`, or `UNDETERMINED`.
- Marks transformations whose checks are not fully satisfied as `REVIEW_REQUIRED`.
- Prevents silent promotion of a `REVIEW_REQUIRED` output claim to `[R]`; an explicit, logged review override and a source-linked verification attestation are required.
- Retains the v1.2 transition alias and conflict-candidate recording behavior.

## Result semantics

| Result | Meaning |
|---|---|
| `PASS` | Every supplied rule was evaluated and satisfied. This does not prove that the rule set is complete or appropriate. |
| `VIOLATION` | At least one explicitly declared rule was breached. This does not mean the output is universally false. |
| `UNDETERMINED` | No rules were supplied, or required property evidence was missing or incomparable. It is never treated as a pass. |
| `RuleConfigurationError` | A rule definition is malformed or unsupported. Raised before the transformation mutates observer state. |

A property change is not automatically an error. Only a change that breaches a declared invariant or constraint is flagged.

## Post-review hardening

The current v1.3 build includes targeted corrections for the following edge cases:

- Booleans use logical equality and are not treated as numbers for tolerance comparisons.
- Rule structures, modes, comparators, and tolerances are validated before state mutation.
- Nested caller-owned properties, conditions, rules, events, and snapshots are defensively copied.
- A `REVIEW_REQUIRED` transformation blocks silent `[R]` promotion. An explicit override is recorded in the event log and still requires a source reference plus a matching verification attestation.
- For `preserve` rules, `NaN → NaN` is treated as unchanged; `NaN ↔ non-NaN` is a violation.

The override mechanism records an operator-supplied attestation; the prototype does not independently authenticate the operator or prove that the evidence is genuinely new.

## Quick start

Requirements: **Python 3.9+**. No third-party packages are required.

Clone or download this repository, then run the test suite from the repository directory:

```bash
python -m unittest -v
```

Run the built-in demonstration:

```bash
python chain_observer_v1_3.py
```

## Minimal usage example

```python
from chain_observer_v1_3 import ChainObserver

observer = ChainObserver()

observer.register_claim(
    claim_id="input-1",
    content="A vector has length 5.",
    status="[K]",
    properties={"norm": 5.0, "dimension": 2},
)

result = observer.record_transformation(
    transformation_id="transform-1",
    input_claim_id="input-1",
    output_claim_id="output-1",
    operation="rotation",
    output_content="The rotated vector has length 5.",
    output_properties={"norm": 5.0, "dimension": 2},
    rules=[
        {"property": "norm", "mode": "preserve", "tolerance": 1e-9},
        {"property": "dimension", "mode": "preserve"},
    ],
)

print(result["overall_check"])  # PASS
print(observer.export_json())
```

### Constraint example

```python
rules = [
    {
        "property": "row_count",
        "mode": "constraint",
        "comparator": "lte",
        "expected": 100,
    }
]
```

Supported comparators: `eq`, `ne`, `lt`, `lte`, `gt`, `gte`.

If `rules` is omitted, `None`, or an empty list, the result is `UNDETERMINED` rather than `PASS`. Invalid rule configuration raises `RuleConfigurationError`.

## Epistemic labels

- `[R]` — verified claim; requires a source reference and matching verification attestation.
- `[K]` — contextual knowledge.
- `[I]` — inference.
- `[H]` — hypothesis.
- `[U]` — unknown or unresolved.

These labels are bookkeeping states supplied and managed by the caller. The prototype does not independently determine the truth of a claim.

## Test coverage

The included test suite contains **31 tests**, covering:

- Mathematical transformations (rotation and scaling)
- AI summarization and rewriting (entity retention, negation, certainty)
- Scientific measurement and unit conversion
- Data filtering and aggregation constraints
- Translation and communication intent preservation
- Missing and incomparable property values
- v1.2 API compatibility and conflict deduplication
- Review-gate behavior and explicit override
- Defensive copying and rule-configuration validation
- Boolean tolerance and NaN comparison edge cases

Run the tests locally with `python -m unittest -v`. The checked-in `TEST_RESULTS.txt` records the result from the packaged build.

## Scope and limitations

This prototype evaluates **explicit, machine-readable property values against caller-declared rules**. It does not:

- Extract semantic properties from arbitrary natural-language text.
- Decide which properties ought to be invariant.
- Infer semantic equivalence for reordered lists or complex structures.
- Authenticate source material or independently establish scientific truth.
- Provide tamper-proof storage against a caller with direct access to the observer's internal Python objects.
- Guarantee thread safety, persistence, or cryptographic audit integrity.

For `preserve`, nested lists and dictionaries use strict structural equality. Domain-specific comparison semantics (for example, order-independent collections or semantic similarity) are not currently pluggable.

The Chain Observer is a standalone demonstrator. It is not the complete underlying research architecture.

### Compatibility note

The included tests exercise the retained transition alias and conflict-candidate behavior documented for v1.2. The original v1.2 source is not included in this repository, so this is not a source-to-source or byte-for-byte compatibility certification.

## Repository contents

- `chain_observer_v1_3.py` — implementation
- `test_chain_observer_v1_3.py` — automated test suite
- `TEST_RESULTS.txt` — packaged test result summary
- `README.md` — documentation

## License

No license is currently specified. Unless a license is added, standard copyright applies and reuse/redistribution permissions should not be assumed. Choose and add a license deliberately before inviting reuse.
