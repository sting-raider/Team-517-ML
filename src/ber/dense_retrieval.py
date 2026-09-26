"""Country-sharded neural blocking over the complete target inventory."""
import json
import time
from pathlib import Path

import numpy as np

from .dense_training import serialize


def encode_target_shard(db, encoder, out, country, part, parts=4,split='train'):
    import duckdb
    import torch
    import torch.nn.functional as F
    from transformers import AutoModel, AutoTokenizer

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    c = duckdb.connect(str(db), read_only=True)
    c.execute("SET memory_limit='8GB'")
    c.execute('SET threads=4')
    predicate = 'source>1 AND country=? AND hash(entity_id)%?=?'
    if split not in ('train','test'):
        raise ValueError('Unknown split')
    count = c.execute(f'SELECT count(*) FROM {split} WHERE {predicate}',
                      [country,parts,part]).fetchone()[0]
    if count < 100000:
        raise ValueError('Unexpectedly small full-inventory shard')
    tokenizer = AutoTokenizer.from_pretrained(encoder)
    model = AutoModel.from_pretrained(encoder).eval().cuda()
    torch.set_num_threads(4)
    dim = model.config.hidden_size
    vectors = np.memmap(out/'vectors.f16',dtype=np.float16,mode='w+',shape=(count,dim))
    rowids = np.memmap(out/'rowids.i64',dtype=np.int64,mode='w+',shape=(count,))
    cursor = c.execute(f'''SELECT rowid,business_name,business_address FROM {split}
        WHERE {predicate} ORDER BY rowid''', [country,parts,part])
    started = time.monotonic()
    written = 0
    with torch.inference_mode():
        while rows := cursor.fetchmany(8192):
            texts = [serialize(n,a) for _,n,a in rows]
            order = sorted(range(len(rows)),key=lambda i:len(texts[i]))
            for offset in range(0,len(rows),512):
                indices = order[offset:offset+512]
                inputs = tokenizer([texts[i] for i in indices],padding=True,
                                   truncation=True,max_length=128,return_tensors='pt').to('cuda')
                with torch.autocast('cuda',dtype=torch.bfloat16):
                    hidden = model(**inputs).last_hidden_state
                    mask = inputs['attention_mask'].unsqueeze(-1)
                    val = F.normalize((hidden.float()*mask).sum(1)/mask.sum(1).clamp_min(1),dim=1)
                vectors[written+np.asarray(indices)] = val.cpu().numpy().astype(np.float16)
            rowids[written:written+len(rows)] = [r[0] for r in rows]
            written += len(rows)
            if written%131072 < len(rows):
                print(f'{country} shard {part}: encoded {written:,}/{count:,} in {time.monotonic()-started:.1f}s',flush=True)
    if written != count:
        raise ValueError('Full inventory scan was incomplete')
    vectors.flush();rowids.flush()
    report = {'country':country,'part':part,'parts':parts,'split':split,'vectors':count,
              'dimension':dim,'seconds':time.monotonic()-started,
              'model':str(encoder),'protocol':'All supplied S2/S3 records in the split and country, hash sharded; no target label filtering'}
    (out/'encoded.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    c.close()
    return report


def build_index(root, nlist=2048):
    import faiss

    root = Path(root)
    info = json.loads((root/'encoded.json').read_text())
    count,dim = info['vectors'],info['dimension']
    vectors = np.memmap(root/'vectors.f16',dtype=np.float16,mode='r',shape=(count,dim))
    rowids = np.memmap(root/'rowids.i64',dtype=np.int64,mode='r',shape=(count,))
    faiss.omp_set_num_threads(8)
    quantizer = faiss.IndexFlatIP(dim)
    index = faiss.IndexIVFScalarQuantizer(quantizer,dim,nlist,
                                         faiss.ScalarQuantizer.QT_8bit,
                                         faiss.METRIC_INNER_PRODUCT)
    training_ids = np.linspace(0,count-1,min(100000,count),dtype=np.int64)
    started=time.monotonic()
    index.train(np.asarray(vectors[training_ids],dtype=np.float32))
    for start in range(0,count,20000):
        end=min(start+20000,count)
        index.add_with_ids(np.asarray(vectors[start:end],dtype=np.float32),
                           np.asarray(rowids[start:end],dtype=np.int64))
    if index.ntotal != count:
        raise ValueError('ANN index size differs from encoded full shard')
    faiss.write_index(index,str(root/'ivfsq8.faiss'))
    info.update(index='IVF2048,SQ8,IP',index_seconds=time.monotonic()-started,
                index_bytes=(root/'ivfsq8.faiss').stat().st_size)
    (root/'indexed.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
    return info


def search_calibration(db, encoder, root, feature_root, country, nprobe=64, topk=64,
                       fold='calibrate'):
    import duckdb
    import faiss
    import torch
    import torch.nn.functional as F
    from transformers import AutoModel, AutoTokenizer

    root=Path(root)
    meta=json.loads((Path(feature_root)/'anchors.json').read_text())
    selected=[m for m in meta if m['fold']==fold and m['country']==country]
    ids=[m['id'] for m in selected]
    c=duckdb.connect(str(db),read_only=True)
    c.execute('CREATE TEMP TABLE query_ids AS SELECT unnest(?) entity_id',[ids])
    records={i:(n,a) for i,n,a in c.execute('''SELECT t.entity_id,t.business_name,t.business_address
        FROM train t JOIN query_ids q USING(entity_id)''').fetchall()}
    if len(records)!=len(ids):
        raise ValueError('Missing calibration anchor')
    tokenizer=AutoTokenizer.from_pretrained(encoder)
    model=AutoModel.from_pretrained(encoder).eval().cuda()
    torch.set_num_threads(4)
    vectors=np.empty((len(ids),model.config.hidden_size),np.float32)
    with torch.inference_mode():
        for start in range(0,len(ids),256):
            rows=ids[start:start+256]
            inputs=tokenizer([serialize(*records[i]) for i in rows],padding=True,
                             truncation=True,max_length=128,return_tensors='pt').to('cuda')
            with torch.autocast('cuda',dtype=torch.bfloat16):
                hidden=model(**inputs).last_hidden_state
                mask=inputs['attention_mask'].unsqueeze(-1)
                val=F.normalize((hidden.float()*mask).sum(1)/mask.sum(1).clamp_min(1),dim=1)
            vectors[start:start+len(rows)]=val.cpu().numpy()
    faiss.omp_set_num_threads(8)
    index=faiss.read_index(str(root/'ivfsq8.faiss'))
    index.nprobe=nprobe
    started=time.monotonic()
    scores,rowids=index.search(vectors,topk)
    out=root/f'{"cal" if fold=="calibrate" else "hold"}_nprobe{nprobe}.npz'
    np.savez_compressed(out,anchor=np.array(ids),rowid=rowids,similarity=scores)
    return {'country':country,'part':json.loads((root/'encoded.json').read_text())['part'],
            'fold':fold,'queries':len(ids),'nprobe':nprobe,'topk':topk,'search_seconds':time.monotonic()-started,
            'result':str(out)}


def evaluate_search(db, feature_root, search_paths, country, topks=(16,32,64,128)):
    import duckdb
    from .metrics import evaluate

    c=duckdb.connect(str(db),read_only=True)
    meta=json.loads((Path(feature_root)/'anchors.json').read_text())
    selected={m['id']:set(m['truth']) for m in meta if m['fold']=='calibrate' and m['country']==country}
    with np.load(Path(feature_root)/'evaluation.npz') as z:
        gs=z['groups'];ts=z['target']
    old={k:set() for k in selected}
    for group,target in zip(gs,ts):
        anchor=meta[int(group)]['id']
        if anchor in old:
            old[anchor].add(str(target))
    answers={k:[] for k in selected}
    for path in search_paths:
        with np.load(path) as z:
            ids=z['anchor'];rids=z['rowid'];scores=z['similarity']
        for i,anchor in enumerate(ids):
            answers[str(anchor)].extend((float(score),int(rid)) for score,rid in zip(scores[i],rids[i]) if rid>=0)
    for a in answers:
        answers[a]=sorted(answers[a],reverse=True)
    needed=sorted({rid for ranked in answers.values() for _,rid in ranked[:max(topks)]})
    c.execute('CREATE TEMP TABLE retrieved_ids AS SELECT unnest(?) rowid',[needed])
    lookup={rid:i for rid,i in c.execute('''SELECT t.rowid,t.entity_id FROM train t
        JOIN retrieved_ids r ON t.rowid=r.rowid''').fetchall()}
    if len(lookup)!=len(needed):
        raise ValueError('ANN returned nonexistent rowid')
    oracle=lambda pool:{a:selected[a]&pool[a] for a in selected}
    report={'country':country,'anchors':len(selected),'baseline':evaluate(selected,oracle(old),old),
            'variants':{},'protocol':'Complete S2/S3 country inventory via 4 IVF-SQ8 ANN shards; no labels used to construct search results'}
    for k in topks:
        dense={a:set(lookup[rid] for _,rid in answers[a][:k]) for a in selected}
        combined={a:old[a]|dense[a] for a in selected}
        report['variants'][str(k)]={'dense':evaluate(selected,oracle(dense),dense),
                                    'union':evaluate(selected,oracle(combined),combined),
                                    'mean_dense_candidates':sum(map(len,dense.values()))/len(dense)}
    c.close()
    return report


def evaluate_capped(db, feature_root, search_paths, country, caps=(32,64,128,160),
                    dense_counts=(4,8,16,32,64),fold='calibrate',output_pairs=None,
                    base_cap=160):
    """Measure an auditable, fixed-cap union using blocker ranks, not matcher scores."""
    from .data import connect
    from .retrieval_v3 import fused_candidates
    from .metrics import evaluate

    c=connect(db)
    c.execute("SET memory_limit='20GB'")
    c.execute('SET threads=8')
    meta=json.loads((Path(feature_root)/'anchors.json').read_text())
    selected={m['id']:set(m['truth']) for m in meta
              if m['fold']==fold and m['country']==country}
    c.execute('CREATE TEMP TABLE cal_anchors AS SELECT * FROM train WHERE source=1 AND entity_id IN (SELECT unnest(?))',
              [sorted(selected)])
    fused_candidates(c,'train','cal_anchors','capped_base',base_cap)
    base={a:[] for a in selected}
    for anchor,target in c.execute('''SELECT p.anchor,t.entity_id FROM capped_base p
        JOIN train t ON p.rid=t.rowid ORDER BY p.anchor,p.retrieval DESC,t.entity_id''').fetchall():
        base[anchor].append(target)
    ranked={a:[] for a in selected}
    for path in search_paths:
        with np.load(path) as z:
            ids=z['anchor'];rids=z['rowid'];sims=z['similarity']
        for i,anchor in enumerate(ids):
            ranked[str(anchor)].extend((float(score),int(rid)) for score,rid
                                       in zip(sims[i],rids[i]) if rid>=0)
    for a in ranked:
        ranked[a].sort(reverse=True)
    needed=sorted({rid for values in ranked.values() for _,rid in values[:max(dense_counts)]})
    c.execute('CREATE TEMP TABLE ann_ids AS SELECT unnest(?) rowid',[needed])
    lookup={rid:t for rid,t in c.execute('SELECT a.rowid,a.entity_id FROM train a JOIN ann_ids b USING(rowid)').fetchall()}
    if len(needed)!=len(lookup):
        raise ValueError('ANN target lookup incomplete')
    baseline={a:set(values) for a,values in base.items()}
    oracle=lambda p:{a:selected[a]&p[a] for a in selected}
    result={'country':country,'fold':fold,'anchors':len(selected),'baseline':evaluate(selected,oracle(baseline),baseline),
            'variants':{},'base_cap':base_cap,
            'protocol':'Full target inventory IVF-SQ8 ANN plus v3 fused blocker ranks, deduplicated and hard-capped before matcher'}
    emitted=[]
    for cap in caps:
        for count in dense_counts:
            if count>cap:
                continue
            pool={}
            for anchor in selected:
                picked=[];seen=set()
                for _,rid in ranked[anchor][:count]:
                    value=lookup[rid]
                    if value not in seen:
                        picked.append(value);seen.add(value)
                for value in base[anchor]:
                    if len(picked)>=cap:
                        break
                    if value not in seen:
                        picked.append(value);seen.add(value)
                pool[anchor]=set(picked)
                if output_pairs is not None and cap==32 and count==16:
                    emitted.extend({'anchor':anchor,'target':target,
                                    'dense_only':target not in baseline[anchor]}
                                   for target in picked)
            result['variants'][f'cap{cap}_dense{count}']=evaluate(selected,oracle(pool),pool)
    if output_pairs is not None:
        Path(output_pairs).parent.mkdir(parents=True,exist_ok=True)
        with Path(output_pairs).open('w',encoding='utf-8') as stream:
            for row in emitted:
                stream.write(json.dumps(row)+'\n')
        result['private_selected_pairs']=len(emitted)
    c.close()
    return result
