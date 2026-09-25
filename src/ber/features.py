"""Language-agnostic comparison features; IDs and country labels are not predictors."""
import re
import os
from functools import lru_cache
import numpy as np
from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler


@lru_cache(maxsize=50000)
def parts(s):
    return frozenset(s.split()), frozenset(re.findall(r'\d+',s)), re.findall(r'\d+',s), s.replace(' ','')


def overlap(a,b):
    inter=len(a&b)
    return [inter/max(1,len(a|b)), inter/max(1,min(len(a),len(b))), inter/max(1,len(a)), inter/max(1,len(b))]


FEATURE_NAMES = []
for field in ('name','address'):
    FEATURE_NAMES += [f'{field}_{s}' for s in ('ratio','sorted_ratio','set_ratio','compact_ratio','jaro_winkler','exact',
        'left_len','right_len','len_ratio','token_jaccard','token_overlap','left_coverage','right_coverage',
        'number_jaccard','number_overlap','left_number_coverage','right_number_coverage',
        'first_number_equal','last_number_equal','number_conflict','left_missing','right_missing')]
FEATURE_NAMES += ['retrieval','key_hits','source']


def features(n1,a1,n2,a2,retrieval,hits,source):
    result=[]
    for l,r in ((n1,n2),(a1,a2)):
        tl,nl,dl,cl=parts(l)
        tr,nr,dr,cr=parts(r)
        result.extend([fuzz.ratio(l,r)/100,fuzz.token_sort_ratio(l,r)/100,
            fuzz.token_set_ratio(l,r)/100,fuzz.ratio(cl,cr)/100,
            JaroWinkler.normalized_similarity(l,r),float(l==r and bool(l)),
            len(l),len(r),min(len(l),len(r))/max(1,len(l),len(r)),
            *overlap(tl,tr),*overlap(nl,nr),
            float(bool(dl and dr) and dl[0]==dr[0]),float(bool(dl and dr) and dl[-1]==dr[-1]),
            float(bool(nl and nr) and not nl&nr),float(not l),float(not r)])
    return result+[retrieval,hits,source]


def batch_features(records):
    if os.environ.get('BER_FAST_FEATURES')=='1':
        from ._fast_features import batch
        return np.frombuffer(batch(records),dtype=np.float32).reshape(-1,len(FEATURE_NAMES))
    return np.asarray([features(*r) for r in records],dtype=np.float32)
