# -*- coding: utf-8 -*-
"""【临时复盘】解析一份 BotBattle 对局日志：逐手结果 / 关键手 / 用时。

用法:
    python 测/_review.py <log.json> [my_seat]
"""
import sys, io, json, collections

p = sys.argv[1] if len(sys.argv) > 1 else r'C:\Users\HP\Downloads\botbattle-holdem-20261012170738-4895b988-log.json'
o = json.load(io.open(p, encoding='utf-8'))
m = o['match']
r = o['replay']
ev = r['events']

me = int(sys.argv[2]) if len(sys.argv) > 2 else 0
if me != 0:
    pass
# 自动判座位：先按 owner_display 含 j1331
for i, k in ((0, 'bot_a'), (1, 'bot_b')):
    if 'j1331' in str((m.get(k) or {}).get('owner_display', '')):
        me = i
opp = 1 - me
print('match_id =', m['id'], '| 我方座位 =', me, '| 结果 deltas =', m['result']['deltas'],
      '| winner =', m['winner'], '| technical_loss =', m['technical_loss'])
print('对手 =', (m.get('bot_%s' % ('a' if opp == 0 else 'b')) or {}).get('display_name'))

# ---- 逐手 ----
cur = None
hands = []
time_used = collections.Counter()
act_time = []       # (hand, 街, 动作, 秒)
acts = []           # 我方动作序列
for e in ev:
    t = e.get('type')
    if t == 'hand_start':
        cur = {'hand': e['hand'], 'start': list(e['chips']), 'street_actions': []}
    elif t == 'deal_hole':
        if cur is not None:
            cur['holes'] = e.get('hole') or e.get('cards') or e
    elif t == 'deal_board':
        if cur is not None:
            cur.setdefault('boards', []).append(list(e.get('board') or e.get('cards') or []))
    elif t == 'action':
        if cur is not None:
            cur['street_actions'].append(e)
        acts.append(e)
    elif t == 'time_used':
        if cur is not None:
            cur['time'] = cur.get('time', 0) + float(e.get('seconds', e.get('time', 0)) or 0)
        time_used[e.get('player_id', e.get('player', '?'))] += float(e.get('seconds', e.get('time', 0)) or 0)
    elif t == 'settle':
        if cur is not None:
            cur['settle'] = e
            cur['delta_me'] = e['deltas'][me]
            cur['net_me'] = e['net'][me]
            cur['reason'] = e.get('reason')
            hands.append(cur)
            cur = None

print()
print('=== 逐手（前 25 手）===')
print('%-4s %-8s %10s %10s %-10s %s' % ('手', '结果', '我净变', '我筹码', 'reason', '牌面'))
for h in hands[:25]:
    print('%-4d %-8s %10d %10d %-10s %s' % (
        h['hand'], '赢' if h['delta_me'] > 0 else ('输' if h['delta_me'] < 0 else '平'),
        h['delta_me'], h['settle']['chips'][me], str(h.get('reason'))[:10],
        ' '.join(h.get('boards', [[]])[-1] if h.get('boards') else [])))

print()
print('=== 汇总 ===')
tot = sum(h['delta_me'] for h in hands)
win = [h for h in hands if h['delta_me'] > 0]
los = [h for h in hands if h['delta_me'] < 0]
print('  手数 %d | 总净变 %d | 赢 %d 手(合计 +%d) | 输 %d 手(合计 %d)' % (
    len(hands), tot, len(win), sum(h['delta_me'] for h in win), len(los), sum(h['delta_me'] for h in los)))
print('  最大赢: %s' % [(h['hand'], h['delta_me']) for h in sorted(hands, key=lambda x: -x['delta_me'])[:5]])
print('  最大输: %s' % [(h['hand'], h['delta_me']) for h in sorted(hands, key=lambda x: x['delta_me'])[:5]])
rc = collections.Counter(h.get('reason') for h in hands)
print('  reason 分布:', dict(rc))

print()
print('=== 用时 ===')
tm = sum(time_used.values())
print('  合计 %.1fs | 我方 %.1fs | 对手 %.1fs' % (tm, time_used.get(me, 0), time_used.get(opp, 0)))
mx = sorted(acts, key=lambda e: -(e.get('seconds', 0) or 0))[:8]
print('  最慢的 8 步:')
for e in mx:
    print('     player=%s hand=%s %s  动作=%s %s  用时=%.2fs' % (
        e.get('player_id', e.get('player')), e.get('hand'), e.get('round', ''),
        e.get('action_type', e.get('type_')), e.get('action'), e.get('seconds', 0) or 0))
