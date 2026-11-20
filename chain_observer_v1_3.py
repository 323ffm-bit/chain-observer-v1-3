"""
Chain Observer v1.3
A rule-based prototype for tracking claims across transformations and
checking declared property-preservation constraints.

Important scope:
- The observer checks explicit, machine-readable property values and rules.
- It does not infer arbitrary semantic meaning from natural language.
- A property change is not inherently invalid: only a declared invariant or
  constraint can make it a violation.
- Missing or incomparable evidence yields UNDETERMINED, not PASS.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Callable
import json
import math
import copy
import operator
import uuid

VALID_STATUSES = {"[R]", "[K]", "[I]", "[H]", "[U]"}
VALID_CHECKS = {"PASS", "VIOLATION", "UNDETERMINED"}


class RuleConfigurationError(ValueError):
    """Raised when a declared rule is malformed or unsupported."""
COMPARATORS: Dict[str, Callable[[Any, Any], bool]] = {
    "eq": operator.eq,
    "ne": operator.ne,
    "lt": operator.lt,
    "lte": operator.le,
    "gt": operator.gt,
    "gte": operator.ge,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class VerificationAttestation:
    source_ref: str
    checked_by: str
    method: str
    checked_at: str

    @classmethod
    def create(cls, source_ref: str, checked_by: str, method: str,
               checked_at: Optional[str] = None) -> "VerificationAttestation":
        values = {
            "source_ref": source_ref.strip(),
            "checked_by": checked_by.strip(),
            "method": method.strip(),
            "checked_at": checked_at or utc_now(),
        }
        if not all(values.values()):
            raise ValueError("Verification attestation requires source_ref, checked_by and method.")
        return cls(**values)


@dataclass
class EpistemicClaim:
    claim_id: str
    content: str
    status: str
    source_ref: Optional[str]
    verification: Optional[VerificationAttestation]
    properties: Dict[str, Any]
    created_at: str
    updated_at: str


class ChainObserver:
    """Claim registry plus transformation lineage and explicit property checks."""

    def __init__(self) -> None:
        self.registry: Dict[str, EpistemicClaim] = {}
        self.events: List[Dict[str, Any]] = []
        self.conflicts: List[Dict[str, Any]] = []
        self.transformations: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _validate_status(status: str) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid epistemic status {status!r}.")

    @staticmethod
    def _validate_nonempty(value: str, field: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-empty string.")

    def _event(self, event_type: str, claim_id: str, details: Dict[str, Any]) -> None:
        self.events.append({
            "event_id": str(uuid.uuid4()),
            "timestamp": utc_now(),
            "event": event_type,
            "claim_id": claim_id,
            "details": copy.deepcopy(details),
        })

    @staticmethod
    def _verification_dict(value):
        return asdict(value) if value else None

    def register_claim(self, claim_id: str, content: str, status: str,
                       source_ref: Optional[str] = None,
                       verification: Optional[VerificationAttestation] = None,
                       properties: Optional[Dict[str, Any]] = None) -> EpistemicClaim:
        self._validate_nonempty(claim_id, "claim_id")
        self._validate_nonempty(content, "content")
        self._validate_status(status)
        if claim_id in self.registry:
            raise ValueError(f"Claim ID {claim_id!r} already exists.")
        if source_ref is not None:
            self._validate_nonempty(source_ref, "source_ref")
            source_ref = source_ref.strip()
        if status == "[R]":
            if not source_ref or verification is None:
                raise ValueError("[R] requires source_ref and verification attestation.")
            if verification.source_ref != source_ref:
                raise ValueError("Attestation source_ref must match claim source_ref.")
        now = utc_now()
        claim = EpistemicClaim(
            claim_id, content.strip(), status, source_ref, verification,
            copy.deepcopy(properties or {}), now, now
        )
        self.registry[claim_id] = claim
        self._event("CLAIM_REGISTERED", claim_id, {
            "content": claim.content, "status": status, "source_ref": source_ref,
            "properties": claim.properties,
            "verification_attestation": self._verification_dict(verification),
        })
        return claim

    def apply_transition(self, claim_id: str, new_status: str, reason: str,
                         source_ref: Optional[str] = None,
                         verification: Optional[VerificationAttestation] = None,
                         override_review: bool = False) -> bool:
        if claim_id not in self.registry:
            raise KeyError(f"Claim {claim_id!r} not found.")
        self._validate_status(new_status)
        self._validate_nonempty(reason, "reason")
        claim = self.registry[claim_id]
        old = {"status": claim.status, "source_ref": claim.source_ref,
               "verification": self._verification_dict(claim.verification)}
        if new_status == "[R]":
            blocking_reviews = [
                item for item in self.transformations.values()
                if item["output_claim_id"] == claim_id
                and item["disposition"] == "REVIEW_REQUIRED"
            ]
            if blocking_reviews and not override_review:
                self._event("TRANSITION_BLOCKED", claim_id, {
                    "from": claim.status, "to": new_status,
                    "reason": "A prior transformation requires review; explicit override_review=True is required.",
                    "blocking_transformations": [item["transformation_id"] for item in blocking_reviews],
                })
                return False
            if not source_ref or verification is None:
                self._event("TRANSITION_BLOCKED", claim_id, {
                    "from": claim.status, "to": new_status,
                    "reason": "Source reference and verification attestation required."
                })
                return False
            if verification.source_ref != source_ref:
                raise ValueError("Attestation source_ref must match transition source_ref.")
        else:
            source_ref, verification = None, None
        claim.status, claim.source_ref, claim.verification = new_status, source_ref, verification
        claim.updated_at = utc_now()
        self._event("STATUS_TRANSITION", claim_id, {
            "from": old["status"], "to": new_status, "reason": reason.strip(),
            "previous_source_ref": old["source_ref"],
            "previous_verification_attestation": old["verification"],
            "current_source_ref": source_ref,
            "current_verification_attestation": self._verification_dict(verification),
            "override_review": bool(override_review),
        })
        return True

    # Backward-compatible v1.2 API.
    def evaluate_transition(self, *args, **kwargs) -> bool:
        return self.apply_transition(*args, **kwargs)

    @staticmethod
    def _validate_rules(rules: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        if rules is None:
            return []
        if not isinstance(rules, list):
            raise RuleConfigurationError("rules must be a list; use [] explicitly for no declared checks.")
        validated = copy.deepcopy(rules)
        for index, rule in enumerate(validated):
            if not isinstance(rule, dict):
                raise RuleConfigurationError(f"Rule {index} must be a dictionary.")
            name = rule.get("property")
            if not isinstance(name, str) or not name.strip():
                raise RuleConfigurationError(f"Rule {index} requires a non-empty string property.")
            mode = rule.get("mode", "preserve")
            if not isinstance(mode, str) or mode not in {"preserve", "constraint"}:
                raise RuleConfigurationError(f"Rule {index} has unsupported mode: {mode!r}.")
            tolerance = rule.get("tolerance", 0)
            try:
                tolerance_is_valid = (
                    not isinstance(tolerance, bool)
                    and isinstance(tolerance, (int, float))
                    and math.isfinite(float(tolerance))
                    and tolerance >= 0
                )
            except (TypeError, ValueError, OverflowError):
                tolerance_is_valid = False
            if not tolerance_is_valid:
                raise RuleConfigurationError(f"Rule {index} tolerance must be a finite non-negative number.")
            if mode == "constraint":
                comparator = rule.get("comparator")
                if not isinstance(comparator, str) or comparator not in COMPARATORS:
                    raise RuleConfigurationError(f"Rule {index} has unsupported comparator: {comparator!r}.")
                if "expected" not in rule:
                    raise RuleConfigurationError(f"Rule {index} requires 'expected' for constraint mode.")
        return validated

    @staticmethod
    def _evaluate_rule(before: Dict[str, Any], after: Dict[str, Any],
                       rule: Dict[str, Any]) -> Dict[str, Any]:
        name = rule["property"]
        mode = rule.get("mode", "preserve")
        tolerance = rule.get("tolerance", 0)
        if name not in before or name not in after:
            return {"property": name, "result": "UNDETERMINED",
                    "reason": "Property missing before or after transformation."}
        old, new = before[name], after[name]
        try:
            if mode == "preserve":
                # bool is an int subclass in Python, but must retain logical equality semantics.
                if (isinstance(old, (int, float)) and not isinstance(old, bool)
                        and isinstance(new, (int, float)) and not isinstance(new, bool)):
                    old_nan = isinstance(old, float) and math.isnan(old)
                    new_nan = isinstance(new, float) and math.isnan(new)
                    if old_nan or new_nan:
                        passed = old_nan and new_nan
                    else:
                        passed = math.isclose(old, new, rel_tol=float(tolerance), abs_tol=float(tolerance))
                else:
                    passed = old == new
            else:  # constraint rules have already been validated at the boundary.
                comparator = rule["comparator"]
                expected = rule["expected"]
                passed = COMPARATORS[comparator](new, expected)
        except (TypeError, ValueError, OverflowError) as exc:
            return {"property": name, "before": old, "after": new,
                    "result": "UNDETERMINED", "reason": f"Not comparable: {exc}"}
        return {
            "property": name, "before": copy.deepcopy(old), "after": copy.deepcopy(new),
            "rule": copy.deepcopy(rule), "result": "PASS" if passed else "VIOLATION",
            "reason": "Declared property rule satisfied." if passed
                      else "Declared property rule was violated.",
        }

    def record_transformation(self, transformation_id: str, input_claim_id: str,
                              output_claim_id: str, operation: str,
                              conditions: Optional[Dict[str, Any]] = None,
                              output_content: Optional[str] = None,
                              output_status: str = "[I]",
                              output_source_ref: Optional[str] = None,
                              output_verification: Optional[VerificationAttestation] = None,
                              output_properties: Optional[Dict[str, Any]] = None,
                              rules: Optional[List[Dict[str, Any]]] = None,
                              actor: str = "operator") -> Dict[str, Any]:
        for value, field in [(transformation_id, "transformation_id"),
                             (input_claim_id, "input_claim_id"),
                             (output_claim_id, "output_claim_id"),
                             (operation, "operation"), (actor, "actor")]:
            self._validate_nonempty(value, field)
        if transformation_id in self.transformations:
            raise ValueError(f"Transformation ID {transformation_id!r} already exists.")
        if input_claim_id not in self.registry:
            raise KeyError(f"Input claim {input_claim_id!r} not found.")
        if output_claim_id in self.registry:
            raise ValueError(f"Output claim ID {output_claim_id!r} already exists.")
        # Validate the complete rule configuration before mutating observer state.
        validated_rules = self._validate_rules(rules)
        source = self.registry[input_claim_id]
        props_after = copy.deepcopy(output_properties or {})
        checks = [self._evaluate_rule(source.properties, props_after, r)
                  for r in validated_rules]
        overall = ("UNDETERMINED" if not checks
                   else "VIOLATION" if any(c["result"] == "VIOLATION" for c in checks)
                   else "UNDETERMINED" if any(c["result"] == "UNDETERMINED" for c in checks)
                   else "PASS")
        # A violation or unknown check does not erase the output; it marks it
        # as requiring review and prevents an unsupported [R] promotion.
        if overall != "PASS" and output_status == "[R]":
            output_status = "[H]" if overall == "VIOLATION" else "[U]"
            output_source_ref, output_verification = None, None
        output = self.register_claim(
            output_claim_id, output_content or f"Output of {transformation_id}",
            output_status, output_source_ref, output_verification, props_after
        )
        record = {
            "transformation_id": transformation_id,
            "input_claim_id": input_claim_id,
            "output_claim_id": output_claim_id,
            "operation": operation,
            "conditions": copy.deepcopy(conditions or {}),
            "actor": actor,
            "timestamp": utc_now(),
            "input_properties": copy.deepcopy(source.properties),
            "output_properties": copy.deepcopy(props_after),
            "property_checks": checks,
            "overall_check": overall,
            "disposition": ("REVIEW_REQUIRED" if overall != "PASS" else "RULES_SATISFIED"),
        }
        self.transformations[transformation_id] = record
        self._event("TRANSFORMATION_RECORDED", output_claim_id, record)
        return record

    def record_conflict_candidate(self, claim_id_a: str, claim_id_b: str,
                                  reported_by: str, note: str) -> Dict[str, Any]:
        if claim_id_a == claim_id_b:
            raise ValueError("A conflict candidate must reference two different claims.")
        if claim_id_a not in self.registry or claim_id_b not in self.registry:
            raise KeyError("Both claims must exist.")
        self._validate_nonempty(reported_by, "reported_by")
        self._validate_nonempty(note, "note")
        pair = tuple(sorted((claim_id_a, claim_id_b)))
        normalized_note = " ".join(note.split()).casefold()
        normalized_reporter = " ".join(reported_by.split()).casefold()
        for item in self.conflicts:
            if (tuple(sorted((item["claim_a"], item["claim_b"]))) == pair
                and " ".join(item["note"].split()).casefold() == normalized_note
                and " ".join(item["reported_by"].split()).casefold() == normalized_reporter):
                return item
        item = {
            "conflict_id": f"CF-{len(self.conflicts)+1:04d}",
            "timestamp": utc_now(), "claim_a": claim_id_a, "claim_b": claim_id_b,
            "status": "UNRESOLVED_REVIEW_REQUIRED",
            "reported_by": reported_by.strip(), "note": note.strip(),
        }
        self.conflicts.append(item)
        self._event("CONFLICT_CANDIDATE_RECORDED", claim_id_a, item)
        return item

    def snapshot(self) -> Dict[str, Any]:
        return {
            "prototype": "Chain Observer v1.3",
            "claims": {
                cid: {**asdict(c), "verification": self._verification_dict(c.verification)}
                for cid, c in self.registry.items()
            },
            "transformations": copy.deepcopy(self.transformations),
            "events": copy.deepcopy(self.events),
            "conflict_candidates": copy.deepcopy(self.conflicts),
            "scope_note": (
                "Property checks evaluate only explicit machine-readable values and declared rules. "
                "They do not infer semantic equivalence or authenticate source truth. "
                "Missing/incomparable properties are UNDETERMINED, not PASS. "
                "Malformed rule configuration raises RuleConfigurationError before state mutation. "
                "For preserve rules, NaN is treated as unchanged only when both sides are NaN. "
                "A violation means a declared rule was breached, not that the output is universally false."
            ),
        }

    def export_json(self, indent: int = 2) -> str:
        return json.dumps(self.snapshot(), indent=indent, ensure_ascii=False, default=str)


if __name__ == "__main__":
    observer = ChainObserver()
    observer.register_claim("MATH-IN", "Vector has length 5.", "[K]",
                            properties={"norm": 5.0, "dimension": 2})
    result = observer.record_transformation(
        "MATH-T1", "MATH-IN", "MATH-OUT", "rotation",
        output_content="Rotated vector has length 5.",
        output_properties={"norm": 5.0, "dimension": 2},
        rules=[{"property": "norm", "mode": "preserve", "tolerance": 1e-9},
               {"property": "dimension", "mode": "preserve"}],
    )
    print(json.dumps(result, indent=2))
