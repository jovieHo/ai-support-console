"""文档切分：按段落边界聚合，以 LangChain TextSplitter 协议交付。
   把文档按空行切成段落，再把相邻段落合并到不超过 chunk_size。
"""

from __future__ import annotations
import re

from langchain_core.documents import Document
from langchain_text_splitters import TextSplitter

# 单块字符上限：一个 FAQ 一个主题，500 字左右
DEFAULT_CHUNK_SIZE = 500

# 写进 KnowledgeDocument.segment_rule 的策略名
STRATEGY = "paragraph"

# 行内连续空格/制表符压缩（保留换行）
_INLINE_SPACE = re.compile(r"[ \t\u3000]+")

# 段落分隔：一个空行
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


def normalize(text: str) -> str:
    """统一换行符并压缩行内空白，保留段落结构。
    返回:
        str: 换行符统一为 \\n、行内多余空白已压缩、每行首尾已去空白的文本
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_INLINE_SPACE.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(lines)

class ParagraphSplitter(TextSplitter):
    """段落聚合切分器：接入 LangChain 切分协议 """

    def __init__(self, chunk_size: int = DEFAULT_CHUNK_SIZE, **kwargs) -> None:
        kwargs["chunk_overlap"] = 0  # 段落是语义边界，重叠会互相污染
        super().__init__(chunk_size=chunk_size, **kwargs)

    def split_text(self, text: str) -> list[str]:
        """按段落切分并聚合为不超过 chunk_size 的知识块。

        规则：段落是切分单元，相邻段落能合并就合并，合并不下就另起一块。
        整篇没有空行时以单行为单元。

        """
        clean = normalize(text).strip()
        if not clean:
            return []

        blocks = [block.strip() for block in _PARAGRAPH_BREAK.split(clean) if block.strip()]
        # 全文只有一个空行分隔出的块，说明这份文档没有空行分段，退到单行做单元
        if len(blocks) == 1 and "\n" in blocks[0]:
            blocks = [line.strip() for line in blocks[0].split("\n") if line.strip()]

        chunks: list[str] = []
        buffer = ""
        for block in blocks:
            if not buffer:
                buffer = block
            elif len(buffer) + 1 + len(block) <= self._chunk_size:
                buffer = f"{buffer}\n{block}"
            else:
                chunks.append(buffer)
                buffer = block
        if buffer:
            chunks.append(buffer)
        return chunks

    def split_to_documents(self, text: str, source: str) -> list[Document]:
        """切分并把结果包成 LangChain Document，metadata 记录来源。"""
        return [
            Document(page_content=chunk, metadata={"source": source})
            for chunk in self.split_text(text)
        ]
