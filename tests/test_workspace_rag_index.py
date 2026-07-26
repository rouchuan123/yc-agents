import json
from pathlib import Path

import pytest

from yc_agents.agents.skill_runtime_agent import SkillRuntimeAgent
from yc_agents.harness.runtime import YCAgentRuntime
from yc_agents.rag import keyword_index as keyword_index_module
from yc_agents.rag import knowledge_index as knowledge_index_module
from yc_agents.rag.knowledge_index import RAGKnowledgeIndex
from yc_agents.rag.keyword_index import KeywordIndex
from yc_agents.tools.rag_search import RAGSearchTool
from yc_agents.tools.registry import ToolRegistry


class SequencedLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.messages = []

    def think(self, messages):
        self.messages.append(messages)
        return self.responses.pop(0)


def build_index(root, knowledge_dir, scope="workspace"):
    keyword_index = KeywordIndex()
    report = RAGKnowledgeIndex(
        root,
        knowledge_dir,
        scope=scope,
        chunk_size=200,
        chunk_overlap=20,
        keyword_index=keyword_index,
    ).build()
    return keyword_index, report


def test_rag_knowledge_index_loads_chunks_and_searches_chinese(tmp_path):
    knowledge_dir = tmp_path / ".ycore" / "memory" / "RAG_knowledge"
    knowledge_dir.mkdir(parents=True)
    (knowledge_dir / "tools.md").write_text(
        "# 工具系统\n\nToolGateway 负责工具权限、参数校验和调用追踪。",
        encoding="utf-8",
    )
    (knowledge_dir / "memory.md").write_text(
        "# 记忆系统\n\nMemory 保存跨会话项目知识。",
        encoding="utf-8",
    )

    keyword_index, report = build_index(
        tmp_path,
        ".ycore/memory/RAG_knowledge",
    )
    results = keyword_index.search("谁负责工具权限", top_k=1)

    assert report["documents"] == 2
    assert report["chunks"] == 2
    assert report["errors"] == []
    assert results[0]["source"] == (
        "workspace:.ycore/memory/RAG_knowledge/tools.md"
    )
    assert results[0]["metadata"]["scope"] == "workspace"
    assert "ToolGateway" in results[0]["text"]


def test_rag_knowledge_index_rejects_directory_outside_root(tmp_path):
    with pytest.raises(ValueError, match="stay inside its root"):
        RAGKnowledgeIndex(
            tmp_path,
            "../private",
            scope="workspace",
        ).build()


def test_global_and_workspace_knowledge_share_index_with_distinct_scopes(tmp_path):
    global_root = tmp_path / "global"
    workspace_root = tmp_path / "workspace"
    global_dir = global_root / "data" / "RAG_knowledge"
    workspace_dir = workspace_root / ".ycore" / "memory" / "RAG_knowledge"
    global_dir.mkdir(parents=True)
    workspace_dir.mkdir(parents=True)
    (global_dir / "common.md").write_text(
        "全局通用标识 GLOBAL-RAG-ONLY-1001",
        encoding="utf-8",
    )
    (workspace_dir / "private.md").write_text(
        "工作区私有标识 WORKSPACE-RAG-ONLY-2002",
        encoding="utf-8",
    )
    keyword_index = KeywordIndex()

    global_report = RAGKnowledgeIndex(
        global_root,
        "data/RAG_knowledge",
        scope="global",
        keyword_index=keyword_index,
    ).build()
    workspace_report = RAGKnowledgeIndex(
        workspace_root,
        ".ycore/memory/RAG_knowledge",
        scope="workspace",
        keyword_index=keyword_index,
    ).build()

    global_result = keyword_index.search("GLOBAL-RAG-ONLY-1001", top_k=1)[0]
    workspace_result = keyword_index.search("WORKSPACE-RAG-ONLY-2002", top_k=1)[0]

    assert global_report["documents"] == 1
    assert workspace_report["documents"] == 1
    assert global_result["source"] == "global:data/RAG_knowledge/common.md"
    assert workspace_result["source"] == (
        "workspace:.ycore/memory/RAG_knowledge/private.md"
    )


def test_keyword_index_does_not_retokenize_corpus_on_search(monkeypatch):
    index = KeywordIndex()
    index.add_chunks(
        "a.md",
        ["ToolGateway 负责工具权限", "Memory 保存跨会话项目知识"],
    )

    calls = []
    original_tokens = keyword_index_module.keyword_tokens

    def counting_tokens(text):
        calls.append(text)
        return original_tokens(text)

    monkeypatch.setattr(keyword_index_module, "keyword_tokens", counting_tokens)

    results = index.search("工具权限", top_k=1)

    assert results[0]["source"] == "a.md"
    # 入库时已分词：search 只需要给查询本身分词一次。
    assert calls == ["工具权限"]


