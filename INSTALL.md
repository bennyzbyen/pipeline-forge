# Install PipelineForge

## Recommended: repository marketplace

PipelineForge uses the same single-repository layout as [Diagram Design](https://github.com/cathrynlavery/diagram-design/blob/main/.agents/plugins/marketplace.json): `.agents/plugins/marketplace.json` points to `./`, where `.codex-plugin/plugin.json`, assets, and all eight skills live. The local path is relative to the fetched repository root, not your home directory. No separate marketplace repository is needed.

Share [bennyzbyen/pipeline-forge](https://github.com/bennyzbyen/pipeline-forge) with other users. With Git and a Codex CLI that supports `plugin marketplace` installed, run:

```powershell
codex plugin marketplace add bennyzbyen/pipeline-forge
```

This follows the repository default branch. Adding a market registers its catalog; installing the plugin is a separate step. In Codex desktop, open **Plugins**, select the **PipelineForge** marketplace, and install PipelineForge. Restart the app if the source has not appeared, then start a new task after installation.

For a reproducible installation of the published stable release instead:

```powershell
codex plugin marketplace add bennyzbyen/pipeline-forge --ref v2.0.3
```

Restart Codex, open **Plugins**, select the **PipelineForge** marketplace, and install PipelineForge. In Codex CLI, restart the session, enter `/plugins`, choose the PipelineForge source, and install `pipeline-forge`.

## Updates

For a default-branch marketplace:

```powershell
codex plugin marketplace upgrade pipeline-forge
```

Then check PipelineForge in **Plugins** and install the offered update; start a new task to pick up its skills. Refreshing a marketplace alone is not proof that the installed plugin was updated. A market pinned with `--ref` stays on that tag; to follow the default branch, remove and add its registration again:

```powershell
codex plugin marketplace remove pipeline-forge
codex plugin marketplace add bennyzbyen/pipeline-forge
```

## Use a local clone

```powershell
git clone https://github.com/bennyzbyen/pipeline-forge.git
codex plugin marketplace add ./pipeline-forge
```

Install from the PipelineForge marketplace as above. This route reads the clone and does not require the personal ZIP installer. Update the clone with `git pull --ff-only`, refresh the marketplace, and check the plugin update in the app.

## Moving from the Personal installation

`pipeline-forge@personal` and `pipeline-forge@pipeline-forge` are different installed identities. Add the repository market, install its PipelineForge entry, disable the Personal copy in the app, and start a new task to verify the repository version. Keep only one enabled entry to avoid duplicate skills. The old ZIP helper remains available for Personal installations and does not migrate them automatically. Do not modify Codex's installation cache by hand.

## Diagram Design dependency

PipelineForge and Diagram Design are installed and updated separately. PipelineForge does not include or automatically install Diagram Design.

- For a new waterline diagram or visual redesign, separately install and enable **Diagram Design**. The waterline skill checks for it before drawing and explains what is missing.
- Existing documents with valid, reviewed SVG bindings can reuse those diagrams when prose or tables change, without loading Diagram Design.
- Other PipelineForge modules do not require Diagram Design.

Use your available plugin installation surface to locate Diagram Design. If it is unavailable there, provide its official installation source so the assistant can help; PipelineForge does not supply a separate installer for it.

## Windows quick setup

1. Extract the downloaded `pipeline-forge.zip` archive.
2. Open PowerShell in the extracted `pipeline-forge` folder.
3. Run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-pipeline-forge.ps1
```

4. Restart the ChatGPT desktop app, open **Plugins > Personal**, and install PipelineForge. In Codex CLI, enter `/plugins` after restarting the session.

The setup script copies the plugin to `%USERPROFILE%\.codex\plugins\pipeline-forge` and adds or refreshes only the `pipeline-forge` entry in `%USERPROFILE%\.agents\plugins\marketplace.json`. Existing entries are preserved. Installation is transactional and uses an operating-system-backed exclusive lock scoped to that Home directory. A concurrent setup attempt fails without changing plugin or marketplace state; an orphaned lock record from a terminated process is recoverable because ownership is determined by the live file handle, not the record alone.

## Manual setup

The supported manual local-plugin process is documented at <https://developers.openai.com/plugins/build/plugins#install-a-local-plugin-manually>.
