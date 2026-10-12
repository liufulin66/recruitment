"""技能解码用例：扫描器单测 + 数据库金样例对照。

金样例（规格"技能表解码留存"：无截断、无乱码）：
key_map id=1（web）的解码结果 == 数据集作者写入的原始技能集合。
注意：`angualar` 是源数据自带的拼写错误（数据实态，照原样保留，不修不改）。
"""

import unittest

from etl.skills import decode_skill_map, scan_tc_strings

GOLD_SKILLS = {"app", "web", "spa", "angualar", "vue", "mobile", "js", "react", "mvc", "jquery"}


class TestScanTcStrings(unittest.TestCase):
    """扫描器字节级用例：0x74 + 2 字节长度 + 原文字节。"""

    def test_basic(self):
        data = b"\xac\xed\x00\x05\x74\x00\x03app\x70\x74\x00\x03vue"
        self.assertEqual(scan_tc_strings(data), ["app", "vue"])

    def test_skip_non_printable(self):
        data = b"\x74\x00\x03ca\xe9"  # 长度 3 的串里混入非 ASCII 字节 -> 跳过
        self.assertEqual(scan_tc_strings(data), [])

    def test_skip_oversize_length(self):
        data = b"\x74\xff\xffx"  # 声称长度 65535，越界 -> 跳过
        self.assertEqual(scan_tc_strings(data), [])


class TestDecodeGoldSample(unittest.TestCase):
    """金样例对照（需要 MySQL 中已有 key_map 暂存表，不可用时跳过）。"""

    def test_gold(self):
        try:
            from db import get_connection
            conn = get_connection()
        except Exception as e:  # 数据库不可用时跳过而非失败
            self.skipTest(f"数据库不可用：{e}")
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT key_words_map FROM key_map WHERE id = 1")
                row = cur.fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row, "key_map 缺少 id=1 的样例")
        skills = decode_skill_map(row[0])
        self.assertEqual(set(skills), GOLD_SKILLS)


if __name__ == "__main__":
    unittest.main()
