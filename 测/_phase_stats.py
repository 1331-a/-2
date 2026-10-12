# -*- coding: utf-8 -*-
"""【临时】按「局内阶段」与「我方投入档位」拆解亏损来源。"""
import json, io, glob, os, collections

paths = sorted(glob.glob(r'C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容\记录\*log.json')
               + glob.glob(r'C:\Users\HP\Downloads\botbattle*log.json'))

rows = []   # (tag, hand, delta, my_invested, reason, my_allin, my_last_act, opp_allin)
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
    ev = o['replay']['events']
    cur = None
    for e in ev:
        t = e.get('type')
        if t == 'hand_start':
            cur = {'hand': e['hand'], 'invest': [0, 0], 'street': [0, 0],
                   'my_allin': False, 'opp_allin': False, 'last_act': None,
                   'my_invest_total': 0}
        elif t == 'action' and cur is not None:
            pl, at = e.get('player'), e.get('action')
            amt = int(e.get('amount', 0) or 0)
            if at in ('raise', 'allin'):
                cur['street'][pl] = amt
            elif at == 'call':
                cur['street'][pl] = cur['street'][pl] + amt
            if pl == seat:
                cur['last_act'] = at
                cur['my_invest_total'] = sum(cur['street'])
            if pl == seat and at == 'allin':
                cur['my_allin'] = True
            if pl == opp and at == 'allin':
                cur['opp_allin'] = True
        elif t == 'deal_board' and cur is not None:
            # 街切换：把本街投入归入总投入，重置本街
            cur['invest'][0] += cur['street'][0]
            cur['invest'][1] += cur['street'][1]
            cur['street'] = [0, 0]
        elif t == 'settle' and cur is not None:
            d = e['deltas'][seat]
            inv = cur['invest'][0] + cur['street'][0]
            rows.append((tag, cur['hand'], d, inv, e.get('reason'),
                         cur['my_allin'], cur['last_act'], cur['opp_allin']))
            cur = None

N = 70
def seg(h, n=N):
    if h < n/3: return '前期(1/3)'
    if h < 2*n/3: return '中期(2/3)'
    return '后期(末1/3)'

print('=== 按局内阶段 ===')
agg = collections.defaultdict(lambda: [0, 0, 0])   # seg -> [手数, 净变合计, 我方投入合计]
for r in rows:
    s = seg(r[1])
    agg[s][0] += 1
    agg[s][1] += r[2]
    agg[s][2] += r[3]
for s in ('前期(1/3)', '中期(2/3)', '后期(末1/3)'):
    n, d, inv = agg[s]
    print('  %-12s %3d 手 | 净变 %+8d | 我方投入 %7d | 均净变 %+7.0f' % (s, n, d, inv, d/max(1,n)))
print('  %-12s %3d 手 | 净变 %+8d | 我方投入 %7d | 均净变 %+7.0f' % (
    '合计', sum(v[0] for v in agg.values()), sum(v[1] for v in agg.values()),
    sum(v[2] for v in agg.values()), sum(v[1] for v in agg.values())/max(1,len(rows))))

print()
print('=== 按我方投入档位 ===')
def bucket(v):
    if v <= 100: return '0) 仅盲注(≤100)'
    if v <= 500: return '1) 100~500'
    if v <= 2000: return '2) 500~2000'
    if v <= 8000: return '3) 2000~8000'
    return '4) 8000+(全押级)'
b = collections.defaultdict(lambda: [0, 0])
for r in rows:
    k = bucket(r[3])
    b[k][0] += 1
    b[k][1] += r[2]
for k in sorted(b):
    n, d = b[k]
    print('  %-16s %4d 手 | 净变 %+9d | 均 %+8.0f' % (k, n, d, d/max(1,n)))

print()
print('=== 按「我方最后一次动作」（仅看有我方动作的手）===')
la = collections.defaultdict(lambda: [0, 0, 0])
for r in rows:
    if not r[6]:
        continue
    k = r[6]
    la[k][0] += 1
    la[k][1] += r[2]
    la[k][2] += r[3]
for k, v in sorted(la.items(), key=lambda x: x[1][1]):
    print('  末动作=%-10s %4d 手 | 净变 %+9d | 均 %+8.0f | 均投入 %6.0f' % (
        k, v[0], v[1], v[1]/max(1,v[0]), v[2]/max(1,v[0])))

print()
print('=== 关键：前期(手0~23) 逐手（净变 != 0 的）===')
print('  %-10s %4s %10s %10s %-10s %s' % ('场次','手','净变','我方投入','reason','末动作'))
for r in sorted([x for x in rows if x[1] < 24 and x[2] != 0], key=lambda x: (x[0], x[1])):
    print('  %-10s %4d %10d %10d %-10s %s' % (r[0], r[1], r[2], r[3], r[4], r[6]))
