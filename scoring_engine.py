"""
AlphaRadar Scoring Engine — Weinstein + O'Neil + Minervini
"""
import numpy as np
import pandas as pd
from scipy.stats import percentileofscore, linregress

STAGE_CAPS = {'2A': 100, '2B': 90, '1B': 70, '1A': 55, '3': 40, '4': 20}
BUCKETS_RANGES = {'MUST_BUY': (80, 100), 'CAN_BUY': (60, 79), 'NEUTRAL': (40, 59), 'AVOID': (20, 39), 'SELL': (0, 19)}

def classify_stage(wc, wv=None):
    if len(wc) < 35:
        return {'full_stage': 'UNKNOWN', 'score': 0, 'price_vs_ma': 0, 'ma_slope': 0, 'ma_value': 0}
    ma30 = wc.rolling(30).mean()
    price, ma_now = float(wc.iloc[-1]), float(ma30.iloc[-1])
    if np.isnan(ma_now) or ma_now == 0:
        return {'full_stage': 'UNKNOWN', 'score': 0, 'price_vs_ma': 0, 'ma_slope': 0, 'ma_value': 0}
    pvm = (price - ma_now) / ma_now
    s5 = (ma30.iloc[-1] - ma30.iloc[-6]) / ma30.iloc[-6] if len(ma30.dropna()) >= 6 else 0
    s10 = (ma30.iloc[-1] - ma30.iloc[-11]) / ma30.iloc[-11] if len(ma30.dropna()) >= 11 else 0
    vt = 1.0
    if wv is not None and len(wv) >= 13:
        rv, pv = wv.iloc[-4:].mean(), wv.iloc[-13:-4].mean()
        if pv > 0: vt = rv / pv
    wr = s10 > 0.003 if len(ma30.dropna()) >= 15 else False
    if s5 > 0.003 and pvm > 0.02:
        if pvm > 0.20:
            stg, sc = '2B', max(20, min(27, 25 - min(5, (pvm - 0.20) * 30)))
        else:
            fb = 2 if s10 < 0.003 else 0
            sc = min(30, 24 + fb + min(3, s5 * 500) + (min(2, max(0, (vt-1)*5)) if vt > 1 else 0))
            stg = '2A'
    elif s5 < -0.003 and pvm < -0.02:
        stg, sc = '4', max(0, 3 - min(3, abs(pvm) * 10))
    elif abs(s5) <= 0.0045 and wr and pvm > -0.05:
        stg, sc = '3', (4 if pvm < 0 else 7)
    else:
        if (s10 < -0.003 and s5 > -0.003) and pvm > -0.05:
            pt = False
            if len(wc) >= 20:
                rr = (wc.iloc[-8:].max() - wc.iloc[-8:].min()) / ma_now
                orr = (wc.iloc[-20:-8].max() - wc.iloc[-20:-8].min()) / ma_now
                pt = rr < orr * 0.7
            if pt or pvm > 0:
                stg, sc = '1B', min(19, 15 + (2 if pvm > 0 else 0) + (2 if vt > 1.1 else 0))
            else:
                stg, sc = '1B', 13
        else:
            stg, sc = '1A', max(8, min(14, 10 + (2 if abs(pvm) < 0.05 else 0)))
    return {'full_stage': stg, 'score': round(float(sc), 1), 'price_vs_ma': round(float(pvm), 4),
            'ma_slope': round(float(s5), 6), 'ma_value': round(float(ma_now), 2)}

