#!/usr/bin/env python3
"""
ecm_period.py — Panda ECM Workforce System, canonical classifier.

Turns a monthly employee master (.xlsx) into one ECM "period record" that matches
exactly what the dashboard's in-browser classifier produces. Use it to validate a
file before upload, to back-fill history in bulk, or to push straight to the
Apps Script backend without opening the browser.

Usage:
    python ecm_period.py master.xlsx --label "Jul 26" --cadence monthly
    python ecm_period.py master.xlsx --label "Jul 26" --cadence monthly \
        --post https://script.google.com/macros/s/XXXX/exec --token CHANGE-ME-TOKEN

Required columns in the master sheet:
    Type, DesigName, DeptName  (SecName, OGross, JDate, Name, EmpID recommended)

Output: prints the period record as JSON (and POSTs it if --post is given).
"""
import argparse, json, re, sys

SUPPORT_DEPTS = {'account & finiance', 'accountant', 'administration',
                 'human resources management', 'merchandising', 'procurement',
                 'sales', 'panda garden'}
LAB_SUPPORT = ['loader', 'cleaner', 'sweeper', 'seweep', 'security', 'fire',
               'driver', 'delivery', 'vehicle', 'fork lift', 'plumber', 'helper',
               'store keeper', 'encoder', 'medical', 'garden']


def norm(s):
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', str(s).lower())).strip()


def classify(typ, dept, desig):
    """ECM segment: Q1 Labour-Ops, Q2 Labour-Support, Q3 Staff-Ops, Q4 Staff-Support."""
    is_staff = norm(typ) == 'staff'
    d, g = norm(dept), norm(desig)
    if is_staff:
        func = 'Support' if (d in SUPPORT_DEPTS or d in ('ware house', 'transport')) \
            else ('Operations' if d in ('production', 'maintenance', 'quality assurance') else 'Support')
    else:
        if any(k in g for k in LAB_SUPPORT):
            func = 'Support'
        elif d in ('production', 'quality assurance'):
            func = 'Operations'
        else:
            func = 'Support'
    return {('Staff', 'Operations'): 'Q3', ('Staff', 'Support'): 'Q4',
            ('Worker', 'Operations'): 'Q1', ('Worker', 'Support'): 'Q2'}[
        ('Staff' if is_staff else 'Worker', func)]


def build_period(path, label):
    import pandas as pd
    df = pd.read_excel(path)
    for col in ('Type', 'DesigName', 'DeptName'):
        if col not in df.columns:
            sys.exit(f'ERROR: master file is missing required column "{col}".')
    if 'OGross' not in df.columns:
        df['OGross'] = 0

    df['ECM'] = df.apply(lambda r: classify(r['Type'], r['DeptName'], r['DesigName']), axis=1)
    head = {q: int((df['ECM'] == q).sum()) for q in ('Q1', 'Q2', 'Q3', 'Q4')}
    cost = {q: float(df[df['ECM'] == q]['OGross'].fillna(0).sum()) for q in head}
    tot = len(df)
    payroll = float(df['OGross'].fillna(0).sum())

    return {
        'label': label,
        'total': tot,
        'head': head,
        'cost': {q: round(cost[q]) for q in cost},
        'payroll': round(payroll),
        'opsSupport': round((head['Q1'] + head['Q3']) / max(1, head['Q2'] + head['Q4']), 2),
        'q3pct': round(head['Q3'] / tot * 100, 1),
        'q4pct': round(head['Q4'] / tot * 100, 1),
        'directIndirect': round(head['Q1'] / max(1, head['Q2']), 1),
        'recon': False,
    }


def main():
    ap = argparse.ArgumentParser(description='Build an ECM period record from a master xlsx.')
    ap.add_argument('xlsx', help='path to the monthly employee master (.xlsx)')
    ap.add_argument('--label', required=True, help='period label, e.g. "Jul 26"')
    ap.add_argument('--cadence', default='monthly', choices=['monthly', 'quarterly', 'yearly'])
    ap.add_argument('--post', help='Apps Script /exec URL to push the record to')
    ap.add_argument('--token', help='upload token (must match the backend TOKEN)')
    a = ap.parse_args()

    period = build_period(a.xlsx, a.label)
    print(json.dumps(period, indent=2, ensure_ascii=False))

    fl = 10.0
    if period['q3pct'] < fl:
        print(f'\n[!] Q3 share {period["q3pct"]}% is below the {fl}% healthy floor — '
              'supervision/QC cover is thin for this period.', file=sys.stderr)

    if a.post:
        import urllib.request
        body = json.dumps({'token': a.token or '', 'cadence': a.cadence, 'period': period}).encode()
        req = urllib.request.Request(a.post, data=body,
                                     headers={'Content-Type': 'text/plain;charset=utf-8'})
        with urllib.request.urlopen(req) as r:
            print('\nbackend:', r.read().decode())


if __name__ == '__main__':
    main()