def test_keyword_index_reuses_bm25_until_corpus_changes(monkeypatch):
    index = KeywordIndex()
    index.add_chunks("a.md", ["ToolGateway 负责工具权限"])

    built = []
    original_bm25 = keyword_index_module.BM25Okapi

    def counting_bm25(corpus):
        built.append(list(corpus))
        return original_bm25(corpus)

    monkeypatch.setattr(keyword_index_module, "BM25Okapi", counting_bm25)

    assert index.search("工具权限", top_k=1)
    assert index.search("ToolGateway", top_k=1)
    assert len(built) == 1  # 语料指纹未变，不重建 BM25 对象

    index.add_chunks("b.md", ["Memory 保存跨会话项目知识"])

    assert index.search("Memory", top_k=1)
    assert len(built) == 2  # 语料变化后按新指纹重建


def test_keyword_index_clear_resets_corpus_and_search(tmp_path):
    index = KeywordIndex()
    index.add_chunks("a.md", ["ToolGateway 负责工具权限"])

    index.clear()

    assert index.items == []
    assert index.search("工具权限", top_k=1) == []


def test_rag_knowledge_index_reuses_cached_chunks_without_rereading(
    tmp_path, monkeypatch
):
    knowledge_dir = tmp_path / ".ycore" / "memory" / "RAG_knowledge"
    knowledge_dir.mkdir(parents=True)
    (knowledge_dir / "tools.md").write_text(
        "# 工具系统\n\nToolGateway 负责工具权限、参数校验和调用追踪。",
        encoding="utf-8",
    )

    _first_index, first_report = build_index(
        tmp_path,
        ".ycore/memory/RAG_knowledge",
    )
    cache_path = tmp_path / ".ycore" / "cache" / "rag-index.json"
    assert cache_path.exists()

    loads = []
    original_load = knowledge_index_module.load_markdown

    def counting_load(path):
        loads.append(Path(path))
        return original_load(path)

    monkeypatch.setattr(knowledge_index_module, "load_markdown", counting_load)

    second_index, second_report = build_index(
        tmp_path,
        ".ycore/memory/RAG_knowledge",
    )
    results = second_index.search("谁负责工具权限", top_k=1)

    assert loads == []  # 缓存命中：跳过读取与分块
    assert second_report["documents"] == first_report["documents"]
    assert second_report["chunks"] == first_report["chunks"]
    assert results[0]["source"] == (
        "workspace:.ycore/memory/RAG_knowledge/tools.md"
    )
    assert results[0]["metadata"]["scope"] == "workspace"


def test_rag_knowledge_index_invalidates_cache_when_file_changes(
    tmp_path, monkeypatch
):
    knowledge_dir = tmp_path / ".ycore" / "memory" / "RAG_knowledge"
    knowledge_dir.mkdir(parents=True)
    source_file = knowledge_dir / "tools.md"
    source_file.write_text("# 工具\n\n旧版内容 OLD-MARKER。", encoding="utf-8")

    build_index(tmp_path, ".ycore/memory/RAG_knowledge")
    source_file.write_text(
        "# 工具\n\n新版内容 NEW-MARKER，篇幅与旧版不同。",
        encoding="utf-8",
    )

    loads = []
    original_load = knowledge_index_module.load_markdown

    def counting_load(path):
        loads.append(Path(path))
        return original_load(path)

    monkeypatch.setattr(knowledge_index_module, "load_markdown", counting_load)

    updated_index, _report = build_index(tmp_path, ".ycore/memory/RAG_knowledge")
    results = updated_index.search("NEW-MARKER", top_k=1)

    assert loads == [source_file.resolve()]
    assert "NEW-MARKER" in results[0]["text"]


def test_rag_knowledge_index_ignores_corrupted_cache(tmp_path):
    knowledge_dir = tmp_path / ".ycore" / "memory" / "RAG_knowledge"
    knowledge_dir.mkdir(parents=True)
    (knowledge_dir / "tools.md").write_text(
        "# 工具\n\nToolGateway 负责工具权限。",
        encoding="utf-8",
    )
    cache_path = tmp_path / ".ycore" / "cache" / "rag-index.json"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text("not-a-json{", encoding="utf-8")

    keyword_index, report = build_index(tmp_path, ".ycore/memory/RAG_knowledge")

    assert report["documents"] == 1
    assert report["errors"] == []
    assert keyword_index.search("工具权限", top_k=1)
    # 损坏缓存被覆盖为可用缓存。
    assert json.loads(cache_path.read_text(encoding="utf-8"))["entries"]


