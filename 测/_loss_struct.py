# -*- coding: utf-8 -*-
"""【临时】精确拆解亏损结构：摊牌明细 / 全押被跟明细 / 位置分布。"""
import json, io, glob, os, collections

paths = sorted(glob.glob(r'C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容\记录\*log.json')
               + glob.glob(r'C:\Users\HP\Downloads\botbattle*log.json'))

SD = []      # 摊牌: (tag, hand, delta, hole, board, my_inv, opp_inv)
SHOVE_CALL = []   # 我方全押被跟: (tag, hand, delta, hole_me, hole_opp, board)
SHOVE_FOLD = 0
SHOVE_FOLD_SUM = 0
MY_ALLIN_BY_POS = collections.Counter()
OPP_ALLIN_ME = []   # 对手全押时我方动作

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
            cur = {'hand': e['hand'], 'holes': None, 'board': [], 'invest': [0, 0],
                   'street_bet': [0, 0], 'sb': e.get('sb'), 'my_allin': False,
                   'opp_allin': False, 'my_act_after_opp_allin': None,
                   'actions': []}
        elif t == 'deal_hole' and cur is not None:
            cur['holes'] = [e['holes'][0], e['holes'][1]]
        elif t == 'deal_board' and cur is not None:
            cur['board'] = list(e.get('board') or [])
        elif t == 'action' and cur is not None:
            pl, at = e.get('player'), e.get('action')
            amt = int(e.get('amount', 0) or 0)
            cur['actions'].append((pl, at, amt, e.get('round', e.get('street'))))
            if at in ('raise', 'allin'):
                cur['street_bet'][pl] = amt
            elif at == 'call':
                cur['street_bet'][pl] = cur['street_bet'][pl] + amt
            if pl == seat and at == 'allin':
                cur['my_allin'] = True
            if pl == opp and at == 'allin':
                cur['opp_allin'] = True
            if cur['opp_allin'] and pl == seat and cur['my_act_after_opp_allin'] is None:
                cur['my_act_after_opp_allin'] = (at, amt)
        elif t == 'settle' and cur is not None:
            d = e['deltas'][seat]
            reason = e.get('reason')
            me_inv, op_inv = sum(cur['street_bet']), 0
            if reason == 'showdown':
                SD.append((tag, cur['hand'], d,
                           ' '.join(cur['holes'][seat]), ' '.join(cur['holes'][opp]),
                           ' '.join(cur['board']), cur['sb'] == seat))
            if cur.get('my_allin'):
                if reason == 'showdown':
                    SHOVE_CALL.append((tag, cur['hand'], d,
                                       ' '.join(cur['holes'][seat]),
                                       ' '.join(cur['holes'][opp]),
                                       ' '.join(cur['board']), cur['sb'] == seat))
                else:
                    SHOVE_FOLD += 1
                    SHOVE_FOLD_SUM += d
                    MY_ALLIN_BY_POS['SB' if cur['sb'] == seat else 'BB'] += 1
            if cur.get('opp_allin') and cur['my_act_after_opp_allin'] is not None:
                OPP_ALLIN_ME.append((tag, cur['hand'],
                                     cur['my_act_after_opp_allin'][0], d,
                                     ' '.join(cur['holes'][seat]),
                                     cur['sb'] == seat))
            cur = None

print('=== A. 摊牌明细（%d 手）===' % len(SD))
tot = 0
for s in sorted(SD, key=lambda x: x[2]):
    tot += s[2]
    print('  %-9s 手%-4d 净变%-8d 我[%s] 对[%s] 面[%s] %s' % (
        s[0], s[1], s[2], s[3], s[4], s[5], '我SB' if s[6] else '我BB'))
print('  摊牌合计 %+d' % tot)

print()
print('=== B. 我方全押：被跟注（%d 次）===' % len(SHOVE_CALL))
t2 = 0
for s in SHOVE_CALL:
    t2 += s[2]
    print('  %-9s 手%-4d 净变%-8d 我[%s] vs 对[%s] 面[%s] %s' % (
        s[0], s[1], s[2], s[3], s[4], s[5], '我SB' if s[6] else '我BB'))
print('  被跟合计 %+d' % t2)
print('=== C. 我方全押：对手弃牌 %d 次，合计 %+d（均 %+.0f）===' % (
    SHOVE_FOLD, SHOVE_FOLD_SUM, SHOVE_FOLD_SUM / max(1, SHOVE_FOLD)))
print('  全押位置分布:', dict(MY_ALLIN_BY_POS))

print()
print('=== D. 对手全押 → 我方应对（%d 次）===' % len(OPP_ALLIN_ME))
cnt = collections.Counter(a[2] for a in OPP_ALLIN_ME)
print('  动作分布:', dict(cnt))
for a in OPP_ALLIN_ME:
    if a[2] in ('call', 'allin'):
        print('  %-9s 手%-4d 我%-6s 净变%-8d 我[%s] %s' % (
            a[0], a[1], a[2], a[3], a[4], '我SB' if a[5] else '我BB'))