def compute_rs_score(sw, bw, ur=None, sr=None):
    ml = min(len(sw), len(bw))
    if ml < 52:
        return {'score': 0, 'rs_percentile': 0, 'sector_percentile': 50, 'rs_new_high': False, 'stock_52w_return': 0}
    s, b = sw.iloc[-ml:].values, bw.iloc[-ml:].values
    sc = 0.0
    rs = s / b; rs = rs / rs[0]
    rma = pd.Series(rs).rolling(min(52, len(rs)-1)).mean().values
    rvma = (rs[-1] - rma[-1]) / rma[-1] if (not np.isnan(rma[-1]) and rma[-1] > 0) else 0
    sc += min(4, rvma * 40) if rs[-1] > rma[-1] else max(0, 2 + rvma * 20)
    s52r = (s[-1] / s[-52] - 1) if len(s) >= 52 else 0
    rp = percentileofscore(ur, s52r) if ur and len(ur) > 10 else 50
    sc += (rp / 100) * 8
    lk = min(52, len(rs))
    rnh = bool(rs[-1] >= np.nanmax(rs[-lk:]) * 0.97)
    sc += 5 if rnh else (2 if rs[-1] >= np.nanmax(rs[-lk:]) * 0.90 else 0)
    tw = min(10, len(rs)-1)
    if tw >= 5:
        try:
            sn = linregress(np.arange(tw), rs[-tw:]).slope / np.mean(rs[-tw:]) * 100
            sc += min(5, sn * 5) if sn > 0 else max(0, 2 + sn * 3)
        except: pass
    sp = percentileofscore(sr, s52r) if sr and len(sr) > 5 else 50
    sc += 3 if sp > 80 else (2 if sp > 60 else (1 if sp > 40 else 0))
    return {'score': min(25, round(float(sc), 1)), 'rs_percentile': round(float(rp), 1),
            'sector_percentile': round(float(sp), 1), 'rs_new_high': rnh, 'stock_52w_return': round(float(s52r), 4)}

def compute_vp_score(dc, dv, dh, dl, wc=None, wh=None, wl=None):
    if len(dc) < 20: return {'score': 0}
    sc = 0.0; n = len(dc); cc = dc.pct_change(); va = dv.rolling(50).mean()
    lb = min(50, n); ud = dd = 0
    for i in range(-lb, 0):
        try:
            if pd.isna(cc.iloc[i]) or pd.isna(va.iloc[i]) or va.iloc[i] == 0: continue
            if cc.iloc[i] > 0 and dv.iloc[i] > va.iloc[i]: ud += 1
            elif cc.iloc[i] < 0 and dv.iloc[i] > va.iloc[i]: dd += 1
        except: pass
    t = ud + dd
    if t > 0: sc += min(5, (ud/t) * 7)
    pb = []
    for i in range(-min(20, n), 0):
        try:
            if cc.iloc[i] < -0.005 and va.iloc[i] > 0: pb.append(dv.iloc[i] / va.iloc[i])
        except: pass
    if pb:
        apv = np.mean(pb)
        sc += 4 if apv < 0.5 else (3 if apv < 0.7 else (1.5 if apv < 0.9 else 0))
    if wc is not None and len(wc) >= 8:
        rw = wc.iloc[-6:]; wr = (rw.max() - rw.min()) / rw.mean()
        sc += 3 if wr < 0.04 else (2 if wr < 0.07 else (1 if wr < 0.10 else 0))
    if wc is not None and wh is not None and len(wc) >= 12:
        pk = wh.iloc[-min(52, len(wc)):].max()
        if pk > 0:
            dp = (pk - wc.iloc[-1]) / pk
            sc += 4 if 0.05 <= dp < 0.15 else (3 if dp < 0.25 else (2 if dp < 0.35 else (2 if dp < 0.05 else 0.5)))
    if len(dh) >= 50:
        h52 = dh.iloc[-252:].max() if len(dh) >= 252 else dh.max()
        dfh = (h52 - dc.iloc[-1]) / h52 if h52 > 0 else 1
        sc += 2 if dfh < 0.03 else (1.5 if dfh < 0.08 else (0.5 if dfh < 0.15 else 0))
    return {'score': min(20, round(float(sc), 1))}

def compute_composite(stage_r, rs_r, vp_r, fund_score=7.5, cat_score=1.0):
    raw = stage_r['score'] + rs_r['score'] + vp_r['score'] + fund_score + cat_score
    fs = stage_r.get('full_stage', 'UNKNOWN')
    cap = STAGE_CAPS.get(fs, 50)
    comp = min(raw, cap)
    bucket = 'NEUTRAL'
    for bn, (lo, hi) in BUCKETS_RANGES.items():
        if lo <= comp <= hi: bucket = bn; break
    if fs == '4' and bucket not in ('SELL', 'AVOID'): bucket = 'AVOID'
    if fs == '3' and bucket == 'MUST_BUY': bucket = 'NEUTRAL'
    return {'composite_score': round(float(comp), 1), 'raw_composite': round(float(raw), 1),
            'bucket': bucket, 'stage_cap_applied': comp < raw}
