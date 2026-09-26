import importlib.util
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'f013', ROOT/'tools'/'experiments'/'f013_s1_anchor_ambiguity.py')
f013 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f013)

def test_norm_semantics():
    assert f013.norm_text('  Café—12/B  ') == 'cafe 12 b'
    assert f013.norm_text('') == ''
    assert f013.norm_text('東京-１２') == '東京 １２'

def test_collision_stats():
    keys=np.array([1,1,2,3,3,3], dtype=np.uint64)
    stats, mask=f013.collision_stats(keys)
    assert stats['groups']==2
    assert stats['affected_anchors']==5
    assert stats['collision_pairs']==4
    assert mask.tolist()==[True,True,False,True,True,True]

def test_normalization_induced_pair_accounting():
    norm=np.array([10,10,20,20],dtype=np.uint64)
    raw=np.array([1,2,3,3],dtype=np.uint64)
    x=f013.norm_induced_stats(norm,raw)
    assert x['normalization_induced_groups']==1
    assert x['anchors_in_induced_groups']==2
    assert x['raw_exact_collision_pairs']==1
    assert x['normalized_collision_pairs']==2
    assert x['normalization_added_collision_pairs']==1
