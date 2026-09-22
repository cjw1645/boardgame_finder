"""Import another shop's CSV files using the same validated snapshot contract."""
import argparse
import re
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'service_app'))
from search import read_csv
from snapshots import FIELDS, publish


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--directory', required=True, type=Path)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z][a-z0-9_]*', args.source):
        parser.error('source must contain lowercase letters, digits or underscores')
    tables = {kind: read_csv(args.directory / f'{kind}_{args.source}.csv') for kind in FIELDS}
    print(publish(args.data_dir, args.source, tables))


if __name__ == '__main__':
    main()
