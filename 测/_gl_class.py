# -*- coding: utf-8 -*-
"""把 4 场每一次我方 all-in 分类：doomed / 0.95也会推 / 0.80新增。"""
import sys, os, json, time, io
sys.path.insert(0, r'C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容')
import strategy as S, game_state as G, opponent as O, match_ctx as M
from botbattle_log import load_botbattle
from ranges import hand_percentile

LOGS = [r'C:\Users\HP\Downloads\botbattle-holdem-20261015125604-40fdce53-log.json',
        r'C:\Users\HP\Downloads\botbattle-holdem-20261015125758-b5b4ee0e-log.json',
        r'C:\Users\HP\Downloads\botbattle-holdem-20261015130657-65f64d5a-log.json',
        r'C:\Users\HP\Downloads\botbattle-holdem-20261015132040-a2af77d5-log.json']
PLAT='23456789TJQKA'; SUIT='cdhs'
def cs(hole):
    if not hole: return '?'
    out=[]
    for c in hole:
        i=c-8; out.append(PLAT[i//4]+SUIT[i%4])
    return ''.join(out)

# 先从日志取真实的"我方 allin"手集合 + 结果
real = {}
for p in LOGS:
    o=json.load(io.open(p,encoding='utf-8')); m=o['match']
    seat=0 if 'j1331' in str((m.get('bot_a') or {}).get('owner_display','')) else 1
    opp=1-seat
    cur=None; acted=[]
    for e in o['replay']['events']:
        t=e.get('type')
        if t=='hand_start': acted=[]; cur=None
        elif t=='action':
            acted.append((e.get('player'),e.get('action')))
            if e.get('player')==seat and e.get('action')=='allin' and cur is None:
                cur=e.get('round',0)
        elif t=='settle':
            if cur is not None:
                after=acted[-1:]
                called = any(pl==opp and ac in ('call','allin') for pl,ac in acted)
                real[(p, e['hand'])] = (called, e['deltas'][seat], e.get('reason'))

for p in LOGS:
    m=O.OpponentModel(); ctx=M.MatchContext.from_dict(m.ctx_dict)
    tag=p[-18:-11]
    print('=== %s ===' % tag)
    for req, meta in load_botbattle(p, my_seat=0):
        st=G.parse_request(req)
        try: O.build_model_from_history(m,req,st)
        except Exception: pass
        try: ctx.update(st)
        except Exception: pass
        S._DECISION_STARTED_WALL=time.time()
        key=(p, req.get('hand'))
        if key in real and st.stage=='preflop':
            lead=st.total_win_chips[st.my_id]-st.total_win_chips[st.opp_id]
            hl=S._hands_left(st); bl=S._blind_line(st,hl,own=False)
            thr95=-0.95*2*bl; thr80=-0.80*2*bl
            zo95 = lead<=thr95; zo80 = lead<=thr80
            doomed = S._match_adjust(st)=='doomed'
            called,d,rs = real[key]
            kind = 'doomed' if doomed else ('0.95也够' if zo95 else ('★0.80新增' if zo80 else '其它'))
            print('   手%-3d %-7s(pct%.2f) lead=%-6d 剩%-2d | %-9s | 对手%s 结果%+d %s' % (
                req.get('hand'), cs(st.hole), hand_percentile(st.hole), lead, hl, kind,
                '跟' if called else '弃', d, rs))
        S.decide(st, m, ctx, debug=False)
