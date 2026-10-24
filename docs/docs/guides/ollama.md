# Ollama in Sibyl

Choose **Settings → AI models → Local → Ollama**. Sibyl checks the endpoint shown in the form and lists installed models and models currently loaded in memory. Choose an installed model, then **Save as workspace default**. Presets and custom IDs remain available; a preset is not proof that a model has been downloaded.

**Check status** probes the native version, model catalog and loaded-model endpoints without running inference. A reachable server with an installed model may still have insufficient resources or unsuitable tool-calling behavior; these checks do not evaluate model answers.

If Ollama is installed locally but stopped, **Start Ollama** launches its installed CLI using `ollama serve`. Only a plain loopback HTTP endpoint on the machine hosting Sibyl's Python backend can be started. The browser cannot supply commands, executable paths or extra process arguments. Startup may take a moment; the panel checks a starting process automatically. **Stop local server** appears only for a process started by this Sibyl instance. Existing desktop/system Ollama processes are reused and must be stopped in Ollama itself. Sibyl stops its own child when the backend shuts down.

## Installation and models

Install Ollama on the **Python backend machine**, which may differ from your browser's computer. Use the official [download page](https://ollama.com/download) and [quickstart](https://docs.ollama.com/quickstart). Open Ollama after installing, then check status again. Remote servers can be checked, but cannot be started from Sibyl.

Model installation is separate. The panel displays a command such as `ollama pull qwen3:8b` for the selected model; run it yourself in a terminal on the Ollama machine. Sibyl does not install software, download models or silently change the selected AI profile when starting a server. See the [Ollama CLI](https://docs.ollama.com/cli).

Implementation lives in `src/sibyl/local_models/ollama.py`. `POST /api/v1/settings/ollama/check`, `/start` and `/stop` accept only `base_url` and `model`, under the normal workspace access controls. Saved credentials are used only at their saved endpoint. Native contracts: [version](https://github.com/ollama/ollama/blob/main/docs/api.md#version), [model catalog](https://docs.ollama.com/api/tags), [loaded models](https://docs.ollama.com/api/ps). Tests use fake HTTP and process boundaries; they never start the developer's Ollama installation.

Optional **Agent models** settings let Sibyl and each specialist use a different saved provider/model without changing the workspace default. See [per-agent setup](settings.md#choose-models-per-agent).
