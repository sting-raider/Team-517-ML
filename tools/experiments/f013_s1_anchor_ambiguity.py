#!/usr/bin/env python3
import argparse, json, time, unicodedata
from pathlib import Path
import numpy as np
import pandas as pd
import regex

NONALNUM = regex.compile(r'[^\p{L}\p{N}]+')
MARKS = regex.compile(r'\p{M}+')

# Close semantic mirror of latest-main DuckDB norm(): lower(strip_accents(coalesce(s,''))),
# non-letter/digit -> space, trim. NFD mark removal preserves non-Latin letters.
def norm_text(s: str) -> str:
    if not s:
        return ''
    s = unicodedata.normalize('NFD', str(s))
    s = MARKS.sub('', s)
    return NONALNUM.sub(' ', s.lower()).strip()

def hseries(s: pd.Series) -> np.ndarray:
    return pd.util.hash_pandas_object(s, index=False).to_numpy(dtype=np.uint64, copy=False)

def hpair(a: pd.Series, b: pd.Series) -> np.ndarray:
    return pd.util.hash_pandas_object(pd.DataFrame({'a':a, 'b':b}), index=False).to_numpy(dtype=np.uint64, copy=False)

def load_truth(path: Path, chunksize=250_000):
    hs=[]; cards=[]; pres=[]
    t0=time.time(); rows=0
    for df in pd.read_csv(path, sep='\t', dtype=str, keep_default_na=False, chunksize=chunksize):
        m=df['matched_entity_ids']
        card=np.where(m.eq('').to_numpy(),0,(m.str.count(',')+1).to_numpy()).astype(np.int16)
        s2=m.str.contains('S2-', regex=False).to_numpy()
        s3=m.str.contains('S3-', regex=False).to_numpy()
        presence=(s2.astype(np.uint8)+2*s3.astype(np.uint8))
        hs.append(hseries(df['source1_entity_id'])); cards.append(card); pres.append(presence); rows+=len(df)
    h=np.concatenate(hs); card=np.concatenate(cards); presence=np.concatenate(pres)
    order=np.argsort(h)
    h=h[order]; card=card[order]; presence=presence[order]
    if len(np.unique(h)) != len(h):
        raise RuntimeError('truth anchor 64-bit hash collision or duplicate ID detected')
    return h, card, presence, {'rows':int(rows),'seconds':time.time()-t0}

def truth_lookup(ids: pd.Series, th, tcard, tpres):
    ih=hseries(ids)
    pos=np.searchsorted(th, ih)
    if np.any(pos>=len(th)) or np.any(th[pos]!=ih):
        raise RuntimeError('missing truth anchor or entity-id hash mismatch')
    return tcard[pos], tpres[pos]

def load_s1(path: Path, truth=None, chunksize=100_000):
    cols={'country':[], 'n':[], 'a':[], 'j':[], 'rawj':[], 'card':[], 'presence':[]}
    t0=time.time(); rows=0
    for df in pd.read_csv(path, sep='\t', dtype=str, keep_default_na=False, chunksize=chunksize):
        n=df['business_name'].map(norm_text)
        a=df['business_address'].map(norm_text)
        cols['country'].append(df['country'].to_numpy(dtype=str))
        cols['n'].append(hseries(n)); cols['a'].append(hseries(a)); cols['j'].append(hpair(n,a))
        cols['rawj'].append(hpair(df['business_name'], df['business_address']))
        if truth is not None:
            card,pres=truth_lookup(df['entity_id'], *truth)
            cols['card'].append(card); cols['presence'].append(pres)
        rows += len(df)
    out={k:np.concatenate(v) for k,v in cols.items() if v}
    return out, {'rows':int(rows),'seconds':time.time()-t0}

