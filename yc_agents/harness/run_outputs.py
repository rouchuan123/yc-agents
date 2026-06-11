class RunOutputWriter:
    def __init__(self, context):
        self.context = context

    def write_input(self):
        return self.write_text("input.md", self.context.user_input)

    def write_final_output(self, content):
        return self.write_text("final_output.md", content)

    def write_text(self, file_name, content):
        self.context.outputs_dir.mkdir(parents=True, exist_ok=True)
        path = self.context.outputs_dir / file_name
        path.write_text(content, encoding="utf-8")
        return path