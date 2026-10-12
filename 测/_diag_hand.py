# -*- coding: utf-8 -*-
"""【临时诊断】重放指定对局日志，定位某手决策走的规则路径。

用法:
    python 测/_diag_hand.py <log.json> <hand0based>
"""
import sys, io, json
sys.path.insert(0, r'C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容')

import strategy as S
import game_state as G
import opponent as O
import match_ctx as M
from botbattle_log import load_botbattle

path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Users\HP\Downloads\botbattle-holdem-20261012170738-4895b988-log.json'
TARGET = int(sys.argv[2]) if len(sys.argv) > 2 else 44

o = json.load(io.open(path, encoding='utf-8'))
seat = 0
for i, k in ((0, 'bot_a'), (1, 'bot_b')):
    if 'j1331' in str((o.get('match') or {}).get(k, {}).get('owner_display', '')):
        seat = i
print('我方座位 =', seat, '| 目标手(0-based) =', TARGET)

m = O.OpponentModel()
ctx = M.MatchContext.from_dict(m.ctx_dict)
n = 0
for req, meta in load_botbattle(path, my_seat=seat):
    st = G.parse_request(req)
    try:
        O.build_model_from_history(m, req, st)
    except Exception as e:
        pass
    try:
        ctx.update(st)
    except Exception:
        pass
    h = req.get('hand')   # ★ req['hand'] 才是平台 0-based 值；meta['hand'] 是 +1 的显示值
    if h == TARGET:
        print()
        print('===== 命中平台 hand %s（meta=%s）=====' % (TARGET, meta))
        print('  stage=%s  hole=%s  board=%s' % (st.stage, st.hole, st.board))
        print('  my_chips=%s  opp_chips=%s  pot=%s  to_call=%s  my_left=%s' % (
            st.my_chips, st.opp_chips, st.pot, st.to_call, st.my_left))
        print('  is_button=%s  my_id=%s  opp_id=%s' % (st.is_button, st.my_id, st.opp_id))
        print('  total_win_chips=%s' % (st.total_win_chips,))
        print('  max_hand=%s  hand=%s' % (getattr(st, 'max_hand', '?'), getattr(st, 'hand_num', '?')))
        print('  _hands_left =', S._hands_left(st))
        print('  _match_adjust =', S._match_adjust(st))
        print('  BIG/SB =', getattr(st, 'big_blind', '?'), getattr(st, 'small_blind', '?'))
        # 尝试各入口
        for nm in ('_lock_win_unified', '_gamble_plan', '_profit_lock_allin'):
            fn = getattr(S, nm, None)
            if fn is None:
                continue
            try:
                print('  %-20s -> %s' % (nm, fn(st, m)))
            except TypeError:
                try:
                    print('  %-20s -> %s' % (nm, fn(st)))
                except Exception as e:
                    print('  %-20s -> ERR %r' % (nm, e))
            except Exception as e:
                print('  %-20s -> ERR %r' % (nm, e))
        print('  --- 实际 decide ---')
        a = S.decide(st, m, ctx, debug=True)
        print('  decide =', a)
    else:
        S.decide(st, m, ctx, debug=False)
    n += 1
print()
print('总决策点 =', n)
