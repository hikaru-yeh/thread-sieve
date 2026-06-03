from __future__ import annotations

from pathlib import Path

import note_generator.config as mod


def test_load_config_uses_note_generator_paths(tmp_path, monkeypatch):
    catch = tmp_path / "catch.json"
    output = tmp_path / "notes"
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"CATCH_PATH={catch}\n"
        f"MARKDOWN_OUTPUT_PATH={output}\n"
        "GEMINI_API_KEY=test-key\n",
        encoding="utf-8",
    )
    for key in (
        "THREADS_BOOKMARK_INPUT",
        "THREADS_MARKDOWN_OUTPUT",
        "CATCH_PATH",
        "MARKDOWN_OUTPUT_PATH",
        "GEMINI_API_KEY",
        "THREADSIEVE_CONFIG",
        "CLASSIFY_CONFIG",
    ):
        monkeypatch.delenv(key, raising=False)

    config = mod.load_config(env_file)

    assert config.input_path == catch
    assert config.output_dir == output
    assert config.gemini_api_key == "test-key"


def test_load_config_uses_config_json_paths(tmp_path, monkeypatch):
    catch = tmp_path / "catch.json"
    output = tmp_path / "notes"
    config_file = tmp_path / "config.json"
    config_file.write_text(
        f"""{{
          "paths": {{
            "catch-json": "{catch.as_posix()}",
            "markdown-output-root": "{output.as_posix()}"
          }}
        }}""",
        encoding="utf-8",
    )
    for key in (
        "THREADS_BOOKMARK_INPUT",
        "THREADS_MARKDOWN_OUTPUT",
        "CATCH_PATH",
        "MARKDOWN_OUTPUT_PATH",
        "GEMINI_API_KEY",
        "CLASSIFY_CONFIG",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("THREADSIEVE_CONFIG", str(config_file))

    config = mod.load_config(dotenv_path=None)

    assert config.input_path == catch
    assert config.output_dir == output


def test_load_config_defaults_are_relative(tmp_path, monkeypatch):
    for key in (
        "THREADS_BOOKMARK_INPUT",
        "THREADS_MARKDOWN_OUTPUT",
        "CATCH_PATH",
        "MARKDOWN_OUTPUT_PATH",
        "GEMINI_API_KEY",
        "CLASSIFY_CONFIG",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("THREADSIEVE_CONFIG", str(tmp_path / "missing-config.json"))

    config = mod.load_config(dotenv_path=None)

    assert config.input_path == Path("data/catch.json")
    assert config.output_dir == Path("output")
    assert not config.output_dir.is_absolute()
    assert config.image_ocr_enabled is False
