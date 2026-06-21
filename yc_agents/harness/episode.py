class EpisodePackage:
    def __init__(self, context):
        self.context = context

    def build_manifest(self):
        output_dir = self.context.outputs_dir
        files = []

        if output_dir.exists():
            files = sorted(
                str(path.relative_to(output_dir)).replace("\\", "/")
                for path in output_dir.iterdir()
                if path.is_file()
            )

        return {
            "run_id": self.context.run_id,
            "created_at": self.context.created_at,
            "output_dir": str(output_dir),
            "files": files,
        }
