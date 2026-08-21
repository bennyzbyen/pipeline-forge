# Install PipelineForge

## Windows quick setup

1. Extract the downloaded `pipeline-forge.zip` archive.
2. Open PowerShell in the extracted `pipeline-forge` folder.
3. Run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-pipeline-forge.ps1
```

4. Restart the ChatGPT desktop app, open **Plugins > Personal**, and install PipelineForge. In Codex CLI, enter `/plugins` after restarting the session.

The setup script copies the plugin to `%USERPROFILE%\.codex\plugins\pipeline-forge` and adds or refreshes only the `pipeline-forge` entry in `%USERPROFILE%\.agents\plugins\marketplace.json`. Existing entries are preserved.

## Manual setup

The supported manual local-plugin process is documented at <https://developers.openai.com/plugins/build/plugins#install-a-local-plugin-manually>.
