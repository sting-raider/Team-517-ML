#!/usr/bin/env python3
"""Dependency-light randomized red-team for M009 char n-gram pair features."""
from __future__ import annotations
import argparse
import json
import math
import random
import time
from pathlib import Path

from ber.features import (
    FEATURE_NAMES,
    batch_char_ngram_features,
    batch_features,
    char_ngram_features,
    features,
)

ALPHABET=list('abcde0123456789 -./')+['é','è','ç','ø','ñ','ü','ß','œ','\u0301']


def _grams(s,n):
    compact=s.replace(' ','')
    if not compact or len(compact)<n:
        return set()
    return {compact[i:i+n] for i in range(len(compact)-n+1)}


def _overlap(left,right,n):
    if not left or not right:
        return 0.0,0.0
    a,b=_grams(left,n),_grams(right,n)
    if not a or not b:
        return 0.0,0.0
    inter=len(a&b)
    return inter/len(a|b), inter/min(len(a),len(b))


def reference(n1,a1,n2,a2):
    out=[]
    for left,right in ((n1,n2),(a1,a2)):
        out.extend(_overlap(left,right,3))
        out.extend(_overlap(left,right,4))
    return out


def run(seed=517,reference_cases=50_000,benchmark_rows=20_000):
    rng=random.Random(seed)
    def rs(maxlen):
        return ''.join(rng.choice(ALPHABET) for _ in range(rng.randrange(maxlen+1)))
    max_error=0.0
    for i in range(reference_cases):
        args=(rs(30),rs(50),rs(30),rs(50))
        got=char_ngram_features(*args)
        expected=reference(*args)
        err=max(abs(a-b) for a,b in zip(got,expected))
        if err>1e-15:
            raise AssertionError((i,args,got,expected))
        if got!=char_ngram_features(args[2],args[3],args[0],args[1]):
            raise AssertionError(('asymmetry',i,args))
        max_error=max(max_error,err)
    for i in range(5000):
        row=(rs(30),rs(50),rs(30),rs(50),rng.random(),rng.randrange(10),rng.choice([2,3]))
        got=features(*row)
        if len(got)!=47 or not all(math.isfinite(float(x)) for x in got):
            raise AssertionError(('legacy',i,row,got))
    rows=[
        (rs(30),rs(50),rs(30),rs(50),rng.random(),rng.randrange(10),rng.choice([2,3]))
        for _ in range(benchmark_rows)
    ]
    started=time.perf_counter()
    legacy=batch_features(rows)
    legacy_s=time.perf_counter()-started
    started=time.perf_counter()
    char=batch_char_ngram_features(rows)
    char_s=time.perf_counter()-started
    return {
      'seed':seed,
      'reference_cases':reference_cases,
      'max_abs_error':max_error,
      'legacy_random_cases':5000,
      'legacy_width':len(FEATURE_NAMES),
      'benchmark_rows':benchmark_rows,
      'legacy47_seconds':legacy_s,
      'legacy47_pairs_per_second':benchmark_rows/legacy_s,
      'char8_seconds':char_s,
      'char8_pairs_per_second':benchmark_rows/char_s,
      'serial_combined_over_legacy_ratio':(legacy_s+char_s)/legacy_s,
      'char_shape':list(char.shape),
      'char_dtype':str(char.dtype),
      'char_min':float(char.min()),
      'char_max':float(char.max()),
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',type=Path)
    a=p.parse_args()
    result=run()
    rendered=json.dumps(result,indent=2)
    if a.out:
        a.out.parent.mkdir(parents=True,exist_ok=True)
        a.out.write_text(rendered,encoding='utf-8')
    print(rendered)


if __name__=='__main__':
    main()
