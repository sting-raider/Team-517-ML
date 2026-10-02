"""Train a compact decision stacker on frozen capped-pair neural scores."""

import hashlib
import json
import re
from pathlib import Path
import time

from catboost import CatBoostClassifier
import duckdb
import numpy as np
from rapidfuzz import fuzz

from ber.features import features, FEATURE_NAMES


def scores(prob, groups, y, truth_count, anchor_indices, grid):
    result=[]
    use=np.isin(groups,anchor_indices)
    g=groups[use]; labels=y[use]
    for threshold in grid:
        predicted=prob[use]>=threshold
        cnt=np.bincount(g,weights=predicted,minlength=len(truth_count))
        tp=np.bincount(g,weights=predicted&labels,minlength=len(truth_count))
        tc=truth_count[anchor_indices]
        pc=cnt[anchor_indices]
        tp=tp[anchor_indices]
        fp=pc-tp; fn=tc-tp
        each=np.where(tc==0,(pc==0).astype(float),
                      1.25*tp/np.maximum(1e-9,1.25*tp+fp+.25*fn))
        result.append((float(threshold),float(np.mean(each))))
    return result


def main():
    started=time.time()
    path=Path('artifacts/capped_pairs/local_decisions.npz')
    with np.load(path) as z:
        anchors=np.array(list(map(str,z['anchor'])))
        targets=np.array(list(map(str,z['target'])))
        folds=np.array(list(map(str,z['fold'])))
        cross=z['cross'].astype(np.float32)
        m021_cross=z['m021_cross'].astype(np.float32)
        cat=z['cat'].astype(np.float32)
        fused=z['fused'].astype(np.float32)
        dense=z['dense'].astype(bool)
        y=z['truth'].astype(np.uint8)
        chosen=z['chosen'].astype(bool)
    ids=sorted(set(anchors)|set(targets))
    con=duckdb.connect('artifacts/data.duckdb',read_only=True)
    con.execute('CREATE TEMP TABLE needed AS SELECT unnest(?) entity_id',[ids])
    records={i:(country,int(source),n,a) for i,country,source,n,a in con.execute('''
        SELECT t.entity_id,t.country,t.source,t.n,t.a FROM train t JOIN needed USING(entity_id)''').fetchall()}
    if len(records)!=len(ids): raise ValueError('Missing records')
    unique_names=set(con.execute('''SELECT country,n FROM train WHERE source=1 AND n<>''
        GROUP BY 1,2 HAVING count(*)=1''').fetchall())
    unique_anchors=sorted(set(anchors))
    gid={a:i for i,a in enumerate(unique_anchors)}
    groups=np.array([gid[a] for a in anchors],np.int32)
    con.execute('CREATE TEMP TABLE sampled_anchors AS SELECT unnest(?) anchor',[unique_anchors])
    truth_count=np.zeros(len(unique_anchors),np.int32)
    for a,n in con.execute('''SELECT e.anchor,count(*) FROM edges e JOIN sampled_anchors s
        USING(anchor) GROUP BY e.anchor''').fetchall():
        truth_count[gid[a]]=n
    aux=[]
    for a,t in zip(anchors,targets):
        _,_,an,aa=records[a]
        _,source,tn,ta=records[t]
        aux.append(features(an,aa,tn,ta,0,0,source))
    aux=np.asarray(aux,np.float32)
    blank_exact=np.array([bool(records[t][3]=='') and bool(records[t][2]) and
                          records[a][2]==records[t][2] and
                          (records[a][0],records[a][2]) in unique_names
                          for a,t in zip(anchors,targets)],bool)
    v6=chosen|blank_exact
    catlog=np.log(np.clip(cat,1e-7,1-1e-7)/(1-np.clip(cat,1e-7,1-1e-7)))
    X=np.column_stack([cross,catlog,fused,dense.astype(np.float32),aux]).astype(np.float32)
    m021_fused=m021_cross+catlog+np.where(dense,-2.,0.)
    names=['cross','cat_logit','fused','dense']+FEATURE_NAMES
    cal1=np.array([folds[i]=='calibrate' and hashlib.md5(anchors[i].encode()).digest()[0]%2==0
                   for i in range(len(anchors))])
    cal2=(folds=='calibrate')&~cal1
    hold=folds=='holdout'
    ca1=np.array(sorted(set(groups[cal1])),np.int32)
    ca2=np.array(sorted(set(groups[cal2])),np.int32)
    ha=np.array(sorted(set(groups[hold])),np.int32)
    grid=np.array([.1,.2,.3,.4,.5,.6,.7,.8,.85,.9,.925,.95,.96,.97,.98,.985,.99,.995,.997,.999])
    baseline=1/(1+np.exp(-np.clip(fused,-30,30)))
    report={'baseline':{'cal2':scores(baseline,groups,y,truth_count,ca2,[.95])[0][1],
                        'holdout':scores(baseline,groups,y,truth_count,ha,[.95])[0][1]},
            'features':names,'training_pairs':int(cal1.sum()),
            'calibration_pairs':int(cal2.sum())}
    report['v6_baseline']={
        'cal2':scores(v6.astype(float),groups,y,truth_count,ca2,[.5])[0][1],
        'holdout':scores(v6.astype(float),groups,y,truth_count,ha,[.5])[0][1]}
    variants=[]
    for depth,iterations in ((4,400),(6,600),(8,800)):
        model=CatBoostClassifier(iterations=iterations,depth=depth,learning_rate=.05,
                                 l2_leaf_reg=8,loss_function='Logloss',
                                 verbose=False,thread_count=8,random_seed=517)
        model.fit(X[cal1],y[cal1])
        prob=model.predict_proba(X)[:,1]
        cal_curve=scores(prob,groups,y,truth_count,ca2,grid)
        chosen=max(cal_curve,key=lambda item:item[1])
        hold_score=scores(prob,groups,y,truth_count,ha,[chosen[0]])[0][1]
        variants.append({'depth':depth,'iterations':iterations,
                         'cal2_threshold':chosen[0],'cal2_score':chosen[1],
                         'holdout_score':hold_score,
                         'holdout_delta_vs_v5':hold_score-report['baseline']['holdout'],
                         'calibration_curve':cal_curve})
        print(json.dumps(variants[-1]),flush=True)
        model.save_model(f'artifacts/capped_pairs/stacker_depth{depth}.cbm')
    report['variants']=variants
    final=CatBoostClassifier(iterations=400,depth=4,learning_rate=.05,
                             l2_leaf_reg=8,loss_function='Logloss',
                             verbose=False,thread_count=8,random_seed=517)
    final.fit(X[folds=='calibrate'],y[folds=='calibrate'])
    final_prob=final.predict_proba(X)[:,1]
    final_hold=scores(final_prob,groups,y,truth_count,ha,[.8])[0][1]
    final_path='artifacts/capped_pairs/stacker_final.cbm'
    final.save_model(final_path)
    report['production_model']={'path':final_path,'training_pairs':int((folds=='calibrate').sum()),
                                'threshold':.8,'holdout_score':final_hold,
                                'holdout_delta_vs_v5':final_hold-report['baseline']['holdout']}
    binary_x=np.column_stack([v6.astype(np.float32),aux]).astype(np.float32)
    binary_grid=np.array([.3,.4,.5,.6,.7,.8,.85,.9,.925,.95,.975,.99])
    binary_variants=[]
    for depth,iterations in ((4,400),(6,600)):
        binary=CatBoostClassifier(iterations=iterations,depth=depth,learning_rate=.05,
                                  l2_leaf_reg=8,loss_function='Logloss',
                                  verbose=False,thread_count=8,random_seed=517)
        binary.fit(binary_x[cal1],y[cal1])
        bp=binary.predict_proba(binary_x)[:,1]
        bcurve=scores(bp,groups,y,truth_count,ca2,binary_grid)
        bbest=max(bcurve,key=lambda r:r[1])
        bhold=scores(bp,groups,y,truth_count,ha,[bbest[0]])[0][1]
        binary_variants.append({'depth':depth,'iterations':iterations,
                                'threshold':bbest[0],'cal2_score':bbest[1],
                                'holdout_score':bhold,
                                'holdout_delta_vs_v6':bhold-report['v6_baseline']['holdout']})
        binary.save_model(f'artifacts/capped_pairs/binary_stacker_depth{depth}.cbm')
    report['binary_variants']=binary_variants
    group_count=len(unique_anchors)
    fused_max=np.full(group_count,-np.inf,np.float32)
    cross_max=np.full(group_count,-np.inf,np.float32)
    np.maximum.at(fused_max,groups,fused)
    np.maximum.at(cross_max,groups,cross)
    fused_rank=np.empty(len(groups),np.float32)
    cross_rank=np.empty(len(groups),np.float32)
    for values,ranks in ((fused,fused_rank),(cross,cross_rank)):
        order=np.lexsort((-values,groups))
        current=-1; rank=0
        for index in order:
            g=groups[index]
            if g!=current:
                current=g; rank=0
            ranks[index]=rank
            rank+=1
    selected_count=np.bincount(groups,weights=v6,minlength=group_count)
    context=np.column_stack([fused_max[groups]-fused,
                             cross_max[groups]-cross,
                             fused_rank,cross_rank,
                             selected_count[groups]]).astype(np.float32)
    context_x=np.column_stack([X,context]).astype(np.float32)
    context_variants=[]
    for depth,iterations in ((4,400),(6,600)):
        contextual=CatBoostClassifier(iterations=iterations,depth=depth,learning_rate=.05,
                                      l2_leaf_reg=8,loss_function='Logloss',
                                      verbose=False,thread_count=8,random_seed=517)
        contextual.fit(context_x[cal1],y[cal1])
        cp=contextual.predict_proba(context_x)[:,1]
        ccurve=scores(cp,groups,y,truth_count,ca2,grid)
        cbest=max(ccurve,key=lambda r:r[1])
        chold=scores(cp,groups,y,truth_count,ha,[cbest[0]])[0][1]
        context_variants.append({'depth':depth,'iterations':iterations,
                                 'threshold':cbest[0],'cal2_score':cbest[1],
                                 'holdout_score':chold,
                                 'holdout_delta_vs_v6':chold-report['v6_baseline']['holdout']})
        contextual.save_model(f'artifacts/capped_pairs/context_stacker_depth{depth}.cbm')
    report['context_variants']=context_variants
    dual_x=np.column_stack([X,m021_cross,m021_fused]).astype(np.float32)
    dual_variants=[]
    dual_errors=[]
    for depth,iterations in ((4,400),(6,600)):
        dual=CatBoostClassifier(iterations=iterations,depth=depth,learning_rate=.05,
                                l2_leaf_reg=8,loss_function='Logloss',
                                verbose=False,thread_count=8,random_seed=517)
        dual.fit(dual_x[cal1],y[cal1])
        dp=dual.predict_proba(dual_x)[:,1]
        curve=scores(dp,groups,y,truth_count,ca2,grid)
        best=max(curve,key=lambda r:r[1])
        held=scores(dp,groups,y,truth_count,ha,[best[0]])[0][1]
        dual_variants.append({'depth':depth,'iterations':iterations,
                              'threshold':best[0],'cal2_score':best[1],
                              'holdout_score':held,
                              'holdout_delta_vs_v6':held-report['v6_baseline']['holdout']})
        dual.save_model(f'artifacts/capped_pairs/dual_stacker_depth{depth}.cbm')
        if depth==6:
            bad=np.flatnonzero(hold & ((dp>=best[0])!=y.astype(bool)))
            for i in bad:
                dual_errors.append({'anchor':anchors[i], 'target':targets[i],
                                    'country':records[anchors[i]][0],
                                    'truth':int(y[i]),'cross':float(cross[i]),
                                    'm021_cross':float(m021_cross[i]),
                                    'cat':float(cat[i]),'dense':bool(dense[i]),
                                    'dual_prob':float(dp[i]),
                                    'anchor_name':records[anchors[i]][2],
                                    'anchor_address':records[anchors[i]][3],
                                    'target_name':records[targets[i]][2],
                                    'target_address':records[targets[i]][3]})
    report['dual_variants']=dual_variants
    Path('artifacts/capped_pairs/dual_errors.json').write_text(json.dumps(dual_errors),encoding='utf-8')
    report['dual_error_pairs']=len(dual_errors)
    # A second, set-aware pass: compare every candidate to the other fragments
    # already accepted for its Source-1 entity. No labels enter these features.
    selected=np.flatnonzero(v6)
    selected_by_group={}
    for i in selected:
        selected_by_group.setdefault(int(groups[i]),[]).append(int(i))
    support=np.zeros((len(groups),8),np.float32)
    for i in range(len(groups)):
        siblings=selected_by_group.get(int(groups[i]),[])
        if not siblings: continue
        tn,ta=records[targets[i]][2:4]
        ts=records[targets[i]][1]
        support[i,0]=len(siblings)-(i in siblings)
        for j in siblings:
            if i==j: continue
            sn,sa=records[targets[j]][2:4]
            nr=fuzz.ratio(tn,sn)/100 if tn and sn else 0
            ar=fuzz.ratio(ta,sa)/100 if ta and sa else 0
            ns=fuzz.token_set_ratio(tn,sn)/100 if tn and sn else 0
            aset=fuzz.token_set_ratio(ta,sa)/100 if ta and sa else 0
            support[i,1]=max(support[i,1],nr)
            support[i,2]=max(support[i,2],ar)
            support[i,3]=max(support[i,3],ns)
            support[i,4]=max(support[i,4],aset)
            support[i,5]=max(support[i,5],nr+ar)
            support[i,6]=max(support[i,6],float(bool(tn) and tn==sn))
            support[i,7]=max(support[i,7],float(ts!=records[targets[j]][1]))
    set_x=np.column_stack([dual_x,support]).astype(np.float32)
    set_variants=[]
    for depth,iterations in ((4,400),(6,600)):
        set_model=CatBoostClassifier(iterations=iterations,depth=depth,learning_rate=.05,
                                     l2_leaf_reg=8,loss_function='Logloss',
                                     verbose=False,thread_count=8,random_seed=517)
        set_model.fit(set_x[cal1],y[cal1])
        sp=set_model.predict_proba(set_x)[:,1]
        curve=scores(sp,groups,y,truth_count,ca2,grid)
        best=max(curve,key=lambda r:r[1])
        held=scores(sp,groups,y,truth_count,ha,[best[0]])[0][1]
        set_variants.append({'depth':depth,'iterations':iterations,
                             'threshold':best[0],'cal2_score':best[1],
                             'holdout_score':held,
                             'holdout_delta_vs_dual_best':held-max(v['holdout_score'] for v in dual_variants)})
        set_model.save_model(f'artifacts/capped_pairs/set_stacker_depth{depth}.cbm')
    report['set_variants']=set_variants
    # Missing provider addresses are the dominant remaining false-negative
    # family. Fit a dedicated name-only expert and gate it on that condition.
    blank=np.array([not records[t][3] for t in targets],bool)
    def canonical_name(value):
        aliases={'private':'pvt','limited':'ltd','incorporated':'inc',
                 'corporation':'corp','company':'co'}
        tokens=[aliases.get(t,t) for t in re.findall(r'\w+',value)]
        return ' '.join(sorted(tokens))
    canonical=np.array([fuzz.ratio(canonical_name(records[a][2]),
                                   canonical_name(records[t][2]))/100
                        for a,t in zip(anchors,targets)],np.float32)
    name_unique=np.array([(records[a][0],records[a][2]) in unique_names
                          for a in anchors],np.float32)
    blank_x=np.column_stack([dual_x,canonical,name_unique,blank_exact.astype(np.float32)])
    blank_variants=[]
    for depth,iterations in ((4,400),(6,600)):
        expert=CatBoostClassifier(iterations=iterations,depth=depth,learning_rate=.05,
                                  l2_leaf_reg=8,loss_function='Logloss',
                                  verbose=False,thread_count=8,random_seed=517)
        expert.fit(blank_x[cal1&blank],y[cal1&blank])
        ep=np.zeros(len(y),np.float32)
        ep[blank]=expert.predict_proba(blank_x[blank])[:,1]
        nonblank_decision=(dp>=dual_variants[-1]['threshold']) & ~blank
        curve=[]
        for threshold in grid:
            decision=nonblank_decision | (blank & (ep>=threshold))
            curve.append((float(threshold),scores(decision.astype(float),groups,y,
                                                 truth_count,ca2,[.5])[0][1]))
        best=max(curve,key=lambda r:r[1])
        decision=nonblank_decision | (blank & (ep>=best[0]))
        held=scores(decision.astype(float),groups,y,truth_count,ha,[.5])[0][1]
        blank_variants.append({'depth':depth,'iterations':iterations,
                               'threshold':best[0],'cal2_score':best[1],
                               'holdout_score':held,
                               'holdout_delta_vs_dual_best':held-max(v['holdout_score'] for v in dual_variants),
                               'blank_pair_count':int(blank.sum())})
        expert.save_model(f'artifacts/capped_pairs/blank_expert_depth{depth}.cbm')
    report['blank_variants']=blank_variants
    dual_choice=dp>=dual_variants[-1]['threshold']
    name_set=np.array([fuzz.token_set_ratio(records[a][2],records[t][2])/100
                       if records[a][2] and records[t][2] else 0
                       for a,t in zip(anchors,targets)],np.float32)
    candidate_name=blank & name_unique.astype(bool)
    recovery=[]
    for similarity in (.9,.93,.95,.97,.99,1.):
        rule=candidate_name & (name_set>=similarity)
        decision=dual_choice | rule
        add=rule & ~dual_choice
        recovery.append({'name_set_threshold':similarity,
                         'cal2':scores(decision.astype(float),groups,y,truth_count,ca2,[.5])[0][1],
                         'holdout':scores(decision.astype(float),groups,y,truth_count,ha,[.5])[0][1],
                         'holdout_true_add':int((add&hold&y.astype(bool)).sum()),
                         'holdout_false_add':int((add&hold&~y.astype(bool)).sum())})
    report['dual_blank_fuzzy_recovery']=recovery
    # Calibrate the two noisy providers separately; the validation fold is
    # disjoint from both fitting anchors and the untouched holdout.
    source_two=np.array([records[t][1]==2 for t in targets],bool)
    source_cal=[]
    for gate2 in (.6,.7,.8,.85,.9,.925,.95,.97):
        for gate3 in (.6,.7,.8,.85,.9,.925,.95,.97):
            choice=np.where(source_two,dp>=gate2,dp>=gate3)
            value=scores(choice.astype(float),groups,y,truth_count,ca2,[.5])[0][1]
            source_cal.append((value,gate2,gate3))
    selected=max(source_cal)
    source_choice=np.where(source_two,dp>=selected[1],dp>=selected[2])
    report['dual_source_calibration']={
        'cal2_score':selected[0],'source2_threshold':selected[1],
        'source3_threshold':selected[2],
        'holdout_score':scores(source_choice.astype(float),groups,y,truth_count,ha,[.5])[0][1]}
    report['seconds']=time.time()-started
    Path('reports/stacked_matcher_experiment.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('DONE',json.dumps({'baseline':report['baseline'],'v6_baseline':report['v6_baseline'],
        'binary_variants':binary_variants,'context_variants':context_variants,
        'dual_variants':dual_variants,
        'production_model':report['production_model'],'variants':[
        {k:v for k,v in x.items() if k!='calibration_curve'} for x in variants],
        'seconds':report['seconds']},indent=2))


if __name__=='__main__': main()
