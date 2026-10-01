<script setup lang="ts">
// 缠论学习训练页（P0）：
//  1. 逐步揭示训练：K线逐根推进，到达关键位置暂停，让用户判断买/卖/观望，
//     再揭示缠论引擎的真实信号 + 结构讲解 + 事后 N 日验证，培养盘感并验证模型准确性。
//  2. 回测复盘讲解：逐笔买卖点讲解卡（为什么成立 + 事后表现）。
import { computed, onMounted, ref, watch } from 'vue'
import ChanlunChart from '../components/ChanlunChart.vue'
import { formatError } from '../api'
import type { Bar } from '../types'

interface ChanlunBi {
  index: number
  direction: 'up' | 'down'
  start_date: string
  end_date: string
  high: number
  low: number
  start_index?: number
  end_index?: number
  done: boolean
}
interface ChanlunXd {
  index: number
  direction: 'up' | 'down'
  start_date: string
  end_date: string
  high: number
  low: number
}
interface ChanlunZs {
  index: number
  zg: number
  zd: number
  gg: number
  dd: number
  line_count: number
  start_date: string
  end_date: string
  start_index?: number
  end_index?: number
  done: boolean
}
interface ChanlunMmd {
  type: string
  date: string | null
  msg: string
  confidence: number
  // V102 缠论决策支持（条件264-267）
  v102_signal_quality?: {
    overall_grade: string
    overall_score: number
    strength: string
    confidence_adjust: number
  } | null
  v102_decision_support?: {
    entry_price: number
    stop_loss: number
    take_profit_1: number
    risk_reward_ratio: number
    position_size_pct: number
    action_recommendation: string
  } | null
  v102_pattern_match?: {
    similar_patterns_found: number
    win_rate: number
    avg_return: number
  } | null
}
interface ChanlunFx {
  // 字段名与后端 fractals[].fx_type 及 ChanlunChart 的 ChanlunFx 保持一致
  fx_type: 'ding' | 'di'
  date: string
  val: number
  index?: number
  bar_index?: number
}
interface ChanlunBc {
  type: 'bi' | 'pz' | 'qs'
  bc: boolean
  date: string | null
  msg: string
}
interface Candidate {
  index: number
  date: string
  kind: 'fractal' | 'mmd'
  fx_type: 'ding' | 'di' | null
  signal: {
    type: string
    confidence: number
    grade: string | null
    // V344: 训练教学展示 V102 决策支持（仅 3买/3卖 有建议）
    v102_grade?: string | null
    v102_advice?: string | null
    // V422: 错误归因「正确解读」（答错时展示）
    explanation?: string | null
  } | null
}
interface MmdOutcome {
  type: string
  date: string | null
  price: number | null
  ret_5d: number | null
  ret_10d: number | null
  ret_20d: number | null
  max_5d: number | null
  min_5d: number | null
}

const code = ref('000001')
const category = ref<'DAY' | 'WEEK' | 'MIN_5' | 'MIN_15' | 'MIN_30' | 'MIN_60'>('DAY')
const count = ref(400)
// V421: 难度分级 + 随机标的
const difficulty = ref<'easy' | 'medium' | 'hard'>('medium')
const seed = ref(0)
// V731 F3：任意历史区间回放（不是只能从「现在」往后退）。
// 后端 train/session 早已支持 start_date/end_date（ChanlunView 的「时光跳转」
// 就是这么用的），但训练页此前既不提供输入、请求里也没传 —— F3 第一条在
// 训练页实际不可用。留空 = 按 K 线根数取最近一段（保持原行为）。
const startDate = ref('')
const endDate = ref('')
/** 是否启用了历史区间（两个都填才生效，避免只填一半导致歧义）。 */
const useDateRange = computed(() => Boolean(startDate.value && endDate.value))
const RANDOM_POOL = [
  '000001',
  '000333',
  '000651',
  '000858',
  '002415',
  '002475',
  '002594',
  '300059',
  '300750',
  '600000',
  '600030',
  '600036',
  '600276',
  '600519',
  '600887',
  '600900',
  '601012',
  '601166',
  '601318',
  '601888',
]
const loading = ref(false)
const error = ref('')
const mode = ref<'train' | 'review' | 'leaderboard'>('train') // 训练 / 复盘 / 排行榜

// V90：训练成绩持久化 + 排行榜
const playerName = ref('学员')
const scoreSubmitted = ref(false)
const leaderboard = ref<any[]>([])
const lbLoading = ref(false)
// V424: 排行榜筛选 + 汇总
const lbDifficulty = ref<string>('')
const lbSummary = ref<{ count: number; avg_hit_rate: number; max_score: number } | null>(null)

const bars = ref<Bar[]>([])
const bis = ref<ChanlunBi[]>([])
const xds = ref<ChanlunXd[]>([])
const zss = ref<ChanlunZs[]>([])
const mmds = ref<ChanlunMmd[]>([])
const fxs = ref<ChanlunFx[]>([])
// 展示用「有效分型」（笔端点分型），与 BacktestView / ChanlunView 一致。
// 原始 fractals 是逐三根滑动窗口扫出来的，含共用K线的重叠分型（缠论原文要求
// 相邻分型之间至少 1 根独立K线），直接渲染会出现「底→顶→底挤在连续三根K线」
// 的伪分型。详见 scripts/verify_fx_independence.py。
const validFxs = ref<ChanlunFx[]>([])
const bcs = ref<ChanlunBc[]>([])
const zsds = ref<ChanlunXd[]>([])
const qsds = ref<ChanlunXd[]>([])
const macd = ref<{ dif: number[]; dea: number[]; hist: number[] } | null>(null)
const analysisLevel = ref<'bi' | 'xd'>('bi')
const rawDetail = ref<any>(null)
const candidates = ref<Candidate[]>([])
const outcomes = ref<MmdOutcome[]>([])

// ── 训练状态 ──
const revealIndex = ref(0) // 当前揭示到第几根 K 线（含）
const autoReveal = ref(false) // 自动推进
let timer: number | null = null

const currentCandidateIdx = ref(-1) // 正在提问的候选点（candidates 下标）
const answered = ref(false) // 本题是否已作答
const userChoice = ref<'buy' | 'sell' | 'hold' | null>(null)

// 计分
const totalAsked = ref(0)
const hitCount = ref(0)
const score = ref(0)

// ── V731 F3：训练会话可保存/续练（localStorage）────────────────────────
// 需求 F3 第二条此前**完全没有实现**（全项目 localStorage 只用于自选股/
// 新手引导/阅读记录/最近浏览）。这里补上。
//
// **安全约束（重要）**：只持久化进度，绝不持久化 candidates[].signal
// 与 mmd_outcomes —— 那些是「答案 + 未来走势」，写进 localStorage 等于
// 把防作弊闸门（4fe2bbb）绕过：用户 F12 看 Application 就能读到全部答案。
// 恢复时仍以 mode=train 重新拉题，答案照旧按需取回。
const SESSION_KEY = 'easy_tdx_train_session_v1'

