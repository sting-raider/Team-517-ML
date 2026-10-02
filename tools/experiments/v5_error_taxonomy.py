"""Aggregate saved labeled V5 mistakes without printing record text."""

from collections import Counter
import json

from rapidfuzz import fuzz

rows=json.load(open('artifacts/private_v5_error_examples.json', encoding='utf-8'))
for fold in ('calibrate','holdout'):
    for kind in ('false_negative','false_positive'):
        current=[r for r in rows if r['fold']==fold and r['kind']==kind]
        print(fold,kind,len(current),Counter(r['country'] for r in current))
        def count(pred):
            return sum(bool(pred(r)) for r in current)
        for title,pred in [
            ('name_exact',lambda r:bool(r['anchor_name']) and r['anchor_name']==r['target_name']),
            ('address_exact',lambda r:bool(r['anchor_address']) and r['anchor_address']==r['target_address']),
            ('address_missing',lambda r:not r['target_address']),
            ('name_ratio90',lambda r:fuzz.ratio(r['anchor_name'],r['target_name'])>=90),
            ('name_set90',lambda r:fuzz.token_set_ratio(r['anchor_name'],r['target_name'])>=90),
            ('address_set90',lambda r:fuzz.token_set_ratio(r['anchor_address'],r['target_address'])>=90 and bool(r['target_address'])),
            ('name_set90_address_set70',lambda r:fuzz.token_set_ratio(r['anchor_name'],r['target_name'])>=90 and fuzz.token_set_ratio(r['anchor_address'],r['target_address'])>=70 and bool(r['target_address'])),
            ('name_set70_address_set90',lambda r:fuzz.token_set_ratio(r['anchor_name'],r['target_name'])>=70 and fuzz.token_set_ratio(r['anchor_address'],r['target_address'])>=90 and bool(r['target_address']))
        ]:
            print(title,count(pred))
