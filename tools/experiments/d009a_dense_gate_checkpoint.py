"""D009a: checkpoint provenance-specific dense-only calibration from INT006 JSON."""
from __future__ import annotations
import argparse, json
from pathlib import Path

SLICES=("all","India","US")
FOLDS=("calibration","holdout")

def _delta(before, after):
    if before["candidate_pair_recall"] != after["candidate_pair_recall"]:
        raise ValueError("candidate pair recall changed under decision-only gate")
    if before["blocking_oracle_macro_f0_5"] != after["blocking_oracle_macro_f0_5"]:
        raise ValueError("blocking oracle changed under decision-only gate")
    return {
        "baseline_macro_f0_5":before["macro_f0_5"],
        "gate_macro_f0_5":after["macro_f0_5"],
        "delta_macro_f0_5":after["macro_f0_5"]-before["macro_f0_5"],
        "baseline_singleton_fpr":before["singleton_false_positive_rate"],
        "gate_singleton_fpr":after["singleton_false_positive_rate"],
        "delta_singleton_fpr":after["singleton_false_positive_rate"]-before["singleton_false_positive_rate"],
        "candidate_pair_recall":before["candidate_pair_recall"],
        "blocking_oracle_macro_f0_5":before["blocking_oracle_macro_f0_5"],
    }

def _provenance(diagnostics, fold):
    v={}
    for country in ("India","US"):
        for channel in ("dense_only","lexical"):
            key=f"{fold}_{country}_{channel}"
            if key not in diagnostics:
                raise ValueError(f"missing selection diagnostic: {key}")
            v[country,channel]=diagnostics[key]
    ds=sum(v[c,"dense_only"]["predicted"] for c in ("India","US"))
    ls=sum(v[c,"lexical"]["predicted"] for c in ("India","US"))
    df=sum(v[c,"dense_only"]["false_positive"] for c in ("India","US"))
    lf=sum(v[c,"lexical"]["false_positive"] for c in ("India","US"))
    dr=df/ds if ds else 0.0
    lr=lf/ls if ls else 0.0
    return {
        "dense_selected":ds,"lexical_selected":ls,
        "dense_selected_share":ds/(ds+ls) if ds+ls else 0.0,
        "dense_false_positives":df,"lexical_false_positives":lf,
        "dense_false_positive_share":df/(df+lf) if df+lf else 0.0,
        "dense_selected_pair_false_positive_rate":dr,
        "lexical_selected_pair_false_positive_rate":lr,
        "false_positive_rate_ratio":dr/lr if lr else None,
    }

def summarize(report):
    baseline=report["selected"]
    gate=report["dense_gate_selected"]
    selected=max(report["dense_gate_sweep"],key=lambda row:row["calibration"]["all"]["macro_f0_5"])
    if selected["extra_dense_logit_penalty"] != gate["extra_dense_logit_penalty"]:
        raise ValueError("dense_gate_selected is not calibration argmax")
    if baseline["dense_prior"] is None:
        raise ValueError("selected INT006 variant has no dense prior")
    result={
        "experiment_id":"D009a","status":"REPLICATE",
        "baseline_variant":baseline["name"],
        "baseline_dense_prior":baseline["dense_prior"],
        "threshold":baseline["threshold"],
        "calibration_selected_extra_dense_logit_penalty":gate["extra_dense_logit_penalty"],
        "equivalent_dense_prior":baseline["dense_prior"]-gate["extra_dense_logit_penalty"],
        "candidate_pool":"unchanged cap32 INT006","metrics":{},"provenance":{},
    }
    for fold in FOLDS:
        result["metrics"][fold]={}
        for slice_name in SLICES:
            result["metrics"][fold][slice_name]=_delta(
                baseline[fold][slice_name],gate[fold][slice_name])
    result["provenance"]["calibration"]=_provenance(report["selection_diagnostics"],"calibrate")
    result["provenance"]["holdout"]=_provenance(report["selection_diagnostics"],"holdout")
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    result=summarize(json.loads(args.input.read_text(encoding="utf-8")))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()
