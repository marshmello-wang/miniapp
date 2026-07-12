"""
协议接口定义 - 定义 Agent 必须实现的接口
"""
from typing import Protocol, Iterator
from .inputs import TaskInput
from .events import Event


class Agent(Protocol):
    """
    Agent 协议接口
    
    所有 Agent 实现（如 ReactAgent）都需要遵循此接口
    """
    
    def run(self, task_input: TaskInput) -> Iterator[Event]:
        """
        执行任务，返回事件流迭代器
        
        Args:
            task_input: 任务输入
            
        Yields:
            Event: 执行过程中产生的事件流
            
        Example:
            >>> agent = ReactAgent(config)
            >>> task = TaskInput(task_id="task-1", messages=[...])
            >>> for event in agent.run(task):
            ...     print(f"收到事件: {event.event_type}")
            ...     for block in event.content:
            ...         if isinstance(block, TextBlock):
            ...             print(block.text)
        """
        ...

