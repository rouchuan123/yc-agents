import os
import time

from yc_agents.memory.long_term import LongTermMemory, chunk_markdown, memory_tokens
from yc_agents.tools.memory_search import MemorySearchTool


def test_chinese_tokenizer_and_markdown_chunking():
    assert "项目" in memory_tokens("项目架构 uses FastAPI")
    chunks = chunk_markdown("## Architecture\n\nFirst paragraph.\n\nSecond paragraph.", max_chars=30)
    assert len(chunks) >= 2
    assert all("Architecture" in chunk[2] for chunk in chunks)


def test_searches_global_workspace_and_excludes_current_session(tmp_path):
    workspace = tmp_path / "project"
    global_dir = tmp_path / "global"
    memory = LongTermMemory(workspace, global_dir=global_dir, min_score=0.1)
    global_dir.mkdir(parents=True)
    memory.memory_dir.mkdir(parents=True, exist_ok=True)
    memory.global_memory_path.write_text("## Preference\n用户偏好中文回答。", encoding="utf-8")
    memory.workspace_memory_path.write_text("## Architecture\n项目架构采用事件驱动。", encoding="utf-8")
    memory.write_session_log("current", [{"role": "user", "content": "当前会话秘密"}])
    memory.write_session_log("old", [{"role": "user", "content": "之前决定使用事件队列"}])

    results = memory.search("项目架构事件队列", top_k=6, exclude_session_id="current")

    assert results
    assert any(item["scope"] == "workspace" for item in results)
    assert all("current.md" not in item["source"] for item in results)


def test_sync_removes_deleted_memory_file(tmp_path):
    memory = LongTermMemory(tmp_path / "project", global_dir=tmp_path / "global", min_score=0.0)
    memory.workspace_memory_path.write_text("## Decision\nUse SQLite for durable memory.", encoding="utf-8")
    assert memory.search("SQLite")

    memory.workspace_memory_path.unlink()

    assert memory.search("SQLite") == []


def test_session_decay_and_memory_search_tool(tmp_path):
    memory = LongTermMemory(
        tmp_path / "project",
        global_dir=tmp_path / "global",
        min_score=0.0,
        session_half_life_days=1,
    )
    old_path = memory.write_session_log(
        "old", [{"role": "user", "content": "release checklist alpha"}]
    )
    old = time.time() - 3 * 86400
    os.utime(old_path, (old, old))
    memory.workspace_memory_path.write_text(
        "## Checklist\nrelease checklist alpha", encoding="utf-8"
    )
    tool = MemorySearchTool(memory, session_id="current")

    payload = tool.run("release checklist alpha")

    assert payload["result_count"] >= 1
    assert payload["results"][0]["scope"] == "workspace"
