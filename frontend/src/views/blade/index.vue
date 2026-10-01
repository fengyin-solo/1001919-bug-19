<template>
  <section class="page" data-module="blade">
    <header class="page-head">
      <div>
        <h2>叶片管理</h2>
        <p class="page-desc">维护叶片，围绕叶片编号、所属机组、叶片长度、制造厂商做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记叶片</button>
        <button class="btn" type="button" :disabled="exporting" @click="exportRows">
          {{ exporting ? '正在导出…' : '导出叶片清单' }}
        </button>
      </div>
    </header>

    <p v-if="errorMessage" class="error-banner" role="alert">
      <span>{{ errorMessage }}</span>
      <button v-if="retryExport" class="link" type="button" @click="exportRows">再试一次</button>
      <button class="link" type="button" @click="errorMessage = ''">知道了</button>
    </p>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>叶片编号</span>
        <input v-model="keyword" placeholder="按叶片编号检索" />
      </label>
      <label class="filter-item">
        <span>叶片状态</span>
        <select v-model="status">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] === '' || row[column] == null ? '—' : row[column] }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">查看详情</button>
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!loading && !rows.length">
          <td :colspan="columns.length + 1" class="empty-state">
            <template v-if="hasFilter">
              <p class="empty-title">没有命中的叶片记录</p>
              <p class="empty-desc">{{ noHitHint }}请调整筛选条件后重试，或重置条件查看全部叶片。</p>
              <button class="btn" type="button" @click="resetFilters">重置筛选条件</button>
            </template>
            <template v-else>
              <p class="empty-title">暂无叶片检查记录</p>
              <p class="empty-desc">叶片检查记录已清空或尚未登记。叶片台账定级仍被保留，重新登记同一编号会沿用原定级。</p>
              <button class="btn primary" type="button" @click="openCreate">重新登记叶片</button>
            </template>
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>{{ loading ? '正在加载叶片记录…' : `共 ${total} 条叶片记录` }}</span>
    </footer>

    <div v-if="createVisible" class="modal-mask" @click.self="createVisible = false">
      <div class="modal">
        <h3>登记叶片</h3>
        <form class="modal-form" @submit.prevent="submitCreate">
          <label v-for="field in createFields" :key="field.key" class="filter-item">
            <span>{{ field.label }}{{ field.required ? ' *' : '' }}</span>
            <input v-model="createForm[field.key]" :placeholder="`请输入${field.label}`" />
          </label>
          <p v-if="createError" class="error-text">{{ createError }}</p>
          <div class="modal-actions">
            <button class="btn" type="button" @click="createVisible = false">取消</button>
            <button class="btn primary" type="submit" :disabled="submitting">
              {{ submitting ? '提交中…' : '提交登记' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <div v-if="detailVisible" class="modal-mask" @click.self="detailVisible = false">
      <div class="modal">
        <h3>叶片详情</h3>
        <div v-if="detailLoading" class="empty-desc">正在加载详情…</div>
        <div v-else-if="detailError" class="error-text">{{ detailError }}</div>
        <dl v-else class="detail-list">
          <div v-for="column in columns" :key="column">
            <dt>{{ column }}</dt>
            <dd>{{ detailRow?.[column] === '' || detailRow?.[column] == null ? '—' : detailRow?.[column] }}</dd>
          </div>
        </dl>
        <div class="modal-actions">
          <button class="btn" type="button" @click="detailVisible = false">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type StatItem = { label: string; value: number }

const ENDPOINT = '/api/blade'
const columns = ["叶片编号", "所属机组", "叶片长度", "制造厂商", "上次检查日", "裂纹数量", "雷击次数", "叶片状态"]
const actions = ["提交检查", "登记缺陷", "更换叶片"]
const statuses = ["待检查", "完好", "存在裂纹", "已更换"]
const createFields = [
  { key: '叶片编号', label: '叶片编号', required: true },
  { key: '所属机组', label: '所属机组', required: true },
  { key: '叶片长度', label: '叶片长度', required: true },
  { key: '制造厂商', label: '制造厂商', required: false },
]

const rows = ref<Row[]>([])
const total = ref(0)
const loading = ref(false)
const stats = ref<StatItem[]>([
  { label: '待检查叶片', value: 0 },
  { label: '存在裂纹叶片', value: 0 },
  { label: '本月更换数', value: 0 },
])

const keyword = ref('')
const status = ref('')
const errorMessage = ref('')
const retryExport = ref(false)
const exporting = ref(false)

const createVisible = ref(false)
const submitting = ref(false)
const createError = ref('')
const createForm = ref<Record<string, string>>({})

const detailVisible = ref(false)
const detailLoading = ref(false)
const detailError = ref('')
const detailRow = ref<Row | null>(null)
let detailId: number | null = null

const hasFilter = computed(() => Boolean(keyword.value.trim() || status.value))
const noHitHint = computed(() => {
  if (keyword.value.trim() && status.value) {
    return `没有同时满足叶片编号包含「${keyword.value.trim()}」、状态为「${status.value}」的记录。`
  }
  if (keyword.value.trim()) return `没有叶片编号包含「${keyword.value.trim()}」的记录。`
  return `没有状态为「${status.value}」的叶片记录。`
})

function currentQuery() {
  const params = new URLSearchParams()
  if (keyword.value.trim()) params.set('keyword', keyword.value.trim())
  if (status.value) params.set('status', status.value)
  const text = params.toString()
  return text ? `?${text}` : ''
}

function resetFilters() {
  keyword.value = ''
  status.value = ''
  void reload()
}

async function readError(response: Response, fallback: string) {
  try {
    const payload = await response.json()
    if (payload && typeof payload.detail === 'string') return payload.detail
  } catch {
    // 非 JSON 响应时使用兜底说明
  }
  return `${fallback}（接口返回 ${response.status}）`
}

async function reload() {
  loading.value = true
  errorMessage.value = ''
  retryExport.value = false
  try {
    const response = await request(`${ENDPOINT}${currentQuery()}`)
    if (!response.ok) {
      throw new Error(await readError(response, '叶片列表读取失败'))
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '叶片列表读取失败'
  } finally {
    loading.value = false
  }
  await loadStats()
  // 详情弹窗开着时同步刷新，保证动作后详情也是最新值
  if (detailVisible.value && detailId !== null) {
    await loadDetail(detailId)
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) return
    const payload = await response.json()
    if (Array.isArray(payload.items)) {
      stats.value = payload.items as StatItem[]
    }
  } catch {
    // 统计失败时保留上一次的值，但不打断列表操作
  }
}

function openCreate() {
  createForm.value = {}
  createError.value = ''
  createVisible.value = true
}

async function submitCreate() {
  submitting.value = true
  createError.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm.value } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload || payload.ok === false) {
      createError.value = payload?.message || (await readError(response, '叶片登记失败'))
      return
    }
    createVisible.value = false
    errorMessage.value = ''
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '叶片登记失败'
  } finally {
    submitting.value = false
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  retryExport.value = false
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(await readError(response, '叶片动作未生效，请稍后重试'))
    }
    if (!payload || payload.ok === false) {
      throw new Error(payload?.message || '叶片动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '叶片操作失败'
  }
}

async function openDetail(row: Row) {
  detailVisible.value = true
  detailId = Number(row.id)
  detailRow.value = row
  detailError.value = ''
  await loadDetail(detailId)
}

async function loadDetail(id: number) {
  detailLoading.value = true
  detailError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${id}`)
    if (!response.ok) {
      detailError.value = await readError(response, '叶片详情读取失败')
      return
    }
    detailRow.value = await response.json()
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : '叶片详情读取失败'
  } finally {
    detailLoading.value = false
  }
}

async function exportRows() {
  exporting.value = true
  errorMessage.value = ''
  retryExport.value = false
  try {
    const response = await request(`${ENDPOINT}/export${currentQuery()}`)
    if (!response.ok) {
      const reason = await readError(response, '叶片清单导出失败')
      throw new Error(`叶片清单导出失败：${reason}`)
    }
    const blob = await response.blob()
    const disposition = response.headers.get('Content-Disposition') ?? ''
    const matched = disposition.match(/filename="?([^"]+)"?/)
    const filename = matched ? matched[1] : 'blade_export.json'
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '叶片清单导出失败'
    retryExport.value = true
  } finally {
    exporting.value = false
  }
}

onMounted(reload)
</script>
