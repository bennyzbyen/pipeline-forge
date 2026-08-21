import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

const projectRoot = new URL("../", import.meta.url);

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the complete PipelineForge product story", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<html[^>]*lang="zh-CN"/i);
  assert.match(html, /<title>PipelineForge — 把数据工程锻造成确定性<\/title>/i);
  assert.match(html, /把数据工程，锻造成确定性。/);
  assert.match(html, /需求可读/);
  assert.match(html, /诊断可查/);
  assert.match(html, /代码可运行/);
  assert.match(html, /变更可审计/);

  for (const capability of [
    "一条龙开发向导",
    "需求文档转开发说明",
    "数据任务日志诊断",
    "数据同步项目代码生成",
    "报表项目代码生成",
    "Pipeline Export 工作簿生成",
    "多数据库 DDL 生成与转换",
  ]) {
    assert.match(html, new RegExp(capability));
  }

  for (const id of ["capabilities", "workflow", "reliability", "enable"]) {
    assert.match(html, new RegExp(`id="${id}"`));
  }

  assert.doesNotMatch(html, /plugin:\/\//);
  assert.match(html, /GitHub marketplace/);
  assert.match(html, /codex plugin marketplace add bennyzbyen\/pipeline-forge --ref main/);
  assert.match(html, /github\.com\/bennyzbyen\/pipeline-forge/);
  assert.match(html, /重启 ChatGPT 桌面端/);
  assert.match(html, /\/plugins/);
  assert.match(html, /新建一个 Codex 任务/);
  assert.match(html, /https:\/\/learn\.chatgpt\.com\/docs\/plugins/);
  assert.match(html, /og\.png/);
  await access(new URL("../public/og.png", import.meta.url));
  assert.match(html, /1 个向导 \+ 6 个专业模块/);
  assert.match(html, /0\.1\.0\+codex\.20260821151410/);
  assert.match(html, /逐表校验字段、调度形态、rowkey 与运行配置/);
  assert.match(html, /通用项目使用受限执行契约并校验全部输出/);
  assert.match(html, /默认不连接数据库/);
  assert.match(html, /默认不执行 SQL/);
});

test("removes starter-only UI and preserves resilient product content", async () => {
  const [page, layout, css, packageJson] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);

  assert.doesNotMatch(page, /SkeletonPreview|codex-preview/);
  assert.doesNotMatch(layout, /Starter Project|next\/font\/google/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
  assert.match(css, /prefers-reduced-motion:\s*reduce/);
  assert.match(css, /:focus-visible/);
  assert.match(css, /min-height:\s*44px/);
  assert.match(css, /overflow-x:\s*(clip|hidden)/);
  assert.match(page, /aria-live="polite"/);

  await assert.rejects(access(new URL("app/_sites-preview", projectRoot)));
  await assert.rejects(access(new URL("app/chatgpt-auth.ts", projectRoot)));
  await assert.rejects(access(new URL("db", projectRoot)));
  await assert.rejects(access(new URL("examples", projectRoot)));
});
