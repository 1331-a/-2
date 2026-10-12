# -*- coding: utf-8 -*-
"""【临时】对比多个打包版（ELF）+ 当前源码：函数名集合 + 模块级常量值。

用法: python 测/_ver_diff.py
"""
import sys, marshal, types, os, re, io

from PyInstaller.archive.readers import CArchiveReader

ROOT = r'C:\Users\HP\WorkBuddy\德扑双人机器人测试'


def load_code(path):
    r = CArchiveReader(path)
    d = r.extract('poker_bot')
    if isinstance(d, tuple):
        d = d[1]
    return marshal.loads(d)


def walk(co, out=None):
    if out is None:
        out = []
    out.append(co)
    for c in co.co_consts:
        if isinstance(c, types.CodeType):
            walk(c, out)
    return out


def module_consts(co):
    """从 <module> 的 co_consts/co_names 里尽力还原「名字 → 简单常量」的对应。

    办法：PyInstaller 打包后模块级名字顺序 = co_names 顺序的近似；
    更可靠的是直接抓 co_consts 里的标量集合（不保证配对，但可看差异）。
    """
    vals = {}
    for c in co.co_consts:
        if isinstance(c, (int, float, str, bool)) and not isinstance(c, bool) is False:
            pass
    return None


def collect(co):
    allc = walk(co)
    fnames = sorted({c.co_name for c in allc})
    scalars = set()
    for c in allc:
        for v in c.co_consts:
            if isinstance(v, (bool, int, float, str)) and not isinstance(v, types.CodeType):
                if isinstance(v, str) and len(v) > 80:
                    continue
                scalars.add(v)
    return fnames, scalars


TARGETS = [
    ('学习升级版(Sep30)', os.path.join(ROOT, '测', '学习升级版', 'poker_bot')),
    ('参考升级版(Oct9)', os.path.join(ROOT, '测', '参考升级版', 'poker_bot')),
    ('参考升级版2-Oct12', os.path.join(ROOT, '测', '参考升级版2(v80以后)', 'poker_bot')),
]

info = {}
for label, path in TARGETS:
    try:
        co = load_code(path)
        fn, sc = collect(co)
        info[label] = (fn, sc, len(walk(co)))
        print('%-22s code_obj=%-4d 函数=%-4d 标量常量=%d' % (label, len(walk(co)), len(fn), len(sc)))
    except Exception as e:
        print('%-22s ERR %r' % (label, repr(e)[:100]))

labels = list(info)
print()
print('=== 函数名集合差异 ===')
base = labels[0]
for lb in labels[1:]:
    a, b = set(info[base][0]), set(info[lb][0])
    print('  %s → %s : 新增 %d, 删除 %d' % (base, lb, len(b-a), len(a-b)))
    if b - a:
        print('     新增:', sorted(b - a)[:25])
    if a - b:
        print('     删除:', sorted(a - b)[:25])
    base = lb

print()
print('=== 标量常量集合差异（数值/短字符串）===')
base = labels[0]
for lb in labels[1:]:
    a, b = info[base][1], info[lb][1]
    nb, na = b - a, a - b
    print('  %s → %s : 新增 %d, 消失 %d' % (base, lb, len(nb), len(na)))
    num_new = sorted([x for x in nb if isinstance(x, (int, float)) and not isinstance(x, bool)])
    num_gone = sorted([x for x in na if isinstance(x, (int, float)) and not isinstance(x, bool)])
    print('     新增数值:', num_new[:30])
    print('     消失数值:', num_gone[:30])
    str_new = sorted([x for x in nb if isinstance(x, str)])
    str_gone = sorted([x for x in na if isinstance(x, str)])
    print('     新增字符串:', str_new[:20])
    print('     消失字符串:', str_gone[:20])
    base = lb