def collision_stats(keys: np.ndarray):
    _, inv, counts=np.unique(keys, return_inverse=True, return_counts=True)
    row_counts=counts[inv]
    cc=counts[counts>1]
    if len(cc):
        qs=np.quantile(cc,[.5,.9,.99],method='linear')
        pairs=int(np.sum((cc.astype(np.int64)*(cc.astype(np.int64)-1))//2))
        return {
            'groups':int(len(cc)), 'affected_anchors':int(np.sum(row_counts>1)),
            'affected_rate':float(np.mean(row_counts>1)), 'collision_pairs':pairs,
            'group_size_p50':float(qs[0]), 'group_size_p90':float(qs[1]), 'group_size_p99':float(qs[2]),
            'group_size_max':int(cc.max())
        }, row_counts>1
    return {'groups':0,'affected_anchors':0,'affected_rate':0.0,'collision_pairs':0,'group_size_p50':0.0,'group_size_p90':0.0,'group_size_p99':0.0,'group_size_max':0}, np.zeros(len(keys),dtype=bool)

def norm_induced_stats(normj: np.ndarray, rawj: np.ndarray):
    # Compute pairs introduced by normalization and groups containing >1 distinct raw representation.
    d=pd.DataFrame({'n':normj,'r':rawj})
    norm_counts=d['n'].value_counts(sort=False)
    raw_counts=d['r'].value_counts(sort=False)
    raw_distinct=d.drop_duplicates(['n','r']).groupby('n',sort=False)['r'].size()
    induced=raw_distinct[raw_distinct>1].index
    induced_counts=norm_counts.reindex(induced).fillna(0).astype(np.int64)
    norm_pairs=((norm_counts[norm_counts>1].astype(np.int64)*(norm_counts[norm_counts>1].astype(np.int64)-1))//2).sum()
    raw_pairs=((raw_counts[raw_counts>1].astype(np.int64)*(raw_counts[raw_counts>1].astype(np.int64)-1))//2).sum()
    return {
        'normalization_induced_groups':int(len(induced)),
        'anchors_in_induced_groups':int(induced_counts.sum()),
        'anchors_in_induced_groups_rate':float(induced_counts.sum()/len(d)),
        'normalization_added_collision_pairs':int(norm_pairs-raw_pairs),
        'raw_exact_collision_pairs':int(raw_pairs),
        'normalized_collision_pairs':int(norm_pairs),
    }

def label_stats(card: np.ndarray, presence: np.ndarray, mask: np.ndarray):
    c=card[mask]; p=presence[mask]
    n=len(c)
    if n==0: return {'anchors':0}
    binc=np.bincount(c.astype(np.int64), minlength=12)
    return {
        'anchors':int(n), 'singleton_count':int(np.sum(c==0)), 'singleton_rate':float(np.mean(c==0)),
        'mean_truth_cardinality':float(np.mean(c)), 'high_cardinality_ge5_rate':float(np.mean(c>=5)),
        'cardinality_distribution':{str(i):int(x) for i,x in enumerate(binc) if x},
        'source_presence':{
            'none':int(np.sum(p==0)), 's2_only':int(np.sum(p==1)), 's3_only':int(np.sum(p==2)), 'both':int(np.sum(p==3))
        }
    }

def analyze_split(data, with_labels=False):
    out={'rows':int(len(data['country'])),'countries':{}}
    for country in sorted(np.unique(data['country'])):
        cm=data['country']==country
        cdat={k:v[cm] for k,v in data.items() if k!='country'}
        co={'rows':int(np.sum(cm)), 'collisions':{}}
        flags={}
        for label,key in [('normalized_name','n'),('normalized_address','a'),('normalized_joint','j'),('raw_exact_joint','rawj')]:
            s,f=collision_stats(cdat[key]); co['collisions'][label]=s; flags[label]=f
        co['normalization_effect']=norm_induced_stats(cdat['j'],cdat['rawj'])
        if with_labels:
            name_amb=flags['normalized_name']; address_amb=flags['normalized_address']
            co['labels']={
              'joint_ambiguous':label_stats(cdat['card'],cdat['presence'],flags['normalized_joint']),
              'joint_unambiguous':label_stats(cdat['card'],cdat['presence'],~flags['normalized_joint']),
              'raw_joint_ambiguous':label_stats(cdat['card'],cdat['presence'],flags['raw_exact_joint']),
              'name_ambiguous':label_stats(cdat['card'],cdat['presence'],name_amb),
              'name_unambiguous':label_stats(cdat['card'],cdat['presence'],~name_amb),
              'address_ambiguous':label_stats(cdat['card'],cdat['presence'],address_amb),
              'address_unambiguous':label_stats(cdat['card'],cdat['presence'],~address_amb),
              'both_field_ambiguous':label_stats(cdat['card'],cdat['presence'],name_amb & address_amb),
              'name_only_ambiguous':label_stats(cdat['card'],cdat['presence'],name_amb & ~address_amb),
              'address_only_ambiguous':label_stats(cdat['card'],cdat['presence'],~name_amb & address_amb),
              'neither_field_ambiguous':label_stats(cdat['card'],cdat['presence'],~name_amb & ~address_amb),
            }
        out['countries'][country]=co
    # overall uses country-local ambiguity: union flags computed independently by country
    overall_joint=np.zeros(len(data['country']),dtype=bool)
    overall_raw=np.zeros(len(data['country']),dtype=bool)
    for country in np.unique(data['country']):
        idx=np.flatnonzero(data['country']==country)
        _,jf=collision_stats(data['j'][idx]); _,rf=collision_stats(data['rawj'][idx])
        overall_joint[idx]=jf; overall_raw[idx]=rf
    out['overall_country_local_joint_affected_anchors']=int(overall_joint.sum())
    out['overall_country_local_joint_affected_rate']=float(overall_joint.mean())
    out['overall_country_local_raw_joint_affected_anchors']=int(overall_raw.sum())
    out['overall_country_local_raw_joint_affected_rate']=float(overall_raw.mean())
    if with_labels:
        out['overall_labels']={
          'joint_ambiguous':label_stats(data['card'],data['presence'],overall_joint),
          'joint_unambiguous':label_stats(data['card'],data['presence'],~overall_joint),
          'raw_joint_ambiguous':label_stats(data['card'],data['presence'],overall_raw),
        }
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--train-source1',type=Path,required=True); ap.add_argument('--truth',type=Path,required=True); ap.add_argument('--test-source1',type=Path,required=True); ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args(); t0=time.time()
    th,tcard,tpres,tmeta=load_truth(args.truth)
    train,trainmeta=load_s1(args.train_source1,(th,tcard,tpres))
    test,testmeta=load_s1(args.test_source1,None)
    result={
      'method':{'normalization':'Unicode NFD combining-mark removal + lowercase + Unicode letter/number punctuation collapse; semantic mirror of DuckDB strip_accents norm, not byte-for-byte DuckDB execution','hashing':'pandas deterministic uint64 hashes for grouping; duplicate entity-id hash guard on truth'},
      'input':{'truth':tmeta,'train_source1':trainmeta,'test_source1':testmeta},
      'train':analyze_split(train,True),'test':analyze_split(test,False),
      'runtime_seconds':time.time()-t0
    }
    args.out.parent.mkdir(parents=True,exist_ok=True); args.out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
if __name__=='__main__': main()
