"""咨询分类：关键词规则。

分类结果只用于两处：
1. 提示词上下文（让模型知道客户在问哪一类问题）
2. 前端标签展示

它不参与流程分支决策——所有分类走的都是同一条检索与生成路径，
因此不需要为它单独设一个流水线步骤。规则集中在这里，是为了避免
分类逻辑散落在多个模块里各写一份。
"""

from __future__ import annotations

# 分类关键词规则：按顺序匹配，先命中先返回
# 顺序即优先级。投诉排最前，否则「合同到期了想投诉」会被 service 抢走；
# 投诉类问题要能被统计到，它也是唯一会触发风险复核口径的类目。
CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("complaint", ("投诉", "不满意")),
    ("price", ("价格", "报价", "费用")),
    ("technical", ("故障", "报错", "不能", "失败")),
    ("service", ("合同", "续费", "服务")),
]

# 未命中任何规则时的默认分类
DEFAULT_CATEGORY = "product"


def classify(question: str) -> str:
    """按关键词将客户问题归入一个分类。

    参数:
        question: 客户问题原文

    返回:
        str: price / technical / complaint / service / product 之一
    """
    for category, words in CATEGORY_RULES:
        if any(word in question for word in words):
            return category
    return DEFAULT_CATEGORY
