def assistant_step_entry(content):
    text = str(content or "").strip()
    if not text:
        return None
    return {
        "type": "assistant_step",
        "content": text,
    }


def tool_call_entry(tool_name):
    name = str(tool_name or "tool")
    return {
        "type": "tool_call",
        "tool_name": name,
        "summary": f"Calling {name}...",
    }


def tool_result_entry(tool_name, result):
    name = str(tool_name or "tool")
    return {
        "type": "tool_result",
        "tool_name": name,
        "summary": summarize_tool_result(name, result),
    }


def summarize_tool_result(tool_name, result):
    if isinstance(result, dict) and result.get("ok") is False:
        error_type = result.get("error_type", "error")
        error = result.get("error_message") or result.get("error") or ""
        if error:
            return f"失败：{error_type}：{error}"
        return f"失败：{error_type}"

    if tool_name == "workspace_files" and isinstance(result, dict):
        count = result.get("count")
        files = result.get("files") or []
        names = [
            str(item.get("name") or item.get("path"))
            for item in files[:3]
            if isinstance(item, dict)
        ]
        names = [name for name in names if name]
        if names:
            return f"找到 {count} 个可读文件，包括 {'、'.join(names)}。"
        return f"找到 {count} 个可读文件。"

    if tool_name == "file_reader" and isinstance(result, dict):
        path = result.get("path", "")
        file_type = result.get("file_type", "")
        characters = result.get("characters", 0)
        return f"读取 {path}：{file_type} 文件，{characters} 字符。"

    if tool_name == "web_search" and isinstance(result, dict):
        results = result.get("results") or []
        titles = [
            str(item.get("title", "")).strip()
            for item in results[:3]
            if isinstance(item, dict)
        ]
        titles = [title for title in titles if title]
        if titles:
            return f"返回 {len(results)} 条搜索结果，包括 {'、'.join(titles)}。"
        return f"返回 {len(results)} 条搜索结果。"

    if tool_name == "markdown_writer" and isinstance(result, dict):
        path = result.get("path", "")
        bytes_written = result.get("bytes", 0)
        return f"写入 {path}：{bytes_written} 字节。"

    if tool_name == "rag_search":
        if isinstance(result, list):
            return f"返回 {len(result)} 条相关片段。"
        if isinstance(result, dict):
            items = result.get("results") or result.get("chunks") or []
            if isinstance(items, list):
                return f"返回 {len(items)} 条相关片段。"

    return "工具执行完成。"
