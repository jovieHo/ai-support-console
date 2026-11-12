# 智企通 AI 商务助手平台

面向 B2B SaaS 场景的智能客服后台。企业用户与 AI 对话，客服审核 AI 草稿并维护知识库，管理员看 AI 系统效果。后端 FastAPI + SQLite，前端 Vue 3。

---

## 特性

- **检索**：Chroma 向量 + 自实现 BM25 双路召回，RRF 按名次融合；FAQ 强命中直接返回，不调模型；多轮指代型问题先改写再检索。
- **生成**：`httpx` 直连 OpenAI 兼容协议；分类模型判定信息不足时先反问，而不是硬答。
- **可观测**：每次调用落 `ai_invocations`（检索路径、命中数、耗时、是否直出），聚合出管理员大屏。

## 问答链路

```
用户提问
  │
  ├─ 多轮指代型（「那它呢」）─> 先改写为独立问句，再检索
  │
  ├─ 首轮 ─> FAQ 强命中（相似度 ≥ 0.85）── 命中 ─> 直接返回标准答案
  │
  └─ 未命中 ─> 双路召回（向量 + BM25，RRF 融合）+ FAQ 独立路
                 │
            分类模型判定缺不缺信息 ── 缺 ─> 先反问，不调生成模型
                 │
            LLM 生成（检索片段 + 平台数据，编不出来就说不知道）
                 │
            风险守卫（承诺收益 / 绝对化 / 越权赔偿）── 命中即落待复核工单
```

## 快速开始

```bash
cp .env.example .env            # 在项目根目录执行，填 LLM_API_KEY / EMBED_API_KEY

cd backend
python -m venv .venv
.venv\Scripts\activate          # macOS / Linux: source .venv/bin/activate
pip install -r ../requirements.txt
uvicorn main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

没有 API Key 也能启动：生成走本地降级模板，向量检索不可用时由 BM25 单路兜底，功能可跑通但回答质量下降。

Docker：`docker compose up --build`（后端 8000 / 前端 80 / Redis 6379）。SQLite 落在命名卷上，重建容器数据不丢。

接口文档：http://127.0.0.1:8000/docs

## 演示账号

| 用户名 | 密码 | 角色 |
|---|---|---|
| `admin` | `admin123` | 管理员，全部页面 |
| `service` | `service123` | 客服，对话 / 工作台 / 知识库 |
| `user` | `user123` | 企业用户，仅 AI 对话 |

公开部署前请改 `init_db.py` 里的种子口令，并同步更新已有库的 `hashed_password`（加盐 PBKDF2，无法反查）。

## 已知限制

- 列表接口全量返回、无分页，当前数据量够用，上千条需补 `LIMIT/OFFSET`，会话列表还有 N+1 查询。
- 未引入 Alembic，加字段要写进 `tools/migrate_schema.py` 的清单（启动时幂等执行）。
- 测试集中在 AI 链路（26 个 unittest），CRUD 层与前端无自动化测试。
