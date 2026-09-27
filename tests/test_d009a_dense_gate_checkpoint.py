import copy
import unittest
from tools.experiments.d009a_dense_gate_checkpoint import summarize

def metric(score,fpr,recall=.98,oracle=.993):
    return {"macro_f0_5":score,"singleton_false_positive_rate":fpr,
            "candidate_pair_recall":recall,"blocking_oracle_macro_f0_5":oracle}

def fixture():
    baseline={"name":"dense_prior_-2","dense_prior":-2.0,"threshold":.95,
        "calibration":{s:metric(.970,.06) for s in ("all","India","US")},
        "holdout":{s:metric(.968,.07) for s in ("all","India","US")}}
    gate={"extra_dense_logit_penalty":.5,
        "calibration":{s:metric(.971,.05) for s in ("all","India","US")},
        "holdout":{s:metric(.969,.06) for s in ("all","India","US")}}
    worse=copy.deepcopy(gate)
    worse["extra_dense_logit_penalty"]=1.0
    for s in ("all","India","US"):
        worse["calibration"][s]["macro_f0_5"]=.969
    d={}
    for fold in ("calibrate","holdout"):
        d[f"{fold}_India_dense_only"]={"predicted":10,"false_positive":2}
        d[f"{fold}_India_lexical"]={"predicted":90,"false_positive":1}
        d[f"{fold}_US_dense_only"]={"predicted":5,"false_positive":1}
        d[f"{fold}_US_lexical"]={"predicted":95,"false_positive":1}
    return {"selected":baseline,"dense_gate_selected":gate,
            "dense_gate_sweep":[worse,gate],"selection_diagnostics":d}

class TestD009aDenseGate(unittest.TestCase):
    def test_calibration_argmax_and_equivalent_prior(self):
        out=summarize(fixture())
        self.assertEqual(out["status"],"REPLICATE")
        self.assertEqual(out["calibration_selected_extra_dense_logit_penalty"],.5)
        self.assertEqual(out["equivalent_dense_prior"],-2.5)
        self.assertAlmostEqual(out["metrics"]["holdout"]["all"]["delta_macro_f0_5"],.001)

    def test_provenance_error_concentration(self):
        p=summarize(fixture())["provenance"]["holdout"]
        self.assertEqual(p["dense_selected"],15)
        self.assertEqual(p["dense_false_positives"],3)
        self.assertGreater(p["false_positive_rate_ratio"],10)

    def test_rejects_candidate_recall_drift(self):
        data=fixture()
        data["dense_gate_selected"]["holdout"]["all"]["candidate_pair_recall"]=.97
        with self.assertRaisesRegex(ValueError,"candidate pair recall"):
            summarize(data)

    def test_rejects_oracle_drift(self):
        data=fixture()
        data["dense_gate_selected"]["calibration"]["India"]["blocking_oracle_macro_f0_5"]=.99
        with self.assertRaisesRegex(ValueError,"blocking oracle"):
            summarize(data)

    def test_rejects_non_argmax_selected_gate(self):
        data=fixture()
        data["dense_gate_selected"]["extra_dense_logit_penalty"]=3.0
        with self.assertRaisesRegex(ValueError,"calibration argmax"):
            summarize(data)

if __name__=="__main__":
    unittest.main()
