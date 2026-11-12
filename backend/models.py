from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class User(Base):
    """平台用户模型，对应 users 表，存储所有角色的账户与认证信息。"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(30), default="enterprise_user", index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    business_datas = relationship("BusinessData", back_populates="owner")
    conversations = relationship("Conversation", back_populates="user")


class BusinessData(Base):
    """商务数据模型，对应 business_datas 表，存储企业用户的业务数据记录。"""

    __tablename__ = "business_datas"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text)
    amount = Column(Float, default=0.0)
    status = Column(String(20), default="draft")
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("User", back_populates="business_datas")


class CustomerConsultation(Base):
    """客服咨询模型，对应 customer_consultations 表，存储客户咨询工单及 AI 回复。"""

    __tablename__ = "customer_consultations"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String(100), nullable=False, index=True)
    question = Column(Text, nullable=False)
    category = Column(String(30), nullable=False, index=True)
    priority = Column(Integer, default=3, nullable=False)
    status = Column(String(20), default="pending", nullable=False, index=True)
    ai_reply = Column(Text)
    satisfaction = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class FAQ(Base):
    """FAQ 知识库模型，对应 faqs 表，存储常见问题及标准答案。"""

    __tablename__ = "faqs"

    id = Column(Integer, primary_key=True, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    category = Column(String(50), default="general", index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class KnowledgeDocument(Base):
    """知识库文档模型，对应 knowledge_documents 表，存储上传文档的元数据信息。"""

    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), default="text/plain")
    chunk_count = Column(Integer, default=0)
    segment_rule = Column(String(255), default="paragraph-500")
    parse_status = Column(String(30), default="indexed", index=True)
    parse_message = Column(String(500), default="已完成解析并建立知识分块")
    parsed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    chunks = relationship("KnowledgeChunk", back_populates="document")


class KnowledgeChunk(Base):
    """知识库分块模型，对应 knowledge_chunks 表，存储文档切分后的文本片段用于 RAG 检索。"""

    __tablename__ = "knowledge_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("knowledge_documents.id"))
    content = Column(Text, nullable=False)
    source = Column(String(255), nullable=False)
    embedding_text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    document = relationship("KnowledgeDocument", back_populates="chunks")


class Conversation(Base):
    """对话会话模型，对应 conversations 表，存储用户与 AI 的对话会话。"""

    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    # 建索引：会话列表按 user_id 过滤，是这张表最主要的查询入口
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    title = Column(String(200), default="新的商务咨询")
    is_favorite = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="conversations")
    messages = relationship("ConversationMessage", back_populates="conversation")


class ConversationMessage(Base):
    """对话消息模型，对应 conversation_messages 表，存储会话中的每一条消息。"""

    __tablename__ = "conversation_messages"

    id = Column(Integer, primary_key=True, index=True)
    # 建索引：每次对话都要按会话拉取历史消息，是高频查询条件
    conversation_id = Column(Integer, ForeignKey("conversations.id"), index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    message_type = Column(String(30), default="chat")
    sources = Column(Text, default="[]")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    conversation = relationship("Conversation", back_populates="messages")


class AiInvocation(Base):
    """AI 调用记录模型，对应 ai_invocations 表，一次请求记一行。

    与 conversation_messages 的分工：那张表存「问了什么、答了什么」，
    这张表存「答的过程花了多少代价、走的是哪条路」。两者通过
    conversation_id 关联，不建 ORM relationship——分析侧只做聚合，
    不需要按对象图遍历。
    """

    __tablename__ = "ai_invocations"

    id = Column(Integer, primary_key=True, index=True)
    # /support/assist 无会话上下文，该列为 NULL
    conversation_id = Column(Integer, ForeignKey("conversations.id"), index=True)
    entry = Column(String(20), default="chat", index=True)
    # hybrid(向量+BM25 双路) / vector(仅向量) / bm25(仅词法) / faq(仅 FAQ 命中) / none(未命中)
    retrieval_mode = Column(String(20), default="none")
    hit_count = Column(Integer, default=0)
    # 分数口径随检索方式不同，不做跨方式比较
    top_score = Column(Float, default=0.0)
    # FAQ 强命中直接出答案，跳过模型调用
    is_faq_direct = Column(Boolean, default=False, index=True)
    # 这是 Agent 的判断，不等于客服实际接管——接管动作目前没有埋点，
    # 对外只能叫「建议转人工率」
    is_escalated = Column(Boolean, default=False, index=True)
    # 系统提示词 + 历史消息 + 检索片段 + 当前问题的总字符数
    prompt_chars = Column(Integer, default=0)
    latency_retrieval_ms = Column(Integer, default=0)
    # FAQ 直出未调用模型时为 0
    latency_llm_ms = Column(Integer, default=0)
    # 仅流式请求记录；非流式请求为 NULL
    ttft_ms = Column(Integer, nullable=True)
    is_success = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
