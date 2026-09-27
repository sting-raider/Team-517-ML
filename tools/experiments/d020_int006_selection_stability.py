"""D020: calibration-to-holdout stability audit for INT006 decision variants."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def ranks(rows, key):
    ordered=sorted(rows, key=lambda r:(-r[key], r["name"]))
    return {r["name"]:i+1 for i,r in enumerate(ordered)}

def spearman_no_ties(a,b):
    names=sorted(a)
    n=len(names)
    if n<2: return 1.0
    d2=sum((a[x]-b[x])**2 for x in names)
    return 1.0-(6.0*d2)/(n*(n*n-1))

def audit(obj):
    rows=[]
    for v in obj["variants"]:
        rows.append({
            "name":v["name"],
            "dense_prior":v.get("dense_prior"),
            "threshold":v["threshold"],
            "calibration":v["calibration"]["all"]["macro_f0_5"],
            "holdout":v["holdout"]["all"]["macro_f0_5"],
            "calibration_india":v["calibration"]["India"]["macro_f0_5"],
            "holdout_india":v["holdout"]["India"]["macro_f0_5"],
            "calibration_us":v["calibration"]["US"]["macro_f0_5"],
            "holdout_us":v["holdout"]["US"]["macro_f0_5"],
            "calibration_singleton_fpr":v["calibration"]["all"]["singleton_false_positive_rate"],
            "holdout_singleton_fpr":v["holdout"]["all"]["singleton_false_positive_rate"],
        })
    cr=ranks(rows,"calibration"); hr=ranks(rows,"holdout")
    selected=next(r for r in rows if r["name"]==obj["selected"]["name"])
    hold_best=max(rows,key=lambda r:r["holdout"])
    india_best=max(rows,key=lambda r:r["holdout_india"])
    us_best=max(rows,key=lambda r:r["holdout_us"])
    return {
        "variant_count":len(rows),
        "calibration_rank":cr,
        "holdout_rank":hr,
        "spearman_rank_correlation":spearman_no_ties(cr,hr),
        "selected":selected,
        "selected_holdout_rank":hr[selected["name"]],
        "selected_holdout_regret":hold_best["holdout"]-selected["holdout"],
        "holdout_best":hold_best["name"],
        "india_holdout_best":india_best["name"],
        "india_selected_regret":india_best["holdout_india"]-selected["holdout_india"],
        "us_holdout_best":us_best["name"],
        "us_selected_regret":us_best["holdout_us"]-selected["holdout_us"],
        "selected_calibration_to_holdout_gap":selected["calibration"]-selected["holdout"],
        "rows":rows,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    result=audit(json.loads(a.input.read_text(encoding="utf-8")))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps(result,indent=2,sort_keys=True))
if __name__=="__main__":
    main()
