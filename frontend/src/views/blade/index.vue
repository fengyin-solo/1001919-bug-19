<template>
  <section class="page" data-module="blade">
    <header class="page-head">
      <div>
        <h2>叶片管理</h2>
        <p class="page-desc">维护叶片，围绕叶片编号、所属机组、叶片长度、制造厂商做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate()">登记叶片</button>
        <button class="btn" type="button" :disabled="exporting" @click="exportRows">
          {{ exporting ? '正在导出…' : '导出叶片清单' }}
        </button>
      </div>
    </header>

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
        <tr v-if="loading">
          <td :colspan="columns.length + 1" class="empty-state">叶片记录加载中…</td>
        </tr>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
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
        <tr v-if="!loading && !rows.length && !hasFilter">
          <td :colspan="columns.length + 1" class="empty-cell">
            <div class="empty-block">
              <p class="empty-title">暂无叶片数据</p>
              <p class="empty-desc">叶片检查记录已清空，不会影响已登记的台账；登记新叶片后列表与统计会同步更新。</p>
              <button class="btn primary" type="button" @click="openCreate()">重新登记叶片</button>
            </div>
          </td>
        </tr>
        <tr v-if="!loading && !rows.length && hasFilter">
          <td :colspan="columns.length + 1" class="empty-cell">
            <div class="empty-block">
              <p class="empty-title">没有命中的叶片记录</p>
              <p class="empty-desc">
                没有{{ keyword ? `编号包含「${keyword}」` : '' }}{{ keyword && status ? '且' : '' }}{{ status ? `状态为「${status}」` : '' }}的叶片，数据并未丢失。
              </p>
              <button class="btn" type="button" @click="resetFilters">清空筛选条件</button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>
        共 {{ total }} 条叶片记录<template v-if="hasFilter && !loading">（已按当前条件筛选）</template>
      </span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 导出失败提示：写清原因并支持再试一次 -->
    <div v-if="exportError" class="notice error-notice" role="alert">
      <span>{{ exportError }}</span>
      <span class="notice-actions">
        <button class="btn" type="button" @click="exportRows">再试一次</button>
        <button class="btn ghost" type="button" @click="exportError = ''">知道了</button>
      </span>
    </div>
    <div v-if="notice" class="notice ok-notice" role="status">
      <span>{{ notice }}</span>
      <button class="btn ghost" type="button" @click="notice = ''">关闭</button>
    </div>

    <!-- 登记叶片 -->
    <div v-if="createOpen" class="modal-mask" @click.self="closeCreate">
      <div class="modal">
        <div class="modal-head">
          <h3>登记叶片</h3>
          <button class="btn ghost" type="button" @click="closeCreate">关闭</button>
        </div>
        <p class="modal-tip">叶片编号与定级以台账为准：重新登记历史编号时，会自动沿用台账里的原记录 ID 与定级。</p>
        <form class="modal-form" @submit.prevent="submitCreate">
          <label v-for="field in formFields" :key="field.key" class="filter-item">
            <span>{{ field.label }}{{ field.required ? ' *' : '' }}</span>
            <input v-model="form[field.key]" :placeholder="`请输入${field.label}`" />
          </label>
          <p v-if="createError" class="error-text">{{ createError }}</p>
          <div class="modal-foot">
            <button class="btn" type="button" @click="closeCreate">取消</button>
            <button class="btn primary" type="submit" :disabled="creating">{{ creating ? '提交中…' : '确认登记' }}</button>
          </div>
        </form>
      </div>
    </div>

    <!-- 叶片详情：始终按 ID 实时拉取，保证与列表、统计同源 -->
    <div v-if="detailOpen" class="modal-mask" @click.self="closeDetail">
      <div class="modal">
        <div class="modal-head">
          <h3>叶片详情</h3>
          <button class="btn ghost" type="button" @click="closeDetail">关闭</button>
        </div>
        <p v-if="detailLoading" class="empty-desc">详情加载中…</p>
        <div v-else-if="detailError" class="notice error-notice">
          <span>{{ detailError }}</span>
          <button class="btn" type="button" @click="retryDetail">再试一次</button>
        </div>
        <dl v-else-if="detail" class="detail-list">
          <div v-for="item in detailFields" :key="item.key">
            <dt>{{ item.label }}</dt>
            <dd>{{ detail[item.key] ?? '—' }}</dd>
          </div>
        </dl>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

