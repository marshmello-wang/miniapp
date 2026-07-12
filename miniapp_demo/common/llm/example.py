"""
LLM 统一接口使用示例

运行前请先安装依赖：
    pip install httpx

设置环境变量：
    export OPENAI_API_KEY="sk-xxx"
    export ANTHROPIC_API_KEY="sk-ant-xxx"
    export GEMINI_API_KEY="xxx"

运行示例：
    python -m common.llm.example
"""

import os
from typing import Optional

# 导入 LLM 模块
from common.llm import (
    LLMClient,
    LLMConfig,
    Message,
    TextContent,
    ImageContent,
    Tool,
    ToolChoice,
    create_client,
)


def example_basic_chat():
    """示例 1: 基本对话"""
    print("\n" + "=" * 50)
    print("示例 1: 基本对话")
    print("=" * 50)
    
    # 方式一：使用 LLMConfig + LLMClient
    config = LLMConfig(
        provider="gemini",
        base_url=os.getenv("LLM_PROXY_GEMINI_BASE_URL", "https://api.openai.com/v1"),
        api_key=os.getenv("GEMINI_API_KEY", "your-api-key"),
        model="gemini-3-flash-preview-thinking",
    )
    client = LLMClient(config)
    
    # 发送消息
    response = client.chat(
        messages=[
            Message(role="system", content="你是一个专业的编程助手，回答简洁明了。"),
            Message(role="user", content="用一句话解释什么是 Python 的装饰器？"),
        ],
        max_tokens=200,
        temperature=0.7,
    )
    
    print(f"回复: {response.content}")
    print(f"Token 使用: {response.usage}")
    

def example_multimodal():
    """示例 3: 多模态 (图文混合)"""
    print("\n" + "=" * 50)
    print("示例 3: 多模态 (图文混合)")
    print("=" * 50)
    
    config = LLMConfig(
        provider="gemini",
        base_url=os.getenv("LLM_PROXY_GEMINI_BASE_URL", "https://api.openai.com/v1"),
        api_key=os.getenv("GEMINI_API_KEY", "your-api-key"),
        model="gemini-3-flash-preview",
    )
    client = LLMClient(config)

    # Claude thinking 模型示例
    # config = LLMConfig(
    #     provider="claude",
    #     base_url=os.getenv("LLM_PROXY_ANTHROPIC_BASE_URL", ""),
    #     api_key=os.getenv("ANTHROPIC_API_KEY", "your-api-key"),
    #     model="claude-3-7-sonnet-20250219",  # 或其他 thinking 模型
    # )
    # client = LLMClient(config)
    
    # 假设这是一个 base64 编码的图片 (实际使用时替换为真实数据)
    fake_image_base64 = "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"
    
    response = client.chat(
        messages=[
            Message(
                role="user",
                content=[
                    TextContent(text="这张图片显示了什么？"),
                    ImageContent(
                        data=fake_image_base64,
                        media_type="image/jpeg",
                    ),
                ],
            ),
        ],
    )
    
    print(f"思考: {response.thinking}")
    print(f"回复: {response.content}")


def example_tool_calling():
    """示例 4: 工具调用 (Function Calling)"""
    print("\n" + "=" * 50)
    print("示例 4: 工具调用 (Function Calling)")
    print("=" * 50)
    
    config = LLMConfig(
        provider="openai",
        base_url=os.getenv("LLM_PROXY_GEMINI_BASE_URL", ""),
        api_key=os.getenv("GEMINI_API_KEY", "your-api-key"),
        model="gemini-3-flash-preview-thinking",
    )
    client = LLMClient(config)
    
    # 定义工具
    tools = [
        Tool(
            name="get_weather",
            description="获取指定城市的当前天气信息",
            parameters={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称，例如：北京、上海",
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "温度单位",
                    },
                },
                "required": ["city"],
            },
        ),
        Tool(
            name="search_web",
            description="在网络上搜索信息",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词",
                    },
                },
                "required": ["query"],
            },
        ),
    ]
    
    # 第一次调用：让模型决定是否调用工具
    response = client.chat(
        messages=[
            Message(role="user", content="北京今天天气怎么样？"),
        ],
        tools=tools,
        tool_choice=ToolChoice(mode="auto"),  # auto: 让模型自己决定
    )
    
    print(f"Finish Reason: {response.finish_reason}")
    
    if response.tool_calls:
        print("模型请求调用工具:")
        for tc in response.tool_calls:
            print(f"  - 工具: {tc.name}")
            print(f"    参数: {tc.arguments}")
            print(f"    ID: {tc.id}")
        
        # 模拟工具执行结果
        # 在实际使用中，这里会调用真正的工具函数
        tool_result = '{"temperature": 25, "condition": "晴朗", "humidity": 40}'
        
        # 第二次调用：将工具结果返回给模型
        messages_with_result = [
            Message(role="user", content="北京今天天气怎么样？"),
            Message(
                role="assistant",
                content=None,  # 工具调用时 content 可能为空
            ),
            Message(
                role="tool",
                content=tool_result,
                tool_call_id=response.tool_calls[0].id,
                name=response.tool_calls[0].name,
            ),
        ]
        
        final_response = client.chat(messages=messages_with_result)
        print(f"\n最终回复: {final_response.content}")
    else:
        print(f"直接回复: {response.content}")


def example_tool_choice_modes():
    """示例 5: tool_choice 的不同模式"""
    print("\n" + "=" * 50)
    print("示例 5: tool_choice 的不同模式")
    print("=" * 50)
    
    print("""
    ToolChoice 支持以下模式:
    
    1. mode="auto"     - 让模型自己决定是否调用工具
    2. mode="none"     - 禁止调用工具，只生成文本回复
    3. mode="required" - 必须调用某个工具 (任意一个)
    4. mode="specific" - 必须调用指定的工具
       需要同时指定 tool_name 参数
    
    示例:
        ToolChoice(mode="auto")
        ToolChoice(mode="none")
        ToolChoice(mode="required")
        ToolChoice(mode="specific", tool_name="get_weather")
    """)


