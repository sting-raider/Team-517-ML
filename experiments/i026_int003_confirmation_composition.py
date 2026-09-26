#!/usr/bin/env python3
"""Full-population composition audit for INT003's consumed confirmation window."""
from __future__ import annotations

import argparse, csv, hashlib, heapq, json, math, time
from collections import Counter
from pathlib import Path

WINDOW_START, WINDOW_END = 45_000, 50_000
EXPECTED = {"entities":5000,"India":2022,"US":2978,"singletons":262,"India_singletons":114,"US_singletons":148}

def parse_truth_count(value: str) -> int:
    return 0 if not value else value.count(",") + 1

def sample_key(entity_id: str) -> int:
    return int(hashlib.md5(("sample517:" + entity_id).encode()).hexdigest(), 16)

class Agg:
    def __init__(self):
        self.n=0; self.country=Counter(); self.singletons=0; self.card=Counter()
        self.sum_card=self.sum_card2=0.0; self.name_missing=self.address_missing=0
        self.sums={k:[0.0,0.0] for k in ("name_len","address_len","name_tokens","address_tokens")}
    def add(self,country,name,address,truth_count):
        name,address=name or "",address or ""; self.n+=1; self.country[country]+=1
        self.singletons += truth_count==0; self.card[min(truth_count,5)] += 1
        self.sum_card += truth_count; self.sum_card2 += truth_count*truth_count
        self.name_missing += name==""; self.address_missing += address==""
        vals={"name_len":len(name),"address_len":len(address),"name_tokens":len(name.split()),"address_tokens":len(address.split())}
        for k,v in vals.items(): self.sums[k][0]+=v; self.sums[k][1]+=v*v
    def summary(self):
        n=self.n
        if not n: return {"n":0}
        def ms(k):
            s,s2=self.sums[k]; m=s/n
            return {"mean":m,"sd":math.sqrt(max(0.0,s2/n-m*m))}
        mc=self.sum_card/n
        return {
            "n":n,"country_counts":dict(self.country),"country_share":{k:v/n for k,v in self.country.items()},
            "singleton_count":self.singletons,"singleton_rate":self.singletons/n,
            "mean_truth_cardinality":mc,"truth_cardinality_sd":math.sqrt(max(0.0,self.sum_card2/n-mc*mc)),
            "truth_cardinality_distribution":{("5+" if k==5 else str(k)):self.card[k]/n for k in range(6)},
            "name_missing_rate":self.name_missing/n,"address_missing_rate":self.address_missing/n,
            **{k:ms(k) for k in self.sums},
        }

def z_prop(p,p0,n):
    if not n or not 0<p0<1: return 0.0
    return (p-p0)/math.sqrt(p0*(1-p0)/n)

def effects(sample,population,sbc,pbc):
    out={}
    for metric in ("singleton_rate","name_missing_rate","address_missing_rate"):
        out[metric]={"delta_pp":100*(sample[metric]-population[metric]),"z_hash_random":z_prop(sample[metric],population[metric],sample["n"])}
    for country in ("US","India"):
        p,p0=sample["country_share"][country],population["country_share"][country]
        out[f"country_share.{country}"]={"delta_pp":100*(p-p0),"z_hash_random":z_prop(p,p0,sample["n"])}
        p,p0=sbc[country]["singleton_rate"],pbc[country]["singleton_rate"]
        out[f"singleton_rate.{country}"]={"delta_pp":100*(p-p0),"z_hash_random":z_prop(p,p0,sbc[country]["n"])}
    for bucket,p0 in population["truth_cardinality_distribution"].items():
        p=sample["truth_cardinality_distribution"][bucket]
        out[f"cardinality.{bucket}"]={"delta_pp":100*(p-p0),"z_hash_random":z_prop(p,p0,sample["n"])}
    delta=sample["mean_truth_cardinality"]-population["mean_truth_cardinality"]
    out["mean_truth_cardinality"]={"delta":delta,"smd":delta/population["truth_cardinality_sd"]}
    for metric in ("name_len","address_len","name_tokens","address_tokens"):
        delta=sample[metric]["mean"]-population[metric]["mean"]
        out[f"{metric}.mean"]={"delta":delta,"smd":delta/population[metric]["sd"]}
    return out

