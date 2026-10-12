"""技能表解码：把 key_map 表里的 Java 序列化 blob 还原成技能词列表。

背景：数据集作者用 Java 把每个岗位的"技能 -> 出现次数"存成 java.util.HashMap，
再把对象序列化后写入 MySQL blob。Java 序列化流的语法要点：
  - 字符串作为 map 的键时，会以 TC_STRING（标记字节 0x74）开头：
    0x74 + 2 字节大端长度 + 原文字节          <- 我们只需要扫这一种
  - 类名 / 字段名是另一种不带 0x74 的 (utf) 形式，扫描天然避开
因此"扫 0x74 + 校验可打印 ASCII"即可取出全部技能词；
对照样例：key_map id=1（web）解码结果应为
[app, web, spa, angular, vue, mobile, js, react, mvc, jquery]（见 tests/test_skills.py）。
"""

import re

_TC_STRING = 0x74
# 技能词合法字符集（兼容 c#、c++、js/css/html、node.js 这类写法）
_SKILL_RE = re.compile(r"^[A-Za-z0-9+#./_\- ]+$")
# 防御性噪声词（按上面的语法理论扫不到，留着兜底）
_NOISE = {"java.util.HashMap", "java.lang.Integer", "java.lang.Number", "loadFactor", "threshold"}


def scan_tc_strings(data: bytes) -> list[str]:
    """扫描 Java 序列化字节流中的全部 TC_STRING，按出现顺序返回。"""
    out = []
    i, n = 0, len(data)
    while i < n - 2:
        if data[i] == _TC_STRING:
            ln = int.from_bytes(data[i + 1:i + 3], "big")
            start, end = i + 3, i + 3 + ln
            if 0 < ln <= 40 and end <= n:
                chunk = data[start:end]
                if all(32 <= b < 127 for b in chunk):  # 必须是可打印 ASCII
                    s = chunk.decode("ascii")
                    if s not in _NOISE:
                        out.append(s)
                    i = end
                    continue
        i += 1
    return out


def decode_skill_map(blob: bytes) -> list[str]:
    """解码一个岗位的技能 blob -> 去重后的技能词列表（保持出现顺序）。"""
    if not blob:
        return []
    skills = []
    for s in scan_tc_strings(bytes(blob)):
        if s.isdigit():
            continue  # 纯数字多半是序列化数值的误扫
        if not _SKILL_RE.match(s):
            continue
        skills.append(s)
    return list(dict.fromkeys(skills))  # 保序去重
