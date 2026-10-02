"""Apply the exact submitted V13 country-specific ownership gates."""
import json
from pathlib import Path

import modal
from pipeline.modal_app import image, volume, VOLUME_ROOT

app = modal.App('team517-v13-final-owner')
image = image.add_local_python_source('pipeline.modal_app')


@app.function(image=image, volumes={str(VOLUME_ROOT): volume},
              cpu=4, memory=16384, timeout=3600)
def run():
    from ber.predict import sha256
    from ber.resolve_owner import resolve
    from ber.validate import validate
    base = VOLUME_ROOT / 'project/output'
    source = base / 'submission_v6_blank_recovery/matching_results.tsv'
    candidates = base / 'submission_v5_neural32/candidate_pairs.tsv'
    db = VOLUME_ROOT / 'project/artifacts/data_v3.duckdb'
    destination = base / 'submission_v13_owner_country'
    destination.mkdir(parents=True, exist_ok=True)
    result = resolve(db, source, destination / 'matching_results.tsv', 50., 5.,
                     {'US': (20., 2.), 'France': (20., 2.)})
    # Hard link the immutable blocking result: matching never creates candidates.
    linked = destination / 'candidate_pairs.tsv'
    if not linked.exists():
        try:
            linked.hardlink_to(candidates)
        except OSError:
            import shutil
            shutil.copy2(candidates, linked)
    result['validation'] = validate(db, destination, check_ids=True)
    result['matching_sha256'] = sha256(destination / 'matching_results.tsv')
    result['candidate_sha256'] = sha256(linked)
    (destination / 'completion.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    volume.commit()
    return result


@app.local_entrypoint()
def main():
    result = run.remote()
    Path('reports/v13_owner_resolution.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2), flush=True)
