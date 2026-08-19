from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI

from app.conf.app_config import app_config


def build_llm(model_name: str, api_key: str, base_url: str = "", proxy: str = ""):
    if base_url:
        return ChatOpenAI(
            model=model_name,
            api_key=api_key or "local",
            base_url=base_url,
            temperature=0,
        )
    kwargs = {"model": model_name, "api_key": api_key, "temperature": 0}
    if proxy:
        kwargs["openai_proxy"] = proxy
    return init_chat_model(**kwargs)


llm = build_llm(app_config.llm.model_name, app_config.llm.api_key, app_config.llm.base_url)
correction_llm = build_llm(
    app_config.llm.correction_model_name or app_config.llm.model_name,
    app_config.llm.correction_api_key or app_config.llm.api_key,
    app_config.llm.correction_base_url,
    app_config.llm.correction_proxy,
)

if __name__ == '__main__':
    for chunk in llm.stream("who are you?"):
        print(chunk.text,end="")
