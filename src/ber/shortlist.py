"""Cheap lexical candidate filtering, before the learned matching stage."""
import numpy as np
from rapidfuzz import fuzz


def budgets(cap):
    side=max(1,min(8,cap//6))
    return cap-2*side,side


def shortlist_mask(groups,targets,name,address,missing_address,cap):
    combined=np.where(missing_address,.9*name,.55*name+.45*address)
    main,side=budgets(cap)
    keep=np.bincount(groups)[groups]<=cap
    for scores,k in ((combined,main),(name,side),(address,side)):
        order=np.lexsort((targets,-scores,groups))
        starts=np.r_[0,np.flatnonzero(np.diff(groups[order]))+1]
        lengths=np.diff(np.r_[starts,len(order)])
        ranks=np.arange(len(order))-np.repeat(starts,lengths)
        keep[order[ranks<k]]=True
    return keep


def shortlist_rows(rows,cap):
    if cap is None or len(rows)<=cap:
        return rows
    main,side=budgets(cap)
    scores=[]
    for row in rows:
        _,target,n1,a1,n2,a2,*_=row
        n=(np.float32(fuzz.ratio(n1,n2)/100)+np.float32(fuzz.token_set_ratio(n1,n2)/100))/np.float32(2)
        a=(np.float32(fuzz.ratio(a1,a2)/100)+np.float32(fuzz.token_set_ratio(a1,a2)/100))/np.float32(2)
        mixed=.9*n if not a1 or not a2 else .55*n+.45*a
        scores.append((mixed,n,a,target))
    selected=set()
    for column,k in ((0,main),(1,side),(2,side)):
        order=sorted(range(len(rows)),key=lambda i:(-scores[i][column],scores[i][3]))
        selected.update(order[:k])
    return [r for i,r in enumerate(rows) if i in selected]
