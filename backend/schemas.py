"""API 请求与响应模型。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Role(str, Enum):
    ENTERPRISE_USER = "enterprise_user"
    CUSTOMER_SERVICE = "customer_service"
    ADMIN = "admin"


class BusinessStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ConsultationCategory(str, Enum):
    PRODUCT = "product"
    SERVICE = "service"
    COMPLAINT = "complaint"
    PRICE = "price"
    TECHNICAL = "technical"
    SUGGESTION = "suggestion"
    OTHER = "other"


# 用户

class UserCreate(BaseModel):
    """管理员创建用户。"""
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., max_length=100)
    password: str = Field(..., min_length=6, max_length=100)
    role: Role = Role.ENTERPRISE_USER


class RegisterRequest(BaseModel):
    """公开注册不接受角色，防止客户端自行提权。"""
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., max_length=100)
    password: str = Field(..., min_length=6, max_length=100)


class UserLogin(BaseModel):
    username: str
    password: str


class UserUpdate(BaseModel):
    email: str | None = None
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(None, min_length=6, max_length=100)


class UserResponse(BaseModel):
    """不包含密码哈希的用户信息。"""
    id: int
    username: str
    email: str
    role: Role
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# 商务数据

class BusinessBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str | None = Field(None, max_length=3000)
    amount: float = Field(0.0, ge=0)
    status: BusinessStatus = BusinessStatus.DRAFT


class BusinessCreate(BusinessBase):
    pass


class BusinessUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    content: str | None = Field(None, max_length=3000)
    amount: float | None = Field(None, ge=0)
    status: BusinessStatus | None = None


class BusinessResponse(BusinessBase):
    id: int
    owner_id: int | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ListResponse(BaseModel):
    """列表响应；当前接口尚未统一分页。"""
    total: int
    items: list[Any]


# 客服咨询相关 Schema

class CustomerConsultationCreate(BaseModel):
    """客服咨询创建请求模型。"""
    customer_name: str = Field(..., min_length=1, max_length=100)
    question: str = Field(..., min_length=1, max_length=2000)
    category: ConsultationCategory = ConsultationCategory.OTHER
    priority: int = Field(3, ge=1, le=5)
    status: str = Field("pending", max_length=20)
    ai_reply: str | None = Field(None, max_length=4000)
    # 无评价入口，未评价时保持为空
    satisfaction: int | None = Field(None, ge=1, le=5)


class CustomerConsultationUpdate(BaseModel):
    """客服咨询更新请求模型（所有字段可选）。"""
    customer_name: str | None = Field(None, min_length=1, max_length=100)
    question: str | None = Field(None, min_length=1, max_length=2000)
    category: ConsultationCategory | None = None
    priority: int | None = Field(None, ge=1, le=5)
    status: str | None = Field(None, max_length=20)
    ai_reply: str | None = Field(None, max_length=4000)
    satisfaction: int | None = Field(None, ge=1, le=5)


class CustomerConsultationResponse(CustomerConsultationCreate):
    """客服咨询响应模型。"""
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# FAQ 相关 Schema

class FAQCreate(BaseModel):
    """FAQ 创建请求模型。"""
    question: str = Field(..., min_length=1, max_length=2000)
    answer: str = Field(..., min_length=1, max_length=4000)
    category: str = Field("general", max_length=50)


class FAQUpdate(BaseModel):
    """FAQ 更新请求模型（所有字段可选）。"""
    question: str | None = Field(None, min_length=1, max_length=2000)
    answer: str | None = Field(None, min_length=1, max_length=4000)
    category: str | None = Field(None, max_length=50)
    is_active: bool | None = None


class FAQResponse(FAQCreate):
    """FAQ 响应模型。"""
    id: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# AI 对话相关 Schema

class ChatMessage(BaseModel):
    """对话消息结构（用于传递给 LLM 的消息格式）。"""
    role: str
    content: str


class ChatRequest(BaseModel):
    """AI 对话请求模型。"""
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: int | None = None
    # window(最近 6 条) / recent(最近 3 条) / all(全部)
    # 只做消息条数截断，不生成任何摘要，所以不叫 summary
    memory_type: str = Field("window", pattern="^(window|recent|all)$")


class SourceSnippet(BaseModel):
    """知识库引用片段模型，用于展示 AI 回答的知识来源。"""
    source: str
    content: str
    # 展示用相关度（0~1，结果集内最高分为 1.0）；只用于展示与排序，不可作阈值判定
    score: float
    # FAQ 命中原始分（0~1，含 FAQ 加分），仅供直出阈值判断；exclude 使它不进 API 响应
    faq_score: float | None = Field(default=None, exclude=True)


class ChatResponse(BaseModel):
    """AI 对话响应模型。"""
    conversation_id: int
    answer: str
    sources: list[SourceSnippet] = []


class ConversationUpdate(BaseModel):
    """会话更新请求模型。"""
    title: str | None = Field(None, min_length=1, max_length=200)
    is_favorite: bool | None = None


class ConversationSummary(BaseModel):
    """会话摘要响应模型（用于会话列表展示）。"""
    id: int
    title: str
    is_favorite: bool = False
    message_count: int = 0
    last_message: str = ""
    created_at: datetime
    updated_at: datetime | None = None


class ConversationMessageResponse(BaseModel):
    """对话消息响应模型。"""
    id: int
    role: str
    content: str
    message_type: str
    sources: list[SourceSnippet] = []
    created_at: datetime


class ConversationDetail(BaseModel):
    """会话详情响应模型（含完整消息列表）。"""
    id: int
    title: str
    is_favorite: bool = False
    created_at: datetime
    updated_at: datetime | None = None
    messages: list[ConversationMessageResponse]


# 知识库相关 Schema

class KnowledgeDocumentResponse(BaseModel):
    """知识库文档响应模型。"""
    id: int
    filename: str
    content_type: str
    chunk_count: int
    segment_rule: str
    parse_status: str = "indexed"
    parse_message: str = ""
    parsed_at: datetime | None = None
    created_at: datetime


class KnowledgeChunkResponse(BaseModel):
    """知识分块响应模型。"""

    id: int
    document_id: int
    source: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KnowledgeOverviewResponse(BaseModel):
    """知识库概览响应模型。"""

    documents: list[KnowledgeDocumentResponse]
    chunks: list[KnowledgeChunkResponse]
    faqs: list[FAQResponse]
    stats: dict[str, int]


class KnowledgeQuery(BaseModel):
    """知识库检索请求模型。"""
    question: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(4, ge=1, le=10)


class KnowledgeQueryResponse(BaseModel):
    """知识库检索响应模型。"""
    answer: str
    sources: list[SourceSnippet]


# AI Agent 相关 Schema

class AgentRequest(BaseModel):
    """AI Agent 请求模型，用于智能客服自动处理客户咨询。"""
    question: str = Field(..., min_length=1, max_length=2000)
    customer_name: str = "匿名客户"


class AgentClassification(BaseModel):
    """LLM 结构化分类结果。

    由 PydanticOutputParser 校验：category/urgency 越出枚举、输出不是
    合法 JSON，都会在解析时抛错，调用方据此降级到关键词规则分类。
    """

    # 五个枚举值与 taxonomy.CATEGORY_RULES 覆盖的范围一致
    category: Literal["price", "technical", "complaint", "service", "product"]
    # 一句话意图描述，如「询价」「报修」；规则降级时为空串
    intent: str = ""
    urgency: Literal["low", "normal", "high"] = "normal"
    # 只影响优先级，转人工复核仍由风险检查把关
    needs_human: bool = False
    # 回答该问题还缺少的信息，如 ["客户规模"]；无缺失为空列表
    missing_information: list[str] = []


class AgentResponse(BaseModel):
    """客服应答响应模型。"""
    # 关键词规则识别出的咨询分类，仅用于展示与提示词上下文
    category: str
    reply: str
    sources: list[SourceSnippet] = []
    # 空列表表示未发现高风险表述
    risk_flags: list[str] = []
    # pass(可直接使用) / escalate(需人工复核)
    action: str = "pass"
    # 本次草稿落库后的咨询记录 ID；前端据此更新同一条记录，避免重复新建
    consultation_id: int | None = None
    trace: list[str] = []
    # llm(结构化分类成功) / rules(降级到关键词规则)
    classification_source: str = "rules"
    # 以下四个字段来自结构化分类；规则降级时 intent 为空、其余取默认值
    intent: str = ""
    urgency: str = "normal"
    needs_human: bool = False
    missing_information: list[str] = []


# 分析报告相关 Schema

class AnalyticsReport(BaseModel):
    """分析报告响应模型，用于决策者仪表盘。"""
    # FAQ 直出占比、失败率、各段耗时、检索方式分布
    ai_metrics: dict[str, Any] = Field(default_factory=dict)
