import json


class RunOutputWriter:
    def __init__(self, context):
        self.context = context

    def write_input(self):
        return self.write_text("input.md", self.context.user_input)

    def write_final_output(self, content):
        return self.write_text("final_output.md", content)

    def write_context(self, data):
        return self.write_json("context.json", data)

    def write_retrieved_sources(self, sources):
        lines = ["# Retrieved Sources", ""]

        if not sources:
            lines.append("No retrieved sources.")
        else:
            for index, source in enumerate(sources, start=1):
                lines.extend(
                    [
                        f"## Source {index}",
                        "",
                        f"- source: {source.get('source', '')}",
                        f"- chunk_id: {source.get('chunk_id', '')}",
                        f"- score: {source.get('score', '')}",
                        "",
                        str(source.get("text", "")),
                        "",
                    ]
                )

        return self.write_text("retrieved_sources.md", "\n".join(lines))

    def write_verification(self, result):
        lines = [
            "# Verification",
            "",
            f"passed: {bool(result.get('passed'))}",
            "",
        ]

        for check in result.get("checks", []):
            lines.extend(
                [
                    f"- [{ 'x' if check.get('passed') else ' ' }] {check.get('name', '')}",
                    f"  {check.get('message', '')}",
                ]
            )

        return self.write_text("verification.md", "\n".join(lines))

    def write_text(self, file_name, content):
        self.context.outputs_dir.mkdir(parents=True, exist_ok=True)
        path = self.context.outputs_dir / file_name
        path.write_text(content, encoding="utf-8")
        return path

    def write_json(self, file_name, data):
        self.context.outputs_dir.mkdir(parents=True, exist_ok=True)
        path = self.context.outputs_dir / file_name

        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return path