type SavedSession = {
  code: string
  category: string
  count: number
  difficulty: string
  seed: number
  startDate: string
  endDate: string
  revealIndex: number
  currentCandidateIdx: number
  totalAsked: number
  hitCount: number
  score: number
  savedAt: string
}

const hasSavedSession = ref(false)
const savedInfo = ref<{ code: string; totalAsked: number; savedAt: string } | null>(null)

function loadSavedSession(): SavedSession | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    if (!raw) return null
    const s = JSON.parse(raw) as Partial<SavedSession>
    // 关键字段缺失就当作无效存档，避免恢复出一个半残状态
    if (typeof s?.code !== 'string' || typeof s?.revealIndex !== 'number') return null
    return s as SavedSession
  } catch {
    return null
  }
}

function refreshSavedInfo() {
  const s = loadSavedSession()
  hasSavedSession.value = Boolean(s)
  savedInfo.value = s
    ? { code: s.code, totalAsked: s.totalAsked ?? 0, savedAt: s.savedAt ?? '' }
    : null
}

/** 存档时间的简短展示（用于「继续上次训练」按钮的 tooltip）。 */
const fmtSavedAt = computed(() => {
  const t = savedInfo.value?.savedAt
  if (!t) return ''
  const d = new Date(t)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString('zh-CN', { hour12: false })
})

function saveSession() {
  const payload: SavedSession = {
    code: code.value,
    category: category.value,
    count: count.value,
    difficulty: difficulty.value,
    seed: seed.value,
    startDate: startDate.value,
    endDate: endDate.value,
    revealIndex: revealIndex.value,
    currentCandidateIdx: currentCandidateIdx.value,
    totalAsked: totalAsked.value,
    hitCount: hitCount.value,
    score: score.value,
    savedAt: new Date().toISOString(),
  }
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify(payload))
    refreshSavedInfo()
  } catch {
    /* 隐私模式下 localStorage 不可写：不影响训练本身 */
  }
}

function clearSavedSession() {
  try {
    localStorage.removeItem(SESSION_KEY)
  } catch {
    /* ignore */
  }
  refreshSavedInfo()
}

/**
 * 续练：把存档的参数恢复回来，再重新拉一次题目。
 * 注意这里**必须**重新请求 —— 不能把 bars/candidates 也存起来，
 * 因为它们带着答案，存下来就是泄题（同上）。
 */
async function resumeSession() {
  const s = loadSavedSession()
  if (!s) return
  code.value = s.code
  category.value = s.category as typeof category.value
  count.value = s.count
  difficulty.value = s.difficulty as typeof difficulty.value
  seed.value = s.seed
  startDate.value = s.startDate ?? ''
  endDate.value = s.endDate ?? ''
  await startTraining()
  // startTraining 会重置进度，这里再把存档的进度覆盖回去
  revealIndex.value = s.revealIndex
  currentCandidateIdx.value = s.currentCandidateIdx
  totalAsked.value = s.totalAsked ?? 0
  hitCount.value = s.hitCount ?? 0
  score.value = s.score ?? 0
  jumpToCandidateIdx(s.currentCandidateIdx)
}

// 训练是否完成
const finished = computed(() => revealIndex.value >= bars.value.length - 1)

// 当前候选点
const currentCandidate = computed<Candidate | null>(() =>
  currentCandidateIdx.value >= 0 ? (candidates.value[currentCandidateIdx.value] ?? null) : null,
)

function detectMarket(code6: string): string {
  if (code6.startsWith('6')) return 'SH'
  return 'SZ'
}

// V421: 随机标的（本地代码池）
function randomStock() {
  const idx = Math.floor(Math.random() * RANDOM_POOL.length)
  code.value = RANDOM_POOL[idx]
  startTraining()
}

/** 后端分型字典 → 图表所需结构（顶层 fractals / valid_fractals 同构）。 */
const mapFx = (fr: any[]): ChanlunFx[] =>
  (fr ?? []).map((f: any) => ({
    fx_type: f.fx_type,
    date: f.date,
    val: f.val,
    bar_index: f.bar_index,
  }))

function applyAnalysisLevel(level: 'bi' | 'xd', data: any) {
  if (level === 'xd' && data?.levels?.xd) {
    const xdLevel = data.levels.xd
    bis.value = xdLevel.bis ?? []
    xds.value = []
    zsds.value = xdLevel.zsds ?? []
    qsds.value = xdLevel.qsds ?? []
    zss.value = xdLevel.zss ?? []
    mmds.value = (xdLevel.mmds ?? []).map((m: any) => ({
      type: m.type,
      date: m.date,
      msg: m.msg,
      confidence: m.confidence ?? 0,
      v102_signal_quality: m.v102_signal_quality ?? null,
      v102_decision_support: m.v102_decision_support ?? null,
      v102_pattern_match: m.v102_pattern_match ?? null,
    }))
    bcs.value = xdLevel.bcs ?? []
    // 递归级别（xd）：后端 levels 不含分型字段，不清空会残留 bi 级别分型，
    // 与本级别笔/中枢不匹配（详见 ChanlunView.applyAnalysisLevel 同处说明）。
    fxs.value = []
    validFxs.value = []
    return
  }

  bis.value = data?.bis ?? []
  xds.value = data?.xds ?? []
  zsds.value = data?.zsds ?? []
  qsds.value = data?.qsds ?? []
  zss.value = data?.zss ?? []
  mmds.value = (data?.mmds ?? []).map((m: any) => ({
    type: m.type,
    date: m.date,
    msg: m.msg,
    confidence: m.confidence ?? 0,
    // V731 修复：bar_index（横轴锚定）+ anchor_val（纵轴锚定，= 触发笔终点
    // 分型极值价）此前双双漏映射。缺 anchor_val 时 ChanlunChart 会退化为
    // 「该K线 low*0.995 / high*1.005」的视觉偏移值，图上画的不是真实买卖点
    // 价格；缺 bar_index 时横轴只能靠日期匹配，分钟级会错位。
    bar_index: m.bar_index,
    anchor_val: m.anchor_val ?? null,
    v102_signal_quality: m.v102_signal_quality ?? null,
    v102_decision_support: m.v102_decision_support ?? null,
    v102_pattern_match: m.v102_pattern_match ?? null,
  }))
  bcs.value = data?.bcs ?? []
  // 回到笔级别：分型只在顶层数据里（levels 中没有），必须恢复，
  // 否则从 xd 切回 bi 后分型会永久丢失。
  fxs.value = mapFx(data?.fractals)
  validFxs.value = mapFx(data?.valid_fractals)
}

