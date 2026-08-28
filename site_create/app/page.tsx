"use client";

import {
  useEffect,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from "react";
import Image from "next/image";
import {
  GITHUB_REPOSITORY_URL,
  MARKETPLACE_ADD_COMMAND,
  OFFICIAL_PLUGIN_GUIDE_URL,
  PLUGIN_CHECKSUM_URL,
  PLUGIN_DOWNLOAD_URL,
  PLUGIN_VERSION,
  capabilities,
  reliabilityPoints,
  workflowSteps,
} from "../lib/site-content";

const navItems = [
  { href: "#capabilities", label: "能力" },
  { href: "#workflow", label: "工作流" },
  { href: "#reliability", label: "可靠性" },
];

function SiteHeader() {
  const [open, setOpen] = useState(false);

  return (
    <header className="site-header">
      <nav className="nav-shell glass-panel" aria-label="主导航">
        <a className="brand" href="#top" aria-label="PipelineForge 首页">
          <Image src="/pipeline-forge-logo.png" alt="" width={40} height={40} />
          <span>PipelineForge</span>
        </a>

        <button
          className="menu-button"
          type="button"
          aria-label={open ? "关闭导航菜单" : "打开导航菜单"}
          aria-expanded={open}
          aria-controls="site-navigation"
          onClick={() => setOpen((value) => !value)}
        >
          <span />
          <span />
        </button>

        <div className={`nav-links ${open ? "is-open" : ""}`} id="site-navigation">
          {navItems.map((item) => (
            <a key={item.href} href={item.href} onClick={() => setOpen(false)}>
              {item.label}
            </a>
          ))}
          <a className="nav-cta" href={PLUGIN_DOWNLOAD_URL} download onClick={() => setOpen(false)}>
            下载插件
          </a>
        </div>
      </nav>
    </header>
  );
}

function HeroPipeline() {
  function moveCard(event: ReactPointerEvent<HTMLDivElement>) {
    if (
      !window.matchMedia("(pointer: fine)").matches ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      return;
    }

    const rect = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width - 0.5;
    const y = (event.clientY - rect.top) / rect.height - 0.5;
    event.currentTarget.style.setProperty("--tilt-x", `${(-y * 5).toFixed(2)}deg`);
    event.currentTarget.style.setProperty("--tilt-y", `${(x * 6).toFixed(2)}deg`);
    event.currentTarget.style.setProperty("--light-x", `${(x + 0.5) * 100}%`);
    event.currentTarget.style.setProperty("--light-y", `${(y + 0.5) * 100}%`);
  }

  function resetCard(event: ReactPointerEvent<HTMLDivElement>) {
    event.currentTarget.style.setProperty("--tilt-x", "0deg");
    event.currentTarget.style.setProperty("--tilt-y", "0deg");
    event.currentTarget.style.setProperty("--light-x", "50%");
    event.currentTarget.style.setProperty("--light-y", "40%");
  }

  return (
    <div
      className="pipeline-stage"
      onPointerMove={moveCard}
      onPointerLeave={resetCard}
      aria-label="PipelineForge 从输入到验证的处理流程"
    >
      <div className="stage-glow stage-glow-blue" aria-hidden="true" />
      <div className="stage-glow stage-glow-violet" aria-hidden="true" />
      <div className="pipeline-window glass-panel">
        <div className="window-bar">
          <div className="window-brand">
            <Image src="/pipeline-forge-icon.png" alt="" width={28} height={28} />
            <span>PipelineForge</span>
          </div>
          <span className="window-status"><i /> Ready</span>
        </div>

        <div className="window-body">
          <div className="input-card">
            <span className="file-chip">MD</span>
            <div>
              <strong>PRD与水线设计.md</strong>
              <span>Markdown · DataHub · COT</span>
            </div>
            <span className="input-check">✓</span>
          </div>

          <div className="pipeline-track" aria-label="输入、理解、生成、验证">
            {workflowSteps.map((step, index) => (
              <div className="track-step" key={step.index} style={{ "--step": index } as CSSProperties}>
                <span>{step.verb}</span>
                {index < workflowSteps.length - 1 && <i aria-hidden="true" />}
              </div>
            ))}
          </div>

          <div className="output-grid">
            <div className="output-card output-code">
              <span className="output-label">SYNC PROJECT</span>
              <div className="code-line code-line-wide" />
              <div className="code-line" />
              <div className="code-line code-line-accent" />
              <span className="output-ready">可运行</span>
            </div>
            <div className="output-card output-ddl">
              <span className="output-label">DDL</span>
              <strong>CREATE TABLE</strong>
              <span>ClickHouse / MySQL</span>
              <span className="output-ready">可审计</span>
            </div>
          </div>
        </div>
      </div>
      <div className="floating-chip chip-top glass-panel" aria-hidden="true">
        <span>✓</span> 语义验证通过
      </div>
      <div className="floating-chip chip-bottom glass-panel" aria-hidden="true">
        <span>7</span> 类工程能力
      </div>
    </div>
  );
}

function EnableActions({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`enable-actions ${compact ? "is-compact" : ""}`}>
      <div className="button-row">
        <a
          className="primary-button"
          href={PLUGIN_DOWNLOAD_URL}
          download
        >
          下载 PipelineForge
          <span aria-hidden="true">↓</span>
        </a>
        {compact ? (
          <a className="secondary-button" href={GITHUB_REPOSITORY_URL} target="_blank" rel="noreferrer">
            查看 GitHub 源码
            <span aria-hidden="true">↗</span>
          </a>
        ) : (
          <a className="secondary-button" href="#capabilities">
            探索能力
            <span aria-hidden="true">↓</span>
          </a>
        )}
      </div>
      {!compact && (
        <div className="manual-fallback">
          <span>完整插件 ZIP · v{PLUGIN_VERSION} · 无需登录即可下载</span>
        </div>
      )}
    </div>
  );
}

