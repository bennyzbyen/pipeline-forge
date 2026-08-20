import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PipelineForge — 把数据工程锻造成确定性",
  description:
    "PipelineForge 是面向数据工程师的 Codex personal 插件，覆盖需求文档转换、日志诊断、数据同步与报表代码生成、Pipeline Export 工作簿，以及多数据库 DDL。",
  icons: {
    icon: "/pipeline-forge-icon.png",
    shortcut: "/pipeline-forge-icon.png",
    apple: "/pipeline-forge-icon.png",
  },
  openGraph: {
    title: "PipelineForge — 把数据工程锻造成确定性",
    description: "从需求文档与任务日志，到可运行项目、可导入工作簿与可审计 DDL。",
    type: "website",
    locale: "zh_CN",
  },
  twitter: {
    card: "summary",
    title: "PipelineForge — 把数据工程锻造成确定性",
    description: "从需求文档与任务日志，到可运行项目、可导入工作簿与可审计 DDL。",
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
