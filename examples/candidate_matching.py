"""一个简单的候选人筛选示例。"""

import sys

# 在 Windows 控制台下保证中文正常输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CANDIDATES = [
    {"name": "张三", "years": 3, "skills": ["python", "django", "mysql"], "salary": 18000},
    {"name": "李四", "years": 6, "skills": ["java", "spring", "mysql"], "salary": 30000},
    {"name": "王五", "years": 1, "skills": ["python", "flask"], "salary": 12000},
    {"name": "赵六", "years": 4, "skills": ["python", "docker", "k8s"], "salary": 25000},
]


def match(candidates, skill, min_years=0):
    """筛选出具备指定技能且年限达标的候选人，按薪资从低到高排序。"""
    hit = [
        c for c in candidates
        if skill.lower() in c["skills"] and c["years"] >= min_years
    ]
    return sorted(hit, key=lambda c: c["salary"])


def main():
    skill, min_years = "python", 2
    print(f"筛选条件：技能={skill}，工作年限>={min_years}年\n")

    result = match(CANDIDATES, skill, min_years)
    if not result:
        print("没有匹配的候选人")
        return

    for i, c in enumerate(result, 1):
        skills = "、".join(c["skills"])
        print(f"{i}. {c['name']}（{c['years']}年，期望 {c['salary']}元）技能：{skills}")

    print(f"\n共匹配到 {len(result)} 人")


if __name__ == "__main__":
    main()
