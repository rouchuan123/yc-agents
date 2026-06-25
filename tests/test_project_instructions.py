from yc_agents.prompts.project_instructions import ProjectInstructionLoader


def test_loader_returns_empty_list_when_files_are_missing(tmp_path):
    loader = ProjectInstructionLoader(tmp_path)

    assert loader.load() == []


def test_loader_reads_root_ycore_md(tmp_path):
    (tmp_path / "YCORE.md").write_text("Root instructions", encoding="utf-8")

    instructions = ProjectInstructionLoader(tmp_path).load()

    assert len(instructions) == 1
    assert instructions[0].source == "YCORE.md"
    assert instructions[0].content == "Root instructions"
    assert instructions[0].path == tmp_path / "YCORE.md"


def test_loader_reads_local_ycore_md(tmp_path):
    local_dir = tmp_path / ".ycore"
    local_dir.mkdir()
    (local_dir / "YCORE.md").write_text("Local instructions", encoding="utf-8")

    instructions = ProjectInstructionLoader(tmp_path).load()

    assert len(instructions) == 1
    assert instructions[0].source == ".ycore/YCORE.md"
    assert instructions[0].content == "Local instructions"
    assert instructions[0].path == local_dir / "YCORE.md"


def test_loader_preserves_root_then_local_order(tmp_path):
    (tmp_path / "YCORE.md").write_text("Root instructions", encoding="utf-8")
    (tmp_path / ".ycore").mkdir()
    (tmp_path / ".ycore" / "YCORE.md").write_text(
        "Local instructions",
        encoding="utf-8",
    )

    instructions = ProjectInstructionLoader(tmp_path).load()

    assert [item.source for item in instructions] == [
        "YCORE.md",
        ".ycore/YCORE.md",
    ]
    assert [item.content for item in instructions] == [
        "Root instructions",
        "Local instructions",
    ]


def test_loader_ignores_empty_instruction_files(tmp_path):
    (tmp_path / "YCORE.md").write_text("   \n", encoding="utf-8")
    (tmp_path / ".ycore").mkdir()
    (tmp_path / ".ycore" / "YCORE.md").write_text(
        "Local instructions",
        encoding="utf-8",
    )

    instructions = ProjectInstructionLoader(tmp_path).load()

    assert [item.source for item in instructions] == [".ycore/YCORE.md"]
