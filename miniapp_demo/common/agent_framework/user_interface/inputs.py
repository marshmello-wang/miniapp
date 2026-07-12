"""
输入类型定义 - 定义任务输入侧的数据结构
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union, Literal
from pathlib import Path


@dataclass
class ImageContent:
    """图片内容，支持 base64 编码或文件路径两种方式"""
    type: Literal["base64", "path"]
    data: str  # base64 字符串或文件路径
    mime_type: Optional[str] = None  # 如 "image/jpeg", "image/png"
    
    @classmethod
    def from_base64(cls, base64_str: str, mime_type: str = "image/jpeg") -> "ImageContent":
        """从 base64 字符串创建"""
        return cls(type="base64", data=base64_str, mime_type=mime_type)
    
    @classmethod
    def from_path(cls, path: Union[str, Path], mime_type: Optional[str] = None) -> "ImageContent":
        """从文件路径创建"""
        return cls(type="path", data=str(path), mime_type=mime_type)


@dataclass
class VideoContent:
    """视频内容，支持 base64 编码或文件路径两种方式"""
    type: Literal["base64", "path"]
    data: str  # base64 字符串或文件路径
    mime_type: Optional[str] = None  # 如 "video/mp4", "video/webm"
    
    @classmethod
    def from_base64(cls, base64_str: str, mime_type: str = "video/mp4") -> "VideoContent":
        """从 base64 字符串创建"""
        return cls(type="base64", data=base64_str, mime_type=mime_type)
    
    @classmethod
    def from_path(cls, path: Union[str, Path], mime_type: Optional[str] = None) -> "VideoContent":
        """从文件路径创建"""
        return cls(type="path", data=str(path), mime_type=mime_type)


@dataclass
class MessageContent:
    """消息内容，可以是文本、图片或视频"""
    type: Literal["text", "image", "video"]
    text: Optional[str] = None
    image: Optional[ImageContent] = None
    video: Optional[VideoContent] = None
    
    @classmethod
    def from_text(cls, text: str) -> "MessageContent":
        """创建文本内容"""
        return cls(type="text", text=text)
    
    @classmethod
    def from_image(cls, image: ImageContent) -> "MessageContent":
        """创建图片内容"""
        return cls(type="image", image=image)
    
    @classmethod
    def from_video(cls, video: VideoContent) -> "MessageContent":
        """创建视频内容"""
        return cls(type="video", video=video)


@dataclass
class Message:
    """单条消息"""
    role: Literal["user", "assistant", "system"]
    content: List[MessageContent]
    
    @classmethod
    def from_role_and_content(cls, role: Literal["user", "assistant", "system"], content: List[MessageContent]) -> "Message":
        """通过角色和消息内容创建消息"""
        return cls(role=role, content=content)

    @classmethod
    def from_role_and_text(cls, role: Literal["user", "assistant", "system"], text: str) -> "Message":
        """通过角色和单文本创建消息"""
        return cls(role=role, content=[MessageContent.from_text(text)])


@dataclass
class AgentConfig:
    """Agent 配置参数"""
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 1.0
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskInput:
    """
    任务输入容器
    
    session_id: 会话 ID，同一 session 下的多个 task 可以复用 KV cache
    task_id: 任务 ID，唯一标识一个任务
    """
    session_id: str
    task_id: str
    messages: List[Message]
    context: Optional[Dict[str, Any]] = None  # 额外的结构化上下文
    config: Optional[AgentConfig] = None

