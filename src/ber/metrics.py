"""Official per-anchor set metric, including singleton behavior."""
import numpy as np


def row_score(truth, predicted):
    truth, predicted = set(truth), set(predicted)
    if not truth:
        return float(not predicted)
    return 1.25 * len(truth & predicted) / (0.25 * len(truth) + len(predicted))


def evaluate(truth, predicted, candidates=None):
    if not truth:
        raise ValueError('Cannot score an empty evaluation set')
    scores = [row_score(t, predicted.get(k, ())) for k,t in truth.items()]
    singletons = [k for k,t in truth.items() if not t]
    result = {
        'entities': len(truth), 'macro_f0_5': float(np.mean(scores)),
        'singleton_count': len(singletons),
        'singleton_false_positive_rate': float(np.mean([bool(predicted.get(k)) for k in singletons])) if singletons else None,
        'all_empty_baseline': len(singletons)/len(truth),
    }
    if candidates is not None:
        positives = {k:t for k,t in truth.items() if t}
        found = {k: set(t) & set(candidates.get(k, ())) for k,t in truth.items()}
        total = sum(map(len, positives.values()))
        result.update({
            'candidate_pair_recall': sum(map(len, found.values()))/total if total else None,
            'candidate_entity_recall': float(np.mean([len(found[k])/len(t) for k,t in positives.items()])) if positives else None,
            'all_matches_retrieved_rate': float(np.mean([len(found[k])==len(t) for k,t in positives.items()])) if positives else None,
            'blocking_oracle_macro_f0_5': float(np.mean([row_score(t,found[k]) for k,t in truth.items()])),
            'candidate_count_quantiles': dict(zip(['p50','p90','p99','max'], map(float,np.quantile([len(candidates.get(k,())) for k in truth], [.5,.9,.99,1])))),
        })
    return result