def audit(source1: Path, truth_path: Path):
    started=time.time(); truth={}
    with truth_path.open("r",encoding="utf-8",newline="") as h:
        for row in csv.DictReader(h,delimiter="\t"):
            eid=row["source1_entity_id"]
            if eid in truth: raise RuntimeError(f"duplicate truth id: {eid}")
            truth[eid]=parse_truth_count(row.get("matched_entity_ids",""))
    population=Agg(); pbc={"US":Agg(),"India":Agg()}; pis=Agg(); heap=[]; rows=0
    with source1.open("r",encoding="utf-8",newline="") as h:
        for row in csv.DictReader(h,delimiter="\t"):
            rows+=1; eid=row["entity_id"]
            if eid not in truth: raise RuntimeError(f"Source-1 id missing truth row: {eid}")
            tc=truth[eid]; country=row.get("country","") or ""; name=row.get("business_name","") or ""; address=row.get("business_address","") or ""
            population.add(country,name,address,tc)
            if country in pbc: pbc[country].add(country,name,address,tc)
            if country=="India" and tc==0: pis.add(country,name,address,tc)
            key=sample_key(eid); item=(-key,eid,country,name,address,tc)
            if len(heap)<WINDOW_END: heapq.heappush(heap,item)
            elif key < -heap[0][0]: heapq.heapreplace(heap,item)
    if rows!=len(truth): raise RuntimeError(f"Source-1/truth row mismatch: {rows} vs {len(truth)}")
    prefix=sorted([(-n,e,c,na,a,t) for n,e,c,na,a,t in heap],key=lambda x:(x[0],x[1]))
    sample=Agg(); sbc={"US":Agg(),"India":Agg()}; sis=Agg()
    for _,_,country,name,address,tc in prefix[WINDOW_START:WINDOW_END]:
        sample.add(country,name,address,tc)
        if country in sbc: sbc[country].add(country,name,address,tc)
        if country=="India" and tc==0: sis.add(country,name,address,tc)
    p,s=population.summary(),sample.summary(); pbc={k:v.summary() for k,v in pbc.items()}; sbc={k:v.summary() for k,v in sbc.items()}
    pis,sis=pis.summary(),sis.summary()
    observed={"entities":s["n"],"India":s["country_counts"].get("India",0),"US":s["country_counts"].get("US",0),
              "singletons":s["singleton_count"],"India_singletons":sbc["India"]["singleton_count"],"US_singletons":sbc["US"]["singleton_count"]}
    parity={k:observed[k]==v for k,v in EXPECTED.items()}
    ise={}
    for metric in ("name_missing_rate","address_missing_rate"):
        ise[metric]={"delta_pp":100*(sis[metric]-pis[metric]),"z_hash_random":z_prop(sis[metric],pis[metric],sis["n"])}
    for metric in ("name_len","address_len","name_tokens","address_tokens"):
        delta=sis[metric]["mean"]-pis[metric]["mean"]; ise[f"{metric}.mean"]={"delta":delta,"smd":delta/pis[metric]["sd"]}
    return {
        "experiment":"I026",
        "protocol":{"anchor_order":"md5('sample517:'||entity_id)","window_one_based":"45001:50000","window_zero_based":"[45000,50000)","complete_population":True,"no_new_holdout_consumed":True},
        "integrity":{"source1_rows":rows,"truth_rows":len(truth)},
        "committed_int003_parity":{"expected":EXPECTED,"observed":observed,"by_field":parity,"all_match":all(parity.values())},
        "population":p,"population_by_country":pbc,"int003_confirmation":s,"int003_by_country":sbc,
        "vs_population":effects(s,p,sbc,pbc),"india_singletons_population":pis,"india_singletons_window":sis,
        "india_singleton_vs_population":ise,"runtime_seconds":time.time()-started,
    }

def main():
    p=argparse.ArgumentParser(); p.add_argument("--source1",type=Path,required=True); p.add_argument("--truth",type=Path,required=True); p.add_argument("--out",type=Path,required=True)
    a=p.parse_args(); result=audit(a.source1,a.truth); a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps({"parity":result["committed_int003_parity"],"effects":result["vs_population"]},indent=2,sort_keys=True))

if __name__=="__main__": main()
