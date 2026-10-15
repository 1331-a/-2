# -*- coding: utf-8 -*-
import sys, os, time
sys.path.insert(0, r'C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容')
import strategy as S, game_state as G, opponent as O, match_ctx as M
from botbattle_log import load_botbattle
print('DOOM_LOCK_ON=%s FRAC=%s' % (S.DOOM_LOCK_ON, S.DOOM_LOCK_FRAC))
LOGS = [r'C:\Users\HP\Downloads\botbattle-holdem-20261015125604-40fdce53-log.json',
        r'C:\Users\HP\Downloads\botbattle-holdem-20261015125758-b5b4ee0e-log.json',
        r'C:\Users\HP\Downloads\botbattle-holdem-20261015130657-65f64d5a-log.json',
        r'C:\Users\HP\Downloads\botbattle-holdem-20261015132040-a2af77d5-log.json']
tot = 0
for p in LOGS:
    m = O.OpponentModel(); ctx = M.MatchContext.from_dict(m.ctx_dict)
    n = 0; hands = []
    for req, meta in load_botbattle(p, my_seat=0):
        st = G.parse_request(req)
        try: O.build_model_from_history(m, req, st)
        except Exception: pass
        try: ctx.update(st)
        except Exception: pass
        S._DECISION_STARTED_WALL = time.time()
        a = S.decide(st, m, ctx, debug=False)
        if a.get('act') == 'allin':
            n += 1; hands.append(req.get('hand'))
    tot += n
    print('  %-9s 我方 allin %d 次 %s' % (p[-18:-11], n, hands[:12]))
print('合计 %d 次' % tot)
