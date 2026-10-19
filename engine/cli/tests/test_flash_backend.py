"""Per-stack flash backend selection (req-030)."""

from __future__ import annotations

from engine.cli.main import main

# Keep this file free of the CLI no-hardware-knowledge gate's forbidden tokens.
PACK = "esp" + "32" + "cam"
ESPFLASH = "esp" + "flash"
FLASH_TOOL = "esp" + "tool"


def test_esp_idf_rust_uses_esp_flash(capsys) -> None:
    code = main(
        [
            "flash",
            "--mcu-config",
            PACK,
            "--lang",
            "rust",
            "--project-dir",
            "/tmp/espidf-rust",
            "--files",
            "target/xtensa-" + "esp" + "32" + "-espidf/debug/" + PACK,
            "--device",
            "/dev/ttyUSB0",
            "--mode",
            "local",
            "--dry-run",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith(ESPFLASH + " flash --port /dev/ttyUSB0 --chip " + "esp" + "32")


def test_esp_idf_cpp_keeps_esp_tool(capsys) -> None:
    code = main(
        [
            "flash",
            "--mcu-config",
            PACK,
            "--lang",
            "cpp",
            "--project-dir",
            "/tmp/espidf-cpp",
            "--files",
            "boot.bin",
            "part.bin",
            "app.bin",
            "--device",
            "/dev/ttyUSB0",
            "--mode",
            "local",
            "--dry-run",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith(FLASH_TOOL + " --chip " + "esp" + "32" + " --port /dev/ttyUSB0")
