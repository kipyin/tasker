"""AI / OpenAI-compatible settings editor (Configuration section)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Button, Input, Static

from tasker.paths import CONFIG_FILENAME, config_path
from tasker.services.config_file import (
    ConfigMutationError,
    mutate_config_file,
    update_ai_config,
)


class ConfigurationScreen(Container):
    """Edit AI settings; persist to TOML under the Tasker data directory."""

    DEFAULT_CSS = """
    #configuration-scroll {
        height: 1fr;
        padding: 1 2;
    }
    .config-heading {
        text-style: bold;
        padding: 0 0 1 0;
    }
    .config-help {
        color: $text-muted;
        padding: 0 0 1 0;
    }
    .config-label {
        text-style: bold;
        padding: 1 0 0 0;
    }
    .config-field-hint {
        color: $text-muted;
        padding: 0 0 0 0;
    }
    #cfg-base-url, #cfg-model, #cfg-api-key {
        margin: 0 0 1 0;
    }
    #cfg-save {
        margin: 1 0 0 0;
        width: auto;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="config")

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="configuration-scroll"):
            yield Static("Configuration", classes="config-heading")
            yield Static(
                "OpenAI-compatible API settings used for email classification and "
                "other AI features. Settings (including the API key) are stored in "
                "your Tasker config file under %APPDATA%.",
                classes="config-help",
            )
            yield Static("Config file", classes="config-label")
            yield Static("", id="cfg-path-line", classes="config-field-hint")
            yield Static("Base URL", classes="config-label")
            yield Static(
                "HTTP endpoint for chat completions "
                "(e.g. OpenAI or a compatible proxy).",
                classes="config-field-hint",
            )
            yield Input(placeholder="https://api.openai.com/v1", id="cfg-base-url")
            yield Static("Model", classes="config-label")
            yield Static(
                "Model id passed to the API (e.g. gpt-4o-mini).",
                classes="config-field-hint",
            )
            yield Input(placeholder="gpt-4o-mini", id="cfg-model")
            yield Static("API key", classes="config-label")
            yield Static(
                "Saved in the config file. Leave blank when saving to keep the "
                "current key; enter a new value to replace it.",
                classes="config-field-hint",
            )
            yield Input(placeholder="", password=True, id="cfg-api-key")
            yield Button("Save AI settings", variant="primary", id="cfg-save")

    def on_mount(self) -> None:
        self._refresh_path_line()
        self._load_fields_from_app()

    def _refresh_path_line(self) -> None:
        line = self.query_one("#cfg-path-line", Static)
        path = config_path()
        if path is None:
            line.update(
                f"%APPDATA% is not set — cannot resolve path to {CONFIG_FILENAME}.",
            )
            return
        line.update(f"{path}  ({CONFIG_FILENAME})")

    def _load_fields_from_app(self) -> None:
        from tasker.ui.app import TaskerApp

        app = self.app
        assert isinstance(app, TaskerApp)
        ai = app._config.ai
        self.query_one("#cfg-base-url", Input).value = ai.base_url
        self.query_one("#cfg-model", Input).value = ai.model
        self.query_one("#cfg-api-key", Input).value = ""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "cfg-save":
            return
        self._save_ai_settings()

    def _save_ai_settings(self) -> None:
        from tasker.ui.app import TaskerApp

        app = self.app
        assert isinstance(app, TaskerApp)

        cfg_file = config_path()
        if cfg_file is None:
            app.notify(
                "APPDATA is not set; cannot save configuration.",
                severity="error",
            )
            return

        base_url = self.query_one("#cfg-base-url", Input).value
        model = self.query_one("#cfg-model", Input).value
        api_key_input = self.query_one("#cfg-api-key", Input).value.strip()
        current_key = app._config.ai.api_key.strip()
        api_key = api_key_input if api_key_input else current_key

        try:
            updated = mutate_config_file(
                cfg_file,
                lambda c: update_ai_config(
                    c,
                    base_url=base_url,
                    model=model,
                    api_key=api_key,
                ),
            )
        except ConfigMutationError as exc:
            app.notify(str(exc), severity="error")
            return

        app.apply_config(updated)
        app.notify("AI settings saved.", severity="information")
