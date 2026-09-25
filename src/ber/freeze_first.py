"""Freeze the calibrated first-submission matcher without changing its learned scores."""
import json
import shutil
from pathlib import Path
from .features import FEATURE_NAMES


def main():
    trial=json.loads(Path('reports/tuning.json').read_text(encoding='utf-8'))['depth10']
    model=Path('artifacts/tuned/depth10.cbm')
    if not model.exists():
        raise FileNotFoundError('Run python -m ber.tune first')
    destination=Path('artifacts/submission_v1')
    destination.mkdir(parents=True,exist_ok=True)
    shutil.copy2(model,destination/'mixed.cbm')
    shutil.copy2('artifacts/address_baseline/anchors.json',destination/'anchors.json')
    config={
        'threshold':trial['threshold'],
        'feature_names':FEATURE_NAMES,
        'candidate_cap':640,
        'seed':517,
        'shortlist_cap':640,
        'blocker_version':2,
        'selection':'highest measured calibration macro F0.5',
        'selected_model':'depth10',
        'calibration_macro_f0_5':trial['macro_f0_5'],
    }
    (destination/'model_config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    print(f'Frozen {destination} with threshold {config["threshold"]}')


if __name__=='__main__':
    main()