interface StatItem {
  label: string
  value: number
}

const ENDPOINT = '/api/blade'
const columns = ["叶片编号", "所属机组", "叶片长度", "制造厂商", "上次检查日", "裂纹数量", "雷击次数", "叶片状态"]
const actions = ["提交检查", "登记缺陷", "更换叶片"]
const statuses = ["待检查", "完好", "存在裂纹", "已更换"]

const rows = ref<Row[]>([])
const stats = ref<StatItem[]>([
  { label: "待检查叶片", value: 0 },
  { label: "存在裂纹叶片", value: 0 },
  { label: "本月更换数", value: 0 },
])
const total = ref(0)
const loading = ref(false)
const errorMessage = ref('')
const notice = ref('')
const keyword = ref('')
const status = ref('')

const hasFilter = computed(() => Boolean(keyword.value.trim() || status.value))

function buildQuery() {
  const params = new URLSearchParams()
  if (keyword.value.trim()) params.set('keyword', keyword.value.trim())
  if (status.value) params.set('status', status.value)
  const query = params.toString()
  return query ? `?${query}` : ''
}

async function readError(response: Response, fallback: string) {
  try {
    const payload = await response.json()
    if (payload && typeof payload.detail === 'string' && payload.detail.trim()) {
      return payload.detail
    }
  } catch {
    // 后端返回的不是 JSON 时退回到兜底提示
  }
  return `${fallback}（接口返回 ${response.status}）`
}

function resetFilters() {
  keyword.value = ''
  status.value = ''
  void reload()
}

async function reload() {
  loading.value = true
  errorMessage.value = ''
  try {
    const [listResponse, statResponse] = await Promise.all([
      request(`${ENDPOINT}${buildQuery()}`),
      request(`${ENDPOINT}/stats`),
    ])
    if (!listResponse.ok) {
      throw new Error(await readError(listResponse, '叶片列表读取失败'))
    }
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (statResponse.ok) {
      const statPayload = await statResponse.json()
      stats.value = statPayload.items ?? []
    } else {
      // 统计读不到时先归零，避免沿用上一批残留的值
      stats.value = stats.value.map((item) => ({ ...item, value: 0 }))
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '叶片列表读取失败'
  } finally {
    loading.value = false
  }
}

// ---- 导出：失败要写清原因，并支持再试一次 ----
const exporting = ref(false)
const exportError = ref('')

async function exportRows() {
  exporting.value = true
  exportError.value = ''
  try {
    const response = await request(`${ENDPOINT}/export${buildQuery()}`)
    if (!response.ok) {
      exportError.value = await readError(response, '导出失败，请稍后重试')
      return
    }
    const payload = await response.json()
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `叶片清单-${new Date().toISOString().slice(0, 10)}.json`
    link.click()
    URL.revokeObjectURL(url)
    notice.value = `已导出 ${payload.total ?? 0} 条叶片记录`
  } catch (error) {
    exportError.value = error instanceof Error ? error.message : '导出失败：网络异常，请检查后端服务后重试'
  } finally {
    exporting.value = false
  }
}

// ---- 登记叶片 ----
const formFields = [
  { key: '叶片编号', label: '叶片编号', required: true },
  { key: '所属机组', label: '所属机组', required: true },
  { key: '叶片长度', label: '叶片长度', required: true },
  { key: '制造厂商', label: '制造厂商', required: false },
] as const

const createOpen = ref(false)
const creating = ref(false)
const createError = ref('')
const form = reactive<Record<string, string>>({})

function openCreate() {
  formFields.forEach((field) => {
    form[field.key] = ''
  })
  createError.value = ''
  createOpen.value = true
}

function closeCreate() {
  createOpen.value = false
}

async function submitCreate() {
  creating.value = true
  createError.value = ''
  const values: Record<string, string> = {}
  formFields.forEach((field) => {
    values[field.key] = form[field.key]?.trim() ?? ''
  })
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload || payload.ok === false) {
      createError.value = payload?.message
        ?? await readError(response, '叶片登记失败，请稍后重试')
      return
    }
    createOpen.value = false
    keyword.value = ''
    status.value = ''
    await reload()
    notice.value = payload.message || '叶片已登记'
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '叶片登记失败：网络异常，请稍后重试'
  } finally {
    creating.value = false
  }
}

