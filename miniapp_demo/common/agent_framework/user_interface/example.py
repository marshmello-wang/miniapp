"""
ReactAgent 示例 - 使用 Gemini 模型的 Agent 演示

演示如何使用 ReactAgent 配合工具执行任务。

使用方法:
    export GEMINI_API_KEY="your-api-key"
    python example.py
"""
import os
import sys
from datetime import datetime

# 添加项目根目录到路径
# example.py 位于 forge_os/common/agent_framework/user_interface/
# 需要添加 forge_os/ 到 sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, PROJECT_ROOT)

from common.llm import LLMClient, LLMConfig
from common.agent_framework.agent_loop.react_agent import ReactAgent
from common.agent_framework.agent_loop.config import ReactAgentConfig
from common.agent_framework.tool_adapter.registry import ToolRegistry
from common.agent_framework.tool_adapter.decorators import tool
from common.agent_framework.context_strategy.default_strategy import DefaultContextStrategy
from common.agent_framework.user_interface.inputs import TaskInput, Message
from common.agent_framework.user_interface.content_blocks import (
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
    ThinkingBlock
)


# ============================================================
# 定义工具
# ============================================================

@tool(
    description="获取当前时间，返回格式化的日期时间字符串"
)
async def get_current_time() -> str:
    """获取当前时间"""
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")


@tool(
    description="计算两个数字的基本运算。operation 可以是 add/subtract/multiply/divide"
)
async def calculate(a: float, b: float, operation: str) -> str:
    """计算器工具"""
    if operation == "add":
        result = a + b
    elif operation == "subtract":
        result = a - b
    elif operation == "multiply":
        result = a * b
    elif operation == "divide":
        if b == 0:
            return "错误：除数不能为零"
        result = a / b
    else:
        return f"错误：不支持的操作 {operation}"
    
    return f"{a} {operation} {b} = {result}"


@tool(
    description="获取指定城市的天气信息（模拟数据）"
)
async def get_weather(city: str) -> str:
    """获取天气信息（模拟）"""
    # 模拟天气数据
    weather_data = {
        "北京": {"temp": 15, "condition": "晴朗", "humidity": 45},
        "上海": {"temp": 18, "condition": "多云", "humidity": 65},
        "深圳": {"temp": 25, "condition": "晴", "humidity": 70},
        "杭州": {"temp": 16, "condition": "阴", "humidity": 60},
    }
    
    if city in weather_data:
        data = weather_data[city]
        return f"{city}天气：{data['condition']}，温度 {data['temp']}°C，湿度 {data['humidity']}%"
    else:
        return f"暂无 {city} 的天气数据"


# ============================================================
# 主程序
# ============================================================

def create_agent() -> ReactAgent:
    """创建并配置 ReactAgent"""
    
    # 从环境变量获取 API Key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("请设置环境变量 GEMINI_API_KEY")
    
    # 配置 LLM Client
    llm_config = LLMConfig(
        provider="gemini",
        base_url=os.getenv("LLM_PROXY_GEMINI_BASE_URL"),
        api_key=os.getenv("GEMINI_API_KEY"),
        model="gemini-3-flash-preview",
    )
    llm_client = LLMClient(llm_config)
    
    # 创建工具注册中心并注册工具
    registry = ToolRegistry()
    registry.register(get_current_time)
    registry.register(calculate)
    registry.register(get_weather)
    
    # 创建上下文策略
    context_strategy = DefaultContextStrategy()
    
    # 创建 Agent 配置
    agent_config = ReactAgentConfig(
        llm_client=llm_client,
        tool_registry=registry,
        context_strategy=context_strategy,
        system_prompt="""你是一个智能助手，可以帮助用户完成各种任务。

你有以下工具可用：
- get_current_time: 获取当前时间
- calculate: 进行数学计算
- get_weather: 查询城市天气

请根据用户的问题选择合适的工具来回答。如果不需要工具，直接回答即可。
回答请使用中文。""",
        max_iterations=10,
        max_tokens=4096,
        temperature=0.7
    )
    
    return ReactAgent(agent_config)


def run_task(agent: ReactAgent, user_message: str):
    """运行一个任务"""
    print(f"\n{'='*60}")
    print(f"用户: {user_message}")
    print('='*60)
    
    # 创建任务输入
    task_input = TaskInput(
        session_id="example-session",
        task_id="example-task",
        messages=[Message.from_role_and_text("user", user_message)]
    )
    
    # 运行 Agent 并处理事件流
    for event in agent.run(task_input):
        print(f"\n[事件] {event.event_type}")
        print("=====event", event)
        
        for block in event.content:
            print("    ====block", block)
            if isinstance(block, ThinkingBlock):
                print(f"  思考: {block.thinking}")
            elif isinstance(block, TextBlock):
                print(f"  文本: {block.text}")
            elif isinstance(block, ToolCallBlock):
                print("111111")
                print(f"  调用工具: {block.tool_name}")
                print(f"  参数: {block.tool_input}")
            elif isinstance(block, ToolResultBlock):
                print("222222")
                print(f"  工具结果: {block.result}")
                if block.is_error:
                    print(f"  错误: {block.error_message}")
        
        if event.metadata:
            if "iteration" in event.metadata:
                print(f"  迭代: {event.metadata['iteration']}")


def main():
    """主函数"""
    print("ReactAgent 示例 - 使用 Gemini gemini-3-flash-preview")
    print("-" * 60)
    
    try:
        agent = create_agent()
        print("Agent 创建成功！")
    except ValueError as e:
        print(f"错误: {e}")
        return
    
    # 示例任务
    tasks = [
        "现在几点了？",
        # "帮我计算 123 乘以 456 等于多少",
        # "北京和上海今天天气怎么样？",
    ]
    
    for task in tasks:
        try:
            run_task(agent, task)
        except Exception as e:
            print(f"任务执行出错: {e}")
    
    print("\n" + "="*60)
    print("示例运行完成！")


if __name__ == "__main__":
    main()

