# PipelineForge Product Site Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and publish a polished Chinese-language PipelineForge product site that explains its five current capabilities and converts visitors toward enabling the personal plugin in Codex.

**Architecture:** A static vinext single-page site will keep all product facts in a typed content module, render semantic sections through small focused React components, and isolate optional pointer/copy interactions in client components. CSS supplies the Liquid Glass visual system, responsive layout, and reduced-motion fallbacks; no login, persistence, external API, database, upload, or online execution is introduced.

**Tech Stack:** Sites/vinext, React, TypeScript, CSS, Vitest or the Sites-provided test runner, Playwright/browser inspection where available.

## Global Constraints

- Formal working directory: the repository-local `site_create/` directory.
- Use the existing `..\assets\logo.png` and `..\assets\icon.png`; do not redraw or alter the brand mark.
- Chinese is the primary language; English is limited to short labels and technical terms.
- Present exactly five current capabilities: requirement-doc conversion, job-log diagnosis, synchronization code generation, report code generation, and multi-database DDL generation/conversion.
- The plugin version displayed by the site is `0.1.0+pf.20260703075507`.
- The primary enable target is `plugin://pipeline-forge@personal`, with a persistent manual fallback telling users to search for `PipelineForge` in Codex.
- Do not add login, persistence, external APIs, server databases, uploads, online task execution, analytics, or user-data collection.
- Meet WCAG AA text contrast, visible keyboard focus, 44×44 px minimum touch targets, semantic headings, and no horizontal overflow at 320 px.
- Respect `prefers-reduced-motion` by removing tilt, float, reveal, and continuous glow animation without hiding content.

---

## File Map

- `package.json`: Sites/vinext scripts and dependencies produced by the Sites scaffold.
- `app/layout.tsx`: Chinese document metadata, viewport, Open Graph, and X card metadata.
- `app/page.tsx`: Semantic page composition and section order.
- `app/globals.css`: Design tokens, Liquid Glass surfaces, responsive layout, focus states, animations, and reduced-motion fallbacks.
- `components/site-header.tsx`: Glass navigation and accessible mobile menu.
- `components/hero-pipeline.tsx`: Optional client-side pointer tilt and decorative pipeline visualization.
- `components/capability-grid.tsx`: Five capability cards from typed data.
- `components/workflow.tsx`: Input-to-output process with progressive visual highlighting.
- `components/enable-cta.tsx`: Custom-protocol enable action, manual fallback, and copy feedback.
- `components/reveal.tsx`: Progressive enhancement for viewport reveals; content remains visible without JavaScript.
- `lib/site-content.ts`: Typed source of truth for version, navigation, capability, workflow, reliability, and enable-copy data.
- `public/pipeline-forge-logo.png`: Copied existing logo.
- `public/pipeline-forge-icon.png`: Copied existing icon.
- `public/og-pipeline-forge.png`: Share card only if text and branding pass visual review.
- `tests/site-content.test.ts`: Exact product-fact and safe-boundary regression tests.
- `tests/site-structure.test.tsx`: Heading, landmarks, anchors, CTA, and fallback-content tests.

### Task 1: Scaffold the Sites app and lock product facts

**Files:**
- Create: `package.json`
- Create: `app/layout.tsx`
- Create: `app/page.tsx`
- Create: `app/globals.css`
- Create: `lib/site-content.ts`
- Create: `tests/site-content.test.ts`
- Create: `public/pipeline-forge-logo.png`
- Create: `public/pipeline-forge-icon.png`

**Interfaces:**
- Consumes: Existing plugin manifest at `..\.codex-plugin\plugin.json` and approved design spec.
- Produces: `PLUGIN_VERSION: string`, `ENABLE_URI: string`, `capabilities: readonly Capability[]`, `workflowSteps: readonly WorkflowStep[]`, and `reliabilityPoints: readonly ReliabilityPoint[]`.

- [ ] **Step 1: Use Sites building to scaffold a minimal vinext project in the formal working directory**

  Keep the generated package manager and script names. Confirm `package.json` exposes a production build script before editing page code.

