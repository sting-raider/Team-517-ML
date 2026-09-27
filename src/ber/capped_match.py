"""Evaluate the exact 32-pair dense/lexical candidate pool end to end."""
import json
import time
from pathlib import Path

import numpy as np

from .dense_training import serialize


def compose_dense_gate_blank_recovery(chosen_logits, dense, threshold,
                                      extra_dense_logit_penalty,
                                      recovery_eligible):
    """Compose a fixed dense-only penalty with post-gate blank-name recovery.

    Recovery is applied to the *gated* decision set. This is intentionally not
    equivalent to adding the independently measured macro deltas: an eligible
    pair removed by the dense gate is re-added by recovery.
    """
    chosen_logits=np.asarray(chosen_logits,dtype=np.float64)
    dense=np.asarray(dense,dtype=bool)
    recovery_eligible=np.asarray(recovery_eligible,dtype=bool)
    if chosen_logits.shape!=dense.shape or chosen_logits.shape!=recovery_eligible.shape:
        raise ValueError('Dense-gate composition arrays must have identical shapes')
    if not 0.<threshold<1.:
        raise ValueError('threshold must be strictly between zero and one')
    cutoff=np.log(threshold/(1.-threshold))
    base_selected=chosen_logits>=cutoff
    gated_logits=chosen_logits-np.where(dense,extra_dense_logit_penalty,0.)
    gated_selected=gated_logits>=cutoff
    recovered=recovery_eligible&~gated_selected
    final_selected=gated_selected|recovered
    readded_gate_removed=recovered&base_selected&~gated_selected
    return {
        'gated_logits':gated_logits,
        'base_selected':base_selected,
        'gated_selected':gated_selected,
        'recovered':recovered,
        'readded_gate_removed':readded_gate_removed,
        'final_selected':final_selected,
    }


def score_dense_only(db, pair_path, model_path, out):
    import duckdb
    import torch
    from transformers import AutoModelForSequenceClassification,AutoTokenizer

    pairs=[]
    with Path(pair_path).open(encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line)
            if row['dense_only']:
                pairs.append((row['anchor'],row['target']))
    needed=sorted({i for pair in pairs for i in pair})
    c=duckdb.connect(str(db),read_only=True)
    c.execute('CREATE TEMP TABLE needed AS SELECT unnest(?) entity_id',[needed])
    records={i:serialize(n,a) for i,n,a in c.execute('''SELECT t.entity_id,t.business_name,
        t.business_address FROM train t JOIN needed x USING(entity_id)''').fetchall()}
    if len(records)!=len(needed):
        raise ValueError('Missing dense-only candidate record')
    tokenizer=AutoTokenizer.from_pretrained(model_path)
    model=AutoModelForSequenceClassification.from_pretrained(model_path).eval().cuda()
    torch.set_num_threads(4)
    scores=np.empty(len(pairs),np.float32)
    started=time.monotonic()
    with torch.inference_mode():
        for start in range(0,len(pairs),128):
            rows=pairs[start:start+128]
            inputs=tokenizer([records[a] for a,_ in rows],
                             [records[t] for _,t in rows],padding=True,truncation=True,
                             max_length=160,return_tensors='pt').to('cuda')
            with torch.autocast('cuda',dtype=torch.bfloat16):
                scores[start:start+len(rows)]=model(**inputs).logits.squeeze(-1).float().cpu().numpy()
    Path(out).parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(out,anchor=np.array([a for a,_ in pairs]),
                        target=np.array([t for _,t in pairs]),logit=scores)
    return {'pairs':len(pairs),'seconds':time.monotonic()-started,
            'country_fold':str(pair_path),'out':str(out)}


