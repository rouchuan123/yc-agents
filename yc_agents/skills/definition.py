from dataclasses import dataclass, field


@dataclass
class SkillDefinition:
    name: str
    description: str
    allowed_tools: list[str] = field(default_factory=list)
    body: str = ""
    path: str = ""
    scripts: list[dict] = field(default_factory=list)
    assets: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "name": self.name,
            "description": self.description,
            "allowed_tools": self.allowed_tools,
            "body": self.body,
            "path": self.path,
            "scripts": self.scripts,
            "assets": self.assets,
            "references": self.references,
        }