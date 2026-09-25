"""Local multilingual representations of supplied records, without external lookup."""
import argparse
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
from .data import connect


def prepare_records(out):
    path=out/'records.parquet'
    if path.exists():
        return path
    ids=[]
    for directory in ('address_baseline','wide_calibration'):
        with np.load(f'artifacts/{directory}/features.npz') as f:
            ids.append(f['target'])
        meta=json.loads(Path(f'artifacts/{directory}/anchors.json').read_text())
        ids.append(np.asarray([m['id'] for m in meta]))
    unique=np.unique(np.concatenate(ids))
    c=connect('artifacts/data.duckdb')
    c.register('needed',pd.DataFrame({'entity_id':unique}))
    c.execute("COPY (SELECT t.entity_id,t.business_name,t.business_address FROM train t JOIN needed n USING(entity_id)) TO ? (FORMAT PARQUET)",[str(path.resolve())])
    print(f'{len(unique):,} unique supplied records for semantic features',flush=True)
    c.close()
    return path


def encode(out,field,batch_size,max_length):
    import torch
    from transformers import AutoModel,AutoTokenizer
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA is required for this experiment; use the GPU environment')
    records=prepare_records(out)
    c=connect(':memory:')
    expr='business_name' if field=='name' else "'business name: '||business_name||'. address: '||business_address"
    rows=c.execute(f'SELECT entity_id,{expr} AS text FROM read_parquet(?) ORDER BY length(text),entity_id',[str(records)]).fetchall()
    c.close()
    ids=np.asarray([r[0] for r in rows])
    texts=['query: '+r[1] for r in rows]
    del rows
    np.save(out/f'{field}_ids.npy',ids)
    model_path='artifacts/pretrained/multilingual-e5-small'
    tokenizer=AutoTokenizer.from_pretrained(model_path,local_files_only=True)
    model=AutoModel.from_pretrained(model_path,local_files_only=True,dtype=torch.float16).cuda().eval()
    path=out/f'{field}_embeddings.npy'
    checkpoint=out/f'{field}_progress.json'
    fingerprint={'model_revision':json.loads(Path('reports/pretrained_model.json').read_text())['revision'],
                 'field':field,'max_length':max_length,'records':len(ids),'dimension':model.config.hidden_size}
    start_at=0
    if checkpoint.exists():
        previous=json.loads(checkpoint.read_text())
        if previous['config']!=fingerprint:
            raise ValueError('Embedding configuration changed; use a separate output directory')
        start_at=previous['completed']
    vectors=np.lib.format.open_memmap(path,mode='r+' if checkpoint.exists() else 'w+',dtype=np.float32,shape=(len(ids),model.config.hidden_size))
    start=time.time()
    with torch.inference_mode():
        for offset in range(start_at,len(ids),batch_size):
            end=min(offset+batch_size,len(ids))
            inputs=tokenizer(texts[offset:end],padding=True,truncation=True,max_length=max_length,return_tensors='pt').to('cuda')
            hidden=model(**inputs).last_hidden_state.float()
            mask=inputs['attention_mask'].unsqueeze(-1)
            pooled=(hidden*mask).sum(1)/mask.sum(1).clamp_min(1)
            pooled=torch.nn.functional.normalize(pooled,p=2,dim=1)
            vectors[offset:end]=pooled.cpu().numpy()
            if end==len(ids) or end//10000!=offset//10000:
                vectors.flush()
                checkpoint.write_text(json.dumps({'config':fingerprint,'completed':end}))
                print(f'{field}: {end:,}/{len(ids):,}; {(end-start_at)/max(.01,time.time()-start):.0f} records/s',flush=True)
    report={**fingerprint,'parameters':sum(p.numel() for p in model.parameters()),'seconds':time.time()-start,
            'peak_gpu_bytes':torch.cuda.max_memory_allocated(),'gpu':torch.cuda.get_device_name(0),'dtype':'float16 forward; float32 pooling and stored vectors'}
    Path(f'reports/semantic_{field}_encoding.json').write_text(json.dumps(report,indent=2))


def pair_features(out,field):
    ids=np.load(out/f'{field}_ids.npy')
    order=np.argsort(ids)
    sorted_ids=ids[order]
    vectors=np.load(out/f'{field}_embeddings.npy',mmap_mode='r')
    progress=json.loads((out/f'{field}_progress.json').read_text())
    if progress['completed']!=len(ids):
        raise ValueError('Embeddings are incomplete')
    for directory in ('address_baseline','wide_calibration'):
        with np.load(f'artifacts/{directory}/features.npz') as f:
            targets,groups=f['target'],f['groups']
        meta=json.loads(Path(f'artifacts/{directory}/anchors.json').read_text())
        anchors=np.asarray([m['id'] for m in meta])
        li=np.searchsorted(sorted_ids,anchors)
        ri=np.searchsorted(sorted_ids,targets)
        if not np.array_equal(sorted_ids[li],anchors) or not np.array_equal(sorted_ids[ri],targets):
            raise ValueError('Missing semantic record IDs')
        result=np.empty(len(targets),dtype=np.float32)
        for offset in range(0,len(targets),10000):
            end=min(offset+10000,len(targets))
            left=vectors[order[li[groups[offset:end]]]]
            right=vectors[order[ri[offset:end]]]
            result[offset:end]=np.einsum('ij,ij->i',left,right)
        np.save(out/f'{field}_{directory}_cosine.npy',result)
        print(f'Saved {field} cosine for {directory}: {len(result):,} pairs',flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',type=Path,default=Path('artifacts/semantic'))
    p.add_argument('--field',choices=['name','record'],default='name')
    p.add_argument('--batch-size',type=int,default=512)
    p.add_argument('--max-length',type=int,default=128)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    encode(a.out,a.field,a.batch_size,a.max_length)
    pair_features(a.out,a.field)


if __name__=='__main__':
    main()
