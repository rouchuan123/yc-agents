from dataclasses import dataclass, field


@dataclass
class SkillDefinition:
    name: str
    description: str
    allowed_tools: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
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
            "triggers": self.triggers,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "examples": self.examples,
            "body": self.body,
            "path": self.path,
            "scripts": self.scripts,
            "assets": self.assets,
            "references": self.references,
        }

    def to_summary(self):
        return {
            "name": self.name,
            "description": self.description,
            "triggers": self.triggers,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "allowed_tools": self.allowed_tools,
        }