- [ ] **Step 2: Copy the approved brand assets without modifying pixels**

  Run:

  ```powershell
  Copy-Item -LiteralPath '..\assets\logo.png' -Destination '.\public\pipeline-forge-logo.png'
  Copy-Item -LiteralPath '..\assets\icon.png' -Destination '.\public\pipeline-forge-icon.png'
  ```

  Expected: both files exist under `public` and their SHA-256 hashes match the sources.

- [ ] **Step 3: Write the failing content regression test**

  ```ts
  import { describe, expect, it } from "vitest";
  import {
    ENABLE_URI,
    PLUGIN_VERSION,
    capabilities,
    reliabilityPoints,
  } from "../lib/site-content";

  describe("PipelineForge product facts", () => {
    it("publishes the exact current plugin identity and capability set", () => {
      expect(PLUGIN_VERSION).toBe("0.1.0+pf.20260703075507");
      expect(ENABLE_URI).toBe("plugin://pipeline-forge@personal");
      expect(capabilities.map((item) => item.title)).toEqual([
        "需求文档转开发说明",
        "数据任务日志诊断",
        "数据同步项目代码生成",
        "报表项目代码生成",
        "多数据库 DDL 生成与转换",
      ]);
      expect(reliabilityPoints.some((item) => item.title === "默认不执行")).toBe(true);
    });
  });
  ```

- [ ] **Step 4: Run the test and verify it fails because the content module does not exist**

  Run the scaffold's test command targeting `tests/site-content.test.ts`.

  Expected: FAIL with module resolution error for `lib/site-content`.

- [ ] **Step 5: Implement the typed content source**

  Define these exact public types and exports:

  ```ts
  export type Capability = Readonly<{
    id: string;
    eyebrow: string;
    title: string;
    description: string;
    input: string;
    output: string;
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

  export const PLUGIN_VERSION = "0.1.0+pf.20260703075507";
  export const ENABLE_URI = "plugin://pipeline-forge@personal";
  ```

  Populate the arrays with concrete Chinese copy derived only from the approved spec and plugin manifest. Include the titles asserted by the test and describe the no-database/no-SQL boundary under `默认不执行`.

- [ ] **Step 6: Add minimal layout and page placeholders, then run the content test**

  `app/layout.tsx` must set `lang="zh-CN"`, title `PipelineForge — 把数据工程锻造成确定性`, and a factual description. `app/page.tsx` may initially render only `<main><h1>把数据工程，锻造成确定性。</h1></main>`.

  Expected: content test PASS; production build PASS.

- [ ] **Step 7: Commit the scaffold and product facts**

  ```powershell
  git add package.json app lib public tests
  git commit -m "Build PipelineForge site foundation"
  ```

### Task 2: Build semantic product-release page sections

**Files:**
- Create: `components/site-header.tsx`
- Create: `components/capability-grid.tsx`
- Create: `components/workflow.tsx`
- Create: `components/enable-cta.tsx`
- Modify: `app/page.tsx`
- Create: `tests/site-structure.test.tsx`

**Interfaces:**
- Consumes: typed arrays and constants from `lib/site-content.ts`.
- Produces: `SiteHeader(): JSX.Element`, `CapabilityGrid(): JSX.Element`, `Workflow(): JSX.Element`, `EnableCta({ compact?: boolean }): JSX.Element`, and a page with anchors `capabilities`, `workflow`, `reliability`, and `enable`.

- [ ] **Step 1: Write failing structure tests**

  ```tsx
  import { render, screen } from "@testing-library/react";
  import Page from "../app/page";

  it("renders the complete product story and installation fallback", () => {
    render(<Page />);
    expect(screen.getByRole("heading", { level: 1, name: "把数据工程，锻造成确定性。" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(5);
    expect(screen.getByText(/在 Codex 中搜索 PipelineForge/)).toBeInTheDocument();
    expect(document.querySelector("#capabilities")).not.toBeNull();
    expect(document.querySelector("#workflow")).not.toBeNull();
    expect(document.querySelector("#reliability")).not.toBeNull();
    expect(document.querySelector("#enable")).not.toBeNull();
  });
  ```

- [ ] **Step 2: Run the structure test and verify the missing sections fail**

  Expected: FAIL because the placeholder page has neither five capability headings nor required anchors.

- [ ] **Step 3: Implement the header and full semantic section order**

  Build this order in `app/page.tsx`: `SiteHeader`, hero, value strip, `CapabilityGrid`, `Workflow`, reliability, final `EnableCta`, footer. Use `header`, `nav`, `main`, `section`, and `footer`; keep only one `h1`, give each major section an `h2`, and each capability an `h3`.

