# -*- coding: utf-8 -*-
"""看 >=400 的翻前动作序列：判断到底是「开池」还是「3-bet」（直接读原始事件）。"""
import glob
import json

PATH_FMT = r'C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容\记录\*log.json'
PLAT = '23456789TJQKA'
SUIT = 'cdhs'


def p2i(s):
    return PLAT.index(s[0]) * 4 + SUIT.index(s[1]) + 8


def cls_of(hole):
    r = sorted((c - 8) // 4 for c in hole)
    s = [(c - 8) % 4 for c in hole]
    if r[0] == r[1]:
        return '对子-%s' % PLAT[r[0]]
    return '%s%s%s' % (PLAT[max(r)], PLAT[min(r)], 's' if s[0] == s[1] else 'o')


paths = sorted(glob.glob(PATH_FMT) + glob.glob(r'C:\Users\HP\Downloads\botbattle*log.json'))
for p in paths:
    o = json.load(open(p, encoding='utf-8'))
    m = o['match']
    da = str((m.get('bot_a') or {}).get('owner_display', ''))
    db = str((m.get('bot_b') or {}).get('owner_display', ''))
    if 'j1331' in da and 'j1331' in db:
        continue
    seat = 0 if 'j1331' in da else 1
    tag = p.split('holdem-')[-1][:9]
    cur = None
    for e in o['replay']['events']:
        t = e.get('type')
        if t == 'hand_start':
            cur = {'hand': e['hand'], 'hole': None, 'pf': [], 'st': 'preflop'}
        elif t == 'deal_board' and cur is not None:
            cur['st'] = e.get('street', cur['st'])
        elif t == 'deal_hole' and cur is not None:
            cur['hole'] = [p2i(c) for c in e['holes'][seat]]
        elif t == 'action' and cur is not None and cur['st'] == 'preflop':
            cur['pf'].append(('我' if e.get('player') == seat else '敌',
                              e.get('action'), int(e.get('amount', 0) or 0)))
        elif t == 'settle' and cur is not None:
            # 我方首个翻前大额动作
            big = None
            opp_before = False
            for who, at, amt in cur['pf']:
                if who == '我' and at in ('raise', 'allin') and big is None:
                    big = amt
                    break
                if who == '敌' and at in ('raise', 'allin'):
                    opp_before = True
            if big and big >= 400:
                seq = ' '.join('%s%s%s' % (w, a, (amt if amt else '')) for w, a, amt in cur['pf'])
                print('%-10s 手%-3d %-8s 净变%-8d %s翻前: %s' % (
                    tag, cur['hand'], cls_of(cur['hole']), e['deltas'][seat],
                    '★3bet ' if opp_before else '开池  ', seq))
            cur = None
