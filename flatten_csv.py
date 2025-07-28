#!/usr/bin/env python3
"""
Aplatit tous les CSV d’un dossier Mongo « bruts » en CSV plats avec clés dot+indice.
Usage :
  python flatten_csv.py --in_dir /path/raw_csv --out_dir /path/csv_flat
"""
import os, json, argparse
import pandas as pd

def flatten_record(rec, sep='.'):
    flat = {}
    def _flatten(obj, prefix=''):
        if isinstance(obj, dict):
            for k, v in obj.items():
                _flatten(v, f"{prefix}{k}{sep}")
        elif isinstance(obj, list):
            # liste de scalaires ?
            if all(not isinstance(x, (dict, list)) for x in obj):
                flat[prefix[:-1]] = "|".join(str(x) for x in obj)
            else:
                for idx, item in enumerate(obj):
                    _flatten(item, f"{prefix}{idx}{sep}")
        else:
            flat[prefix[:-1]] = obj
    _flatten(rec)
    return flat

def process_file(in_path, out_path):
    df = pd.read_csv(in_path, dtype=str, keep_default_na=False)
    rows = []
    for rec in df.to_dict(orient='records'):
        if len(rec)==1:
            only = next(iter(rec))
            try:
                obj = json.loads(rec[only])
            except:
                obj = rec
        else:
            obj = rec
        rows.append(flatten_record(obj))
    pd.DataFrame(rows).to_csv(out_path, index=False)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--in_dir",  required=True, help="CSV bruts")
    p.add_argument("--out_dir", required=True, help="CSV plats")
    args = p.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    for f in os.listdir(args.in_dir):
        if not f.endswith(".csv"): continue
        print(f"Aplatissage {f}")
        process_file(os.path.join(args.in_dir,f),
                     os.path.join(args.out_dir,f))

if __name__=="__main__":
    main()
