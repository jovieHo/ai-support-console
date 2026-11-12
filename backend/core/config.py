"""应用配置：从 .env 文件与环境变量加载所有配置项。

配置优先级：环境变量 > .env 文件 > 类属性默认值
所有配置项均通过 Settings 类集中管理，使用 get_settings() 单例获取。
"""

from functools import lru_cache
from pathlib import Path
import os


try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if load_dotenv is not None:
    load_dotenv(PROJECT_ROOT / ".env")


class Settings:
    """应用配置类：所有字段均从环境变量读取，未设置时使用默认值。

    字段分类：
    - 应用基础配置：app_name, api_prefix, base_dir
    - 数据库与缓存：database_url, redis_url
    - 跨域配置：cors_origins
    - 大模型配置：llm_api_key, llm_base_url, llm_model, llm_temperature
    - 安全配置：secret_key
    """

    # ---- 应用基础配置 ----
    app_name: str = "智企通 AI 商务助手平台"
    api_prefix: str = "/api/v1"
    base_dir: Path = Path(__file__).resolve().parents[1]
    """backend 目录的绝对路径，用于构建文件路径（如 SQLite 数据库文件、上传文件目录等）"""

    # ---- 数据库与缓存 ----
    database_url: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(Path(__file__).resolve().parents[1] / 'neusoft_ai.db').as_posix()}",
    )
    """数据库连接 URL，默认使用 backend/ 目录下的 SQLite 文件"""
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    """Redis 连接 URL，用于缓存和会话存储"""

    # ---- 跨域配置 ----
    cors_origins: list[str] = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://127.0.0.1:5174,http://127.0.0.1:5175,http://127.0.0.1:5176,http://127.0.0.1:5177",
    ).split(",")
    """允许跨域请求的前端源地址列表，逗号分隔"""

    # ---- 大模型配置 ----
    llm_api_key: str = (
        os.getenv("LLM_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("OPENAI_API_KEY", "")
    )
    """大模型 API 密钥，依次读取 LLM_API_KEY / DASHSCOPE_API_KEY / OPENAI_API_KEY；
    均未配置时部分 AI 功能降级为本地回复"""
    llm_base_url: str = os.getenv(
        "LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    """大模型 API 基础地址，兼容 OpenAI 协议（默认阿里云百炼）"""
    llm_model: str = os.getenv("LLM_MODEL", "qwen-plus")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    """大模型生成温度，0.3 表示较确定性的回复，适合商务场景"""

    # ---- 嵌入模型配置 ----
    embed_api_key: str = (
        os.getenv("EMBED_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("OPENAI_API_KEY", "")
    )
    """嵌入模型 API Key，未单独配置时复用大模型 Key（阿里云百炼同一个 Key）；
    仍未配置时 EmbeddingService.embed 返回空列表 [] 触发降级"""
    embed_base_url: str = os.getenv("EMBED_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    """嵌入模型 API 基础地址，兼容 OpenAI 协议（默认阿里云百炼；DeepSeek 无 embedding 接口）"""
    embed_model: str = os.getenv("EMBED_MODEL", "text-embedding-v3")
    """嵌入模型名称（默认 text-embedding-v3）"""

    # ---- Chroma 向量库配置 ----
    chroma_persist_dir: str = os.getenv(
        "CHROMA_PERSIST_DIR",
        str((Path(__file__).resolve().parents[1] / "storage" / "chroma").as_posix()),
    )
    """Chroma 索引持久化目录"""
    chroma_collection_name: str = os.getenv("CHROMA_COLLECTION_NAME", "knowledge_base")
    """Chroma 集合名"""

    # ---- 安全配置 ----
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
    """应用密钥，用于 JWT 签名和密码哈希的盐值。生产环境务必修改！"""


@lru_cache
def get_settings() -> Settings:
    """获取 Settings 单例实例。

    使用 lru_cache 装饰器确保整个应用生命周期中只创建一次 Settings 对象，
    避免重复读取环境变量。

    返回:
        Settings: 应用配置单例
    """
    return Settings()
