# -*- coding: utf-8 -*-
"""
按双指针贪心扫描对齐行为数据与眼动数据。
行为数据为完整参考，眼动数据为可能缺失的观测流。
"""

import csv
import os
from collections import defaultdict

BEHAVE_PATH = r"D:\PHD\find\Projects\rcsci\precheck\mine\behave.csv"
EYE_PATH    = r"D:\PHD\find\Projects\rcsci\precheck\mine\merged.csv"
OUTPUT_DIR  = r"D:\PHD\find\Projects\rcsci\precheck\mine"


def detect_sep(path):
    with open(path, 'r', encoding='utf-8-sig', errors='replace') as f:
        line = f.readline()
    t, c, s = line.count('\t'), line.count(','), line.count(';')
    if t >= c and t >= s:
        return '\t'
    if c >= s:
        return ','
    return ';'


# ========== 读取行为数据 ==========
behave_sep = detect_sep(BEHAVE_PATH)
print(f"[行为] 分隔符: {repr(behave_sep)}")
with open(BEHAVE_PATH, 'r', encoding='utf-8-sig', newline='') as f:
    reader = csv.DictReader(f, delimiter=behave_sep)
    behave_rows = list(reader)
print(f"[行为] 行数: {len(behave_rows)}")

# 构建行为事件流
stim_map = {'o': 101, 's': 102, 'n': 103, 'f': 103}
resp_map = {'down': 104, 'left': 105, 'right': 106, 'none': 107}

events = []
for ri, row in enumerate(behave_rows):
    tt = (row.get('trialType') or '').strip().lower()
    mrun = (row.get('mrun') or '').strip()
    trial = (row.get('trial') or '').strip()
    resp_raw = (row.get('resp') or '').strip()

    if tt in ('rest', 'rest_between'):
        events.append({'type': 'REST', 'expected': 108, 'row_idx': ri,
                       'mrun': mrun, 'trial': trial, 'trialType': tt, 'resp': resp_raw})
    elif tt in stim_map:
        events.append({'type': 'STIM', 'expected': stim_map[tt], 'row_idx': ri,
                       'mrun': mrun, 'trial': trial, 'trialType': tt, 'resp': resp_raw})
        rl = resp_raw.lower() if resp_raw else 'none'
        events.append({'type': 'RESP', 'expected': resp_map.get(rl, 107), 'row_idx': ri,
                       'mrun': mrun, 'trial': trial, 'trialType': tt, 'resp': resp_raw})

print(f"[行为] 事件流长度: {len(events)}")


# ========== 读取眼动数据 ==========
eye_sep = detect_sep(EYE_PATH)
print(f"[眼动] 分隔符: {repr(eye_sep)}")
with open(EYE_PATH, 'r', encoding='utf-8-sig', newline='') as f:
    reader = csv.reader(f, delimiter=eye_sep)
    header = next(reader)

udp_idx = ts_idx = rec_idx = tod_idx = None
for i, c in enumerate(header):
    cl = c.lower()
    if udp_idx is None and 'udp' in cl and 'receive' in cl:
        udp_idx = i
    if ts_idx is None and 'recording' in cl and 'stamp' in cl:
        ts_idx = i
    if rec_idx is None and 'record' in cl and 'name' in cl:
        rec_idx = i
    if tod_idx is None and 'time of day' in cl:
        tod_idx = i

print(f"[眼动] udp_idx={udp_idx}, ts_idx={ts_idx}, rec_idx={rec_idx}, tod_idx={tod_idx}")
assert udp_idx is not None and ts_idx is not None and rec_idx is not None and tod_idx is not None

