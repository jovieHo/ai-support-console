<script setup>
// 决策大屏：AI 系统效果指标卡 + 检索路径分布（纯 AI 效果看板，仅管理员可见）
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { analyticsApi } from '../api/modules'
import { retrievalModeLabel } from '../constants'

const report = ref(null)
const modeRef = ref(null)
const loading = ref(true)

const ai = computed(() => report.value?.ai_metrics || {})
const modes = computed(() => ai.value.retrieval_modes || [])

// 后端给的是 0~1 小数
const pct = (value) => `${Math.round((value || 0) * 100)}%`

// 耗时为 null（没有样本）时显示破折号，超过 1 秒换成秒
const ms = (value) => {
  if (value === null || value === undefined) return '—'
  return value >= 1000 ? `${(value / 1000).toFixed(2)}s` : `${Math.round(value)}ms`
}

let modeChart = null

// 按需加载 ECharts
const loadEcharts = async () => {
  const [echarts, charts, components, renderer] = await Promise.all([
    import('echarts/core'),
    import('echarts/charts'),
    import('echarts/components'),
    import('echarts/renderers'),
  ])
  echarts.use([
    charts.PieChart,
    components.TooltipComponent,
    components.LegendComponent,
    renderer.CanvasRenderer,
  ])
  return echarts
}

const renderCharts = async () => {
  const echarts = await loadEcharts()
  modeChart = echarts.init(modeRef.value)

  // 检索路径分布：向量命中 / 词频命中 / 仅 FAQ / 无命中
  modeChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} 次 ({d}%)' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie', radius: ['48%', '72%'],
      data: modes.value.map((item) => ({ name: retrievalModeLabel(item.mode), value: item.count })),
      label: { show: false },
    }],
  })
}

// 窗口变化时重绘，否则图表停在初始尺寸
const handleResize = () => modeChart?.resize()

onMounted(async () => {
  loading.value = true
  try {
    report.value = await analyticsApi.report()
    await renderCharts()
    window.addEventListener('resize', handleResize)
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  modeChart?.dispose()
})
</script>

<template>
  <section v-loading="loading" class="dashboard">
    <div class="section-title">
      <div>
        <p>决策者可视化大屏</p>
        <h2>AI 系统效果</h2>
      </div>
    </div>

    <div class="metric-row">
      <div class="metric-card">
        <span>AI 调用总量</span>
        <strong>{{ ai.total_invocations || 0 }}</strong>
        <small>一条用户消息记一次</small>
      </div>
      <div class="metric-card">
        <span>FAQ 直出占比</span>
        <strong>{{ pct(ai.faq_direct_rate) }}</strong>
        <small>强命中直接返回，未调模型</small>
      </div>
      <div class="metric-card">
        <span>平均检索耗时</span>
        <strong>{{ ms(ai.avg_retrieval_ms) }}</strong>
        <small>含一次 embedding 调用</small>
      </div>
      <div class="metric-card">
        <span>平均生成耗时</span>
        <strong>{{ ms(ai.avg_llm_ms) }}</strong>
        <small>仅统计进入模型的请求</small>
      </div>
    </div>

    <div class="chart-grid">
      <div class="panel">
        <h3>检索路径分布</h3>
        <div class="chart-wrap">
          <div ref="modeRef" class="chart"></div>
          <p v-if="!modes.length" class="chart-empty">暂无 AI 调用记录</p>
        </div>
      </div>
      <div class="panel">
        <h3>指标口径</h3>
        <dl class="metric-notes">
          <div>
            <dt>FAQ 直出占比</dt>
            <dd>FAQ 余弦相似度过线且为首轮提问时，直接返回标准答案、不调模型。它不等于「自主解决率」。</dd>
          </div>
          <div>
            <dt>检索耗时</dt>
            <dd>每次请求都要调一次 embedding 把问题转成向量，通常是链路上最慢的一段。</dd>
          </div>
        </dl>
      </div>
    </div>
  </section>
</template>
