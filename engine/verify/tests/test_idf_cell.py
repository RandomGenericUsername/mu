"""ESP-IDF verify-cell tests (task-016, E4; AD-15).

The unit half; the cell's real build runs in the pinned image (see the ticket).
"""

from engine.core.build_cells import build_cell_for
from engine.verify.e2e import _APP_PARTITION_RE, CELLS, build_idf_cell


def test_cells_include_the_esp32_language():
    assert ("esp32cam", "c") in CELLS
    # The 9 STM32 cells are unchanged, in order, and come first.
    assert CELLS[:9] == tuple(
        (pack, lang)
        for pack in ("stm32f411re", "stm32h755", "stm32wl55jc")
        for lang in ("c", "cpp", "rust")
    )
    assert CELLS[9:] == (("esp32cam", "c"), ("esp32cam", "cpp"), ("esp32cam", "rust"))
    assert len(CELLS) == 12  # 9 STM32 + C/C++/Rust ESP32


def test_idf_builder_is_registered_for_the_stack_family():
    assert build_cell_for("idf-cmake") is build_idf_cell


def test_idf_rust_builder_is_registered():
    from engine.verify.e2e import build_idf_rust_cell

    assert build_cell_for("esp-idf-rust") is build_idf_rust_cell


def test_app_partition_size_is_parsed_from_idf_output():
    line = (
        "esp32cam.bin binary size 0x24660 bytes. Smallest app partition is "
        "0x100000 bytes. 0xdb9a0 bytes (86%) free."
    )
    match = _APP_PARTITION_RE.search(line)
    assert match is not None
    assert int(match.group(1), 16) == 0x100000