function onAnalysisLevelChange() {
  if (rawDetail.value) {
    applyAnalysisLevel(analysisLevel.value, rawDetail.value)
  }
}

/**
 * 切到「复盘讲解」：F2 需要 mmd_outcomes（信号后 5/10/20 日实际涨跌）。
 * 但训练会话是带防作弊闸门拉的（outcomes 为空），直接切过去会得到**空表格**
 * —— 这正是 V731 引入闸门时引入的回归（复盘面板 v-for 的就是 outcomes）。
 * 因此这里检测到 outcomes 为空就单独以 review 模式补拉一次。
 * 主动切到复盘页已不是在答题，此时取事后收益不构成泄题。
 */
/**
 * 统一的 train/session 请求（V731 F3）。
 *
 * 三处调用（开始训练 / 作答后取答案 / 复盘补拉）必须**参数完全一致**，
 * 否则同一轮训练会拿到不同区间的数据 —— 题目与答案对不上。此前三处各写
 * 一遍，已经出现过「复盘取不到 outcomes」这类不一致（见 6b83562）。
 *
 * 同时这里带上历史区间：F3 要求「任意历史区间回放」，后端早已支持
 * start_date/end_date，但训练页此前从未传过。
 */
async function fetchSession(
  opts: { mode?: 'train' | 'review'; revealLimit?: number | null } = {},
): Promise<any> {
  const qs = new URLSearchParams({
    difficulty: String(difficulty.value),
    seed: String(seed.value),
    mode: opts.mode ?? 'train',
  })
  if (opts.revealLimit != null) qs.set('reveal_limit', String(opts.revealLimit))
  const body: Record<string, unknown> = {
    market: detectMarket(code.value),
    code: code.value,
    category: category.value,
    count: count.value,
    start: 0,
  }
  // F3：历史区间（两个都填才传，留空则按 K 线根数取最近一段）
  if (useDateRange.value) {
    body.start_date = startDate.value
    body.end_date = endDate.value
  }
  const resp = await fetch(`/api/v1/chanlun/train/session?${qs}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return await resp.json()
}

async function switchToReview() {
  mode.value = 'review'
  if (!bars.value.length || outcomes.value.length > 0) return
  loading.value = true
  try {
    const d = await fetchSession({ mode: 'review' })
    // 只补 outcomes，**不覆盖 candidates**：复盘模式的 candidates 是带答案的，
    // 若写回前端，用户切回训练就会在内存里看到答案（泄题）。训练进度也
    // 保持不动，避免中途看一眼复盘就丢分。
    if (!d?.error) outcomes.value = d?.mmd_outcomes ?? []
  } catch {
    /* 复盘数据取不到时保持原样，不打断用户 */
  } finally {
    loading.value = false
  }
}

async function startTraining() {
  loading.value = true
  error.value = ''
  try {
    // V731 防作弊闸门：固定 train 模式开局（不下发答案与未来走势，避免
    // F12 看 Network 泄题）。复盘需要的 mmd_outcomes 由 switchToReview()
    // 单独补拉 —— 两者分开，复盘数据才不会污染训练态。
    // 参数构造统一走 fetchSession（含 F3 历史区间），避免三处不一致。
    const d = await fetchSession({ mode: 'train', revealLimit: 0 })
    if (d?.error) throw new Error(d.error)
    bars.value = d.bars ?? []
    rawDetail.value = d
    analysisLevel.value = 'bi'
    applyAnalysisLevel('bi', d)
    fxs.value = mapFx(d.fractals)
    validFxs.value = mapFx(d.valid_fractals)
    macd.value = d.macd && d.macd.dif?.length ? d.macd : null
    candidates.value = d.candidates ?? []
    outcomes.value = d.mmd_outcomes ?? []

    // 初始揭示：从第一根开始
    revealIndex.value = 0
    currentCandidateIdx.value = -1
    answered.value = false
    userChoice.value = null
    totalAsked.value = 0
    hitCount.value = 0
    score.value = 0
    scoreSubmitted.value = false
    // 快进到第一个候选点之前几根，让用户看到背景
    jumpToNextCandidate()
  } catch (e) {
    error.value = formatError(e)
  } finally {
    loading.value = false
  }
}

// 揭示到下一个候选点：需要至少 CONTEXT 根背景 K 线，揭示到转折点本身
const CONTEXT = 30
/** 定位到指定候选点下标（续练用：恢复到上次停下的那一题）。 */
function jumpToCandidateIdx(idx: number) {
  const c = candidates.value[idx]
  if (c && c.index < bars.value.length) {
    revealIndex.value = Math.min(c.index, bars.value.length - 1)
    currentCandidateIdx.value = idx
  } else if (candidates.value.length) {
    // 存档下标越界（数据变了）→ 退化为跳到第一个候选点
    jumpToNextCandidate()
    return
  }
  answered.value = false
  userChoice.value = null
}

function jumpToNextCandidate() {
  for (let i = 0; i < candidates.value.length; i++) {
    const c = candidates.value[i]
    if (c.index >= CONTEXT && c.index < bars.value.length) {
      revealIndex.value = Math.min(c.index, bars.value.length - 1)
      currentCandidateIdx.value = i
      answered.value = false
      userChoice.value = null
      return
    }
  }
  // 没有更多候选点 → 直接揭示到末尾
  revealIndex.value = bars.value.length - 1
  currentCandidateIdx.value = -1
}

// 手动逐根推进
function stepForward() {
  if (finished.value) return
  revealIndex.value = Math.min(revealIndex.value + 5, bars.value.length - 1)
  // 检查是否越过某个候选点
  const c = candidates.value[currentCandidateIdx.value]
  if (!c || revealIndex.value >= c.index) {
    // 当前候选点已被揭示，若未作答则进入提问；否则跳到下一个
    if (currentCandidateIdx.value >= 0 && !answered.value && revealIndex.value >= (c?.index ?? 0)) {
      // 停在提问态
      return
    }
    // 找下一个未到达的候选点
    for (let i = 0; i < candidates.value.length; i++) {
      const ci = candidates.value[i]
      if (ci.index >= revealIndex.value && ci.index < bars.value.length) {
        if (i !== currentCandidateIdx.value) {
          currentCandidateIdx.value = i
          answered.value = false
          userChoice.value = null
          return
        }
      }
    }
  }
}

// 提交用户判断
function submitChoice(choice: 'buy' | 'sell' | 'hold') {
  userChoice.value = choice
  answered.value = true
  totalAsked.value++
  const c = currentCandidate.value
  if (!c) return

  // V731：开局为了防止作弊，后端没下发 signal 答案。作答**之后**才按需
  // 拉取这一题的真实结论用于判分与讲解 —— 顺序不能反，否则就是提前泄题。
  void (async () => {
    const sig = await fetchSignalFor(c.index, c)
    judge(choice, c, sig)
  })()
}

/** V731：作答后按需取回该题的真实信号（防作弊闸门的配套）。 */
async function fetchSignalFor(index: number, c: Candidate): Promise<string> {
  if (c.signal?.type) return c.signal.type // 复盘模式/已带答案时直接用
  try {
    // 统一走 fetchSession：必须与开局请求同区间、同难度/种子，否则取回的
    // 答案可能来自另一段行情（题目与答案对不上）。
    const d = await fetchSession({ mode: 'train', revealLimit: index })
    const hit = (d?.candidates ?? []).find(
      (x: { index: number }) => x.index === index,
    ) as Candidate | undefined
    if (hit?.signal?.type) {
      // 回填到本地候选点，供讲解/错题集复用（本题已作答，不算泄题）
      c.signal = hit.signal
      return hit.signal.type
    }
  } catch {
    /* 取不到答案时不判分，不计入正确数 */
  }
  return ''
}

/** 判分 + 讲解 + 错题库（抽出来以便答案异步到位后执行）。 */
function judge(choice: 'buy' | 'sell' | 'hold', c: Candidate, sig: string) {
  let actual: 'buy' | 'sell' | 'hold' = 'hold'
  if (sig.includes('buy')) actual = 'buy'
  else if (sig.includes('sell')) actual = 'sell'

  const isHit = choice === actual
  if (isHit) {
    hitCount.value++
    score.value += 2
    // 精确命中类型（如恰好都是 1buy）额外加分
    if (c.kind === 'mmd' && sig.toLowerCase() === choice.toLowerCase() + '点') score.value += 1
  } else {
    score.value += 0
    // V426: 答错入错题集
    recordMistake(c, choice, actual)
  }
  // V731 F3：每题作答后自动存进度，用户中途关页面也能续练。
  // 存的是进度与计分，不含答案（见 saveSession 的安全约束）。
  saveSession()
}

// V426: 答错时提交错题（fire-and-forget，不阻塞训练）
function recordMistake(c: Candidate, choice: string, actual: string) {
  if (c.kind !== 'mmd' || !c.signal) return
  fetch('/api/v1/learn/mistakes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      player: playerName.value.trim() || '学员',
      symbol: `${detectMarket(code.value)}${code.value}`,
      category: category.value,
      difficulty: difficulty.value,
      question_date: c.date,
      signal_type: c.signal.type,
      user_choice: choice,
      actual,
      explanation: c.signal.explanation ?? '',
    }),
  }).catch(() => {
    // 错题记录失败不阻塞训练
  })
}

// 进入下一题
function nextQuestion() {
  // 从当前候选点后继续
  const from = (currentCandidate.value ? currentCandidate.value.index : revealIndex.value) + 1
  for (let i = 0; i < candidates.value.length; i++) {
    const c = candidates.value[i]
    if (c.index >= from && c.index < bars.value.length) {
      revealIndex.value = Math.min(c.index, bars.value.length - 1)
      currentCandidateIdx.value = i
      answered.value = false
      userChoice.value = null
      return
    }
  }
  revealIndex.value = bars.value.length - 1
  currentCandidateIdx.value = -1
}

// 自动播放
function toggleAuto() {
  autoReveal.value = !autoReveal.value
  if (autoReveal.value) {
    timer = window.setInterval(() => {
      if (finished.value) {
        stopAuto()
        return
      }
      revealIndex.value = Math.min(revealIndex.value + 2, bars.value.length - 1)
    }, 120)
  } else {
    stopAuto()
  }
}
function stopAuto() {
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
  autoReveal.value = false
}

// 命中率
const hitRate = computed(() =>
  totalAsked.value ? Math.round((hitCount.value / totalAsked.value) * 100) : 0,
)

// ── V90：提交成绩 + 加载排行榜 ─────────────────────────────────────
async function submitScore() {
  if (scoreSubmitted.value || totalAsked.value === 0) return
  try {
    const resp = await fetch('/api/v1/chanlun/train/score', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        player_name: playerName.value.trim() || '学员',
        score: score.value,
        total_asked: totalAsked.value,
        hit_count: hitCount.value,
        hit_rate: hitRate.value,
        code: code.value,
        market: detectMarket(code.value),
        category: category.value,
        count: count.value,
      }),
    })
    if (resp.ok) {
      scoreSubmitted.value = true
      loadLeaderboard()
    }
  } catch {
    // 提交失败不打断训练流程，静默忽略
  }
}

function showLeaderboard() {
  mode.value = 'leaderboard'
  loadLeaderboard()
}

async function loadLeaderboard() {
  lbLoading.value = true
  try {
    const qs = lbDifficulty.value ? `?limit=10&difficulty=${lbDifficulty.value}` : '?limit=10'
    const resp = await fetch('/api/v1/chanlun/train/leaderboard' + qs)
    if (resp.ok) {
      const d = await resp.json()
      leaderboard.value = d.items ?? []
      lbSummary.value = d.summary ?? null
    }
  } catch {
    // 排行榜加载失败不阻塞页面
  } finally {
    lbLoading.value = false
  }
}

// 训练完成后自动提交一次成绩
watch(finished, (v) => {
  if (v) submitScore()
})

// 图表数据：训练模式用 revealIndex 截断
const chartReveal = computed(() => (mode.value === 'train' ? revealIndex.value : undefined))

// V423: 结构时间线（已揭示的分型/笔/中枢事件，点击跳转）
interface StructureEvent {
  index: number
  kind: 'fx' | 'bi' | 'zs'
  label: string
}
const structureTimeline = computed<StructureEvent[]>(() => {
  const limit = revealIndex.value
  const events: StructureEvent[] = []
  // 与图上同源：也只列有效分型，否则时间线会出现图上没画的伪分型
  for (const fx of validFxs.value) {
    const idx = fx.bar_index ?? fx.index
    if (idx !== undefined && idx <= limit) {
      events.push({
        index: idx,
        kind: 'fx',
        label: `${fx.fx_type === 'ding' ? '顶分型' : '底分型'}`,
      })
    }
  }
  for (const bi of bis.value) {
    const idx = bi.end_index ?? bi.start_index
    if (idx !== undefined && idx <= limit) {
      events.push({ index: idx, kind: 'bi', label: `笔 ${bi.direction === 'up' ? '↑' : '↓'}` })
    }
  }
  for (const zs of zss.value) {
    const idx = zs.end_index ?? zs.start_index
    if (idx !== undefined && idx <= limit) {
      events.push({ index: idx, kind: 'zs', label: `中枢 [${zs.zd}, ${zs.zg}]` })
    }
  }
  return events.sort((a, b) => a.index - b.index)
})

function jumpToStructure(ev: StructureEvent) {
  revealIndex.value = Math.min(ev.index, bars.value.length - 1)
}

function confidenceColor(c: number): string {
  if (c >= 0.85) return '#22c55e'
  if (c >= 0.7) return '#eab308'
  if (c >= 0.55) return '#f97316'
  return '#6b7280'
}
function retColor(v: number | null): string {
  if (v === null) return '#94a3b8'
  return v >= 0 ? '#22c55e' : '#ef4444'
}
// 某个候选点（买卖点）对应的事后验证数据
function outcomeFor(c: Candidate | null): MmdOutcome | null {
  if (!c || c.kind !== 'mmd' || !c.signal) return null
  return outcomes.value.find((o) => o.type === c.signal!.type && o.date === c.date) ?? null
}

// 当前候选点答案判定（用于模板渲染）
const answerVerdict = computed<{ ok: boolean; text: string; cls: string }>(() => {
  const c = currentCandidate.value
  if (!c || !answered.value) return { ok: true, text: '', cls: 'hold' }
  const sig = c.signal?.type ?? ''
  const actual = sig.includes('buy') ? 'buy' : sig.includes('sell') ? 'sell' : 'hold'
  const u = userChoice.value
  if (actual === u) {
    return { ok: true, text: '✅ 判断正确', cls: 'good' }
  }
  if (actual === 'hold') return { ok: false, text: '❌ 应观望，此处无信号', cls: 'miss' }
  return {
    ok: false,
    text: `❌ 应为${actual === 'buy' ? '买入' : '卖出'}，判断有偏差`,
    cls: 'miss',
  }
})

// 复盘表：买入后 20 日收跌 / 卖出后 20 日收涨 → 未命中
function isOutcomeMiss(o: MmdOutcome): boolean {
  if (o.ret_20d === null) return false
  return o.type.includes('buy') ? o.ret_20d < 0 : o.type.includes('sell') ? o.ret_20d > 0 : false
}

onMounted(() => {
  refreshSavedInfo() // F3：读存档，决定是否显示「继续上次训练」
  startTraining()
  loadLeaderboard()
})
</script>

<template>
  <div class="train-view">
    <!-- 配置栏 -->
    <div class="config-bar">
      <div class="field-group">
        <label>代码</label>
        <input v-model="code" type="text" placeholder="如 000001" maxlength="6" />
      </div>
      <div class="field-group">
        <label>周期</label>
        <select v-model="category">
          <option value="DAY">日线</option>
          <option value="WEEK">周线</option>
          <option value="MIN_5">5分钟</option>
          <option value="MIN_15">15分钟</option>
          <option value="MIN_30">30分钟</option>
          <option value="MIN_60">60分钟</option>
        </select>
      </div>
      <div class="field-group">
        <label>K 线根数</label>
        <input v-model.number="count" type="number" min="100" max="2000" step="100" />
      </div>
      <!-- V731 F3：任意历史区间回放（不是只能从「现在」往后退）。
           两个都填才生效，留空则按 K 线根数取最近一段（保持原行为）。 -->
      <div class="field-group">
        <label>历史区间起</label>
        <input v-model="startDate" type="date" />
      </div>
      <div class="field-group">
        <label>历史区间止</label>
        <input v-model="endDate" type="date" :min="startDate || undefined" />
      </div>
      <div v-if="useDateRange" class="field-group">
        <label>&nbsp;</label>
        <button class="ghost" @click="startDate = ''; endDate = ''">清除区间</button>
      </div>
      <div class="field-group">
        <label>难度</label>
        <select v-model="difficulty">
          <option value="easy">简单（高置信度信号）</option>
          <option value="medium">中等（全部信号）</option>
          <option value="hard">困难（低置信度 + 干扰项）</option>
        </select>
      </div>
      <div class="field-group">
        <label>分析级别</label>
        <select v-model="analysisLevel" @change="onAnalysisLevelChange">
          <option value="bi">笔级别</option>
          <option value="xd">线段级别</option>
        </select>
      </div>
      <button class="primary" :disabled="loading" @click="startTraining">
        {{ loading ? '加载中…' : '🔄 开始训练' }}
      </button>
      <button class="ghost" :disabled="loading" @click="randomStock">🎲 随机标的</button>
      <!-- V731 F3：训练会话可保存/续练 -->
      <button
        v-if="hasSavedSession"
        class="ghost"
        :disabled="loading"
        :title="`上次：${savedInfo?.code} 已答 ${savedInfo?.totalAsked} 题（${fmtSavedAt}）`"
        @click="resumeSession()"
      >
        ⏯ 继续上次训练
      </button>
      <button class="ghost" :disabled="loading || !bars.length" @click="saveSession()">
        💾 保存进度
      </button>
      <div class="mode-tabs">
        <button :class="['tab', { active: mode === 'train' }]" @click="mode = 'train'">
          🎯 逐步揭示训练
        </button>
        <button :class="['tab', { active: mode === 'review' }]" @click="switchToReview()">
          📖 复盘讲解
        </button>
        <button :class="['tab', { active: mode === 'leaderboard' }]" @click="showLeaderboard">
          🏆 排行榜
        </button>
      </div>
    </div>

    <div v-if="error" class="error-banner">⚠ {{ error }}</div>

    <!-- 训练模式 -->
    <template v-if="mode === 'train' && bars.length">
      <div class="train-layout">
        <div class="train-main">
          <div class="chart-area">
            <ChanlunChart
              :bars="bars"
              :bis="bis"
              :xds="xds"
              :zsds="zsds"
              :qsds="qsds"
              :zss="zss"
              :mmds="mmds"
              :fxs="fxs"
              :validFxs="validFxs"
              :bcs="bcs"
              :macd="macd ?? undefined"
              :frequency="category"
              :reveal-index="chartReveal"
            />
          </div>
          <div class="train-controls">
            <button class="ghost" :disabled="finished" @click="stepForward">⏩ 揭示 +5 根</button>
            <button class="ghost" :disabled="finished" @click="jumpToNextCandidate()">
              🎯 跳至下个关键点
            </button>
            <button class="ghost" @click="toggleAuto">
              {{ autoReveal ? '⏸ 暂停' : '▶ 自动播放' }}
            </button>
            <span class="reveal-info"
              >已揭示 {{ Math.min(revealIndex + 1, bars.length) }} / {{ bars.length }} 根</span
            >
          </div>

          <!-- V423: 结构时间线（已揭示的分型/笔/中枢，点击跳转） -->
          <div class="structure-timeline">
            <div class="timeline-head">
              结构时间线（{{ structureTimeline.length }} 个已成形事件）
            </div>
            <div class="timeline-scroll">
              <button
                v-for="(ev, i) in structureTimeline"
                :key="i"
                class="timeline-item"
                :class="'kind-' + ev.kind"
                @click="jumpToStructure(ev)"
              >
                <span class="tl-idx">#{{ ev.index }}</span>
                <span class="tl-label">{{ ev.label }}</span>
              </button>
              <div v-if="structureTimeline.length === 0" class="timeline-empty">
                尚未揭示到任何结构
              </div>
            </div>
          </div>
        </div>

        <!-- 提问面板 -->
        <div class="train-side">
          <template v-if="currentCandidate">
            <div class="question-card">
              <div class="q-header">
                <span class="q-kind">{{
                  currentCandidate.kind === 'mmd' ? '🔔 潜在信号' : '🔎 关键分型'
                }}</span>
                <span class="q-date">{{ currentCandidate.date }}</span>
              </div>
              <p class="q-text">
                这里是{{
                  currentCandidate.fx_type === 'ding'
                    ? '顶分型'
                    : currentCandidate.fx_type === 'di'
                      ? '底分型'
                      : '转折点'
                }}附近 （第 {{ currentCandidate.index + 1 }} 根K线），你认为接下来会怎么走？
              </p>
              <div v-if="!answered" class="q-actions">
                <button class="choice buy" @click="submitChoice('buy')">📈 买入</button>
                <button class="choice sell" @click="submitChoice('sell')">📉 卖出</button>
                <button class="choice hold" @click="submitChoice('hold')">⏸ 观望</button>
              </div>
              <!-- 答案揭示 -->
              <div v-else class="q-answer">
                <div class="answer-line">
                  <span class="answer-label">你的判断：</span>
                  <span
                    :class="[
                      'answer-val',
                      userChoice === 'buy' ? 'buy' : userChoice === 'sell' ? 'sell' : 'hold',
                    ]"
                  >
                    {{ userChoice === 'buy' ? '买入' : userChoice === 'sell' ? '卖出' : '观望' }}
                  </span>
                </div>
                <div class="answer-line">
                  <span class="answer-label">缠论引擎：</span>
                  <span
                    v-if="currentCandidate.signal"
                    :class="[
                      'answer-val',
                      currentCandidate.signal.type.includes('buy') ? 'buy' : 'sell',
                    ]"
                  >
                    {{ currentCandidate.signal.type }}（置信度
                    {{ (currentCandidate.signal.confidence * 100).toFixed(0) }}%{{
                      currentCandidate.signal.grade
                        ? ' · ' + currentCandidate.signal.grade + ' 级'
                        : ''
                    }}）
                  </span>
                  <span v-else class="answer-val hold">未发现信号（观望）</span>
                  <!-- V344: V102 决策支持教学提示（仅 3买/3卖 有） -->
                  <span
                    v-if="currentCandidate.signal?.v102_grade"
                    class="train-v102-grade"
                    :class="'g' + currentCandidate.signal.v102_grade"
                  >
                    V102·{{ currentCandidate.signal.v102_grade }}
                  </span>
                  <span
                    v-if="currentCandidate.signal?.v102_advice"
                    class="train-v102-advice"
                    :class="{
                      'adv-buy': currentCandidate.signal.v102_advice.includes('买入'),
                      'adv-sell': currentCandidate.signal.v102_advice.includes('卖出'),
                    }"
                  >
                    {{ currentCandidate.signal.v102_advice }}
                  </span>
                </div>
                <div class="answer-line">
                  <span class="answer-label">结果：</span>
                  <span class="answer-val" :class="answerVerdict.cls">{{
                    answerVerdict.text
                  }}</span>
                </div>
                <!-- V422: 错误归因「正确解读」（答错时展示） -->
                <div
                  v-if="!answerVerdict.ok && currentCandidate.signal?.explanation"
                  class="explain-box"
                >
                  <div class="explain-title">💡 正确解读</div>
                  <p class="explain-text">{{ currentCandidate.signal.explanation }}</p>
                </div>
                <!-- 事后验证 -->
                <div v-if="outcomeFor(currentCandidate)" class="outcome-box">
                  <div class="outcome-title">📊 事后 20 日验证（复盘该点是否可靠）</div>
                  <div class="outcome-grid">
                    <div class="outcome-item">
                      <span class="o-label">5日</span>
                      <span
                        class="o-val"
                        :style="{ color: retColor(outcomeFor(currentCandidate)!.ret_5d) }"
                        >{{
                          outcomeFor(currentCandidate)!.ret_5d != null
                            ? (outcomeFor(currentCandidate)!.ret_5d! >= 0 ? '+' : '') +
                              outcomeFor(currentCandidate)!.ret_5d +
                              '%'
                            : '—'
                        }}</span
                      >
                    </div>
                    <div class="outcome-item">
                      <span class="o-label">10日</span>
                      <span
                        class="o-val"
                        :style="{ color: retColor(outcomeFor(currentCandidate)!.ret_10d) }"
                        >{{
                          outcomeFor(currentCandidate)!.ret_10d != null
                            ? (outcomeFor(currentCandidate)!.ret_10d! >= 0 ? '+' : '') +
                              outcomeFor(currentCandidate)!.ret_10d +
                              '%'
                            : '—'
                        }}</span
                      >
                    </div>
                    <div class="outcome-item">
                      <span class="o-label">20日</span>
                      <span
                        class="o-val"
                        :style="{ color: retColor(outcomeFor(currentCandidate)!.ret_20d) }"
                        >{{
                          outcomeFor(currentCandidate)!.ret_20d != null
                            ? (outcomeFor(currentCandidate)!.ret_20d! >= 0 ? '+' : '') +
                              outcomeFor(currentCandidate)!.ret_20d +
                              '%'
                            : '—'
                        }}</span
                      >
                    </div>
                    <div class="outcome-item">
                      <span class="o-label">20日区间</span>
                      <span class="o-val" style="color: #94a3b8">{{
                        outcomeFor(currentCandidate)!.max_5d != null
                          ? outcomeFor(currentCandidate)!.min_5d +
                            '% ~ ' +
                            outcomeFor(currentCandidate)!.max_5d +
                            '%'
                          : '—'
                      }}</span>
                    </div>
                  </div>
                </div>
                <button class="primary next-btn" @click="nextQuestion()">下一题 →</button>
              </div>
            </div>
          </template>
          <template v-else>
            <div class="question-card done-card">
              <template v-if="finished">
                <p class="done-title">🎉 训练完成！</p>
                <p class="done-sub">
                  共 {{ totalAsked }} 题，方向命中 {{ hitCount }} 题（{{ hitRate }}%）
                </p>
                <p class="done-score">得分：{{ score }}</p>
                <div class="done-save" v-if="totalAsked > 0">
                  <span class="save-label">昵称</span>
                  <input
                    v-model="playerName"
                    class="name-input"
                    maxlength="12"
                    placeholder="学员"
                    :disabled="scoreSubmitted"
                  />
                  <button class="ghost save-btn" :disabled="scoreSubmitted" @click="submitScore()">
                    {{ scoreSubmitted ? '✅ 已存入排行榜' : '💾 保存成绩' }}
                  </button>
                </div>
                <p class="done-hint">
                  切换到「📖 复盘讲解」逐笔回看买卖点的结构依据，或「🏆 排行榜」看成绩排名。
                </p>
              </template>
              <template v-else>
                <p>加载完成，等待揭示…</p>
              </template>
            </div>
          </template>

          <!-- 计分板 -->
          <div class="score-card">
            <div class="score-item">
              <span>题目</span><b>{{ totalAsked }}</b>
            </div>
            <div class="score-item">
              <span>命中</span><b>{{ hitCount }}</b>
            </div>
            <div class="score-item">
              <span>命中率</span><b>{{ hitRate }}%</b>
            </div>
            <div class="score-item">
              <span>得分</span><b class="score-num">{{ score }}</b>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 复盘讲解模式 -->
    <template v-if="mode === 'review' && mmds.length">
      <div class="review-panel">
        <h3>买卖点复盘讲解（{{ mmds.length }} 个信号）</h3>
        <p class="review-hint">
          逐笔查看「为什么成立」+「事后 20 日表现」——用历史验证本模型准确性。命中率定义：买入信号后
          20 日收涨 / 卖出信号后 20 日收跌。
        </p>
        <table>
          <thead>
            <tr>
              <th>类型</th>
              <th>日期</th>
              <th>置信度</th>
              <th>事后 20 日</th>
              <th>验证</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(o, i) in outcomes"
              :key="o.date + o.type"
              :class="{ miss: isOutcomeMiss(o) }"
            >
              <td>
                <strong :style="{ color: o.type.includes('buy') ? '#22c55e' : '#ef4444' }">{{
                  o.type
                }}</strong>
              </td>
              <td>{{ o.date }}</td>
              <td>
                <span class="conf" :style="{ color: confidenceColor(mmds[i]?.confidence ?? 0) }"
                  >{{ ((mmds[i]?.confidence ?? 0) * 100).toFixed(0) }}%</span
                >
              </td>
              <td :style="{ color: retColor(o.ret_20d) }">
                {{ o.ret_20d != null ? (o.ret_20d >= 0 ? '+' : '') + o.ret_20d + '%' : '—' }}
              </td>
              <td>
                <span :class="['verdict', isOutcomeMiss(o) ? 'miss' : 'ok']">{{
                  isOutcomeMiss(o) ? '✗' : '✓'
                }}</span>
              </td>
              <td class="msg-cell">
                {{ mmds[i]?.msg ?? '' }}
                <!-- V102: 信号质量评分卡评级 + 操作建议摘要 -->
                <span
                  v-if="mmds[i]?.v102_signal_quality?.overall_grade"
                  class="train-v102-grade"
                  :class="'g' + mmds[i]!.v102_signal_quality!.overall_grade"
                >
                  V102·{{ mmds[i]!.v102_signal_quality!.overall_grade }}
                </span>
                <span
                  v-if="mmds[i]?.v102_decision_support?.action_recommendation"
                  class="train-v102-advice"
                  :class="{
                    'adv-buy':
                      mmds[i]!.v102_decision_support!.action_recommendation.includes('买入'),
                    'adv-sell':
                      mmds[i]!.v102_decision_support!.action_recommendation.includes('卖出'),
                  }"
                >
                  {{ mmds[i]!.v102_decision_support!.action_recommendation }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- 排行榜模式（V90） -->
    <template v-if="mode === 'leaderboard'">
      <div class="leaderboard-panel">
        <div class="lb-head">
          <h3>🏆 训练排行榜（逐步揭示命中率）</h3>
          <div class="lb-filters">
            <select v-model="lbDifficulty" @change="loadLeaderboard()">
              <option value="">全部难度</option>
              <option value="easy">简单</option>
              <option value="medium">中等</option>
              <option value="hard">困难</option>
            </select>
            <button class="ghost" @click="loadLeaderboard()" :disabled="lbLoading">
              {{ lbLoading ? '加载中…' : '🔄 刷新' }}
            </button>
          </div>
        </div>
        <p v-if="lbSummary" class="review-hint">
          <span class="lb-sum">人数 {{ lbSummary.count }}</span>
          <span class="lb-sum">平均命中率 {{ lbSummary.avg_hit_rate }}%</span>
          <span class="lb-sum">最高分 {{ lbSummary.max_score }}</span>
        </p>
        <p class="review-hint">
          按得分降序；每轮训练完成后成绩自动/手动保存。得分 = 方向命中 +2/题 + 精确命中 +1。
        </p>
        <table class="lb-table">
          <thead>
            <tr>
              <th>#</th>
              <th>学员</th>
              <th>得分</th>
              <th>命中率</th>
              <th>题数</th>
              <th>标的</th>
              <th>周期</th>
              <th>时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in leaderboard" :key="r.id">
              <td class="rank" :class="{ top: i < 3 }">{{ i + 1 }}</td>
              <td class="lb-player">{{ r.player_name }}</td>
              <td class="lb-score">{{ r.score }}</td>
              <td>{{ r.hit_rate.toFixed ? r.hit_rate.toFixed(0) + '%' : r.hit_rate + '%' }}</td>
              <td>{{ r.total_asked }}</td>
              <td class="code-cell">{{ r.market }}.{{ r.code }}</td>
              <td>{{ r.category }}</td>
              <td class="lb-time">{{ (r.created_at || '').slice(0, 16).replace('T', ' ') }}</td>
            </tr>
            <tr v-if="!lbLoading && leaderboard.length === 0">
              <td colspan="8" class="lb-empty">暂无成绩——完成一轮训练后自动保存 🚀</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <div v-if="!loading && bars.length === 0 && !error" class="placeholder">
      <p>选择代码和周期，点击「开始训练」进入缠论学习。</p>
    </div>
  </div>
</template>

<style scoped>
.train-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px 20px;
  overflow-y: auto;
  height: 100%;
}
.config-bar {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  flex-wrap: wrap;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 16px;
}
.field-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.field-group label {
  font-size: 11px;
  color: var(--text-muted);
}
.field-group input,
.field-group select {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px 10px;
  font-size: 13px;
  color: var(--text);
  width: 110px;
}
.field-group input[type='text'] {
  width: 90px;
}
.primary {
  padding: 7px 18px;
  font-size: 13px;
  height: 34px;
}
.mode-tabs {
  display: flex;
  gap: 8px;
  margin-left: auto;
}
.tab {
  padding: 7px 14px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-dim);
  font-size: 13px;
  cursor: pointer;
}
.tab.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.error-banner {
  background: rgba(239, 65, 70, 0.12);
  border: 1px solid var(--up);
  color: var(--up);
  padding: 10px 14px;
  border-radius: var(--radius);
  font-size: 13px;
}
.train-layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.train-main {
  flex: 1;
  min-width: 0;
}
.chart-area {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}
.train-controls {
  display: flex;
  gap: 8px;
  margin-top: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.train-controls .ghost {
  font-size: 12px;
  padding: 5px 12px;
}
.reveal-info {
  font-size: 12px;
  color: var(--text-dim);
  margin-left: auto;
}
.structure-timeline {
  margin-top: 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}
.timeline-head {
  padding: 6px 10px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-dim);
  border-bottom: 1px solid var(--border);
}
.timeline-scroll {
  max-height: 140px;
  overflow-y: auto;
  padding: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.timeline-item {
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 3px 8px;
  cursor: pointer;
  color: var(--text);
  display: flex;
  gap: 6px;
  align-items: center;
  font-size: 11px;
}
.timeline-item:hover {
  background: #1f2937;
}
.timeline-item.kind-fx {
  border-color: #f59e0b;
}
.timeline-item.kind-bi {
  border-color: #22c55e;
}
.timeline-item.kind-zs {
  border-color: #60a5fa;
}
.tl-idx {
  font-family: monospace;
  color: var(--text-dim);
}
.timeline-empty {
  color: var(--text-muted);
  font-size: 12px;
  padding: 8px;
}
.train-side {
  width: 360px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.question-card {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
}
.q-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.q-kind {
  font-size: 12px;
  font-weight: 700;
  color: var(--accent);
}
.q-date {
  font-size: 12px;
  color: var(--text-muted);
}
.q-text {
  font-size: 13px;
  color: var(--text);
  line-height: 1.5;
  margin: 0 0 12px 0;
}
.q-actions {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
.choice {
  padding: 9px 0;
  border-radius: 6px;
  border: 1px solid var(--border);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  background: var(--bg);
  color: var(--text);
}
.choice.buy:hover {
  border-color: #22c55e;
  color: #22c55e;
}
.choice.sell:hover {
  border-color: #ef4444;
  color: #ef4444;
}
.choice.hold:hover {
  border-color: #fbbf24;
  color: #fbbf24;
}
.q-answer {
  display: flex;
  flex-direction: column;
  gap: 8px;
  border-top: 1px dashed var(--border);
  padding-top: 12px;
}
.answer-line {
  display: flex;
  gap: 8px;
  font-size: 13px;
  align-items: baseline;
}
.answer-label {
  color: var(--text-dim);
  flex-shrink: 0;
}
.answer-val {
  font-weight: 700;
}
.answer-val.buy {
  color: #22c55e;
}
.answer-val.sell {
  color: #ef4444;
}
.answer-val.hold {
  color: #fbbf24;
}
.answer-val.good {
  color: #22c55e;
}
.answer-val.miss {
  color: #ef4444;
}
.explain-box {
  background: rgba(96, 165, 250, 0.08);
  border: 1px solid rgba(96, 165, 250, 0.3);
  border-radius: 6px;
  padding: 10px;
}
.explain-title {
  font-size: 11px;
  font-weight: 700;
  color: #60a5fa;
  margin-bottom: 6px;
}
.explain-text {
  font-size: 12px;
  color: #cbd5e1;
  line-height: 1.6;
  margin: 0;
}
.outcome-box {
  background: rgba(255, 255, 255, 0.03);
  border-radius: 6px;
  padding: 10px;
}
.outcome-title {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 6px;
}
.outcome-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px;
}
.outcome-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 4px;
  padding: 6px 4px;
}
.o-label {
  font-size: 10px;
  color: var(--text-dim);
}
.o-val {
  font-size: 13px;
  font-weight: 700;
  font-family: var(--font-mono);
}
.next-btn {
  width: 100%;
  margin-top: 10px;
}
.score-card {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}
.score-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px 4px;
}
.score-item span {
  font-size: 11px;
  color: var(--text-dim);
}
.score-item b {
  font-size: 18px;
  color: var(--text);
}
.score-item b.score-num {
  color: var(--accent);
}
.done-card {
  text-align: center;
}
.done-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--accent);
  margin: 0 0 8px;
}
.done-sub {
  font-size: 13px;
  color: var(--text);
  margin: 0 0 4px;
}
.done-score {
  font-size: 24px;
  font-weight: 700;
  color: var(--text);
  margin: 0 0 8px;
}
.done-hint {
  font-size: 12px;
  color: var(--text-dim);
  margin: 0;
}
.review-panel {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
}
.review-panel h3 {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 6px;
}
.review-hint {
  font-size: 12px;
  color: var(--text-dim);
  margin: 0 0 10px;
}
.review-panel table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.review-panel th {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  color: var(--text-dim);
  font-weight: 500;
}
.review-panel td {
  padding: 6px 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  color: var(--text);
}
.review-panel tr.miss td {
  background: rgba(239, 65, 70, 0.05);
}
.conf {
  font-weight: 600;
}
.verdict {
  font-weight: 700;
}
.verdict.ok {
  color: #22c55e;
}
.verdict.miss {
  color: #ef4444;
}
.msg-cell {
  color: var(--text-dim);
  font-size: 11px;
  max-width: 420px;
}

/* V102: 信号质量评级 + 操作建议摘要（复盘讲解） */
.train-v102-grade {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 700;
  color: #fff;
}
.train-v102-grade.gA {
  background: #22c55e;
}
.train-v102-grade.gB {
  background: #3b82f6;
}
.train-v102-grade.gC {
  background: #f59e0b;
}
.train-v102-grade.gD {
  background: #ef4444;
}
.train-v102-advice {
  display: block;
  margin-top: 3px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 360px;
}
.train-v102-advice.adv-buy {
  color: #22c55e;
}
.train-v102-advice.adv-sell {
  color: #ef4444;
}
.done-save {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: center;
  margin: 10px 0;
}
.save-label {
  font-size: 12px;
  color: var(--text-dim);
}
.name-input {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 5px 10px;
  font-size: 12px;
  color: var(--text);
  width: 90px;
}
.save-btn {
  font-size: 12px;
  padding: 5px 12px;
}
.leaderboard-panel {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
}
.lb-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.lb-head h3 {
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
  margin: 0;
}
.lb-head .ghost {
  font-size: 12px;
  padding: 5px 12px;
}
.lb-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.lb-table th {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  color: var(--text-dim);
  font-weight: 500;
}
.lb-table td {
  padding: 6px 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  color: var(--text);
}
.rank {
  font-weight: 700;
  color: var(--text-dim);
}
.rank.top {
  color: #f59e0b;
}
.lb-player {
  font-weight: 600;
}
.lb-score {
  font-weight: 700;
  color: var(--accent);
}
.code-cell {
  font-family: monospace;
  font-weight: 600;
}
.lb-time {
  color: var(--text-dim);
  font-size: 11px;
}
.lb-empty {
  text-align: center;
  color: var(--text-muted);
  padding: 24px;
}
.placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 300px;
  color: var(--text-dim);
  gap: 8px;
}
</style>
