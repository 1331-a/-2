# -*- coding: utf-8 -*-
"""搏命前账本：逐手还原我方投入/动作/牌型，定位\"线上落后\"的成因。

用法: python 测/_pregamble.py <log.json> [gam_h[...]]
口径（按项目约定）:
  action.amount: raise/allin = 本街 raise-to；call = 本次增量
  我方本街投入 my_street: call 累加 / raise(allin) 取 raise-to
  牌型用 evaluate_7 原始档位（公面三条/公对会虚高，已在输出里标 *）
"""
import io
import json
import os
import sys

sys.path.insert(0, r'C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容')
from evaluator import evaluate_7, CATEGORY_NAMES  # noqa: E402

PLAT = '23456789TJQKA'
SUIT = 'cdhs'
RANKN = {c: i for i, c in enumerate(PLAT)}


def p2i(s):
    return RANKN[s[0]] * 4 + SUIT.index(s[1]) + 8


def cstr(c):
    n = c - 8          # 内部编码 = rank*4 + suit + 8
    return PLAT[n // 4] + SUIT[n % 4]


def cards_str(cs):
    return ' '.join(cstr(c) for c in cs)


def cat_of(hole, board):
    if not hole:
        return '?'
    if len(board) >= 3:
        try:
            return CATEGORY_NAMES.get(evaluate_7(hole + board)[0], '?')
        except Exception:
            return '?'
    r = sorted(c // 4 for c in hole)
    return '口袋对' if r[0] == r[1] else '高牌'


def load(path):
    o = json.load(io.open(path, encoding='utf-8'))
    m = o['match']
    seat = None
    for i, k in ((0, 'bot_a'), (1, 'bot_b')):
        if 'j1331' in str((m.get(k) or {}).get('owner_display', '')):
            seat = i
    opp = 1 - seat
    ev = o['replay']['events']
    hands = []
    cur = None
    for e in ev:
        t = e.get('type')
        if t == 'hand_start':
            sb = e.get('sb')
            cur = dict(hand=e['hand'], sb=sb, bb=e.get('bb'),
                       my_blind=50 if sb == seat else 100,
                       board=[], street='preflop', hole=None,
                       my_street=0, invested_prev=0,
                       last_act=None, first_lead=None, folded_at=None,
                       opp_at=None, acts=[])
            cur['invested'] = cur['my_blind']
        elif t == 'deal_hole' and cur is not None:
            cur['hole'] = [p2i(c) for c in e['holes'][seat]]
        elif t == 'deal_board' and cur is not None:
            cur['board'] = [p2i(c) for c in (e.get('board') or [])]
            cur['street'] = e.get('street', cur['street'])
            cur['invested_prev'] = cur['invested']
            cur['my_street'] = 0
        elif t == 'action' and cur is not None:
            pl = e.get('player')
            at = e.get('action')
            amt = int(e.get('amount', 0) or 0)
            if pl == seat:
                if at == 'call':
                    cur['my_street'] += amt
                elif at in ('raise', 'allin'):
                    cur['my_street'] = amt
                cur['invested'] = cur['invested_prev'] + cur['my_street']
                cur['last_act'] = (cur['street'], at, amt)
                if at in ('raise', 'allin') and cur['first_lead'] is None:
                    cur['first_lead'] = (cur['street'], at, amt)
                if at == 'fold' and cur['folded_at'] is None:
                    cur['folded_at'] = cur['street']
                cur['acts'].append((cur['street'], at, amt, cur['invested']))
            elif pl == opp:
                if cur['opp_at'] is None and at in ('raise', 'allin'):
                    cur['opp_at'] = (cur['street'], at, amt)
        elif t == 'settle' and cur is not None:
            cur['delta'] = e['deltas'][seat]
            cur['reason'] = e.get('reason')
            hands.append(cur)
            cur = None
    return m, seat, hands


def main():
    path = sys.argv[1]
    m, seat, hands = load(path)
    print('日志 =', os.path.basename(path))
    print('我方座位 =', seat, '| 对手 =', (m.get('bot_%s' % ('b' if seat == 0 else 'a')) or {}).get('display_name'))
    print('结果 =', m['result'], '| reason =', m.get('reason'), '| 技术判负 =', m.get('technical_loss'))
    print()
    cum = 0
    print('%-5s %-9s %-9s %-10s %-22s %-9s %-11s %s' % (
        '手', '我方累计前', '本手', '累计后', '我方动作序列', '投入', '牌型(终局)', '对手加注'))
    for h in hands:
        before = cum
        cum += h['delta']
        seq = ' '.join('%s%s%s' % (s[:2], a, ('%d' % n) if n else '') for s, a, n, _ in h['acts'])
        oa = h['opp_at']
        oas = ('%s%s%d' % (oa[0][:2], oa[1], oa[2])) if oa else '-'
        flag = ''
        if h['delta'] < 0 and h['last_act'] and h['last_act'][1] == 'fold':
            flag = '  << 弃牌'
        print('%-5d %-9d %-9d %-10d %-22s %-9d %-11s %-8s%s' % (
            h['hand'], before, h['delta'], cum, seq[:22], h['invested'],
            cat_of(h['hole'], h['board']), oas, flag))
    print()
    print('最终累计 =', cum)


if __name__ == '__main__':
    main()
