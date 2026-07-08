from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    deepseek_api_key: str = ""
    deepseek_api_base: str = "https://api.deepseek.com/v1"
    
    qianwen_api_key: str = ""
    qianwen_api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    
    doubao_api_key: str = ""
    doubao_api_base: str = "https://ark.cn-beijing.volces.com/api/v3"
    
    yuanbao_api_key: str = ""
    yuanbao_api_base: str = "https://api.yuanbao.tencent.com/v1"
    
    ollama_base_url: str = "http://localhost:11434"
    
    vllm_base_url: str = "http://localhost:8000/v1"
    vllm_model_name: str = "qwen2-7b"
    
    localai_base_url: str = "http://localhost:8080/v1"
    localai_model_name: str = "qwen2"
    
    openai_api_key: str = ""
    openai_api_base: str = "https://api.openai.com/v1"
    
    redis_url: str = "redis://localhost:6379/0"
    
    cache_ttl_default: int = 3600
    cache_ttl_short: int = 600
    cache_ttl_medium: int = 1800
    cache_ttl_long: int = 86400
    
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096
    llm_timeout: int = 60
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()