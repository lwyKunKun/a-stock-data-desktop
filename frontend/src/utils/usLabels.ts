export const US_SOURCE_LABELS: Record<string, string> = {
  sina_quote: '新浪美股行情',
  tencent_quote: '腾讯美股行情',
  history: 'Yahoo K线',
  sina_history: '新浪历史行情',
  yahoo_summary: 'Yahoo Finance基本面',
  eastmoney: '东方财富',
  sec: 'SEC官方数据',
}

export const US_CHAPTER_KEY_LABELS: Record<string, string> = {
  us_ch1_quote: '行情概览',
  us_ch2_price_trend: 'K线与趋势',
  us_ch3_technical: '技术指标',
  us_ch4_profile: '公司档案与行业',
  us_ch5_valuation: '估值与市场定价',
  us_ch6_income: '营收与盈利趋势',
  us_ch7_balance: '资产负债与偿债能力',
  us_ch8_cashflow: '现金流与盈利质量',
  us_ch9_sec_facts: 'SEC关键事实与数据质量',
  us_ch10_summary: '综合评估',
}

export const SOURCE_STATUS_LABELS: Record<string, string> = {
  ok: '正常',
  failed: '失败',
  skipped: '已跳过',
}

export const US_TABLE_HEADER_LABELS: Record<string, string> = {
  ...US_SOURCE_LABELS,
  symbol: '证券代码',
  name: '公司名称',
  name_zh: '中文名称',
  price: '最新价',
  previous_close: '前收盘价',
  open: '开盘价',
  high: '最高价',
  low: '最低价',
  volume: '成交量',
  change: '涨跌额',
  change_pct: '涨跌幅',
  currency: '币种',
  pe_ttm: '市盈率TTM',
  pb: '市净率',
  market_cap: '总市值',
  marketCap: '总市值',
  market_cap_hundred_million: '总市值(亿)',
  eps_ttm: '每股收益TTM',
  high_52w: '52周最高价',
  low_52w: '52周最低价',
  as_of: '行情时间',
  source: '数据来源',
  date: '日期',
  close: '收盘价',
  adj_close: '复权收盘价',
  sample_count: '样本数量',
  ma5: 'MA5(5日均线)',
  ma10: 'MA10(10日均线)',
  ma20: 'MA20(20日均线)',
  ma50: 'MA50(50日均线)',
  ma200: 'MA200(200日均线)',
  ema12: 'EMA12(12日指数均线)',
  ema26: 'EMA26(26日指数均线)',
  macd_dif: 'MACD DIF',
  macd_dea: 'MACD DEA',
  macd_hist: 'MACD柱值',
  rsi6: 'RSI6',
  rsi14: 'RSI14',
  k: 'KDJ-K',
  d: 'KDJ-D',
  j: 'KDJ-J',
  boll_upper: '布林线上轨',
  boll_middle: '布林线中轨',
  boll_lower: '布林线下轨',
  volume_avg_20d: '20日平均成交量',
  volatility_20d_pct: '20日年化波动率',
  exchange: '交易所',
  sector: '行业板块',
  industry: '细分行业',
  country: '国家/地区',
  website: '公司网站',
  description: '公司简介',
  cik: 'SEC公司标识号',
  CIK: 'SEC公司标识号',
  company: '公司名称',
  available: '数据可用',
  note: '数据说明',
  metrics: '指标集合',
  enterprise_value: '企业价值',
  pe_forward: '远期市盈率',
  ps_ttm: '市销率TTM',
  eps_forward: '远期每股收益',
  dividend_yield: '股息率',
  revenue_growth: '营收增速',
  revenue: '营收',
  net_income: '净利润',
  eps_diluted: '稀释后每股收益',
  assets: '资产',
  liabilities: '负债',
  equity: '股东权益',
  cash: '现金',
  operating_cashflow: '经营活动现金流',
  capex: '资本性支出',
  tag: 'SEC指标',
  unit: '计量单位',
  start: '期间开始日期',
  end: '期间结束日期',
  value: '数值',
  form: 'SEC表单',
  filed: '提交日期',
  fy: '财年',
  fp: '财务期间',
  accn: 'SEC档案编号',
  endDate: '截止日期',
  totalRevenue: '总营收',
  costOfRevenue: '营业成本',
  grossProfit: '毛利润',
  operatingRevenue: '营业收入',
  operatingIncome: '营业利润',
  researchDevelopment: '研发费用',
  totalOperatingExpenses: '营业总支出',
  incomeBeforeTax: '税前利润',
  incomeTaxExpense: '所得税费用',
  interestExpense: '利息费用',
  ebit: '息税前利润',
  ebitda: '息税折旧摊销前利润',
  basicEPS: '基本每股收益',
  dilutedEPS: '稀释后每股收益',
  netIncome: '净利润',
  totalAssets: '总资产',
  totalLiabilitiesNetMinorityInterest: '总负债',
  totalLiab: '总负债',
  stockholdersEquity: '股东权益',
  totalEquityGrossMinorityInterest: '股东权益总额',
  cashAndCashEquivalents: '现金及现金等价物',
  currentAssets: '流动资产',
  currentLiabilities: '流动负债',
  currentRatio: '流动比率',
  longTermDebt: '长期债务',
  totalDebt: '总债务',
  netDebt: '净债务',
  capitalExpenditures: '资本性支出',
  freeCashflow: '自由现金流',
  operatingCashflow: '经营活动现金流',
  totalCashFromOperatingActivities: '经营活动现金流',
  REPORT_DATE: '报告期',
  SECUCODE: '证券代码',
  SECURITY_CODE: '证券代码',
  SECURITY_NAME_ABBR: '证券简称',
  TOTAL_OPERATE_INCOME: '营业总收入',
  PARENT_NETPROFIT: '归母净利润',
  BASIC_EPS: '基本每股收益',
  TOTAL_ASSETS: '总资产',
  TOTAL_LIABILITIES: '总负债',
  MONETARYFUNDS: '货币资金',
  NETCASH_OPERATE: '经营活动现金流净额',
}

