"""Recover exact-name matches whose provider record omits its address.

The rule is calibrated only on supplied train labels. It never introduces a
target outside the already frozen candidate set.
"""

import json
from pathlib import Path


def recover(db_path, candidate_path, matching_path, output_path):
    import duckdb

    con = duckdb.connect(str(db_path), read_only=True)
    con.execute("SET threads=4")
    unique_names = set(con.execute("""SELECT country,n FROM test
        WHERE source=1 AND n<>'' GROUP BY country,n HAVING count(*)=1""").fetchall())
    eligible = {entity_id:(country,name) for entity_id,country,name in
        con.execute("""SELECT entity_id,country,n FROM test
            WHERE source=1 AND n<>''""").fetchall()
        if (country,name) in unique_names}
    del unique_names
    blank_targets = {entity_id:(country,name) for entity_id,country,name in
        con.execute("""SELECT entity_id,country,n FROM test
            WHERE source IN (2,3) AND a='' AND n<>''""").fetchall()}
    con.close()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    added = {'France':0,'India':0,'US':0}
    changed_rows = 0
    rows = 0
    with Path(candidate_path).open(encoding='utf-8',newline='') as candidates, \
            Path(matching_path).open(encoding='utf-8',newline='') as matches, \
            output_path.with_suffix('.tmp').open('w',encoding='utf-8',newline='') as out:
        candidate_header=candidates.readline()
        matching_header=matches.readline()
        if candidate_header!='source1_entity_id\tcandidate_entity_ids\n' or \
                matching_header!='source1_entity_id\tmatched_entity_ids\n':
            raise ValueError('Unexpected submission headers')
        out.write(matching_header)
        for candidate_line, matching_line in zip(candidates,matches,strict=True):
            anchor,candidate_ids=candidate_line.rstrip('\r\n').split('\t',1)
            match_anchor,match_ids=matching_line.rstrip('\r\n').split('\t',1)
            if anchor!=match_anchor:
                raise ValueError(f'Candidate/match anchor misalignment at row {rows+1}')
            rows+=1
            if anchor not in eligible:
                out.write(matching_line)
                continue
            country,name=eligible[anchor]
            selected=set(match_ids.split(',')) if match_ids else set()
            supplements=[]
            for target in candidate_ids.split(',') if candidate_ids else ():
                if target not in selected and blank_targets.get(target)==(country,name):
                    supplements.append(target)
                    selected.add(target)
            if not supplements:
                out.write(matching_line)
                continue
            changed_rows+=1
            added[country]+=len(supplements)
            out.write(anchor+'\t'+','.join(
                ([match_ids] if match_ids else [])+supplements)+'\n')
    output_path.with_suffix('.tmp').replace(output_path)
    return {'rows':rows,'changed_rows':changed_rows,'added_by_country':added,
            'total_added':sum(added.values()),'eligible_anchors':len(eligible),
            'blank_targets':len(blank_targets),
            'output_bytes':output_path.stat().st_size}