// ---- 动作流转 ----
async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload || payload.ok === false) {
      throw new Error(payload?.message ?? '叶片动作未生效，请稍后重试')
    }
    await reload()
    notice.value = payload.message || `叶片已${action}`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '叶片操作失败'
  }
}

// ---- 详情 ----
const detailFields = [
  { key: 'id', label: '记录ID' },
  ...columns.map((key) => ({ key, label: key })),
]
const detailOpen = ref(false)
const detailLoading = ref(false)
const detailError = ref('')
const detail = ref<Row | null>(null)
let detailId: string | number | null = null

async function loadDetail(entryId: string | number) {
  detailLoading.value = true
  detailError.value = ''
  detail.value = null
  try {
    const response = await request(`${ENDPOINT}/${entryId}`)
    if (!response.ok) {
      detailError.value = await readError(response, '叶片详情读取失败')
      return
    }
    detail.value = await response.json()
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : '叶片详情读取失败'
  } finally {
    detailLoading.value = false
  }
}

function openDetail(row: Row) {
  if (row.id === null || row.id === undefined) {
    errorMessage.value = '该叶片记录缺少 ID，无法查看详情'
    return
  }
  detailId = row.id
  detailOpen.value = true
  void loadDetail(row.id)
}

function closeDetail() {
  detailOpen.value = false
  detail.value = null
  detailError.value = ''
}

function retryDetail() {
  if (detailId !== null) void loadDetail(detailId)
}

onMounted(reload)
</script>

<style scoped>
.empty-cell {
  text-align: center;
  padding: 32px 12px;
}
.empty-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.empty-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
}
.empty-desc {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
  max-width: 420px;
}
.notice {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 12px;
  max-width: 460px;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
  box-shadow: 0 6px 20px rgba(15, 23, 42, 0.18);
}
.error-notice {
  background: #fef3f2;
  border: 1px solid #fecdca;
  color: #b42318;
}
.ok-notice {
  bottom: 84px;
  background: #ecfdf3;
  border: 1px solid #abefc6;
  color: #067647;
}
.notice-actions {
  display: flex;
  gap: 6px;
}
.modal .notice {
  position: static;
  z-index: auto;
  max-width: none;
  box-shadow: none;
}
.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 30;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
}
.modal {
  width: 520px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 48px);
  overflow: auto;
  background: #fff;
  border-radius: 10px;
  padding: 16px 18px;
}
.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.modal-head h3 {
  margin: 0;
  font-size: 15px;
}
.modal-tip {
  margin: 0 0 12px;
  padding: 8px 10px;
  font-size: 12px;
  color: #8a5a00;
  background: #fffaeb;
  border: 1px solid #fedf89;
  border-radius: 6px;
}
.modal-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.modal-form .filter-item input {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.modal-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}
.detail-list {
  margin: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 16px;
}
.detail-list div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.detail-list dt {
  font-size: 12px;
  color: var(--muted);
}
.detail-list dd {
  margin: 0;
  font-size: 13px;
}
</style>
