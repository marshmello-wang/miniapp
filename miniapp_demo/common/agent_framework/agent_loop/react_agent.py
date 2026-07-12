"""
ReactAgent 实现 - React 模式的 Agent 执行循环
"""
import asyncio
from pathlib import Path
from typing import Iterator, List, Optional, Dict, Any
from uuid import uuid4
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from common.agent_framework.user_interface.protocol import Agent
from common.agent_framework.user_interface.inputs import TaskInput
from common.agent_framework.user_interface.events import Event
from common.agent_framework.user_interface.content_blocks import (
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
    ThinkingBlock,
    ContentBlock
)
from common.agent_framework.context_strategy.builder import ContextBuilder
from common.agent_framework.tool_adapter.executor import ToolExecutor
from common.agent_framework.tool_adapter.protocol import ToolResult
from common.llm import ChatResponse, ToolCall

from .config import ReactAgentConfig, SkillConfig, SubAgentConfig
from .hooks import Hook, HookContext, HookResult, DefaultHook, CompositeHook


class ReactAgent:
    """
    React Agent 实现
    
    实现了 Reasoning-Action 循环模式：
    1. 调用模型进行推理
    2. 解析模型响应，判断是否需要执行工具
    3. 如果需要执行工具，执行工具并获取结果
    4. 将工具结果加入上下文，继续下一轮推理
    5. 直到模型返回 stop 或达到最大迭代次数
    
    Example:
        >>> from common.llm import LLMClient, LLMConfig
        >>> config = ReactAgentConfig(
        ...     llm_client=LLMClient(LLMConfig(provider="openai", api_key="...", model="gpt-4o")),
        ...     tool_registry=registry,
        ...     context_strategy=DefaultStrategy(),
        ...     system_prompt="You are a helpful assistant."
        ... )
        >>> agent = ReactAgent(config)
        >>> 
        >>> task = TaskInput(
        ...     session_id="session-1",
        ...     task_id="task-1",
        ...     messages=[Message.from_role_and_text("user", "Hello!")]
        ... )
        >>> 
        >>> for event in agent.run(task):
        ...     print(f"Event: {event.event_type}")
        ...     for block in event.content:
        ...         if isinstance(block, TextBlock):
        ...             print(block.text)
    """
    
    def __init__(self, config: ReactAgentConfig):
        """
        初始化 ReactAgent
        
        Args:
            config: ReactAgentConfig 配置
        """
        self._config = config
        self._llm_client = config.llm_client
        self._max_tokens = config.max_tokens
        self._temperature = config.temperature
        self._thinking_level = config.thinking_level
        
        # ================================================================
        # Phase 1: ContextBuilder 之前 - 注册内置工具到 tool_registry
        # ================================================================
        
        # Skill 集成 (Phase 1): 创建 manager，注册 load_skill 工具
        self._skill_manager = None
        self._load_skill_tool = None
        self._skill_prompt_extra = ""
        if config.skill_config:
            self._setup_skills(config.skill_config)
        
        # Sub Agent 集成 (Phase 1): 创建 manager，注册 create_sub_agent 工具
        self._sub_agent_manager = None
        self._create_sub_agent_tool = None
        if config.sub_agent_config:
            self._setup_sub_agents(config.sub_agent_config)
        
        self._tool_executor = ToolExecutor(config.tool_registry)
        
        # 获取工具 schema 列表（此时 tool_registry 已包含 load_skill / create_sub_agent）
        tools_schema = [
            tool.schema 
            for tool in config.tool_registry.list_tools()
        ] if config.tool_registry else None
        
        # Jinja2 模板渲染 system_prompt
        resolved_system_prompt = self._render_system_prompt(config)
        
        # 将 Skill / Sub Agent 候选列表合入 base system prompt（非 Jinja 模式）
        if not self._is_jinja_template(config.system_prompt):
            extra_parts = []
            if self._skill_prompt_extra:
                extra_parts.append(self._skill_prompt_extra)
            if self._sub_agent_manager:
                candidates = self._sub_agent_manager.get_candidates_prompt()
                if candidates:
                    extra_parts.append(candidates)
            if extra_parts:
                resolved_system_prompt = resolved_system_prompt + "\n\n" + "\n\n".join(extra_parts)
        
        # ================================================================
        # Phase 2: 创建 ContextBuilder
        # ================================================================
        memory_helper = None
        if config.memory_config:
            from common.agent_framework.context_strategy.memory import (
                ContextMemoryHelper,
            )
            from common.agent_framework.context_strategy.memory.store import InMemoryStore

            store = InMemoryStore()
            memory_helper = ContextMemoryHelper(config.memory_config, store=store)

            if self._uses_prefix_ref(config.memory_config):
                from common.agent_framework.builtin_tools import ReadExpireHistoryTool
                read_expire_tool = ReadExpireHistoryTool(store)
                config.tool_registry.register(read_expire_tool)

        self._context_builder = ContextBuilder(
            strategy=config.context_strategy,
            base_system_prompt=resolved_system_prompt,
            truncation=config.truncation_strategy,
            memory=memory_helper,
            tools=tools_schema
        )
        
        # 设置 Hook
        if config.hooks:
            if len(config.hooks) == 1:
                self._hook: Hook = config.hooks[0]
            else:
                self._hook = CompositeHook(config.hooks)
        else:
            self._hook = DefaultHook()
        
        self._max_iterations = config.max_iterations
        
        # ================================================================
        # Phase 3: ContextBuilder 之后 - 需要 ContextBuilder 的操作
        # ================================================================
        
        # Skill 集成 (Phase 3): 将 static skill 的 binding tools 加入 ContextBuilder
        if self._skill_manager:
            self._post_setup_skills()
    
    def _setup_skills(self, skill_config: SkillConfig) -> None:
        """
        Skill 集成 Phase 1（ContextBuilder 之前）
        
        创建 SkillManager，注册 LoadSkillTool 到 tool_registry，
        准备非 Jinja 模式下的 system prompt 片段。
        """
        from common.agent_framework.skill import (
            SkillRegistry, SkillLoader, SkillManager
        )
        from common.agent_framework.builtin_tools import LoadSkillTool

        skill_registry = SkillRegistry()
        skill_registry.load_from_config(skill_config.skills_config)

        skill_loader = SkillLoader(base_path=skill_config.base_path)
        self._skill_manager = SkillManager(
            skill_registry=skill_registry,
            tool_registry=self._config.tool_registry,
            skill_loader=skill_loader,
            global_envs=skill_config.global_envs,
        )

        # 准备非 Jinja 模式下的 prompt 片段（由 __init__ 主流程合入 base_system_prompt）
        if not self._is_jinja_template(self._config.system_prompt):
            static_prompt = self._skill_manager.get_static_skill_prompt()
            dynamic_prompt = self._skill_manager.get_dynamic_skill_candidates_prompt()
            if static_prompt or dynamic_prompt:
                parts = [p for p in [static_prompt, dynamic_prompt] if p]
                self._skill_prompt_extra = "\n\n".join(parts)

        # 注册 load_skill 工具到 tool_registry（仅当有 dynamic skills 时）
        if skill_registry.list_dynamic():
            self._load_skill_tool = LoadSkillTool(self._skill_manager)
            self._config.tool_registry.register(self._load_skill_tool)

    def _post_setup_skills(self) -> None:
        """
        Skill 集成 Phase 3（ContextBuilder 之后）
        
        将 static skill 的 binding tools 加入 ContextBuilder。
        """
        for skill_name, tool_schemas in self._skill_manager.get_static_skill_binding_tools().items():
            self._context_builder.add_skill_tools(skill_name, tool_schemas)

    def _setup_sub_agents(self, sub_agent_config: SubAgentConfig) -> None:
        """
        初始化 Sub Agent 支持（在 ContextBuilder 创建之前调用）
        
        注册 SubAgentRegistry/Manager 和 CreateSubAgentTool 到 tool_registry。
        system prompt 注入由 __init__ 主流程在创建 ContextBuilder 时处理。
        """
        from common.agent_framework.sub_agent import (
            SubAgentDefinition, SubAgentRegistry, SubAgentManager
        )
        from common.agent_framework.builtin_tools.create_sub_agent_tool import CreateSubAgentTool

        registry = SubAgentRegistry()
        for name, defn in sub_agent_config.agents.items():
            if isinstance(defn, SubAgentDefinition):
                registry.register_definition(defn)
            elif isinstance(defn, dict):
                registry.register(
                    name=name,
                    agent=defn["agent"],
                    description=defn.get("description", ""),
                )
            else:
                registry.register(name=name, agent=defn, description="")

        self._sub_agent_manager = SubAgentManager(registry)
        self._create_sub_agent_tool = CreateSubAgentTool(self._sub_agent_manager)
        self._config.tool_registry.register(self._create_sub_agent_tool)

    @staticmethod
    def _uses_prefix_ref(memory_config) -> bool:
        """检查 memory 配置中是否使用了 prefix_ref 折叠策略"""
        for cfg in [memory_config.l1, memory_config.l2]:
            if cfg is None:
                continue
            hc = cfg.history_collapse
            for strategy in [hc.thinking_collapse, hc.tool_call_collapse, hc.tool_response_collapse]:
                if strategy.type == "prefix_ref":
                    return True
        return False

    @staticmethod
    def _is_jinja_template(text: str) -> bool:
        """判断字符串是否包含 Jinja2 模板语法"""
        return "{{" in text or "{%" in text

    @staticmethod
    def _render_system_prompt(config: ReactAgentConfig) -> str:
        """
        渲染 system_prompt：如果是 Jinja2 模板则渲染，否则原样返回。
        
        Returns:
            渲染后的 system_prompt 字符串
        """
        if not ReactAgent._is_jinja_template(config.system_prompt):
            return config.system_prompt

        from jinja2 import Template

        # 构造 skills 模板变量
        skills_data: List[Dict[str, str]] = []
        if config.skill_config:
            base_path = Path(config.skill_config.base_path) if config.skill_config.base_path else Path(".")
            for name, conf in config.skill_config.skills_config.items():
                if not isinstance(conf, dict):
                    continue
                content_file_path = conf.get("content_file_path", "")
                local_path = str((base_path / content_file_path).resolve()) if content_file_path else ""
                skills_data.append({
                    "name": name,
                    "description": conf.get("description", ""),
                    "load_type": conf.get("load_type", "dynamic"),
                    "content_file_path": content_file_path,
                    "local_path": local_path,
                })

        # 合并渲染变量
        template_vars: Dict[str, Any] = {"skills": skills_data}
        if config.system_prompt_vars:
            template_vars.update(config.system_prompt_vars)

        # 渲染模板
        template = Template(config.system_prompt)
        return template.render(**template_vars)

    def run(self, task_input: TaskInput) -> Iterator[Event]:
        """
        执行任务，返回事件流迭代器
        
        实现 Agent 协议接口。
        
        Args:
            task_input: 任务输入
        
        Yields:
            Event: 执行过程中产生的事件流
        """
        # 使用 asyncio 运行异步循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # 创建异步生成器
            async_gen = self._run_async(task_input)
            
            while True:
                try:
                    event = loop.run_until_complete(async_gen.__anext__())
                    yield event
                except StopAsyncIteration:
                    break
        finally:
            loop.close()
    
    async def run_async(self, task_input: TaskInput):
        """
        异步执行任务
        
        如果调用方本身是异步环境，可以直接使用此方法。
        
        Args:
            task_input: 任务输入
        
        Yields:
            Event: 执行过程中产生的事件流
        """
        async for event in self._run_async(task_input):
            yield event
    
    async def _run_async(self, task_input: TaskInput):
        """
        内部异步执行逻辑
        """
        session_id = task_input.session_id
        task_id = task_input.task_id
        
        # 重置上下文构建器
        self._context_builder.reset(task_input)
        
        # 设置 sub agent 的 session_id
        if self._create_sub_agent_tool:
            self._create_sub_agent_tool.set_session_id(session_id)
        
        # 记录已产生的事件
        events: List[Event] = []
        
        # 主循环
        for iteration in range(self._max_iterations):
            # ================================================================
            # Skill Offload Check
            # ================================================================
            if self._skill_manager and self._load_skill_tool:
                self._load_skill_tool.set_current_round(iteration)
                offload_names = self._skill_manager.check_offload(iteration)
                if offload_names:
                    self._skill_manager.execute_offload(offload_names)
                    for name in offload_names:
                        self._context_builder.remove_skill_tools(name)

            # ================================================================
            # Before Reasoning Hook
            # ================================================================
            hook_ctx = HookContext(
                phase="before_reasoning",
                iteration=iteration,
                task_input=task_input,
                events=events.copy()
            )
            hook_result = self._hook.before_reasoning(hook_ctx)
            
            if hook_result.force_stop:
                break
            
            if hook_result.skip_phase:
                continue
            
            # 处理注入的 prompt
            if hook_result.inject_prompt:
                self._context_builder.modify_system_prompt(
                    lambda p, inject=hook_result.inject_prompt: f"{p}\n\n{inject}"
                )
            
            # ================================================================
            # 构建上下文 & 调用模型（含 L1 budget 截断 + L2 微折叠）
            # ================================================================
            context = self._context_builder.build_with_compaction(iteration)
            
            # 设置运行时参数
            context.max_tokens = self._max_tokens
            context.temperature = self._temperature
            if self._thinking_level:
                context.thinking_level = self._thinking_level
            
            try:
                # 使用 LLMClient 调用模型（同步调用）
                response: ChatResponse = self._llm_client.chat_with_request(context)
            except Exception as e:
                # 生成错误事件
                error_event = self._create_event(
                    session_id=session_id,
                    task_id=task_id,
                    event_type="error",
                    content=[TextBlock(f"Model call failed: {str(e)}")],
                    metadata={"error": str(e), "iteration": iteration}
                )
                events.append(error_event)
                self._context_builder.add_event(error_event)
                yield error_event
                break

            # ================================================================
            # 生成 Reasoning 事件
            # ================================================================
            reasoning_content: List[ContentBlock] = []
            
            # 提取 thinking 内容
            thinking = response.thinking
            if thinking:
                reasoning_content.append(ThinkingBlock(thinking))
            
            # 提取文本内容
            text = response.content
            if text:
                reasoning_content.append(TextBlock(text))
            
            # 提取工具调用内容
            tool_calls: List[ToolCall] = response.tool_calls or []
            for tool_call in tool_calls:
                reasoning_content.append(ToolCallBlock(
                    tool_name=tool_call.name,
                    tool_input=tool_call.arguments,
                    call_id=tool_call.id
                ))
            
            # 构建 usage 字典
            usage_dict = None
            if response.usage:
                usage_dict = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
            
            reasoning_event = self._create_event(
                session_id=session_id,
                task_id=task_id,
                event_type="reasoning",
                content=reasoning_content,
                metadata={
                    "iteration": iteration,
                    "finish_reason": response.finish_reason,
                    "usage": usage_dict
                }
            )
            events.append(reasoning_event)
            self._context_builder.add_event(reasoning_event)
            yield reasoning_event
            
            # ================================================================
            # After Reasoning Hook
            # ================================================================
            hook_ctx = HookContext(
                phase="after_reasoning",
                iteration=iteration,
                task_input=task_input,
                events=events.copy(),
                current_response=response
            )
            hook_result = self._hook.after_reasoning(hook_ctx)
            
            if hook_result.force_stop:
                break
            
            # ================================================================
            # 处理工具调用
            # ================================================================
            if tool_calls:
                for tool_call in tool_calls:
                    # Before Tool Execution Hook
                    hook_ctx = HookContext(
                        phase="before_tool_execution",
                        iteration=iteration,
                        task_input=task_input,
                        events=events.copy(),
                        current_response=response,
                        current_tool_name=tool_call.name
                    )
                    hook_result = self._hook.before_tool_execution(hook_ctx)
                    
                    if hook_result.force_stop:
                        # 生成任务完成事件
                        complete_event = self._create_event(
                            session_id=session_id,
                            task_id=task_id,
                            event_type="task_complete",
                            content=[TextBlock("Task stopped by hook.")],
                            metadata={"reason": "hook_force_stop", "iteration": iteration}
                        )
                        events.append(complete_event)
                        yield complete_event
                        return
                    
                    if hook_result.skip_phase:
                        # 生成跳过的工具结果事件
                        skip_event = self._create_event(
                            session_id=session_id,
                            task_id=task_id,
                            event_type="tool_result",
                            content=[ToolResultBlock(
                                tool_name=tool_call.name,
                                result=None,
                                call_id=tool_call.id,
                                is_error=False,
                                error_message="Skipped by hook"
                            )],
                            metadata={"skipped": True}
                        )
                        events.append(skip_event)
                        self._context_builder.add_event(skip_event)
                        yield skip_event
                        continue
                    
                    # 处理参数修改
                    tool_params = tool_call.arguments
                    if hook_result.modify_tool_params:
                        tool_params = {**tool_params, **hook_result.modify_tool_params}
                    
                    # 执行工具
                    tool_result = await self._tool_executor.execute(
                        tool_name=tool_call.name,
                        parameters=tool_params,
                        call_id=tool_call.id
                    )
                    
                    # 生成工具结果事件
                    tool_result_event = self._create_event(
                        session_id=session_id,
                        task_id=task_id,
                        event_type="tool_result",
                        content=[ToolResultBlock(
                            tool_name=tool_call.name,
                            result=tool_result.formatted_data or tool_result.data,
                            call_id=tool_call.id,
                            is_error=not tool_result.success,
                            error_message=tool_result.error
                        )],
                        metadata={
                            "success": tool_result.success,
                            "metadata": tool_result.metadata
                        }
                    )
                    events.append(tool_result_event)
                    self._context_builder.add_event(tool_result_event)
                    yield tool_result_event
                    
                    # After Tool Execution Hook
                    hook_ctx = HookContext(
                        phase="after_tool_execution",
                        iteration=iteration,
                        task_input=task_input,
                        events=events.copy(),
                        current_response=response,
                        current_tool_name=tool_call.name,
                        current_tool_result=tool_result
                    )
                    hook_result = self._hook.after_tool_execution(hook_ctx)
                    
                    if hook_result.force_stop:
                        complete_event = self._create_event(
                            session_id=session_id,
                            task_id=task_id,
                            event_type="task_complete",
                            content=[TextBlock("Task stopped by hook after tool execution.")],
                            metadata={"reason": "hook_force_stop", "iteration": iteration}
                        )
                        events.append(complete_event)
                        yield complete_event
                        return
                    
                    # Skill: 处理 load_skill 的返回结果
                    if (
                        tool_call.name == "load_skill"
                        and self._skill_manager
                        and tool_result.success
                        and tool_result.metadata
                    ):
                        binding_schemas = tool_result.metadata.get("binding_tool_schemas", [])
                        skill_name = tool_result.metadata.get("skill_name", "")
                        if binding_schemas and skill_name:
                            self._context_builder.add_skill_tools(skill_name, binding_schemas)
            
            # ================================================================
            # 检查是否有 end_tool 被调用
            # ================================================================
            if tool_calls and self._config.end_tools:
                if any(tc.name in self._config.end_tools for tc in tool_calls):
                    break

            # ================================================================
            # 检查是否结束
            # ================================================================
            if response.finish_reason == "stop":
                break
            
            if response.finish_reason == "max_tokens":
                # 达到 token 限制，生成警告事件
                warning_event = self._create_event(
                    session_id=session_id,
                    task_id=task_id,
                    event_type="warning",
                    content=[TextBlock("Response truncated due to max_tokens limit.")],
                    metadata={"iteration": iteration}
                )
                events.append(warning_event)
                yield warning_event
        
        # ================================================================
        # 生成任务完成事件
        # ================================================================
        complete_event = self._create_event(
            session_id=session_id,
            task_id=task_id,
            event_type="task_complete",
            content=[],
            metadata={
                "total_iterations": min(iteration + 1, self._max_iterations),
                "reason": "completed" if iteration < self._max_iterations - 1 else "max_iterations"
            }
        )
        events.append(complete_event)
        yield complete_event
    
    def _create_event(
        self,
        session_id: str,
        task_id: str,
        event_type: str,
        content: List[ContentBlock],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Event:
        """创建事件的辅助方法"""
        return Event.create(
            event_id=str(uuid4()),
            session_id=session_id,
            task_id=task_id,
            event_type=event_type,
            content=content,
            metadata=metadata
        )


def create_react_agent(config: ReactAgentConfig) -> ReactAgent:
    """
    创建 React Agent 的工厂函数
    
    Args:
        config: ReactAgentConfig 配置
    
    Returns:
        ReactAgent: 创建的 React Agent 实例
    
    Example:
        >>> from common.llm import LLMClient, LLMConfig
        >>> config = ReactAgentConfig(
        ...     llm_client=LLMClient(LLMConfig(provider="openai", api_key="...", model="gpt-4o")),
        ...     tool_registry=registry,
        ...     context_strategy=DefaultStrategy(),
        ...     system_prompt="You are a helpful assistant."
        ... )
        >>> agent = create_react_agent(config)
    """
    return ReactAgent(config)

