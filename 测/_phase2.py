# -*- coding: utf-8 -*-
"""【临时】只看「输的场次」的阶段净变 + fold 细分（是否主动投入后弃牌）。"""
import json, io, glob, os, collections

paths = sorted(glob.glob(r'C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容\记录\*log.json')
               + glob.glob(r'C:\Users\HP\Downloads\botbattle*log.json'))

games = []
for p in paths:
    o = json.load(io.open(p, encoding='utf-8'))
    m = o['match']
    seat = None
    for i, k in ((0, 'bot_a'), (1, 'bot_b')):
        if 'j1331' in str((m.get(k) or {}).get('owner_display', '')):
            seat = i
    if seat is None:
        continue
    opp = 1 - seat
    tag = os.path.basename(p)[18:26]
    final = m['result']['deltas'][seat]
    ev = o['replay']['events']
    cur = None
    rows = []
    for e in ev:
        t = e.get('type')
        if t == 'hand_start':
            cur = {'hand': e['hand'], 'street': [0, 0], 'invest': 0,
                   'lead': False, 'last_act': None, 'my_allin': False}
        elif t == 'action' and cur is not None:
            pl, at = e.get('player'), e.get('action')
            amt = int(e.get('amount', 0) or 0)
            if at in ('raise', 'allin'):
                cur['street'][pl] = amt
            elif at == 'call':
                cur['street'][pl] = cur['street'][pl] + amt
            if pl == seat:
                cur['last_act'] = at
                if at in ('raise', 'allin'):
                    cur['lead'] = True          # 我方主动投入过筹码
                cur['invest'] = cur['street'][seat]
            if pl == seat and at == 'allin':
                cur['my_allin'] = True
        elif t == 'settle' and cur is not None:
            rows.append({
                'hand': cur['hand'], 'delta': e['deltas'][seat],
                'invest': cur['invest'], 'reason': e.get('reason'),
                'lead': cur['lead'], 'last': cur['last_act'],
                'allin': cur['my_allin'],
            })
            cur = None
    games.append((tag, final, m['created_at'][:10], rows))

print('=== 输的场次：阶段净变 ===')
print('%-10s %-11s %-9s | %-12s %-12s %-12s' % ('场次','日期','最终','前期','中期','后期'))
for tag, final, date, rows in games:
    if final >= 0:
        continue
    seg = [0, 0, 0]
    for r in rows:
        i = 0 if r['hand'] < 70/3 else (1 if r['hand'] < 140/3 else 2)
        seg[i] += r['delta']
    print('%-10s %-11s %-9d | %-12d %-12d %-12d' % (tag, date, final, seg[0], seg[1], seg[2]))

print()
print('=== 赢的场次：阶段净变（对照）===')
for tag, final, date, rows in games:
    if final < 0:
        continue
    seg = [0, 0, 0]
    for r in rows:
        i = 0 if r['hand'] < 70/3 else (1 if r['hand'] < 140/3 else 2)
        seg[i] += r['delta']
    print('%-10s %-11s %-9d | %-12d %-12d %-12d' % (tag, date, final, seg[0], seg[1], seg[2]))

print()
print('=== fold 手细分（我方末动作 = fold）===')
cats = collections.defaultdict(lambda: [0, 0, 0])
for tag, final, date, rows in games:
    for r in rows:
        if r['last'] != 'fold':
            continue
        if r['invest'] <= 100:
            k = 'A) 只丢盲注(≤100)'
        elif r['lead']:
            k = 'B) 主动加注后弃牌'
        else:
            k = 'C) 跟注后弃牌'
        cats[k][0] += 1
        cats[k][1] += r['delta']
        cats[k][2] += r['invest']
for k in sorted(cats):
    n, d, inv = cats[k]
    print('  %-18s %4d 手 | 净变 %+9d | 均 %+7.0f | 均投入 %6.0f' % (k, n, d, d/max(1,n), inv/max(1,n)))

print()
print('=== 输的场次里，我方「主动加注后弃牌」的明细（前 30）===')
n = 0
for tag, final, date, rows in games:
    if final >= 0:
        continue
    for r in rows:
        if r['last'] == 'fold' and r['lead'] and r['invest'] > 100:
            print('  %-10s 手%-4d 净变%-8d 投入%-8d' % (tag, r['hand'], r['delta'], r['invest']))
            n += 1
            if n >= 30:
                break
    if n >= 30:
        break
