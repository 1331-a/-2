# -*- coding: utf-8 -*-
"""【临时】解包 PyInstaller ELF，提取 poker_bot 主脚本 → marshal → 识别版本特征。

用法: python 测/_unpack_ver.py <elf> [elf2 ...]
"""
import sys, marshal, types, io, os

from PyInstaller.archive.readers import CArchiveReader


def load_code(path):
    r = CArchiveReader(path)
    data = r.extract('poker_bot')
    if isinstance(data, tuple):
        data = data[1]
    return marshal.loads(data)


def walk(co, depth=0, out=None):
    if out is None:
        out = []
    out.append((depth, co))
    for c in co.co_consts:
        if isinstance(c, types.CodeType):
            walk(c, depth + 1, out)
    return out


def collect_names(co, names=None, consts=None):
    if names is None:
        names, consts = set(), set()
    names.update(co.co_names)
    for c in co.co_consts:
        if isinstance(c, str):
            consts.add(c)
        elif isinstance(c, types.CodeType):
            collect_names(c, names, consts)
    return names, consts


MARKERS = ['EQ_VETO', 'BIGBET_THRESH', 'BIG_CALL_RAMP', 'FLUSH_MADE_PASS',
           '_lock_win_unified', '_gamble_plan', '_face_bet', '_stability_guard',
           '_big_money_guard', '_doom_call_upgrade', '_eq_veto_keep',
           '_last_req_info', '_LAST_REQ_INFO', 'UA_CROSS_CHECK', 'RANGE_SOFT_TAIL',
           'BOT_VERSION', 'OPEN_SIZE_BB', 'ALLIN_RELAX_CAP', 'GAMBLE_LINE_FACTOR']

for path in sys.argv[1:]:
    print('=' * 70)
    print(path)
    try:
        co = load_code(path)
    except Exception as e:
        print('  解包失败:', repr(e)[:200])
        continue
    allc = walk(co)
    names, consts = collect_names(co)
    print('  code objects =', len(allc))
    blob = ' '.join(names) + ' ' + ' '.join(c for c in consts if len(c) < 60)
    print('  命中特征:')
    for mk in MARKERS:
        if mk.lower() in blob.lower():
            print('     +', mk)
    print('  顶层 co_names 前 30:', list(co.co_names)[:30])
    # 找版本串
    ver = [c for c in consts if 'v' in c.lower() and len(c) < 30 and any(ch.isdigit() for ch in c)]
    print('  可能的版本串:', ver[:12])
    # 所有函数名（co_name）
    fnames = sorted({c.co_name for _, c in allc})
    print('  函数总数 =', len(fnames))
    print('  函数名样例:', fnames[:40])
