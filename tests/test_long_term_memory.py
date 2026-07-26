import os
import sqlite3
import time
from pathlib import Path

import yc_agents.memory.long_term as long_term_module
from yc_agents.memory.long_term import LongTermMemory, chunk_markdown, memory_tokens
from yc_agents.tools.memory_search import MemorySearchTool


class FakeDreamLLM:
    def __init__(self, output):
        self.output = output
        self.prompts = []

    def think(self, messages):
        self.prompts.append(messages)
        return self.output


def _dream_memory(tmp_path, llm):
    return LongTermMemory(
        tmp_path / "project",
        global_dir=tmp_path / "global",
        min_score=0.0,
        dream_config={"enabled": True, "minHours": 0, "minSessions": 1},
        llm=llm,
    )


def _chunk_access_counts(memory):
    connection = sqlite3.connect(memory.db_path)
    try:
        return [row[0] for row in connection.execute("SELECT access_count FROM memory_chunks")]
    finally:
        connection.close()


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


def test_dream_feeds_existing_memory_and_writes_backup(tmp_path):
    llm = FakeDreamLLM("## Memory\n\n" + "整合后的长期记忆条目。" * 10)
    memory = _dream_memory(tmp_path, llm)
    old_content = "## Decisions\n既有决定：使用 SQLite。\n"
    memory.workspace_memory_path.write_text(old_content, encoding="utf-8")
    memory.write_session_log("old", [{"role": "user", "content": "新会话讨论了事件队列。"}])

    assert memory.maybe_dream(current_session_id="current") is True

    prompt_text = "\n".join(str(message["content"]) for message in llm.prompts[0])
    assert "既有决定" in prompt_text
    backup_path = memory.workspace_memory_path.with_name("MEMORY.md.bak")
    assert backup_path.read_text(encoding="utf-8") == old_content
    assert "整合后的长期记忆条目" in memory.workspace_memory_path.read_text(encoding="utf-8")


def test_dream_backup_keeps_most_recent_copy(tmp_path):
    llm = FakeDreamLLM("## Memory\n\n" + "第一次整合的结果。" * 10)
    memory = _dream_memory(tmp_path, llm)
    memory.workspace_memory_path.write_text("## Decisions\n初始记忆。\n", encoding="utf-8")
    memory.write_session_log("old", [{"role": "user", "content": "第一批会话内容。"}])
    assert memory.maybe_dream() is True
    first_output = memory.workspace_memory_path.read_text(encoding="utf-8")

    llm.output = "## Memory\n\n" + "第二次整合的结果。" * 10
    later_log = memory.write_session_log("later", [{"role": "user", "content": "第二批会话内容。"}])
    future = time.time() + 60
    os.utime(later_log, (future, future))
    assert memory.maybe_dream() is True

    backup_path = memory.workspace_memory_path.with_name("MEMORY.md.bak")
    assert backup_path.read_text(encoding="utf-8") == first_output
    assert "第二次整合的结果" in memory.workspace_memory_path.read_text(encoding="utf-8")


def test_dream_refuses_to_overwrite_when_output_shrinks(tmp_path):
    old_content = "## Decisions\n" + "长期记忆里的重要内容不可丢失。\n" * 40
    llm = FakeDreamLLM("太短")
    memory = _dream_memory(tmp_path, llm)
    memory.workspace_memory_path.write_text(old_content, encoding="utf-8")
    memory.write_session_log("old", [{"role": "user", "content": "会话内容"}])

    assert memory.maybe_dream() is False

    assert memory.workspace_memory_path.read_text(encoding="utf-8") == old_content
    assert not memory.workspace_memory_path.with_name("MEMORY.md.bak").exists()


def test_search_record_access_flag_controls_count_writes(tmp_path):
    memory = LongTermMemory(tmp_path / "project", global_dir=tmp_path / "global", min_score=0.0)
    memory.workspace_memory_path.write_text(
        "## Decision\nUse SQLite for durable memory.", encoding="utf-8"
    )

    assert memory.search("SQLite", record_access=False)
    assert memory.search("SQLite", record_access=False)
    assert set(_chunk_access_counts(memory)) == {0}

    assert memory.search("SQLite")
    assert max(_chunk_access_counts(memory)) == 1


def test_sync_stat_fast_path_skips_rehash(tmp_path, monkeypatch):
    memory = LongTermMemory(tmp_path / "project", global_dir=tmp_path / "global", min_score=0.0)
    memory.workspace_memory_path.write_text(
        "## Decision\nUse SQLite for durable memory.", encoding="utf-8"
    )
    memory.sync()

    reads = []
    original_read_text = Path.read_text

    def counting_read_text(self, *args, **kwargs):
        reads.append(str(self))
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)
    memory.sync()
    assert reads == []

    memory.workspace_memory_path.write_text(
        "## Decision\nSwitched to Postgres instead of SQLite.", encoding="utf-8"
    )
    bumped = time.time() + 5
    os.utime(memory.workspace_memory_path, (bumped, bumped))
    memory.sync()
    assert reads
    assert memory.search("Postgres", record_access=False)


def test_bm25_corpus_cache_reused_until_files_change(tmp_path, monkeypatch):
    memory = LongTermMemory(tmp_path / "project", global_dir=tmp_path / "global", min_score=0.0)
    memory.workspace_memory_path.write_text(
        "## Decision\nUse SQLite for durable memory.", encoding="utf-8"
    )

    builds = []
    original_bm25 = long_term_module.BM25Okapi

    def counting_bm25(corpus):
        builds.append(len(corpus))
        return original_bm25(corpus)

    monkeypatch.setattr(long_term_module, "BM25Okapi", counting_bm25)

    assert memory.search("SQLite", record_access=False)
    assert memory.search("SQLite", record_access=False)
    assert len(builds) == 1

    memory.workspace_memory_path.write_text(
        "## Decision\nSwitched to Postgres instead of SQLite.", encoding="utf-8"
    )
    bumped = time.time() + 5
    os.utime(memory.workspace_memory_path, (bumped, bumped))
    assert memory.search("Postgres", record_access=False)
    assert len(builds) == 2
