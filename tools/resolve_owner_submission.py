"""Resolve confidently conflicting predicted target owners in a submission."""

import argparse
import json
from pathlib import Path

from ber.resolve_owner import resolve


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--matching', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--min-address', type=float, default=70)
    parser.add_argument('--min-margin', type=float, default=10)
    parser.add_argument('--country-gate', action='append', default=[],
                        help='Override as COUNTRY:MIN_ADDRESS:MIN_MARGIN')
    args = parser.parse_args()
    country_gates={}
    for item in args.country_gate:
        country,address,margin=item.split(':')
        if country in country_gates or country not in ('France','India','US'):
            raise ValueError('Invalid or duplicate country gate')
        country_gates[country]=(float(address),float(margin))
    print(json.dumps(resolve(args.db, args.matching, args.output,
                             args.min_address, args.min_margin,country_gates), indent=2))


if __name__ == '__main__':
    main()
