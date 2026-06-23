def build_enhanced_demo_summary():
    return {
        "type": "enhanced_runtime_demo",
        "title": "YCore enhanced Skill Runtime",
        "capabilities": [
            {
                "name": "ProviderHub",
                "description": "统一读取模型配置，并隐藏不同模型服务的调用差异。",
            },
            {
                "name": "Memory/RAG",
                "description": "把最近聊天、阶段摘要、长期画像和检索结果注入上下文。",
            },
            {
                "name": "IntentRouter",
                "description": "融合规则、语义和 LLM 三路结果选择合适 Skill。",
            },
            {
                "name": "PermissionGate",
                "description": "危险工具调用和敏感写入先返回 needs_approval。",
            },
            {
                "name": "EpisodePackage",
                "description": "把输入、上下文、trace、最终输出、检索来源和验证结果归档。",
            },
            {
                "name": "MCPToolAdapter",
                "description": "预留 MCP 工具接入层，并复用 ToolRegistry 和 ToolGateway。",
            },
            {
                "name": "MultiAgentOrchestrator",
                "description": "由 ManagerAgent 决定任务交给哪个 Agent 处理。",
            },
        ],
        "verification_commands": [
            ".\\.venv\\Scripts\\python.exe -m unittest discover",
        ],
    }
