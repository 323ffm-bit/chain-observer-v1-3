import unittest
from chain_observer_v1_3 import ChainObserver, VerificationAttestation

class ChainObserverV13Tests(unittest.TestCase):
    def setUp(self):
        self.o = ChainObserver()

    def claim(self, cid, props, content="Input"):
        return self.o.register_claim(cid, content, "[K]", properties=props)

    def transform(self, tid, inp, out, op, before_after, rules, **kw):
        return self.o.record_transformation(
            tid, inp, out, op, output_properties=before_after,
            rules=rules, **kw
        )

    def test_math_rotation_preserves_norm(self):
        self.claim("a", {"norm": 5.0, "dimension": 2})
        r = self.transform("t", "a", "b", "rotation", {"norm": 5.0, "dimension": 2},
            [{"property":"norm","mode":"preserve","tolerance":1e-9},
             {"property":"dimension","mode":"preserve"}])
        self.assertEqual(r["overall_check"], "PASS")

    def test_math_scaling_flags_declared_norm_invariant(self):
        self.claim("a", {"norm": 5.0})
        r = self.transform("t", "a", "b", "scaling", {"norm": 10.0},
            [{"property":"norm","mode":"preserve"}])
        self.assertEqual(r["overall_check"], "VIOLATION")

    def test_math_scaling_allowed_when_rule_is_constraint(self):
        self.claim("a", {"norm": 5.0})
        r = self.transform("t", "a", "b", "scale_by_2", {"norm": 10.0},
            [{"property":"norm","mode":"constraint","comparator":"gte","expected":0}])
        self.assertEqual(r["overall_check"], "PASS")

    def test_ai_summary_preserves_required_entities(self):
        self.claim("a", {"entities":["Alice","Acme"], "negation":True})
        r = self.transform("t", "a", "b", "summarize",
            {"entities":["Alice","Acme"], "negation":True},
            [{"property":"entities","mode":"preserve"},
             {"property":"negation","mode":"preserve"}])
        self.assertEqual(r["overall_check"], "PASS")

    def test_ai_summary_omitting_entity_is_violation(self):
        self.claim("a", {"entities":["Alice","Acme"]})
        r = self.transform("t", "a", "b", "summarize", {"entities":["Alice"]},
            [{"property":"entities","mode":"preserve"}])
        self.assertEqual(r["overall_check"], "VIOLATION")

    def test_ai_negation_flip_is_violation(self):
        self.claim("a", {"negation":True})
        r = self.transform("t", "a", "b", "rewrite", {"negation":False},
            [{"property":"negation","mode":"preserve"}])
        self.assertEqual(r["overall_check"], "VIOLATION")

    def test_scientific_unit_conversion_preserves_quantity(self):
        self.claim("a", {"quantity_si": 1.0})
        r = self.transform("t", "a", "b", "meters_to_centimeters",
            {"quantity_si":1.0}, [{"property":"quantity_si","mode":"preserve","tolerance":1e-12}])
        self.assertEqual(r["overall_check"], "PASS")

    def test_scientific_measurement_outside_tolerance_flags(self):
        self.claim("a", {"calibrated_value": 10.0})
        r = self.transform("t", "a", "b", "instrument_conversion",
            {"calibrated_value":10.4},
            [{"property":"calibrated_value","mode":"preserve","tolerance":0.01}])
        self.assertEqual(r["overall_check"], "VIOLATION")

    def test_data_filter_preserves_monotonicity_constraint(self):
        self.claim("a", {"row_count":100})
        r = self.transform("t", "a", "b", "filter_rows", {"row_count":65},
            [{"property":"row_count","mode":"constraint","comparator":"lte","expected":100}])
        self.assertEqual(r["overall_check"], "PASS")

    def test_data_filter_cannot_increase_rows_under_declared_constraint(self):
        self.claim("a", {"row_count":100})
        r = self.transform("t", "a", "b", "filter_rows", {"row_count":120},
            [{"property":"row_count","mode":"constraint","comparator":"lte","expected":100}])
        self.assertEqual(r["overall_check"], "VIOLATION")

    def test_communication_translation_preserves_speaker_intent_flag(self):
        self.claim("a", {"request_type":"question", "certainty":"uncertain"})
        r = self.transform("t", "a", "b", "translate",
            {"request_type":"question", "certainty":"uncertain"},
            [{"property":"request_type","mode":"preserve"},
             {"property":"certainty","mode":"preserve"}])
        self.assertEqual(r["overall_check"], "PASS")

    def test_communication_rewrite_strengthening_certainty_flags(self):
        self.claim("a", {"certainty":"possible"})
        r = self.transform("t", "a", "b", "paraphrase", {"certainty":"certain"},
            [{"property":"certainty","mode":"preserve"}])
        self.assertEqual(r["overall_check"], "VIOLATION")

    def test_missing_property_is_undetermined(self):
        self.claim("a", {"source_language":"de"})
        r = self.transform("t", "a", "b", "translate", {},
            [{"property":"source_language","mode":"preserve"}])
        self.assertEqual(r["overall_check"], "UNDETERMINED")

    def test_incomparable_values_are_undetermined(self):
        self.claim("a", {"value": {"complex": 1}})
        r = self.transform("t", "a", "b", "convert", {"value": 1},
            [{"property":"value","mode":"constraint","comparator":"lt","expected":"x"}])
        self.assertEqual(r["overall_check"], "UNDETERMINED")

    def test_violation_prevents_requested_verified_output_promotion(self):
        self.claim("a", {"meaning":"not approved"})
        att = VerificationAttestation.create("src", "tester", "manual check")
        r = self.o.record_transformation("t", "a", "b", "rewrite",
            output_status="[R]", output_source_ref="src", output_verification=att,
            output_properties={"meaning":"approved"},
            rules=[{"property":"meaning","mode":"preserve"}])
        self.assertEqual(r["overall_check"], "VIOLATION")
        self.assertEqual(self.o.registry["b"].status, "[H]")

    def test_undetermined_prevents_requested_verified_output_promotion(self):
        self.claim("a", {"critical_flag":True})
        att = VerificationAttestation.create("src", "tester", "manual check")
        r = self.o.record_transformation("t", "a", "b", "rewrite",
            output_status="[R]", output_source_ref="src", output_verification=att,
            output_properties={},
            rules=[{"property":"critical_flag","mode":"preserve"}])
        self.assertEqual(r["overall_check"], "UNDETERMINED")
        self.assertEqual(self.o.registry["b"].status, "[U]")

    def test_no_rules_means_undetermined_not_pass(self):
        self.claim("a", {"x":1})
        r = self.transform("t", "a", "b", "unknown_op", {"x":2}, [])
        self.assertEqual(r["overall_check"], "UNDETERMINED")

    def test_transformation_lineage_is_stored(self):
        self.claim("a", {"x":1})
        self.transform("t", "a", "b", "copy", {"x":1},
            [{"property":"x","mode":"preserve"}])
        self.assertEqual(self.o.transformations["t"]["input_claim_id"], "a")
        self.assertEqual(self.o.transformations["t"]["output_claim_id"], "b")

    def test_duplicate_transformation_id_rejected(self):
        self.claim("a", {"x":1})
        self.transform("t", "a", "b", "copy", {"x":1},
            [{"property":"x","mode":"preserve"}])
        with self.assertRaises(ValueError):
            self.o.record_transformation("t", "a", "c", "copy", output_properties={"x":1})

    def test_unknown_input_rejected(self):
        with self.assertRaises(KeyError):
            self.o.record_transformation("t", "missing", "b", "copy")

    def test_v12_transition_alias_retained(self):
        self.claim("a", {"x":1})
        self.assertTrue(self.o.evaluate_transition("a", "[K]", "legacy alias"))

    def test_v12_conflict_recording_retained(self):
        self.claim("a", {"x":1})
        self.claim("b", {"x":2})
        first = self.o.record_conflict_candidate("a","b","reviewer","check")
        second = self.o.record_conflict_candidate("b","a","reviewer"," CHECK ")
        self.assertEqual(first["conflict_id"], second["conflict_id"])

    def test_json_snapshot_contains_transformations(self):
        self.claim("a", {"x":1})
        self.transform("t", "a", "b", "copy", {"x":1},
            [{"property":"x","mode":"preserve"}])
        data = self.o.snapshot()
        self.assertIn("transformations", data)
        self.assertEqual(data["prototype"], "Chain Observer v1.3")

    def test_boolean_flip_cannot_pass_with_numeric_tolerance(self):
        self.claim("a", {"flag": True})
        r = self.transform("t", "a", "b", "rewrite", {"flag": False},
            [{"property":"flag","mode":"preserve","tolerance":1.0}])
        self.assertEqual(r["overall_check"], "VIOLATION")

    def test_invalid_rule_configuration_raises_before_state_mutation(self):
        from chain_observer_v1_3 import RuleConfigurationError
        self.claim("a", {"x": 1})
        with self.assertRaises(RuleConfigurationError):
            self.transform("t", "a", "b", "copy", {"x": 1},
                [{"property":"x","mode":"constraint","comparator":"greater_than","expected":0}])
        self.assertNotIn("b", self.o.registry)
        self.assertNotIn("t", self.o.transformations)

    def test_missing_rules_remain_undetermined(self):
        self.claim("a", {"x": 1})
        r = self.transform("t", "a", "b", "copy", {"x": 1}, None)
        self.assertEqual(r["overall_check"], "UNDETERMINED")

    def test_nested_input_properties_are_deep_copied(self):
        entities = ["Alice", "Acme"]
        self.claim("a", {"entities": entities})
        entities.append("Injected-Corp")
        self.assertEqual(self.o.registry["a"].properties["entities"], ["Alice", "Acme"])
        self.transform("t", "a", "b", "copy", {"entities": ["Alice", "Acme"]},
            [{"property":"entities","mode":"preserve"}])
        entities_after = ["Alice", "Acme"]
        # Mutating caller-owned output data after recording must not rewrite the audit.
        out_props = {"entities": entities_after}
        self.o2 = ChainObserver()
        self.o2.register_claim("x", "Input", "[K]", properties={"entities":["Alice","Acme"]})
        self.o2.record_transformation("tx", "x", "y", "copy", output_properties=out_props,
            rules=[{"property":"entities","mode":"preserve"}])
        entities_after.append("Injected-Corp")
        self.assertEqual(self.o2.transformations["tx"]["output_properties"]["entities"],
                         ["Alice", "Acme"])

    def test_failed_transformation_blocks_silent_r_promotion(self):
        self.claim("a", {"meaning":"not approved"})
        att = VerificationAttestation.create("src2", "tester", "independent check")
        r = self.o.record_transformation("t", "a", "b", "rewrite",
            output_status="[R]", output_source_ref="src2", output_verification=att,
            output_properties={"meaning":"approved"},
            rules=[{"property":"meaning","mode":"preserve"}])
        self.assertEqual(r["overall_check"], "VIOLATION")
        att2 = VerificationAttestation.create("src3", "tester", "new evidence")
        self.assertFalse(self.o.apply_transition("b", "[R]", "promote", "src3", att2))
        self.assertEqual(self.o.registry["b"].status, "[H]")
        self.assertTrue(self.o.apply_transition("b", "[R]", "explicit reviewed override",
                                                "src3", att2, override_review=True))
        self.assertEqual(self.o.registry["b"].status, "[R]")

    def test_nan_preserved_when_nan_on_both_sides(self):
        self.claim("a", {"measurement": float("nan")})
        r = self.transform("t", "a", "b", "copy", {"measurement": float("nan")},
            [{"property":"measurement","mode":"preserve"}])
        self.assertEqual(r["overall_check"], "PASS")

    def test_bad_tolerance_is_configuration_error(self):
        from chain_observer_v1_3 import RuleConfigurationError
        self.claim("a", {"x": 1.0})
        with self.assertRaises(RuleConfigurationError):
            self.transform("t", "a", "b", "copy", {"x": 1.0},
                [{"property":"x","mode":"preserve","tolerance":float("nan")}])
        self.assertNotIn("b", self.o.registry)

    def test_non_string_mode_and_comparator_are_configuration_errors(self):
        from chain_observer_v1_3 import RuleConfigurationError
        self.claim("a", {"x": 1})
        bad_rules = [
            [{"property":"x","mode":["preserve"]}],
            [{"property":"x","mode":"constraint","comparator":["gt"],"expected":0}],
        ]
        for index, rules in enumerate(bad_rules):
            with self.assertRaises(RuleConfigurationError):
                self.o.record_transformation(f"bad-{index}", "a", f"b{index}", "test",
                    output_properties={"x":1}, rules=rules)
            self.assertNotIn(f"b{index}", self.o.registry)

if __name__ == "__main__":
    unittest.main()