def example_error_handling():
    """示例 7: 错误处理"""
    print("\n" + "=" * 50)
    print("示例 7: 错误处理")
    print("=" * 50)
    
    from common.llm import (
        LLMError,
        AuthenticationError,
        RateLimitError,
        InvalidRequestError,
        APIError,
    )
    
    client = create_client("openai", "invalid-api-key", "gpt-4o-mini")
    
    try:
        response = client.chat(
            messages=[Message(role="user", content="Hello")],
        )
    except AuthenticationError as e:
        print(f"认证失败: {e}")
        print(f"状态码: {e.status_code}")
    except RateLimitError as e:
        print(f"速率限制: {e}")
    except InvalidRequestError as e:
        print(f"无效请求: {e}")
    except APIError as e:
        print(f"API 错误: {e}")
    except LLMError as e:
        print(f"LLM 错误: {e}")


def example_thinking_model():
    """示例 9: 思考模型 (Thinking Models)"""
    print("\n" + "=" * 50)
    print("示例 9: 思考模型 (Thinking Models)")
    print("=" * 50)
    
    # # Gemini 3.0+ thinking 模型示例
    # config = LLMConfig(
    #     provider="gemini",
    #     base_url=os.getenv("LLM_PROXY_GEMINI_BASE_URL", ""),
    #     api_key=os.getenv("GEMINI_API_KEY", "your-api-key"),
    #     model="gemini-3-flash-preview",  # 或其他 thinking 模型
    # )

    # Claude thinking 模型示例
    config = LLMConfig(
        provider="claude",
        base_url=os.getenv("LLM_PROXY_ANTHROPIC_BASE_URL", ""),
        api_key=os.getenv("ANTHROPIC_API_KEY", "your-api-key"),
        model="claude-3-7-sonnet-20250219",  # 或其他 thinking 模型
    )
    client = LLMClient(config)
    
    # 使用 thinking_level 控制思考深度
    # 可选值: "minimal", "low", "medium", "high"
    response = client.chat(
        messages=[
            Message(role="user", content="请逐步分析：如果一个人以每小时5公里的速度走了3小时，然后以每小时10公里的速度骑自行车2小时，总共走了多少公里？"),
        ],
        thinking_level="low",  # 统一的思考级别
    )
    
    # 分别获取思考过程和最终回答
    if response.thinking:
        print("思考过程:")
        print("-" * 40)
        print(response.thinking)
        print("-" * 40)
    
    print(f"\n最终回答: {response.content}")
    print(f"Token 使用: {response.usage}")


def example_thinking_levels():
    """示例 10: thinking_level 的不同级别"""
    print("\n" + "=" * 50)
    print("示例 10: thinking_level 的不同级别")
    print("=" * 50)
    
    print("""
    thinking_level 支持以下统一档位:
    
    1. "minimal" - 最少思考
       - Gemini: thinkingLevel="MINIMAL"
       - Claude: budget_tokens=1024
       - OpenAI: reasoning.effort="low"
    
    2. "low" - 低程度思考
       - Gemini: thinkingLevel="LOW"
       - Claude: budget_tokens=4096
       - OpenAI: reasoning.effort="low"
    
    3. "medium" - 中等思考 (推荐)
       - Gemini: thinkingLevel="MEDIUM"
       - Claude: budget_tokens=10240
       - OpenAI: reasoning.effort="medium"
    
    4. "high" - 深度思考
       - Gemini: thinkingLevel="HIGH"
       - Claude: budget_tokens=32768
       - OpenAI: reasoning.effort="high"
    
    使用示例:
        response = client.chat(
            messages=[Message(role="user", content="复杂问题...")],
            thinking_level="medium",
        )
        
        # 获取思考过程
        print(response.thinking)
        
        # 获取最终回答
        print(response.content)
    """)


def example_custom_base_url():
    """示例 8: 自定义 API 端点 (用于代理或私有部署)"""
    print("\n" + "=" * 50)
    print("示例 8: 自定义 API 端点")
    print("=" * 50)
    
    print("""
    如果你使用代理或私有部署，可以自定义 base_url:
    
    config = LLMConfig(
        provider="openai",
        api_key="your-api-key",
        model="gpt-4o",
        base_url="https://your-proxy.com/v1",  # 自定义端点
        timeout=120,  # 超时时间 (秒)
        max_retries=3,  # 重试次数
    )
    """)


def main():
    """运行所有示例"""
    print("=" * 50)
    print("LLM 统一接口使用示例")
    print("=" * 50)
    
    # 显示所有示例说明
    print("""
    本文件包含以下示例:
    
    1. example_basic_chat()        - 基本对话
    3. example_multimodal()        - 多模态 (图文混合)
    4. example_tool_calling()      - 工具调用 (Function Calling)
    5. example_tool_choice_modes() - tool_choice 的不同模式
    7. example_error_handling()    - 错误处理
    8. example_custom_base_url()   - 自定义 API 端点
    9. example_thinking_model()    - 思考模型 (Thinking Models)
    10. example_thinking_levels()  - thinking_level 的不同级别
    
    请确保已设置相应的环境变量后，取消下方的注释来运行示例。
    """)
    
    # 取消注释来运行对应的示例:
    # example_basic_chat()
    example_multimodal()
    # example_tool_calling()
    # example_tool_choice_modes()
    # example_error_handling()
    # example_custom_base_url()
    # example_thinking_model()
    # example_thinking_levels()


if __name__ == "__main__":
    main()