export default function Home() {
  useEffect(() => {
    const root = document.documentElement;
    const elements = Array.from(document.querySelectorAll<HTMLElement>(".reveal"));
    root.classList.add("js-ready");

    if (
      window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
      !("IntersectionObserver" in window)
    ) {
      elements.forEach((element) => element.classList.add("is-visible"));
      return () => root.classList.remove("js-ready");
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            (entry.target as HTMLElement).classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12 },
    );
    elements.forEach((element) => observer.observe(element));

    return () => {
      observer.disconnect();
      root.classList.remove("js-ready");
    };
  }, []);

  return (
    <div id="top" className="site-root">
      <div className="ambient ambient-one" aria-hidden="true" />
      <div className="ambient ambient-two" aria-hidden="true" />
      <SiteHeader />

      <main>
        <section className="hero section-shell" aria-labelledby="hero-title">
          <div className="hero-copy reveal">
            <div className="eyebrow"><span /> DATA ENGINEERING TOOLKIT</div>
            <h1 id="hero-title">把数据工程，锻造成确定性。</h1>
            <p className="hero-lead">
              从需求文档与任务日志，到可运行项目、可导入工作簿与可审计 DDL。PipelineForge
              把复杂的数据开发链路，收拢成清晰、可靠的工程产物。
            </p>
            <EnableActions />
            <div className="hero-proof" aria-label="产品特性">
              <span><i /> Personal Plugin</span>
              <span><i /> 1 个向导 + 6 个专业模块</span>
              <span><i /> 默认离线生成</span>
            </div>
          </div>
          <div className="hero-visual reveal">
            <HeroPipeline />
          </div>
        </section>

        <section className="value-strip section-shell reveal" aria-label="核心价值">
          {[
            ["01", "需求可读"],
            ["02", "诊断可查"],
            ["03", "代码可运行"],
            ["04", "变更可审计"],
          ].map(([index, label]) => (
            <div key={index}><span>{index}</span><strong>{label}</strong></div>
          ))}
        </section>

        <section className="capabilities section-shell" id="capabilities" aria-labelledby="capabilities-title">
          <div className="section-heading reveal">
            <div>
              <span className="section-kicker">CORE CAPABILITIES</span>
              <h2 id="capabilities-title">一条龙向导，串起六项专业能力。</h2>
            </div>
            <p>新手从向导开始，熟悉后也可以直接调用任一专业模块。</p>
          </div>

          <div className="capability-grid">
            {capabilities.map((item, index) => (
              <article className={`capability-card glass-panel reveal card-${index + 1}`} key={item.id}>
                <div className="card-topline">
                  <span className="capability-index">0{index + 1}</span>
                  <span className={`capability-icon icon-${item.tone}`}>{item.glyph}</span>
                </div>
                <span className="card-eyebrow">{item.eyebrow}</span>
                <h3>{item.title}</h3>
                <p>{item.description}</p>
                <div className="io-row">
                  <span><small>INPUT</small>{item.input}</span>
                  <i aria-hidden="true">→</i>
                  <span><small>OUTPUT</small>{item.output}</span>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="workflow-section" id="workflow" aria-labelledby="workflow-title">
          <div className="workflow-orb" aria-hidden="true" />
          <div className="section-shell">
            <div className="section-heading centered reveal">
              <span className="section-kicker">ONE CONTINUOUS FLOW</span>
              <h2 id="workflow-title">从模糊输入，到明确下一步。</h2>
              <p>向导持续说明当前阶段、已确认事实、阻塞问题和交付状态。</p>
            </div>

            <div className="workflow-grid reveal">
              {workflowSteps.map((step, index) => (
                <article className="workflow-step" key={step.index} style={{ "--step": index } as CSSProperties}>
                  <div className="workflow-marker">
                    <span>{step.index}</span>
                    {index < workflowSteps.length - 1 && <i aria-hidden="true" />}
                  </div>
                  <span className="workflow-verb">{step.verb}</span>
                  <h3>{step.title}</h3>
                  <p>{step.description}</p>
                </article>
              ))}
            </div>

            <div className="artifact-flow glass-panel reveal">
              <div className="artifact-group">
                <span className="artifact-label">INPUT</span>
                <div><b>MD</b><b>DOCX</b><b>LOG</b><b>XLSX</b><b>SCHEMA</b></div>
              </div>
              <span className="artifact-arrow" aria-hidden="true">→</span>
              <div className="forge-core">
                <Image src="/pipeline-forge-icon.png" alt="" width={52} height={52} />
                <strong>PipelineForge</strong>
                <span>Understand · Generate · Verify</span>
              </div>
              <span className="artifact-arrow" aria-hidden="true">→</span>
              <div className="artifact-group output-group">
                <span className="artifact-label">OUTPUT</span>
                <div><b>MD</b><b>PY</b><b>XLSX</b><b>SQL</b></div>
              </div>
            </div>
          </div>
        </section>

        <section className="reliability section-shell" id="reliability" aria-labelledby="reliability-title">
          <div className="reliability-intro reveal">
            <span className="section-kicker">BUILT FOR TRUST</span>
            <h2 id="reliability-title">让每一次生成，<br />都有边界与依据。</h2>
            <p>
              PipelineForge 以可审计产物、现有模板和确定的验证规则建立信任。
              它生成工程材料，但不会越过你的运行边界。
            </p>
            <div className="safety-badge"><span>✓</span> Safe by default</div>
          </div>

          <div className="reliability-list reveal">
            {reliabilityPoints.map((item, index) => (
              <article key={item.title}>
                <span>0{index + 1}</span>
                <div><h3>{item.title}</h3><p>{item.description}</p></div>
              </article>
            ))}
          </div>
        </section>

        <section className="final-cta section-shell reveal" id="enable" aria-labelledby="enable-title">
          <div className="cta-glow" aria-hidden="true" />
          <div className="cta-content">
            <Image src="/pipeline-forge-logo.png" alt="" width={68} height={68} />
            <span className="section-kicker">READY TO FORGE?</span>
            <h2 id="enable-title">让下一项数据工程任务，<br />从确定性开始。</h2>
            <p>
              推荐直接添加公开的 GitHub Marketplace 源；也可以从本站下载完整插件包。
              两条路线都无需进入 OpenAI 官方目录，源码在 GitHub 公开可查。
            </p>
            <div className="marketplace-package glass-panel" aria-label="通过 GitHub Marketplace 安装 PipelineForge">
              <div className="package-copy">
                <span>RECOMMENDED</span>
                <strong>添加公开 Marketplace 源</strong>
                <small>运行命令后，从 Plugins 或 /plugins 安装</small>
              </div>
              <pre><code>{MARKETPLACE_ADD_COMMAND}</code></pre>
            </div>
            <div className="download-package glass-panel" aria-label="PipelineForge 插件下载">
              <div className="package-copy">
                <span>DIRECT DOWNLOAD</span>
                <strong>pipeline-forge.zip</strong>
                <small>完整插件包 · v{PLUGIN_VERSION} · ZIP</small>
              </div>
              <div className="package-actions">
                <a className="primary-button" href={PLUGIN_DOWNLOAD_URL} download>
                  直接下载 ZIP <span aria-hidden="true">↓</span>
                </a>
                <a className="checksum-link" href={PLUGIN_CHECKSUM_URL} download>
                  SHA-256 校验值
                </a>
              </div>
            </div>
            <div className="install-guide" aria-label="PipelineForge 下载与安装步骤">
              <article className="install-card glass-panel">
                <span className="install-label">DOWNLOAD</span>
                <h3>下载完整插件包</h3>
                <ol>
                  <li>点击上方 <b>直接下载 ZIP</b>。</li>
                  <li>解压后打开其中的 <code>pipeline-forge</code> 文件夹。</li>
                  <li>可先对照本站公布的 SHA-256 校验下载完整性。</li>
                  <li>包内含插件清单、全部技能、脚本、参考资料和图标。</li>
                </ol>
              </article>
              <article className="install-card glass-panel">
                <span className="install-label">INSTALL ON WINDOWS</span>
                <h3>安装到 Codex</h3>
                <ol>
                  <li>在解压目录中运行 <code>install-pipeline-forge.ps1</code>。</li>
                  <li>脚本只写入个人 Codex 插件目录，并保留已有插件条目。</li>
                  <li>重启 ChatGPT 桌面端，打开 <b>Plugins → Personal</b> 安装。</li>
                  <li>Codex CLI 用户重启会话后输入 <code>/plugins</code>。</li>
                </ol>
              </article>
            </div>
            <EnableActions compact />
            <a className="official-guide-link" href={OFFICIAL_PLUGIN_GUIDE_URL} target="_blank" rel="noreferrer">
              查看 OpenAI 官方插件说明 ↗
            </a>
          </div>
        </section>
      </main>

      <footer className="site-footer section-shell">
        <div className="footer-brand">
          <Image src="/pipeline-forge-icon.png" alt="" width={34} height={34} />
          <div><strong>PipelineForge</strong><span>Data engineering, forged with certainty.</span></div>
        </div>
        <div className="footer-meta">
          <span>Personal Plugin</span>
          <span>v{PLUGIN_VERSION}</span>
          <a href="#top">返回顶部 ↑</a>
        </div>
      </footer>
    </div>
  );
}
