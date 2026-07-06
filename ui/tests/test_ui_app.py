import sys
from unittest.mock import patch, MagicMock

import pytest

# Adjust this import to match your actual module path
from flow_forge_ai_ui.app import main


class TestMain:
    """Tests for the CLI entrypoint that launches the FlowForge AI UI."""

    def test_main_uses_default_host_and_port(self, monkeypatch):
        """No CLI args -> uvicorn.run should get the documented defaults."""
        monkeypatch.setattr(sys, "argv", ["prog"])

        with patch("flow_forge_ai_ui.app.uvicorn.run") as mock_run:
            main()

        mock_run.assert_called_once_with(
            "flow_forge_ai_ui.app:app",
            host="127.0.0.1",
            port=8080,
            reload=False,
        )

    def test_main_uses_custom_host_and_port_long_flags(self, monkeypatch):
        monkeypatch.setattr(
            sys, "argv", ["prog", "--host", "0.0.0.0", "--port", "9000"]
        )

        with patch("flow_forge_ai_ui.app.uvicorn.run") as mock_run:
            main()

        mock_run.assert_called_once_with(
            "flow_forge_ai_ui.app:app",
            host="0.0.0.0",
            port=9000,
            reload=False,
        )

    def test_main_uses_custom_host_and_port_short_flags(self, monkeypatch):
        monkeypatch.setattr(
            sys, "argv", ["prog", "-H", "192.168.1.10", "-p", "3000"]
        )

        with patch("flow_forge_ai_ui.app.uvicorn.run") as mock_run:
            main()

        mock_run.assert_called_once_with(
            "flow_forge_ai_ui.app:app",
            host="192.168.1.10",
            port=3000,
            reload=False,
        )

    def test_main_rejects_non_integer_port(self, monkeypatch, capsys):
        """argparse should error out (SystemExit) on a bad --port value."""
        monkeypatch.setattr(sys, "argv", ["prog", "--port", "not-a-number"])

        with patch("flow_forge_ai_ui.app.uvicorn.run") as mock_run:
            with pytest.raises(SystemExit):
                main()

        mock_run.assert_not_called()

    def test_main_reload_always_false(self, monkeypatch):
        """reload should never be toggled on regardless of args passed."""
        monkeypatch.setattr(sys, "argv", ["prog"])

        with patch("flow_forge_ai_ui.app.uvicorn.run") as mock_run:
            main()

        _, kwargs = mock_run.call_args
        assert kwargs["reload"] is False

    def test_lifespan_raises_runtime_error_on_config_failure(self):
        """If get_runtime_config() raises, lifespan should raise RuntimeError."""
        with patch("flow_forge_ai_ui.app.get_config_handler") as mock_get_config:
            mock_get_config.return_value.get_runtime_config.side_effect = Exception(
                "config failure"
            )

            from flow_forge_ai_ui.app import lifespan

            with pytest.raises(RuntimeError) as exc_info:
                # Call the async context manager directly
                import asyncio

                async def test_lifespan():
                    async with lifespan(None):
                        pass

                asyncio.run(test_lifespan())

            assert "Failed to load runtime configuration" in str(exc_info.value)
