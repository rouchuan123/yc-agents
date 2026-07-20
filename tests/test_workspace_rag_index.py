import json
from pathlib import Path

import pytest

from yc_agents.agents.skill_runtime_agent import SkillRuntimeAgent
from yc_agents.harness.runtime import YCAgentRuntime
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
    observation_prompt = llm.messages[2][1]["content"]
    assert "ToolGateway 负责工具权限" in observation_prompt
    assert "workspace:.ycore/memory/RAG_knowledge/tools.md" in observation_prompt