- [ ] **Step 4: Implement the five capability cards from data**

  `CapabilityGrid` maps `capabilities` once and exposes input/output facts as visible text, not tooltips. Use stable `item.id` keys and no hardcoded sixth card.

- [ ] **Step 5: Implement workflow, reliability, and CTA copy**

  Render the workflow as `输入 → 理解 → 生成 → 验证`. The CTA anchor uses `href={ENABLE_URI}` and visible text `在 Codex 中启用`. Keep this fallback visible beside it: `若未自动打开 Codex，请在插件目录中搜索 PipelineForge 并启用。`

- [ ] **Step 6: Run structure tests and production build**

  Expected: all tests PASS; build PASS; no React key or nesting warnings.

- [ ] **Step 7: Commit the semantic product story**

  ```powershell
  git add app components tests
  git commit -m "Add PipelineForge product story"
  ```

### Task 3: Apply the Liquid Glass visual system and responsive behavior

**Files:**
- Modify: `app/globals.css`
- Create: `components/hero-pipeline.tsx`
- Modify: `app/page.tsx`

**Interfaces:**
- Consumes: semantic sections and the site logo.
- Produces: `HeroPipeline(): JSX.Element`, reusable CSS classes `.glass-panel`, `.section-shell`, `.eyebrow`, `.primary-button`, and responsive behavior at desktop/tablet/mobile widths.

- [ ] **Step 1: Establish visual tokens and base accessibility styles**

  Define exact tokens for cold-white background, graphite text, system blue, muted violet, border alpha, shadow, radii, and maximum content width. Set `box-sizing: border-box`, smooth anchor offsets, visible `:focus-visible`, and typography using `-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`.

- [ ] **Step 2: Style the floating glass navigation and hero layout**

  Use a translucent white surface with `backdrop-filter` plus a solid-color fallback. Desktop hero is a two-column grid with generous whitespace; at the mobile breakpoint it becomes a single column with text first and pipeline card second.

- [ ] **Step 3: Implement the decorative pipeline card**

  Render four nodes labeled `输入`, `理解`, `生成`, `验证`, plus compact code/schema artifacts. Mark purely decorative glows `aria-hidden="true"`; keep readable labels in normal text. Do not use generated illustrations or hand-authored SVG.

- [ ] **Step 4: Style capability, workflow, reliability, CTA, and footer sections**

  Use restrained depth and one orange status accent derived from the existing mark. Preserve readable contrast on all translucent surfaces; use spacing and type hierarchy rather than excessive borders.

- [ ] **Step 5: Add responsive and reduced-motion rules**

  At 320 px, enforce single-column cards, wrapped CTA controls, and `overflow-x: clip`. In `@media (prefers-reduced-motion: reduce)`, set animation and transition durations to near-zero and disable transforms while leaving opacity at `1`.

- [ ] **Step 6: Verify with the production build and browser screenshots**

  Inspect at 1440×900, 768×1024, 390×844, and 320×720. Expected: no horizontal scrollbar, no clipped text, CTA visible in the latter half of the mobile hero, and 44×44 px controls.

- [ ] **Step 7: Commit the visual system**

  ```powershell
  git add app components
  git commit -m "Style PipelineForge liquid glass launch page"
  ```

### Task 4: Add progressive interactions and resilient fallbacks

**Files:**
- Modify: `components/site-header.tsx`
- Modify: `components/hero-pipeline.tsx`
- Modify: `components/enable-cta.tsx`
- Create: `components/reveal.tsx`
- Modify: `app/page.tsx`
- Modify: `app/globals.css`
- Modify: `tests/site-structure.test.tsx`

**Interfaces:**
- Consumes: static semantic page and `ENABLE_URI`.
- Produces: keyboard-operable mobile navigation, optional pointer tilt CSS variables `--tilt-x`, `--tilt-y`, copy feedback with an `aria-live="polite"` region, and `Reveal({ children, className? })` progressive enhancement.

- [ ] **Step 1: Add failing tests for menu and fallback controls**

  Test that the mobile menu button has an accessible name and `aria-expanded`; test that the enable link keeps the custom URI; test that manual instructions are visible before any interaction.