def test_rag_knowledge_index_rechunks_when_chunk_config_changes(
    tmp_path, monkeypatch
):
    knowledge_dir = tmp_path / ".ycore" / "memory" / "RAG_knowledge"
    knowledge_dir.mkdir(parents=True)
    source_file = knowledge_dir / "tools.md"
    source_file.write_text(
        "# 工具\n\nToolGateway 负责工具权限、参数校验和调用追踪。",
        encoding="utf-8",
    )
    RAGKnowledgeIndex(
        tmp_path,
        ".ycore/memory/RAG_knowledge",
        scope="workspace",
        chunk_size=200,
        chunk_overlap=20,
    ).build()

    loads = []
    original_load = knowledge_index_module.load_markdown

    def counting_load(path):
        loads.append(Path(path))
        return original_load(path)

    monkeypatch.setattr(knowledge_index_module, "load_markdown", counting_load)

    RAGKnowledgeIndex(
        tmp_path,
        ".ycore/memory/RAG_knowledge",
        scope="workspace",
        chunk_size=50,
        chunk_overlap=5,
    ).build()

    assert loads == [source_file.resolve()]  # 分块配置变化必须重新分块


def test_rag_knowledge_index_prunes_deleted_files_from_cache(tmp_path):
    knowledge_dir = tmp_path / ".ycore" / "memory" / "RAG_knowledge"
    knowledge_dir.mkdir(parents=True)
    (knowledge_dir / "keep.md").write_text("保留文档 KEEP-1", encoding="utf-8")
    removable = knowledge_dir / "remove.md"
    removable.write_text("待删除文档 REMOVE-2", encoding="utf-8")

    build_index(tmp_path, ".ycore/memory/RAG_knowledge")
    removable.unlink()
    build_index(tmp_path, ".ycore/memory/RAG_knowledge")

    cache_path = tmp_path / ".ycore" / "cache" / "rag-index.json"
    entries = json.loads(cache_path.read_text(encoding="utf-8"))["entries"]
    assert set(entries) == {
        "workspace:.ycore/memory/RAG_knowledge/keep.md"
    }


def test_rag_tool_loop_retrieves_context_before_final_answer(tmp_path):
    knowledge_dir = tmp_path / ".ycore" / "memory" / "RAG_knowledge"
    knowledge_dir.mkdir(parents=True)
    (knowledge_dir / "tools.md").write_text(
        "# ToolGateway\n\nToolGateway 负责工具权限、参数校验和调用追踪。",
        encoding="utf-8",
    )
    keyword_index, _report = build_index(
        tmp_path,
        ".ycore/memory/RAG_knowledge",
    )
    rag_tool = RAGSearchTool(keyword_index, default_top_k=2)
    registry = ToolRegistry()
    registry.register(rag_tool)
    llm = SequencedLLM(
        [
            json.dumps(
                {
                    "type": "skill_selection",
                    "selected_skill": None,
                    "confidence": 0.1,
                    "reason": "knowledge question",
                }
            ),
            json.dumps(
                {
                    "type": "tool_call",
                    "tool_name": "rag_search",
                    "arguments": {"query": "谁负责工具权限", "top_k": 2},
                    "reason": "search workspace knowledge",
                }
            ),
            json.dumps(
                {
                    "type": "final_answer",
                    "content": (
                        "ToolGateway 负责工具权限和参数校验。"
                        "来源：workspace:.ycore/memory/RAG_knowledge/tools.md"
                    ),
                }
            ),
        ]
    )
    agent = SkillRuntimeAgent(
        llm,
        skills_dir=tmp_path / "skills",
        workspace_context={
            "path": str(tmp_path),
            "available_tools": ["rag_search"],
            "tool_catalog": registry.list_tools(),
        },
    )
    runtime = YCAgentRuntime(
        agent,
        expects_json=True,
        tool_registry=registry,
        allowed_tools=["rag_search"],
        output_root=tmp_path / "runs",
    )

    answer = runtime.run("请根据知识库说明谁负责工具权限，并给出来源。")

    assert "ToolGateway" in answer
    assert "workspace:.ycore/memory/RAG_knowledge/tools.md" in answer
    assert len(llm.messages) == 3
    observation_prompt = llm.messages[2][-1]["content"]
    assert "ToolGateway 负责工具权限" in observation_prompt
    assert "workspace:.ycore/memory/RAG_knowledge/tools.md" in observation_prompt
