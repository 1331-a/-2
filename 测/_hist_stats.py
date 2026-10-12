# -*- coding: utf-8 -*-
"""【临时】全历史对局统计：我方全押/大额投入的结果分布。

用法: python 测/_hist_stats.py
"""
import json, io, glob, os, collections

paths = sorted(glob.glob(r'C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容\记录\*log.json')
               + glob.glob(r'C:\Users\HP\Downloads\botbattle*log.json'))

PLAT = "23456789TJQKA"
SUIT = "cdhs"   # 平台 suit: 0=c 1=d 2=h 3=s


def cards_str(cs):
    return ' '.join(str(c) for c in cs)


all_shoves = []      # (file, hand, my_allin_amt, opp_fold, my_delta, hole, board)
hand_rows = []       # (file, hand, my_delta, my_invested, reason)

for p in paths:
    o = json.load(io.open(p, encoding='utf-8'))
    m = o['match']
    seat = None
    for i, k in ((0, 'bot_a'), (1, 'bot_b')):
        if 'j1331' in str((m.get(k) or {}).get('owner_display', '')):
            seat = i
    if seat is None:
        continue
    tag = os.path.basename(p)[18:32]
    ev = o['replay']['events']
    cur = None
    for e in ev:
        t = e.get('type')
        if t == 'hand_start':
            cur = {'hand': e['hand'], 'invested': [0, 0], 'street_bet': [0, 0],
                   'hole': None, 'board': [], 'my_allin': None, 'my_allin_street': None}
        elif t == 'deal_hole' and cur is not None:
            cur['hole'] = e['holes'][seat]
        elif t == 'deal_board' and cur is not None:
            cur['board'] = list(e.get('board') or [])
        elif t == 'action' and cur is not None:
            pl = e.get('player')
            at = e.get('action')
            amt = int(e.get('amount', 0) or 0)
            if at in ('raise', 'allin'):
                cur['street_bet'][pl] = amt
            elif at == 'call':
                cur['street_bet'][pl] = cur['street_bet'][pl] + amt
            if pl == seat and at == 'allin' and cur['my_allin'] is None:
                cur['my_allin'] = amt
                cur['my_allin_street'] = e.get('round', e.get('street'))
        elif t == 'settle' and cur is not None:
            d = e['deltas'][seat]
            # 记录
            if cur['my_allin'] is not None:
                all_shoves.append((tag, cur['hand'], cur['my_allin'],
                                   e.get('reason') == 'fold',
                                   d, cards_str(cur['hole'] or []),
                                   cards_str(cur['board'] or []),
                                   cur.get('my_allin_street')))
            invested = sum(cur['street_bet'])
            hand_rows.append((tag, cur['hand'], d, invested, e.get('reason')))
            cur = None

print('=== 我方全押（%d 次）===' % len(all_shoves))
print('%-12s %4s %-8s %-10s %8s %-14s %s' % ('场次', '手', '街', '对手', '我净变', '底牌', '牌面'))
for s in all_shoves:
    print('%-12s %4d %-8s %-10s %8d %-14s %s' % (
        s[0], s[1], str(s[7]), '弃牌' if s[3] else '跟注', s[4], s[5], s[6]))

fold_sh = [s for s in all_shoves if s[3]]
call_sh = [s for s in all_shoves if not s[3]]
print()
print('  对手弃牌 %d 次，合计 %+d（均 %+.0f）' % (
    len(fold_sh), sum(s[4] for s in fold_sh),
    sum(s[4] for s in fold_sh) / max(1, len(fold_sh))))
print('  对手跟注 %d 次，合计 %+d（均 %+.0f）' % (
    len(call_sh), sum(s[4] for s in call_sh),
    sum(s[4] for s in call_sh) / max(1, len(call_sh))))
print('  全押总合计 %+d' % sum(s[4] for s in all_shoves))

print()
print('=== 我方大额投入手（成交额 ≥ 3000）===')
big = [h for h in hand_rows if h[3] >= 3000]
for h in big:
    print('%-12s 手%-4d 投入%-7d 净变%-8d %s' % (h[0], h[1], h[3], h[2], h[4]))
print('  共 %d 手，合计 %+d' % (len(big), sum(h[2] for h in big)))

print()
print('=== 全部手数分布 ===')
print('  总手数 %d | 合计净变 %+d' % (len(hand_rows), sum(h[2] for h in hand_rows)))
print('  按是否摊牌:')
for r in ('fold', 'showdown'):
    sub = [h for h in hand_rows if h[4] == r]
    print('    %-10s %3d 手，合计 %+8d' % (r, len(sub), sum(h[2] for h in sub)))
