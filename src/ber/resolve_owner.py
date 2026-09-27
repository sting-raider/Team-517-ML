"""Remove duplicate target assignments when one predicted owner has decisive address evidence.

All evidence comes from the supplied test records and the already predicted
links. This pass only removes links, so the frozen candidate file remains valid.
"""
import json
from collections import defaultdict
from pathlib import Path


def _iter_rows(path):
    with Path(path).open(encoding='utf-8', newline='') as stream:
        if stream.readline() != 'source1_entity_id\tmatched_entity_ids\n':
            raise ValueError('Unexpected matching_results.tsv header')
        for line in stream:
            anchor, ids = line.rstrip('\r\n').split('\t', 1)
            yield anchor, ids


def resolve(db_path, matching_path, output_path, min_address=80., min_margin=10.):
    """Resolve only conflicts with an unambiguous target-to-owner address margin.

    The two scans keep memory proportional to unique target IDs plus the
    conflicting edge set; the large output remains streamed in input order.
    """
    import duckdb
    from rapidfuzz.fuzz import token_sort_ratio

    seen = set()
    conflict_ids = set()
    rows = edges = 0
    for _, ids in _iter_rows(matching_path):
        rows += 1
        for target in ids.split(',') if ids else ():
            edges += 1
            if target in seen:
                conflict_ids.add(target)
            else:
                seen.add(target)
    del seen
    owners = defaultdict(list)
    for anchor, ids in _iter_rows(matching_path):
        for target in ids.split(',') if ids else ():
            if target in conflict_ids:
                owners[target].append(anchor)
    if set(owners) != conflict_ids:
        raise ValueError('Conflict collection lost target IDs')

    ids = sorted(conflict_ids | {a for members in owners.values() for a in members})
    con = duckdb.connect(str(db_path), read_only=True)
    con.execute('CREATE TEMP TABLE owner_ids AS SELECT unnest(?) entity_id', [ids])
    records = {i:(n,a,country) for i,n,a,country in con.execute('''
        SELECT entity_id,n,a,country FROM test JOIN owner_ids USING(entity_id)
        ''').fetchall()}
    con.close()
    if len(records) != len(ids):
        raise ValueError('Missing test records for owner comparison')

    removals = defaultdict(set)
    reviewed = defaultdict(int)
    resolved = defaultdict(int)
    removed_edges = defaultdict(int)
    for target, members in owners.items():
        if len(members) < 2:
            raise ValueError('Conflict target has one owner')
        target_name, target_address, country = records[target]
        if not target_address:
            continue
        reviewed[country] += 1
        ranked = []
        for anchor in members:
            _, address, owner_country = records[anchor]
            if owner_country != country:
                raise ValueError('Cross-country predicted ownership conflict')
            ranked.append((token_sort_ratio(target_address, address), anchor))
        ranked.sort(reverse=True)
        if ranked[0][0] < min_address or ranked[0][0] - ranked[1][0] < min_margin:
            continue
        resolved[country] += 1
        winner = ranked[0][1]
        for _, loser in ranked[1:]:
            if loser == winner:
                raise ValueError('Duplicate predicted owner in one target')
            removals[loser].add(target)
            removed_edges[country] += 1

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix('.tmp')
    changed = written = 0
    with tmp.open('w', encoding='utf-8', newline='') as out:
        out.write('source1_entity_id\tmatched_entity_ids\n')
        for anchor, ids in _iter_rows(matching_path):
            drop = removals.get(anchor)
            if drop:
                kept = [target for target in ids.split(',') if target not in drop]
                if len(kept) == len(ids.split(',')):
                    raise ValueError('Planned owner removal absent from row')
                out.write(anchor + '\t' + ','.join(kept) + '\n')
                changed += 1
            else:
                out.write(anchor + '\t' + ids + '\n')
            written += 1
    tmp.replace(output_path)
    if written != rows:
        raise ValueError('Output anchor count differs from input')
    report = {'input_rows':rows,'input_edges':edges,
              'conflicting_targets':len(conflict_ids),
              'min_address':min_address,'min_margin':min_margin,
              'reviewed_with_address':dict(reviewed),
              'resolved_targets':dict(resolved),
              'removed_edges':dict(removed_edges),
              'changed_anchors':changed,'output_edges':edges-sum(removed_edges.values()),
              'output_bytes':output_path.stat().st_size}
    (output_path.parent / 'owner_resolution.json').write_text(
        json.dumps(report,indent=2),encoding='utf-8')
    return report
