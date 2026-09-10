# Install PipelineForge

## GitHub marketplace setup

Add the public PipelineForge marketplace source:

```powershell
codex plugin marketplace add bennyzbyen/pipeline-forge --ref v2.0.2
```

Restart the ChatGPT desktop app, open **Plugins > Personal**, and install PipelineForge. In Codex CLI, restart the session, enter `/plugins`, choose the PipelineForge source, and install `pipeline-forge`.

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