- [ ] **Step 2: Run targeted interaction tests and verify failure**

  Expected: FAIL because the menu state and accessible copy feedback are not implemented.

- [ ] **Step 3: Implement accessible mobile navigation**

  Toggle a boolean with a real `<button>`, update `aria-expanded`, close after an anchor selection, and keep desktop links usable without JavaScript through ordinary anchor elements.

- [ ] **Step 4: Implement pointer tilt as optional visual enhancement**

  On fine pointers only, derive clamped values from the card bounds and set CSS variables. Reset on pointer leave. Do not store user data and do not make content depend on pointer movement.

- [ ] **Step 5: Implement manual-instruction copy feedback**

  Copy only `PipelineForge` when `navigator.clipboard` exists. Show `已复制 PipelineForge` in an `aria-live` region on success and `请手动复制 PipelineForge` on failure; the visible fallback sentence remains unchanged.

- [ ] **Step 6: Implement viewport reveals with no-JavaScript safety**

  Content is visible in base CSS. A client-side enhancement adds a class only after mounting and observes elements; unsupported `IntersectionObserver` immediately marks all content visible. Reduced-motion styles bypass transforms and transitions.

- [ ] **Step 7: Run tests, production build, keyboard checks, and JavaScript-disabled inspection**

  Expected: tests PASS; build PASS; Tab/Enter/Space operate navigation and copy controls; with JavaScript disabled, headings, anchors, capabilities, and manual activation instructions remain readable.

- [ ] **Step 8: Commit interactions and fallbacks**

  ```powershell
  git add app components tests
  git commit -m "Add accessible PipelineForge interactions"
  ```

### Task 5: Final verification, metadata, and Sites publication

**Files:**
- Modify: `app/layout.tsx`
- Create conditionally: `public/og-pipeline-forge.png`
- Modify if generated by Sites: `.openai/hosting.json`

**Interfaces:**
- Consumes: completed static site and approved brand assets.
- Produces: successful production build, verified private Sites deployment, and a shareable URL.

- [ ] **Step 1: Add factual metadata**

  Set canonical title/description and icon metadata using `pipeline-forge-icon.png`. Include Open Graph/X image metadata only if the final share image is visually inspected and its text is exact; otherwise omit image metadata.

- [ ] **Step 2: Run all automated verification**

  Run the package's test command, typecheck/lint command if supplied by the scaffold, and production build.

  Expected: every command exits `0`; production output contains no missing asset or hydration errors.

- [ ] **Step 3: Perform final browser QA**

  Check all four target viewports, every navigation anchor, primary and secondary CTA, mobile menu, copy feedback, keyboard focus, reduced-motion, and JavaScript-disabled content. Confirm exactly five capabilities and version `0.1.0+pf.20260703075507` appear.

- [ ] **Step 4: Confirm scope and security boundaries**

  Search the built source for fetch calls, analytics, login, upload, database, and online-execution code. Expected: none. Confirm the reliability section says the plugin does not connect to databases or execute SQL by default.

- [ ] **Step 5: Commit final metadata and verification fixes**

  ```powershell
  git add app public .openai
  git commit -m "Prepare PipelineForge site for release"
  ```

- [ ] **Step 6: Publish only after the production build succeeds**

  Invoke Sites hosting from the repository-local `site_create/` directory, choose private publication unless the user explicitly changes visibility, and retain the returned deployment URL.

- [ ] **Step 7: Verify the hosted page**

  Open the returned URL and confirm the title, logo, first-screen CTA, all five capability cards, and final activation fallback render from the hosted artifact.

- [ ] **Step 8: Deliver the result**

  Report the production build result, tested viewport/accessibility coverage, publication visibility, and exact hosted URL.

## Plan Self-Review

- Spec coverage: all ten design-spec sections map to Tasks 1–5, including exact capability scope, interactions, reduced motion, no-JavaScript fallback, safety boundaries, metadata gating, responsive QA, build, and private publication.
- Placeholder scan: no deferred requirements, unspecified error handling, or incomplete test directions remain.
- Type consistency: `Capability`, `WorkflowStep`, `ReliabilityPoint`, `PLUGIN_VERSION`, and `ENABLE_URI` are defined once in Task 1 and consumed with matching names thereafter.
