# -*- coding: utf-8 -*-
"""优势局被逼走：我方领先(lead0>0)时弃牌的手 —— 含对手最大注/池比与双方牌型。"""
import sys, os, glob, json, io
sys.path.insert(0, r'C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容')
from evaluator import evaluate_7, CATEGORY_NAMES
from collections import Counter
BASE = r'C:\Users\HP\WorkBuddy\德扑双人机器人测试'
PLAT='23456789TJQKA'; SUIT='cdhs'
def intern(s): return PLAT.index(s[0])*4 + SUIT.index(s[1]) + 8
def cs(cards): return ' '.join(PLAT[(c-8)//4]+SUIT[(c-8)%4] for c in cards)
def cat(hole, board):
    if not hole or len(board) < 3: return None, '-'
    try:
        v = evaluate_7(list(hole)+list(board)); return v[0], CATEGORY_NAMES.get(v[0], str(v[0]))
    except Exception: return None, '?'
paths = sorted(set(glob.glob(os.path.join(BASE,'内容','记录','*log.json'))
                   + glob.glob(r'C:\Users\HP\Downloads\botbattle*log.json')))
rows=[]
for p in paths:
    o = json.load(io.open(p, encoding='utf-8')); m=o['match']
    a=m.get('bot_a') or {}; b=m.get('bot_b') or {}
    da=str(a.get('owner_display','')); db=str(b.get('owner_display',''))
    if 'j1331' in da and 'j1331' in db: continue
    seat = 0 if 'j1331' in da else 1; opp = 1-seat
    tag = os.path.basename(p)[18:32]; cum = 0; cur = None
    for e in o['replay']['events']:
        t = e.get('type')
        if t == 'hand_start':
            cur = {'hand': e['hand'], 'lead0': cum, 'hole': {}, 'board': [], 'commit':[0,0],
                   'street':'preflop', 'fold_st':None, 'opp_max':0, 'opp_max_pot':0}
        elif t == 'deal_hole' and cur is not None:
            cur['hole'][0]=[intern(c) for c in e['holes'][0]]
            cur['hole'][1]=[intern(c) for c in e['holes'][1]]
        elif t == 'deal_board' and cur is not None:
            cur['board']=[intern(c) for c in (e.get('board') or [])]
            cur['street']=e.get('street', cur['street'])
        elif t == 'action' and cur is not None:
            pl=e.get('player'); at=e.get('action'); amt=int(e.get('amount',0) or 0)
            pot = 150 + sum(cur['commit'])
            if at in ('raise','allin'):
                if pl==seat and amt > cur['commit'][pl]: cur['commit'][pl]=amt
                elif pl==opp:
                    cur['commit'][opp]=max(cur['commit'][opp], amt)
                    if amt > cur['opp_max']: cur['opp_max']=amt; cur['opp_max_pot']=pot
            elif at=='call': cur['commit'][pl]+=amt
            if pl==seat and at=='fold' and cur['fold_st'] is None:
                cur['fold_st']=cur['street']
                cur['holeF']=dict(cur['hole']); cur['boardF']=list(cur['board'])
        elif t == 'settle' and cur is not None:
            cum += e['deltas'][seat]
            if cur['fold_st'] and cur['lead0'] > 0:
                mh=cur.get('holeF',{}).get(seat); oh=cur.get('holeF',{}).get(opp); bd=cur.get('boardF',[])
                mc,mn=cat(mh,bd); oc,on=cat(oh,bd)
                rows.append((tag, cur['hand'], cur['lead0'], cur['fold_st'], cur['opp_max'],
                             cur['opp_max_pot'], e['deltas'][seat], cs(mh), mn, on, mc, oc))
            cur = None
print('「领先时弃牌」的手数 = %d | 合计净变 %+d' % (len(rows), sum(r[6] for r in rows)))
print()
print('%-14s %4s %7s %-6s %8s %7s %9s %6s %-12s %-8s %s' % ('日志','手','lead','弃于','敌最大注','当时池','本手净变','注/池','我方底牌','我牌型','敌牌型'))
for r in sorted(rows, key=lambda x: x[6]):
    ratio = (r[4]/r[5] if r[5] else 0)
    print('%-14s %4d %7d %-6s %8d %7d %9d %6.2f %-12s %-8s %s' % (r[0],r[1],r[2],r[3],r[4],r[5],r[6],ratio,r[7],r[8],r[9]))
print()
print('弃牌街:', dict(Counter(r[3] for r in rows)))
print('我牌型:', dict(Counter(r[8] for r in rows)))
print('对手牌型:', dict(Counter(r[9] for r in rows)))
