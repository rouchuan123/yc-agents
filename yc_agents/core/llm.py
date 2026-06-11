import os #读取环境变量
from openai import OpenAI #创建 API 客户端


class YCAgentsLLM:
    def __init__(self):
        self.model = os.getenv("LLM_MODEL_ID")
        self.api_key = os.getenv("LLM_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL")
        
        if not self.model:
            raise ValueError("缺少 LLM_MODEL_ID")

        if not self.api_key:
            raise ValueError("缺少 LLM_API_KEY")

        if not self.base_url:
            raise ValueError("缺少 LLM_BASE_URL")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )
        self.provider = os.getenv("LLM_PROVIDER", "auto").lower()

        if self.provider == "auto":
            self.provider = self._detect_provider(self.base_url)


    def think(self, messages, **kwargs):   
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs,
        )

        return response.choices[0].message.content
    
    
    @staticmethod
    def _detect_provider(base_url):
        normalized_url = base_url.lower()

        provider_keywords = {
            "deepseek": "deepseek",
            "modelscope": "modelscope",
            "openai": "openai",
            "ollama": "ollama",
            "11434": "ollama",
            "vllm": "vllm",
        }

        for keyword, provider in provider_keywords.items():
            if keyword in normalized_url:
                return provider

        return "openai_compatible"
    
    