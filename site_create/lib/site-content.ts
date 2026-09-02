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

export const PLUGIN_VERSION = "1.4.0";
export const OFFICIAL_PLUGIN_GUIDE_URL = "https://learn.chatgpt.com/docs/plugins";
export const GITHUB_REPOSITORY_URL = "https://github.com/bennyzbyen/pipeline-forge";
export const MARKETPLACE_ADD_COMMAND = "codex plugin marketplace add bennyzbyen/pipeline-forge --ref v1.4.0";
export const PLUGIN_DOWNLOAD_URL = "/downloads/pipeline-forge.zip";
export const PLUGIN_CHECKSUM_URL = "/downloads/pipeline-forge.zip.sha256";

export const capabilities: readonly Capability[] = [
  {
    id: "guided-workflow",
    eyebrow: "BEGINNER GUIDE",
    title: "一条龙开发向导",
    description: "先检查材料和代码边界，再给出代码单元拆分建议；由你确认合并或拆分后，逐单元路由、生成和验证。",
    input: "任意现场材料",
    output: "路线 / 产物 / 状态",
    glyph: "导",
    tone: "violet",
  },
  {
    id: "waterline-documents",
    eyebrow: "PIPELINE DOCUMENTS",
    title: "可交互水线文档生成",
    description: "从 PRD / HLD 提炼同步或报表水线，直接展示完整表格与 Graphviz 流程图；支持会话修改、自动变更摘要和缺失信息确认。",
    input: "DOCX / 内嵌 Excel / Markdown / PDF",
    output: "Markdown / 交互 HTML / PDF",
    glyph: "线",
    tone: "cyan",
  },
  {
    id: "requirements",
    eyebrow: "DOCUMENT INTELLIGENCE",
    title: "需求文档转技术设计",
    description: "解析 Markdown 或 DOCX 编写的 PRD、水线与 COT 需求，识别共享逻辑、参数、状态和写入边界，形成待确认的代码单元计划。",
    input: "Markdown / DOCX / 表格",
    output: "技术设计 / 单元契约",
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
  { index: "02", verb: "确认", title: "确认代码边界", description: "综合共享算法、参数化、状态、写入与部署边界提出拆分建议；确认前不生成完整代码。" },
  { index: "03", verb: "生成", title: "逐单元交付", description: "把已确认单元分别路由到报表、同步或匹配模块，生成独立代码、配置、入口与测试。" },
  { index: "04", verb: "验证", title: "给出明确状态", description: "每个单元独立报告就绪和阻塞状态，不用一个通用脚手架掩盖真实边界。" },
] as const;

export const reliabilityPoints: readonly ReliabilityPoint[] = [
  { title: "产物可审计", description: "关键假设、字段映射与变更内容保留在可读文件中，便于复核与交接。" },
  { title: "契约可确认", description: "项目总契约与单元执行契约记录拆分依据、用户覆盖和失效条件，边界变化时重新确认。" },
  { title: "语义可验证", description: "每个代码单元独立校验运行、状态、写入和失败语义，减少“能生成、不能运行”的落差。" },
  { title: "模板可复用", description: "优先基于既有工程模板与平台调用方式生成，避免脱离团队真实环境。" },
  { title: "默认不执行", description: "默认不连接数据库，默认不执行 SQL；所有运行与发布动作都留在你的控制之内。" },
] as const;