# 收集 marker
markers = []
subject = ''
with open(EYE_PATH, 'r', encoding='utf-8-sig', newline='') as f:
    reader = csv.reader(f, delimiter=eye_sep)
    next(reader)
    for line_no, row in enumerate(reader, start=2):
        if len(row) <= max(udp_idx, ts_idx, rec_idx):
            continue
        rec = row[rec_idx].strip()
        if not subject and rec:
            subject = rec.split('_')[0] if '_' in rec else rec

        v = row[udp_idx].strip()
        if not v or v.lower() == 'nan':
            continue
        try:
            mv = int(float(v))
        except ValueError:
            continue
        if mv < 101 or mv > 108:
            continue
        try:
            ts = float(row[ts_idx])
        except ValueError:
            ts = 0.0
        tod = row[tod_idx].strip() if len(row) > tod_idx else ''
        markers.append((line_no, rec, ts, mv, tod))

print(f"[眼动] 标记数: {len(markers)}")
print(f"[眼动] subject: {subject}")


# ========== 主对齐 ==========
missing_records = []
extra_records = []
trial_matches = {}
e_ptr = 0
N_events = len(events)

for (line_no, rec, ts, mv, tod) in markers:
    if mv == 108:
        if e_ptr >= N_events:
            extra_records.append({'mrun': '', 'rec': rec, 'ts': ts, 'v': 108,
                                  'note': '行为事件流已走完'})
            continue
        cur = events[e_ptr]
        tt = cur['trialType']
        if tt in ('rest', 'rest_between'):
            e_ptr += 1
        elif tt in stim_map:
            try:
                trial_int = int(float(cur['trial'])) if cur['trial'] else -1
            except (ValueError, TypeError):
                trial_int = -1
            if trial_int != 1:
                missing_records.append({
                    'mrun': cur['mrun'], 'trial': cur['trial'],
                    'trialType': cur['trialType'], 'resp': cur['resp'],
                    'type': 'run_start_unmatched', 'expected': 108,
                    'eyeMarkerValue': mv, 'eyeTimeOfDay': tod,
                    'note': '该 108 未能匹配 REST/REST_BETWEEN，且对应 trial 非 1'
                })
        continue

    # 101-107
    found = False
    while e_ptr < N_events:
        cur = events[e_ptr]
        if cur['expected'] == mv:
            row_idx = cur['row_idx']
            if row_idx not in trial_matches:
                trial_matches[row_idx] = {'stim': None, 'resp': None, 'row_idx': row_idx}
            if cur['type'] == 'STIM':
                trial_matches[row_idx]['stim'] = (line_no, rec, ts)
            elif cur['type'] == 'RESP':
                trial_matches[row_idx]['resp'] = (line_no, rec, ts)
            e_ptr += 1
            found = True
            break
        else:
            mtype = 'stim' if cur['type'] == 'STIM' else ('resp' if cur['type'] == 'RESP' else 'rest_skipped')
            missing_records.append({
                'mrun': cur['mrun'], 'trial': cur['trial'],
                'trialType': cur['trialType'], 'resp': cur['resp'],
                'type': mtype, 'expected': cur['expected'],
                'eyeMarkerValue': mv, 'eyeTimeOfDay': tod,
                'note': ''
            })
            e_ptr += 1
    if not found:
        extra_records.append({'mrun': '', 'rec': rec, 'ts': ts, 'v': mv,
                              'note': '行为事件流已走完，找不到匹配'})

# 尾部
while e_ptr < N_events:
    cur = events[e_ptr]
    mtype = 'stim' if cur['type'] == 'STIM' else ('resp' if cur['type'] == 'RESP' else 'rest_skipped')
    missing_records.append({
        'mrun': cur['mrun'], 'trial': cur['trial'],
        'trialType': cur['trialType'], 'resp': cur['resp'],
        'type': mtype, 'expected': cur['expected'],
        'eyeMarkerValue': 'EOF', 'eyeTimeOfDay': '',
        'note': '尾部剩余'
    })
    e_ptr += 1

print(f"[对齐] 缺失 marker: {len(missing_records)}")
print(f"[对齐] 多余 marker: {len(extra_records)}")
print(f"[对齐] 匹配 trial: {len(trial_matches)}")


