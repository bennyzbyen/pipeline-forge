export type Capability = Readonly<{
  id: string;
  eyebrow: string;
  title: string;
  description: string;
  input: string;
  output: string;
  glyph: string;
  tone: "blue" | "violet" | "cyan" | "indigo" | "orange";
}>;

export type WorkflowStep = Readonly<{
  index: string;
  verb: string;
  title: string;
  description: string;
}>;

export type ReliabilityPoint = Readonly<{
  title: string;
  description: string;
}>;

export const PLUGIN_VERSION = "1.1.1";
export const OFFICIAL_PLUGIN_GUIDE_URL = "https://learn.chatgpt.com/docs/plugins";
export const GITHUB_REPOSITORY_URL = "https://github.com/bennyzbyen/pipeline-forge";
export const MARKETPLACE_ADD_COMMAND = "codex plugin marketplace add bennyzbyen/pipeline-forge --ref v1.1.1";
export const PLUGIN_DOWNLOAD_URL = "/downloads/pipeline-forge.zip";
export const PLUGIN_CHECKSUM_URL = "/downloads/pipeline-forge.zip.sha256";

export const capabilities: readonly Capability[] = [
  {
    id: "guided-workflow",
    eyebrow: "BEGINNER GUIDE",
    title: "一条龙开发向导",
    description: "先检查材料，再选择正确模块；把 rowkey、周期分类与写入策略等阻塞项翻译成易回答的问题，并持续推进到本地验证交付。",
    input: "任意现场材料",
    output: "路线 / 产物 / 状态",
    glyph: "导",
    tone: "violet",
  },
  {
    id: "requirements",
    eyebrow: "DOCUMENT INTELLIGENCE",
    title: "需求文档转开发说明",
    description: "解析 PRD、DataHub 与 COT 需求，把散落在文档和嵌入表格中的规则整理为 AI 可读的开发说明。",
    input: "DOCX / 表格",
    output: "开发说明.md",
    glyph: "文",
    tone: "blue",
  },
  {
    id: "diagnostics",
    eyebrow: "LOG DIAGNOSTICS",
    title: "数据任务日志诊断",
    description: "从完整日志或截图定位同步、报表及数据平台任务失败原因，区分配置、权限、数据与环境问题。",
    input: "日志 / 截图",
    output: "根因与修复路径",
    glyph: "析",
    tone: "violet",
  },
  {
    id: "sync-code",
    eyebrow: "SYNC CODEGEN",
    title: "数据同步项目代码生成",
    description: "依据开发说明生成可迁移的 DataEngine / DataHub Python 同步项目，逐表校验字段、调度形态、rowkey 与运行配置，并熔断未解决契约。",
    input: "开发说明",
    output: "Python 项目",
    glyph: "同",
    tone: "cyan",
  },
  {
    id: "report-code",
    eyebrow: "REPORT CODEGEN",
    title: "报表项目代码生成",
    description: "生成覆盖 KPI、汇总明细、ClickHouse 写入与 HBase prepare 的报表代码；通用项目使用受限执行契约并校验全部输出。",
    input: "报表规则",
    output: "报表项目",
    glyph: "报",
    tone: "indigo",
  },
  {
    id: "pipeline-excel",
    eyebrow: "PIPELINE EXPORT",
    title: "Pipeline Export 工作簿生成",
    description: "根据水线设计和结构化事实填充 DataHub / DataEngine Pipeline Export 模板，并校验工作表、引用与字段规则。",
    input: "水线事实 / XLSX",
    output: "可导入工作簿",
    glyph: "表",
    tone: "blue",
  },
  {
    id: "ddl",
    eyebrow: "SCHEMA FORGE",
    title: "多数据库 DDL 生成与转换",
    description: "从字段清单、文档或已有 SQL 生成并转换 MySQL、MSSQL、ClickHouse 与 PostgreSQL 建表语句。",
    input: "Schema / DDL",
    output: "可审计 SQL",
    glyph: "库",
    tone: "orange",
  },
] as const;

export const workflowSteps: readonly WorkflowStep[] = [
  { index: "01", verb: "识别", title: "接住现场材料", description: "向导先读取需求文档、任务日志、Pipeline Export 模板、字段表或已有 DDL。" },
  { index: "02", verb: "路由", title: "选择专业路线", description: "识别任务类型和工程语义，只调用当前交付真正需要的模块。" },
  { index: "03", verb: "生成", title: "交付真实产物", description: "输出开发说明、诊断结论、项目代码、Excel 工作簿与 SQL。" },
  { index: "04", verb: "验证", title: "给出明确状态", description: "运行适用校验，区分阻塞、安全脚手架、测试通过和待部署复核。" },
] as const;

export const reliabilityPoints: readonly ReliabilityPoint[] = [
  { title: "产物可审计", description: "关键假设、字段映射与变更内容保留在可读文件中，便于复核与交接。" },
  { title: "语义可验证", description: "生成项目沿用确定的运行语义验证，减少“能生成、不能运行”的落差。" },
  { title: "模板可复用", description: "优先基于既有工程模板与平台调用方式生成，避免脱离团队真实环境。" },
  { title: "默认不执行", description: "默认不连接数据库，默认不执行 SQL；所有运行与发布动作都留在你的控制之内。" },
] as const;