def evaluate_capped_match(baseline, retrieval_root, cross_root, dense_score_root, out,
                          scheme='capped',ownership_root=None,owner_cross_root=None,
                          record_db=None):
    from .experiment import choose_threshold
    from .v2 import score_slices

    baseline=Path(baseline)
    meta=json.loads((baseline/'anchors.json').read_text())
    byid={m['id']:i for i,m in enumerate(meta)}
    with np.load(baseline/'evaluation.npz') as z:
        base_g,base_t,base_p=(z[k] for k in ('groups','target','prob'))
    base_logit=np.full(len(base_g),np.nan,np.float32)
    for fold in ('calibrate','holdout'):
        for part in range(8):
            with np.load(Path(cross_root)/f'{fold}_part{part}.npz') as z:
                base_logit[z['indices']]=z['logits']
    selected={}
    for country in ('India','US'):
        for fold,prefix in [('calibrate','cal'),('holdout','hold')]:
            path=Path(retrieval_root)/country/f'{scheme}_{prefix}_pairs.jsonl'
            if not path.exists():
                raise FileNotFoundError(path)
            with path.open(encoding='utf-8') as stream:
                for line in stream:
                    row=json.loads(line)
                    selected[row['anchor'],row['target']]=row['dense_only']
    values={}
    for g,t,p,logit in zip(base_g,base_t,base_p,base_logit):
        anchor=meta[int(g)]['id'];target=str(t)
        if (anchor,target) in selected and not selected[anchor,target]:
            if not np.isfinite(logit):
                raise ValueError('Missing cross score on retained v3 candidate')
            values[anchor,target]=(float(p),float(logit))
    for country in ('India','US'):
        for prefix in ('cal','hold'):
            path=Path(dense_score_root)/f'{country}_{prefix}.npz'
            with np.load(path) as z:
                for anchor,target,logit in zip(z['anchor'],z['target'],z['logit']):
                    pair=(str(anchor),str(target))
                    if pair in values:
                        raise ValueError('Dense-only candidate duplicated baseline')
                    values[pair]=(None,float(logit))
    if len(values)!=len(selected):
        raise ValueError(f'Incomplete capped scores: {len(values)} vs {len(selected)}')
    keys=list(selected)
    groups=np.array([byid[a] for a,_ in keys],np.int32)
    targets=np.array([t for _,t in keys])
    dense=np.array([selected[k] for k in keys],bool)
    cross=np.array([values[k][1] for k in keys],np.float32)
    cat=np.array([values[k][0] if not selected[k] else .5 for k in keys],np.float32)
    oldlogit=np.log(np.clip(cat,1e-7,1-1e-7)/(1-np.clip(cat,1e-7,1-1e-7)))
    cal=[i for i,m in enumerate(meta) if m['fold']=='calibrate']
    variants=[]
    for name,beta in [('cross_only',None),('dense_prior_-2',-2.),
                      ('dense_prior_-1',-1.),('dense_prior_0',0.),
                      ('dense_prior_1',1.)]:
        logits=cross if beta is None else oldlogit+cross+np.where(dense,beta,0.)
        probability=1/(1+np.exp(-np.clip(logits,-30,30)))
        threshold,_=choose_threshold(meta,groups,targets,probability,cal)
        variants.append({'name':name,'dense_prior':beta,'threshold':threshold,
                         'calibration':score_slices(meta,groups,targets,probability,'calibrate',threshold),
                         'holdout':score_slices(meta,groups,targets,probability,'holdout',threshold)})
    best=max(variants,key=lambda r:r['calibration']['all']['macro_f0_5'])
    best_prior=best['dense_prior']
    chosen_logits=(cross if best_prior is None else
                   oldlogit+cross+np.where(dense,best_prior,0.))
    chosen=chosen_logits>=np.log(best['threshold']/(1-best['threshold']))
    truth=np.array([t in meta[int(g)]['truth'] for g,t in zip(groups,targets)],bool)
    diagnostics={}
    for fold_name in ('calibrate','holdout'):
        for country in ('India','US'):
            entity_mask=np.array([m['fold']==fold_name and m['country']==country
                                  for m in meta],bool)
            in_slice=entity_mask[groups]
            for channel,channel_mask in [('dense_only',dense),('lexical',~dense)]:
                mask=in_slice&channel_mask
                predicted=mask&chosen
                true_positive=int(np.count_nonzero(predicted&truth))
                count=int(np.count_nonzero(predicted))
                diagnostics[f'{fold_name}_{country}_{channel}']={
                    'candidates':int(np.count_nonzero(mask)),
                    'predicted':count,'true_positive':true_positive,
                    'false_positive':count-true_positive,
                    'selected_pair_precision':true_positive/count if count else None}
    report={'protocol':'Exact dense top16 plus top v3 lexical/character candidates, cap32; complete train target inventory; cross-encoder scores all selected pairs; threshold chosen calibration only',
            'scheme':scheme,
            'pairs':len(keys),'dense_only_pairs':int(dense.sum()),
            'variants':variants,'selected':best,
            'selection_diagnostics':diagnostics}
    dense_gates=[]
    for extra_penalty in (-1.,0.,.5,1.,1.5,2.,3.):
        gated_logits=chosen_logits-np.where(dense,extra_penalty,0.)
        gated_prob=1/(1+np.exp(-np.clip(gated_logits,-30,30)))
        dense_gates.append({
            'extra_dense_logit_penalty':extra_penalty,
            'calibration':score_slices(meta,groups,targets,gated_prob,
                                       'calibrate',best['threshold']),
            'holdout':score_slices(meta,groups,targets,gated_prob,
                                   'holdout',best['threshold'])})
    report['dense_gate_sweep']=dense_gates
    report['dense_gate_selected']=max(
        dense_gates,key=lambda row:row['calibration']['all']['macro_f0_5'])
    budget={}
    for fold_name in ('calibrate','holdout'):
        fold_entities=np.array([m['fold']==fold_name for m in meta],bool)
        fold_pairs=fold_entities[groups]
        for country in ('India','US'):
            entity_mask=fold_entities & np.array([m['country']==country for m in meta],bool)
            pair_mask=entity_mask[groups]
            budget[f'{fold_name}_{country}']={
                'entities':int(np.count_nonzero(entity_mask)),
                'truth_links':sum(len(meta[i]['truth']) for i in np.flatnonzero(entity_mask)),
                'retrieved_true_links':int(np.count_nonzero(pair_mask&truth)),
                'predicted_true_links':int(np.count_nonzero(pair_mask&truth&chosen)),
                'predicted_false_links':int(np.count_nonzero(pair_mask&~truth&chosen)),
                'missed_true_inside_candidates':int(np.count_nonzero(pair_mask&truth&~chosen))}
        budget[f'{fold_name}_all']={
            'entities':int(np.count_nonzero(fold_entities)),
            'truth_links':sum(len(meta[i]['truth']) for i in np.flatnonzero(fold_entities)),
            'retrieved_true_links':int(np.count_nonzero(fold_pairs&truth)),
            'predicted_true_links':int(np.count_nonzero(fold_pairs&truth&chosen)),
            'predicted_false_links':int(np.count_nonzero(fold_pairs&~truth&chosen)),
            'missed_true_inside_candidates':int(np.count_nonzero(fold_pairs&truth&~chosen))}
    report['error_budget']=budget
    cat_rescue=[]
    for minimum in (.9,.95,.98,.99,.995,.999):
        added=(~chosen)&(~dense)&(cat>=minimum)
        adjusted=1/(1+np.exp(-np.clip(chosen_logits,-30,30)))
        adjusted[added]=1.
        counts={}
        for fold_name in ('calibrate','holdout'):
            fold_mask=np.array([m['fold']==fold_name for m in meta],bool)[groups]
            counts[fold_name]={
                'added_true_edges':int(np.count_nonzero(added&truth&fold_mask)),
                'added_false_edges':int(np.count_nonzero(added&~truth&fold_mask))}
        cat_rescue.append({
            'minimum_cat_probability':minimum,'counts':counts,
            'calibration':score_slices(meta,groups,targets,adjusted,'calibrate',best['threshold']),
            'holdout':score_slices(meta,groups,targets,adjusted,'holdout',best['threshold'])})
    report['catboost_veto_rescue']=cat_rescue
    if ownership_root is not None:
        owner_scores={}
        best_owner={}
        for fold_name in ('calibrate','holdout'):
            path=Path(ownership_root)/fold_name/'pair_scores.npz'
            with np.load(path) as z:
                for target,owner,similarity in zip(z['target'],z['owner'],z['dense']):
                    target=str(target);owner=str(owner);similarity=float(similarity)
                    owner_scores[target,owner]=similarity
                    best_owner[target]=max(best_owner.get(target,-2.),similarity)
        known=np.array([(key[1],key[0]) in owner_scores for key in keys],bool)
        removed=np.array([bool(chosen[i] and known[i] and
            best_owner[key[1]]>owner_scores[key[1],key[0]]+.05+1e-7)
            for i,key in enumerate(keys)],bool)
        adjusted=1/(1+np.exp(-np.clip(chosen_logits,-30,30)))
        adjusted[removed]=0.
        removal={}
        for fold_name in ('calibrate','holdout'):
            fold_mask=np.array([m['fold']==fold_name for m in meta],bool)[groups]
            removal[fold_name]={
                'predicted_with_reverse_scores':int(np.count_nonzero(chosen&known&fold_mask)),
                'predicted_without_reverse_scores':int(np.count_nonzero(chosen&~known&fold_mask)),
                'removed_true_edges':int(np.count_nonzero(removed&truth&fold_mask)),
                'removed_false_edges':int(np.count_nonzero(removed&~truth&fold_mask))}
        report['owner_filter']={
            'protocol':'Frozen D017 full-S1 reverse retrieval; dense margin .05; preserve v5 predictions absent from D017 target cache; v5 threshold unchanged',
            'removal':removal,
            'calibration':score_slices(meta,groups,targets,adjusted,'calibrate',best['threshold']),
            'holdout':score_slices(meta,groups,targets,adjusted,'holdout',best['threshold'])}
    if owner_cross_root is not None:
        cross_owner={}
        best_cross={}
        for fold_name in ('calibrate','holdout'):
            path=Path(owner_cross_root)/f'{fold_name}.npz'
            with np.load(path) as z:
                for target,owner,logit in zip(z['target'],z['owner'],z['logit']):
                    target=str(target);owner=str(owner);logit=float(logit)
                    cross_owner[target,owner]=logit
                    best_cross[target]=max(best_cross.get(target,-float('inf')),logit)
        known=np.array([(key[1],key[0]) in cross_owner for key in keys],bool)
        owner_variants=[]
        for margin in (0.,.5,1.,2.,3.,4.):
            removed=np.array([bool(chosen[i] and known[i] and
                best_cross[key[1]]>cross_owner[key[1],key[0]]+margin+1e-7)
                for i,key in enumerate(keys)],bool)
            adjusted=1/(1+np.exp(-np.clip(chosen_logits,-30,30)))
            adjusted[removed]=0.
            removal={}
            for fold_name in ('calibrate','holdout'):
                fold_mask=np.array([m['fold']==fold_name for m in meta],bool)[groups]
                removal[fold_name]={
                    'predicted_with_cross_owner_score':int(np.count_nonzero(chosen&known&fold_mask)),
                    'predicted_without_cross_owner_score':int(np.count_nonzero(chosen&~known&fold_mask)),
                    'removed_true_edges':int(np.count_nonzero(removed&truth&fold_mask)),
                    'removed_false_edges':int(np.count_nonzero(removed&~truth&fold_mask))}
            owner_variants.append({
                'margin':margin,'removal':removal,
                'calibration':score_slices(meta,groups,targets,adjusted,'calibrate',best['threshold']),
                'holdout':score_slices(meta,groups,targets,adjusted,'holdout',best['threshold'])})
        report['cross_owner_variants']=owner_variants
        report['cross_owner_selected']=max(
            owner_variants,key=lambda row:row['calibration']['all']['macro_f0_5'])
    if record_db is not None:
        import duckdb
        c=duckdb.connect(str(record_db),read_only=True)
        error_indices=np.flatnonzero(chosen!=truth)
        needed=sorted(set(map(str,targets))|{anchor for anchor,_ in keys})
        c.execute('CREATE TEMP TABLE needed_targets AS SELECT unnest(?) entity_id',[needed])
        records={identifier:(name,address) for identifier,name,address in
                 c.execute('''SELECT t.entity_id,t.n,t.a FROM train t
                     JOIN needed_targets n USING(entity_id)''').fetchall()}
        if len(records)!=len(needed):
            raise ValueError('Missing target record for exact-cluster audit')
        selected_groups=set()
        group_key=[]
        for i,(anchor,target) in enumerate(keys):
            name,address=records[target]
            key=(anchor,name,address) if name and address else None
            group_key.append(key)
            if chosen[i] and key is not None:
                selected_groups.add(key)
        added=np.array([key is not None and key in selected_groups and not chosen[i]
                        for i,key in enumerate(group_key)],bool)
        adjusted=1/(1+np.exp(-np.clip(chosen_logits,-30,30)))
        adjusted[added]=1.
        counts={}
        for fold_name in ('calibrate','holdout'):
            fold_mask=np.array([m['fold']==fold_name for m in meta],bool)[groups]
            counts[fold_name]={
                'added_true_edges':int(np.count_nonzero(added&truth&fold_mask)),
                'added_false_edges':int(np.count_nonzero(added&~truth&fold_mask))}
        report['exact_target_cluster_completion']={
            'protocol':'Within the final 32 candidates, add an unselected target only when it has the same nonempty normalized name AND address as another target already predicted for that Source 1; no labels or IDs used by rule',
            'counts':counts,
            'calibration':score_slices(meta,groups,targets,adjusted,'calibrate',best['threshold']),
            'holdout':score_slices(meta,groups,targets,adjusted,'holdout',best['threshold'])}
        blank_exact=np.array([bool(records[a][0] and
            records[a][0]==records[t][0] and not records[t][1])
            for a,t in keys],bool)
        exact_names=sorted({records[a][0] for a,t in keys
                            if records[a][0] and records[a][0]==records[t][0]})
        c.execute('CREATE TEMP TABLE needed_names AS SELECT unnest(?) n',[exact_names])
        name_counts={(country,name):count for country,name,count in
            c.execute('''SELECT t.country,t.n,count(*) FROM train t
                JOIN needed_names n USING(n) WHERE t.source=1
                GROUP BY t.country,t.n''').fetchall()}
        c.close()
        recovery=[]
        for min_cat in (0.,.5,.8,.9,.95,.98):
            added=blank_exact&~chosen&~dense&(cat>=min_cat)
            adjusted=1/(1+np.exp(-np.clip(chosen_logits,-30,30)))
            adjusted[added]=1.
            counts={}
            for fold_name in ('calibrate','holdout'):
                fold_mask=np.array([m['fold']==fold_name for m in meta],bool)[groups]
                counts[fold_name]={
                    'added_true_edges':int(np.count_nonzero(added&truth&fold_mask)),
                    'added_false_edges':int(np.count_nonzero(added&~truth&fold_mask))}
            recovery.append({
                'minimum_cat_probability':min_cat,'counts':counts,
                'calibration':score_slices(meta,groups,targets,adjusted,'calibrate',best['threshold']),
                'holdout':score_slices(meta,groups,targets,adjusted,'holdout',best['threshold'])})
        report['blank_address_exact_name_recovery']=recovery
        unique_recovery=[]
        for max_count in (1,2,3,5,10):
            added=np.array([bool(blank_exact[i] and not chosen[i] and
                name_counts.get((meta[int(groups[i])]['country'],records[a][0]),999999)
                <=max_count) for i,(a,_) in enumerate(keys)],bool)
            adjusted=1/(1+np.exp(-np.clip(chosen_logits,-30,30)))
            adjusted[added]=1.
            counts={}
            for fold_name in ('calibrate','holdout'):
                fold_mask=np.array([m['fold']==fold_name for m in meta],bool)[groups]
                counts[fold_name]={
                    'added_true_edges':int(np.count_nonzero(added&truth&fold_mask)),
                    'added_false_edges':int(np.count_nonzero(added&~truth&fold_mask))}
            unique_recovery.append({
                'max_same_name_s1_anchors':max_count,'counts':counts,
                'calibration':score_slices(meta,groups,targets,adjusted,'calibrate',best['threshold']),
                'holdout':score_slices(meta,groups,targets,adjusted,'holdout',best['threshold'])})
        report['blank_address_unique_name_recovery']=unique_recovery

        # D021: direct composition of the calibration-selected dense gate with
        # the already-fixed INT007 max-count=1 recovery rule. Evaluate recovery
        # after gating because qualifying gate removals can be re-added.
        selected_dense_penalty=report['dense_gate_selected']['extra_dense_logit_penalty']
        unique_recovery_eligible=np.array([bool(blank_exact[i] and
            name_counts.get((meta[int(groups[i])]['country'],records[a][0]),999999)<=1)
            for i,(a,_) in enumerate(keys)],bool)
        composed=compose_dense_gate_blank_recovery(
            chosen_logits,dense,best['threshold'],selected_dense_penalty,
            unique_recovery_eligible)
        composed_probability=1/(1+np.exp(-np.clip(composed['gated_logits'],-30,30)))
        composed_probability[composed['recovered']]=1.
        composed_counts={}
        for fold_name in ('calibrate','holdout'):
            fold_mask=np.array([m['fold']==fold_name for m in meta],bool)[groups]
            gate_removed=composed['base_selected']&~composed['gated_selected']&fold_mask
            recovered=composed['recovered']&fold_mask
            readded=composed['readded_gate_removed']&fold_mask
            composed_counts[fold_name]={
                'gate_removed_true_edges':int(np.count_nonzero(gate_removed&truth)),
                'gate_removed_false_edges':int(np.count_nonzero(gate_removed&~truth)),
                'recovered_true_edges':int(np.count_nonzero(recovered&truth)),
                'recovered_false_edges':int(np.count_nonzero(recovered&~truth)),
                'readded_gate_removed_true_edges':int(np.count_nonzero(readded&truth)),
                'readded_gate_removed_false_edges':int(np.count_nonzero(readded&~truth)),
            }
        report['dense_gate_plus_blank_unique_recovery']={
            'protocol':'Fixed calibration-selected dense-only penalty, then INT007 exact-name blank-address recovery for Source-1 names unique within country; same frozen cap32 pool and threshold',
            'extra_dense_logit_penalty':float(selected_dense_penalty),
            'max_same_name_s1_anchors':1,
            'counts':composed_counts,
            'calibration':score_slices(meta,groups,targets,composed_probability,
                                       'calibrate',best['threshold']),
            'holdout':score_slices(meta,groups,targets,composed_probability,
                                   'holdout',best['threshold'])}
        from rapidfuzz import fuzz
        nonblank_exact_unique=np.array([bool(not chosen[i] and records[t][1] and
            records[a][0] and records[a][0]==records[t][0] and
            name_counts.get((meta[int(groups[i])]['country'],records[a][0]),999999)==1)
            for i,(a,t) in enumerate(keys)],bool)
        address_ratios=np.zeros(len(keys),np.float32)
        for i in np.flatnonzero(nonblank_exact_unique):
            a,t=keys[i]
            address_ratios[i]=fuzz.ratio(records[a][1],records[t][1])
        nonblank_recovery=[]
        for minimum in (0.,40.,60.,75.,85.,95.):
            added=nonblank_exact_unique&(address_ratios>=minimum)
            adjusted=1/(1+np.exp(-np.clip(chosen_logits,-30,30)))
            adjusted[added]=1.
            counts={}
            for fold_name in ('calibrate','holdout'):
                fold_mask=np.array([m['fold']==fold_name for m in meta],bool)[groups]
                counts[fold_name]={
                    'added_true_edges':int(np.count_nonzero(added&truth&fold_mask)),
                    'added_false_edges':int(np.count_nonzero(added&~truth&fold_mask))}
            nonblank_recovery.append({
                'minimum_address_ratio':minimum,'counts':counts,
                'calibration':score_slices(meta,groups,targets,adjusted,'calibrate',best['threshold']),
                'holdout':score_slices(meta,groups,targets,adjusted,'holdout',best['threshold'])})
        report['nonblank_exact_unique_name_recovery']=nonblank_recovery
        selected_indices=np.flatnonzero(chosen)
        selected_name_ratio=np.zeros(len(keys),np.float32)
        selected_address_ratio=np.zeros(len(keys),np.float32)
        selected_name_token=np.zeros(len(keys),np.float32)
        selected_address_token=np.zeros(len(keys),np.float32)
        for i in selected_indices:
            a,t=keys[i]
            an,aa=records[a];tn,ta=records[t]
            selected_name_ratio[i]=fuzz.ratio(an,tn)
            selected_address_ratio[i]=fuzz.ratio(aa,ta)
            selected_name_token[i]=fuzz.token_set_ratio(an,tn)
            selected_address_token[i]=fuzz.token_set_ratio(aa,ta)
        removal_rules=[
            ('dense_ratio_40_50',dense,selected_name_ratio,selected_address_ratio,40.,50.),
            ('dense_ratio_50_50',dense,selected_name_ratio,selected_address_ratio,50.,50.),
            ('dense_ratio_50_60',dense,selected_name_ratio,selected_address_ratio,50.,60.),
            ('all_ratio_40_50',np.ones(len(keys),bool),selected_name_ratio,selected_address_ratio,40.,50.),
            ('all_ratio_50_50',np.ones(len(keys),bool),selected_name_ratio,selected_address_ratio,50.,50.),
            ('dense_token_50_50',dense,selected_name_token,selected_address_token,50.,50.),
            ('all_token_50_50',np.ones(len(keys),bool),selected_name_token,selected_address_token,50.,50.)]
        low_evidence_removal=[]
        for name,channel,name_sim,address_sim,ncut,acut in removal_rules:
            removed=chosen&channel&(name_sim<ncut)&(address_sim<acut)
            adjusted=1/(1+np.exp(-np.clip(chosen_logits,-30,30)))
            adjusted[removed]=0.
            counts={}
            for fold_name in ('calibrate','holdout'):
                fold_mask=np.array([m['fold']==fold_name for m in meta],bool)[groups]
                counts[fold_name]={
                    'removed_true_edges':int(np.count_nonzero(removed&truth&fold_mask)),
                    'removed_false_edges':int(np.count_nonzero(removed&~truth&fold_mask))}
            low_evidence_removal.append({
                'name':name,'counts':counts,
                'calibration':score_slices(meta,groups,targets,adjusted,'calibrate',best['threshold']),
                'holdout':score_slices(meta,groups,targets,adjusted,'holdout',best['threshold'])})
        report['low_evidence_removal']=low_evidence_removal
        blank_unique=np.array([bool(not chosen[i] and not records[t][1] and
            records[a][0] and records[t][0] and
            name_counts.get((meta[int(groups[i])]['country'],records[a][0]),999999)==1)
            for i,(a,t) in enumerate(keys)],bool)
        blank_indices=np.flatnonzero(blank_unique)
        name_ratio=np.zeros(len(keys),np.float32)
        name_token=np.zeros(len(keys),np.float32)
        for i in blank_indices:
            a,t=keys[i]
            name_ratio[i]=fuzz.ratio(records[a][0],records[t][0])
            name_token[i]=fuzz.token_set_ratio(records[a][0],records[t][0])
        fuzzy_recovery=[]
        for metric,values in [('ratio',name_ratio),('token_set',name_token)]:
            for minimum in (85.,90.,95.,100.):
                added=blank_unique&(values>=minimum)
                adjusted=1/(1+np.exp(-np.clip(chosen_logits,-30,30)))
                adjusted[added]=1.
                counts={}
                for fold_name in ('calibrate','holdout'):
                    fold_mask=np.array([m['fold']==fold_name for m in meta],bool)[groups]
                    counts[fold_name]={
                        'added_true_edges':int(np.count_nonzero(added&truth&fold_mask)),
                        'added_false_edges':int(np.count_nonzero(added&~truth&fold_mask))}
                fuzzy_recovery.append({
                    'metric':metric,'minimum':minimum,'counts':counts,
                    'calibration':score_slices(meta,groups,targets,adjusted,'calibrate',best['threshold']),
                    'holdout':score_slices(meta,groups,targets,adjusted,'holdout',best['threshold'])})
        report['blank_address_fuzzy_unique_recovery']=fuzzy_recovery
        selected_by_anchor={}
        for i,(anchor,target) in enumerate(keys):
            if chosen[i]:
                selected_by_anchor.setdefault(anchor,[]).append(target)
        neighbor_strength=np.zeros(len(keys),np.float32)
        cross_source_strength=np.zeros(len(keys),np.float32)
        for i,(anchor,target) in enumerate(keys):
            if chosen[i]:
                continue
            name,address=records[target]
            if not name or not address:
                continue
            for neighbor in selected_by_anchor.get(anchor,[]):
                other_name,other_address=records[neighbor]
                if not other_name or not other_address:
                    continue
                strength=min(fuzz.ratio(name,other_name),
                             fuzz.ratio(address,other_address))
                if strength>neighbor_strength[i]:
                    neighbor_strength[i]=strength
                if target[:2]!=neighbor[:2] and strength>cross_source_strength[i]:
                    cross_source_strength[i]=strength
        neighbor_recovery=[]
        for minimum in (80.,85.,90.,95.):
            for cross_only in (False,True):
                added=(cross_source_strength if cross_only else neighbor_strength)>=minimum
                adjusted=1/(1+np.exp(-np.clip(chosen_logits,-30,30)))
                adjusted[added]=1.
                counts={}
                for fold_name in ('calibrate','holdout'):
                    fold_mask=np.array([m['fold']==fold_name for m in meta],bool)[groups]
                    counts[fold_name]={
                        'added_true_edges':int(np.count_nonzero(added&truth&fold_mask)),
                        'added_false_edges':int(np.count_nonzero(added&~truth&fold_mask))}
                neighbor_recovery.append({
                    'minimum_name_and_address_ratio':minimum,
                    'cross_source_only':cross_only,'counts':counts,
                    'calibration':score_slices(meta,groups,targets,adjusted,'calibrate',best['threshold']),
                    'holdout':score_slices(meta,groups,targets,adjusted,'holdout',best['threshold'])})
        report['selected_neighbor_recovery']=neighbor_recovery
        private_errors=[{
            'fold':meta[int(groups[i])]['fold'],
            'country':meta[int(groups[i])]['country'],
            'kind':'false_negative' if truth[i] else 'false_positive',
            'channel':'dense_only' if dense[i] else 'lexical',
            'anchor':keys[i][0], 'target':keys[i][1],
            'anchor_name':records[keys[i][0]][0],
            'anchor_address':records[keys[i][0]][1],
            'target_name':records[keys[i][1]][0],
            'target_address':records[keys[i][1]][1],
            'cross_logit':float(cross[i]),
            'cat_probability':float(cat[i]),
            'fused_logit':float(chosen_logits[i])}
            for i in error_indices]
        Path(out).with_name('private_error_examples.json').write_text(
            json.dumps(private_errors,ensure_ascii=False),encoding='utf-8')
    Path(out).parent.mkdir(parents=True,exist_ok=True)
    Path(out).write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report
