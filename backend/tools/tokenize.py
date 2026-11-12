"""检索用分词器：英文词、中文字符与中文二元组。

BM25 与 FAQ 余弦两路共用，保证「同一句话在两条检索路里切成同样的词」，
融合时的排名才有可比性。
"""

from __future__ import annotations

import re


def tokenize(text: str) -> list[str]:
    """切成可检索的 token 序列（保留重复项，BM25 需要词频信息）。"""
    lowered = text.lower()
    tokens = re.findall(r"[a-zA-Z0-9_]+", lowered)
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", lowered)
    chinese_bigrams = [
        "".join(chinese_chars[index : index + 2])
        for index in range(max(len(chinese_chars) - 1, 0))
    ]
    return tokens + chinese_chars + chinese_bigrams
