import json
from pathlib import Path

class SimpleAgent:
    def __init__(self, name, llm, system_prompt):
        self.name = name
        self.llm = llm
        self.system_prompt = system_prompt
        self.history = []
        
        
    def run(self, user_input):
        messages = [
            {"role": "system", "content": self.system_prompt},
            *self.history,
            {"role": "user", "content": user_input},
        ]
        
        response = self.llm.think(messages)
        
        self.history.append({"role": "user", "content": user_input})
        self.history.append({"role": "assistant", "content": response})
        
        return response
    
    # 存聊天记录
    def save_history(self, file_path):
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)
    
    # 读取聊天记录
    def load_history(self, file_path):
        path = Path(file_path)

        if not path.exists():
            self.history = []
            return
        
        with path.open("r", encoding="utf-8") as f:
            self.history = json.load(f)