export function formatUsSource(source: string): string {
  return US_SOURCE_LABELS[source] ?? source
}

export function formatUsChapterKey(key: string): string {
  return US_CHAPTER_KEY_LABELS[key] ?? key
}

export function formatSourceStatus(status: string): string {
  return SOURCE_STATUS_LABELS[status] ?? status
}

export function formatUsTaskMessage(message: string | null | undefined): string {
  const raw = String(message ?? '').trim()
  if (!raw) return ''
  // 取最后一个冒号后的片段做映射：进度文案形如“正在采集美股数据：yahoo_summary”，
  // 只翻译末尾的数据源 id 或章节 key，前缀原文保留。
  const separatorIndex = raw.lastIndexOf('：')
  if (separatorIndex > 0) {
    const prefix = raw.slice(0, separatorIndex + 1)
    const tail = raw.slice(separatorIndex + 1).trim()
    return `${prefix}${US_SOURCE_LABELS[tail] ?? US_CHAPTER_KEY_LABELS[tail] ?? tail}`
  }
  return US_CHAPTER_KEY_LABELS[raw] ?? US_SOURCE_LABELS[raw] ?? raw
}

export function localizeUsTableHeaders(markdown: string): string {
  const lines = (markdown || '').split('\n')
  let inTable = false

  return lines
    .map((line) => {
      const trimmed = line.trim()
      if (!trimmed.startsWith('|') || !trimmed.endsWith('|')) {
        inTable = false
        return line
      }
      if (!inTable) {
        inTable = true
        // 数据单元格可能包含 `\|` 转义，直接 split 会破坏列结构，因此整行跳过。
        if (trimmed.includes('\\|')) return line
        const cells = trimmed.slice(1, -1).split('|').map((cell) => cell.trim())
        return `| ${cells.map((cell) => US_TABLE_HEADER_LABELS[cell] ?? cell).join(' | ')} |`
      }
      return line
    })
    .join('\n')
}

export function localizeUsDataMarkdown(markdown: string): string {
  return localizeUsTableHeaders(markdown)
}
