// 后端枚举码转中文展示。码值来源：tools/taxonomy.py（分类）、customer_consultations.status（状态）

export const CATEGORY_LABELS = {
  price: '价格咨询',
  technical: '技术故障',
  complaint: '投诉',
  service: '合同与服务',
  product: '产品咨询',
}

export const categoryLabel = (code) => CATEGORY_LABELS[code] || code

export const STATUS_LABELS = {
  pending: '待处理',
  resolved: '已解决',
  closed: '已关闭',
}

export const statusLabel = (code) => STATUS_LABELS[code] || code

// 检索路径：码值来源 rag_service.last_retrieval_mode
// tfidf 是历史埋点残留值，历史数据仍会显示，保留映射
export const RETRIEVAL_MODE_LABELS = {
  hybrid: '混合检索',
  vector: '仅向量',
  bm25: '仅词法 BM25',
  tfidf: '词频降级',
  faq: '仅 FAQ 命中',
  none: '无命中',
}

export const retrievalModeLabel = (code) => RETRIEVAL_MODE_LABELS[code] || code
