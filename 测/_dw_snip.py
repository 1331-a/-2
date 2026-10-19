
import sys, time, json, glob, os
sys.path.insert(0, r"C:\Users\HP\WorkBuddy\德扑双人机器人测试\内容")
import strategy as S, game_state as G, opponent as O, match_ctx as M
from botbattle_log import load_botbattle
BASE = r"C:\Users\HP\WorkBuddy\德扑双人机器人测试"
paths = sorted(set(glob.glob(os.path.join(BASE,"内容","记录","*log.json"))
                   + glob.glob(r"C:\Users\HP\Downloads\botbattle*log.json")))
out = []
for p in paths:
    o = json.load(open(p, encoding="utf-8")); m0 = o.get("match") or {}
    da = str((m0.get("bot_a") or {}).get("owner_display",""))
    db = str((m0.get("bot_b") or {}).get("owner_display",""))
    _owners = [da, db]
    _hits = [i for i, v in enumerate(_owners) if "j1331" in v]
    if len(_hits) == 1:
        seat = _hits[0]
    else:
        # 人机对局：双方 owner 都可能是 j1331，用 human_seat 反推 bot 座位
        _hs = m0.get("human_seat")
        if _hs is None:
            continue
        seat = 1 - int(_hs)
    m = O.OpponentModel(); ctx = M.MatchContext.from_dict(m.ctx_dict)
    try:
        for req, meta in load_botbattle(p, my_seat=seat):
            st = G.parse_request(req)
            try: O.build_model_from_history(m, req, st)
            except Exception: pass
            try: ctx.update(st)
            except Exception: pass
            S._DECISION_STARTED_WALL = time.time()
            S._LAST_REQ_INFO = None
            a = S.decide(st, m, ctx, debug=False)
            out.append("%s|%s|%s|%s|%s" % (os.path.basename(p)[18:32], req.get("hand"),
                                            st.stage, a.get("act"), a.get("num") or ""))
    except Exception as e:
        out.append("ERR|%s|%s" % (os.path.basename(p)[18:32], repr(e)[:60]))
print("\n".join(out))
