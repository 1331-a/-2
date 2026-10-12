# -*- coding: utf-8 -*-
"""【临时】归因：我方「主动下注」时的牌力，与「下注后被加注弃牌」的关系。

把每手我方第一次主动 lead 的时点记下来，用当时的 hole+board 算牌型，
再看这笔 lead 最终是「赚回」还是「被加注弃掉」。
"""
import sys, json, io, glob, os, collections
sys.path.insert(0, r'C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容')
from evaluator import evaluate_7, CATEGORY_NAMES

paths = sorted(glob.glob(r'C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容\记录\*log.json')
               + glob.glob(r'C:\Users\HP\Downloads\botbattle*log.json'))


def p2i(s):
    """平台牌字符串 -> 内部编码（内部 = 平台 + 8）。"""
    rank = "23456789TJQKA".index(s[0])
    suit = "cdhs".index(s[1])
    return rank * 4 + suit + 8


def made(hole, board):
    if len(board) >= 3:
        try:
            return CATEGORY_NAMES.get(evaluate_7(hole + board)[0], '?')
        except Exception:
            return '?'
    # 翻前：只看 pocket pair / 高张
    r = sorted(c // 4 for c in hole)
    return '口袋对' if r[0] == r[1] else '高牌'


grp = collections.defaultdict(lambda: {'n': 0, 'fold': 0, 'net': 0, 'fold_net': 0, 'sizes': []})
STREET_NAME = {'preflop': '翻前', 'flop': '翻牌', 'turn': '转牌', 'river': '河牌'}

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
    ev = o['replay']['events']
    cur = None
    for e in ev:
        t = e.get('type')
        if t == 'hand_start':
            cur = {'lead': None, 'folded_after_lead': False, 'board': [],
                   'hole': None, 'street': 'preflop', 'size': 0}
        elif t == 'deal_hole' and cur is not None:
            cur['hole'] = [p2i(c) for c in e['holes'][seat]]
        elif t == 'deal_board' and cur is not None:
            cur['board'] = [p2i(c) for c in (e.get('board') or [])]
            cur['street'] = e.get('street', cur['street'])
        elif t == 'action' and cur is not None:
            pl, at = e.get('player'), e.get('action')
            amt = int(e.get('amount', 0) or 0)
            if pl == seat and at in ('raise', 'allin') and cur['lead'] is None:
                cur['lead'] = (cur['street'], amt, list(cur['board']), list(cur['hole'] or []))
            elif cur['lead'] is not None and cur['lead'][0] == cur['street']:
                pass
            if pl == seat and at == 'fold' and cur['lead'] is not None:
                cur['folded_after_lead'] = True
        elif t == 'settle' and cur is not None:
            if cur['lead'] is not None:
                st, amt, bd, hl = cur['lead']
                cat = made(hl, bd) if hl else '?'
                is_pre = (st == 'preflop')
                key = ('翻前·%s' % ('对子' if len(set(hl)) == 1 else '非对子')) if is_pre else cat
                g = grp[key]
                g['n'] += 1
                g['sizes'].append(amt)
                g['net'] += e['deltas'][seat]
                if cur['folded_after_lead']:
                    g['fold'] += 1
                    g['fold_net'] += e['deltas'][seat]
            cur = None

print('=== 我方「主动下注」时的牌力 → 结果 ===')
print('  %-16s %5s %8s %10s %12s %10s' % ('下注时牌型', '次数', '被弃率', '总净变', '均净变', '均尺寸'))
for k in sorted(grp, key=lambda x: -grp[x]['n']):
    g = grp[k]
    print('  %-16s %5d %7.0f%% %10d %12.0f %10.0f' % (
        k, g['n'], 100*g['fold']/max(1,g['n']), g['net'], g['net']/max(1,g['n']),
        sum(g['sizes'])/max(1,len(g['sizes']))))