# ========== 输出缺失报告 ==========
missing_path = os.path.join(OUTPUT_DIR, f"missing_trials_{subject}.csv")
with open(missing_path, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['subject', 'mrun', 'trial', 'trialType', 'resp',
                     'missingMarkerType', 'expectedMarkerValue',
                     'eyeMarkerValue', 'eyeTimeOfDay', 'note'])
    for r in missing_records:
        writer.writerow([subject, r['mrun'], r['trial'], r['trialType'], r['resp'],
                         r['type'], r['expected'],
                         r.get('eyeMarkerValue', ''), r.get('eyeTimeOfDay', ''),
                         r['note']])
print(f"[输出] {missing_path}")


# ========== 输出多余 marker（仅在非空时） ==========
if extra_records:
    extra_path = os.path.join(OUTPUT_DIR, f"extra_markers_{subject}.csv")
    with open(extra_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['subject', 'mrun', 'eye_record_name', 'eye_timestamp',
                         'marker_value', 'note'])
        for r in extra_records:
            writer.writerow([subject, r['mrun'], r['rec'], r['ts'], r['v'], r['note']])
    print(f"[输出] {extra_path}")


# ========== 切片提取 ==========
slices = []
for row_idx, m in trial_matches.items():
    if m['stim'] is None:
        continue
    stim_line, stim_rec, stim_ts = m['stim']
    b_row = behave_rows[row_idx]
    if m['resp'] is not None:
        _, _, resp_ts = m['resp']
        start_ts = stim_ts - 200.0
        end_ts = resp_ts + 200.0
    else:
        rt_raw = b_row.get('rt', '')
        try:
            rt_ms = float(rt_raw) if rt_raw else 0.0
        except ValueError:
            rt_ms = 0.0
        start_ts = stim_ts - 200.0
        end_ts = stim_ts + rt_ms + 200.0
    slices.append({
        'rec': stim_rec, 'start': start_ts, 'end': end_ts,
        'mrun': b_row.get('mrun', ''), 'trial': b_row.get('trial', ''),
        'trialType': b_row.get('trialType', ''), 'stim': b_row.get('stim', ''),
        'resp': b_row.get('resp', ''), 'acc': b_row.get('acc', ''),
        'rt': b_row.get('rt', '')
    })

slices_by_rec = defaultdict(list)
for s in slices:
    slices_by_rec[s['rec']].append(s)
for rec in slices_by_rec:
    slices_by_rec[rec].sort(key=lambda x: x['start'])

ptr_by_rec = defaultdict(int)

aligned_path = os.path.join(OUTPUT_DIR, f"aligned_eye_{subject}.csv")
with open(aligned_path, 'w', encoding='utf-8-sig', newline='') as fout:
    writer = csv.writer(fout)
    writer.writerow(header + ['mrun', 'trial', 'trialType', 'stim', 'resp', 'acc', 'rt'])

    written = 0
    with open(EYE_PATH, 'r', encoding='utf-8-sig', newline='') as fin:
        reader = csv.reader(fin, delimiter=eye_sep)
        next(reader)
        for row in reader:
            if len(row) <= max(udp_idx, ts_idx, rec_idx):
                continue
            rec = row[rec_idx].strip()
            try:
                ts = float(row[ts_idx])
            except ValueError:
                continue
            if rec not in slices_by_rec:
                continue
            slist = slices_by_rec[rec]
            ptr = ptr_by_rec[rec]
            while ptr < len(slist) and slist[ptr]['end'] < ts:
                ptr += 1
            ptr_by_rec[rec] = ptr
            if ptr >= len(slist):
                continue
            s = slist[ptr]
            if s['start'] <= ts <= s['end']:
                writer.writerow(row + [s['mrun'], s['trial'], s['trialType'],
                                       s['stim'], s['resp'], s['acc'], s['rt']])
                written += 1

print(f"[输出] {aligned_path}  (行数: {written})")
print("=" * 50)
print(f"总 trial:    {len(behave_rows)}")
print(f"匹配 trial:  {len(trial_matches)}")
print(f"缺失 marker: {len(missing_records)}")
print(f"多余 marker: {len(extra_records)}")
print("=" * 50)