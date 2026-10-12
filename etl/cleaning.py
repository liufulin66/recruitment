"""清洗核心：薪资解析与枚举归一。

纯函数模块：不连数据库、不依赖框架，便于单测与逐段讲解。
对应规格：openspec/changes/add-recruitment-analysis-system/specs/data-pipeline/spec.md
"""

import re

# ---------------- 薪资解析 ----------------

# 单位换算：统一折算为"元"
_UNITS = {"k": 1000, "千": 1000, "w": 10000, "万": 10000, "元": 1}
# 默认单位：中文招聘数据里不带单位的数字普遍以 k（千元/月）计（如"15-25"）
_DEFAULT_UNIT = "k"
_NUM = r"\d+(?:\.\d+)?"


def parse_salary(text):
    """解析薪资文本 -> (最低, 最高, 平均)（元/月）；无法解析返回 None。

    规则（对应规格场景）：
    - 区间 `15k-25k`、`6千-1.2万`：某侧缺单位时借用另一侧；两侧都无单位按 k
    - 年薪（含 `/年`、`年薪`）：两端点按 12 个月折算；平均按换算后中点
    - 薪月数（如 `·13薪`）：平均 = 区间中点 × 月数 ÷ 12；最低/最高保持月薪原值
    - 单一值 `12k`、`9000元`、裸数字 `12`（按 k 惯例）
    - `面议`、空值、无法识别 -> None（规格中的"薪资缺失"）
    """
    if text is None:
        return None
    s = str(text).strip().lower()
    if not s or "面议" in s:
        return None

    # 1) 抠出薪月数标记（如 ·13薪）并从串里移除，避免干扰后面的数字解析
    months = 12.0
    m = re.search(r"[·*x×]?\s*(\d{2})\s*薪", s)
    if m:
        months = float(m.group(1))
        s = s[: m.start()] + s[m.end():]

    yearly = ("/年" in s) or ("年薪" in s) or s.endswith("年")

    def piece(seg):
        """从片段中取出（数值, 单位或 None），取不出数字返回 None。"""
        m2 = re.search(rf"({_NUM})\s*([k千w万元])?", seg)
        if not m2:
            return None
        return float(m2.group(1)), m2.group(2)

    # 2) 按常见的区间分隔符切分（连字符/波浪号/至/到）
    segs = re.split(r"[-~－—至到]", s, maxsplit=1)
    left = right = None
    if len(segs) == 2:
        left, right = piece(segs[0]), piece(segs[1])

    if left and right:  # 区间
        unit_l = left[1] or right[1] or _DEFAULT_UNIT
        unit_r = right[1] or left[1] or _DEFAULT_UNIT
        lo, hi = left[0] * _UNITS[unit_l], right[0] * _UNITS[unit_r]
    else:  # 单一值：取能解析出来的那一侧
        one = left or right or piece(s)
        if one is None:
            return None
        lo = hi = one[0] * _UNITS[one[1] or _DEFAULT_UNIT]

    if yearly:
        lo, hi = lo / 12, hi / 12
    avg = (lo + hi) / 2 * (months / 12)
    return lo, hi, avg


# ---------------- 枚举归一 ----------------

# 城市里的分隔符：`北京·朝阳区`、`北京-朝阳`、`北京（朝阳）` 等
_CITY_SEP = re.compile(r"[·．.\-—－(（\s]")


def normalize_city(text):
    """城市归一 -> 城市名；无值返回 None。

    `北京·朝阳区`->`北京`；`深圳市南山区`->`深圳`；`杭州市`->`杭州`。
    """
    if not text:
        return None
    s = _CITY_SEP.split(str(text).strip())[0]
    if "市" in s:
        s = s.split("市")[0]
    if "省" in s:
        s = s.split("省")[0]
    return s or None


# 学历固定档位（顺序即层级，从高到低）
EDU_TIERS = ("博士", "硕士", "本科", "大专", "高中及以下", "不限")


def normalize_education(text):
    """学历归一 -> 固定档位；无值 None；未识别的取值原样返回（供 ETL 统计异常）。"""
    if not text:
        return None
    s = str(text).strip()
    if "不限" in s:
        return "不限"
    if "博士" in s:
        return "博士"
    if "硕士" in s or "研究生" in s:
        return "硕士"
    if "本科" in s:  # 含 `本科及以上`
        return "本科"
    if "大专" in s or "专科" in s:
        return "大专"
    if any(k in s for k in ("高中", "中专", "技校", "以下", "初中", "小学")):
        return "高中及以下"
    return s


# 经验固定档位
EXP_TIERS = ("应届生", "1年以内", "1-3年", "3-5年", "5-10年", "10年以上", "不限")
_EXP_BANDS = ((1, 3, "1-3年"), (3, 5, "3-5年"), (5, 10, "5-10年"))


def normalize_experience(text):
    """经验归一 -> 固定档位；无值 None；未识别的取值原样返回。

    数据实态：`experience` 列 = 前导空格 + 经验段 + 学历段（如 ` 1-3年本科`），
    本函数只取经验段；同时兼容 `经验3-5年` 写法。
    """
    if not text:
        return None
    s = str(text).strip().removeprefix("经验")
    if s.startswith("应届"):
        return "应届生"
    if s.startswith("不限"):
        return "不限"
    m = re.match(r"(\d+)(?:-(\d+))?年(以内|以上)?", s)
    if not m:
        return s
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    if m.group(3) == "以内":
        return "1年以内"
    if m.group(3) == "以上":
        return "10年以上" if lo >= 10 else s
    for band_lo, band_hi, name in _EXP_BANDS:
        if lo == band_lo and hi == band_hi:
            return name
    if lo >= 10:
        return "10年以上"
    return s
