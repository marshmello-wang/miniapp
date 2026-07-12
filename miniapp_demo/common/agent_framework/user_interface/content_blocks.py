"""
内容块定义 - 定义事件输出中的各种内容类型
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional, Literal
from .inputs import ImageContent, VideoContent


@dataclass
class ContentBlock:
    """内容块基类"""
    type: str  # 内容块类型标识
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {"type": self.type}


@dataclass
class TextBlock(ContentBlock):
    """文本内容块"""
    text: str
    
    def __init__(self, text: str):
        super().__init__(type="text")
        self.text = text
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "text": self.text
        }


@dataclass
class ImageBlock(ContentBlock):
    """图片内容块"""
    image: ImageContent
    caption: Optional[str] = None
    
    def __init__(self, image: ImageContent, caption: Optional[str] = None):
        super().__init__(type="image")
        self.image = image
        self.caption = caption
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "image": {
                "type": self.image.type,
                "data": self.image.data,
                "mime_type": self.image.mime_type
            },
            "caption": self.caption
        }


@dataclass
class VideoBlock(ContentBlock):
    """视频内容块"""
    video: VideoContent
    caption: Optional[str] = None
    
    def __init__(self, video: VideoContent, caption: Optional[str] = None):
        super().__init__(type="video")
        self.video = video
        self.caption = caption
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "video": {
                "type": self.video.type,
                "data": self.video.data,
                "mime_type": self.video.mime_type
            },
            "caption": self.caption
        }


@dataclass
class ToolCallBlock(ContentBlock):
    """工具调用内容块"""
    tool_name: str
    tool_input: Dict[str, Any]
    call_id: Optional[str] = None  # 工具调用的唯一标识
    
    def __init__(self, tool_name: str, tool_input: Dict[str, Any], call_id: Optional[str] = None):
        super().__init__(type="tool_call")
        self.tool_name = tool_name
        self.tool_input = tool_input
        self.call_id = call_id
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "call_id": self.call_id
        }


@dataclass
class ToolResultBlock(ContentBlock):
    """工具执行结果内容块"""
    tool_name: str
    result: Any  # 工具返回结果（完整返回，可能很大）
    call_id: Optional[str] = None
    is_error: bool = False
    error_message: Optional[str] = None
    
    def __init__(
        self,
        tool_name: str,
        result: Any,
        call_id: Optional[str] = None,
        is_error: bool = False,
        error_message: Optional[str] = None
    ):
        super().__init__(type="tool_result")
        self.tool_name = tool_name
        self.result = result
        self.call_id = call_id
        self.is_error = is_error
        self.error_message = error_message
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "tool_name": self.tool_name,
            "result": self.result,
            "call_id": self.call_id,
            "is_error": self.is_error,
            "error_message": self.error_message
        }


@dataclass
class ThinkingBlock(ContentBlock):
    """思考过程内容块"""
    thinking: str
    
    def __init__(self, thinking: str):
        super().__init__(type="thinking")
        self.thinking = thinking
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "thinking": self.thinking
        }


@dataclass
class StructuredDataBlock(ContentBlock):
    """结构化数据内容块（用于传递任意 JSON 可序列化的数据）"""
    data: Dict[str, Any]
    schema_name: Optional[str] = None  # 可选的 schema 标识
    
    def __init__(self, data: Dict[str, Any], schema_name: Optional[str] = None):
        super().__init__(type="structured_data")
        self.data = data
        self.schema_name = schema_name
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "data": self.data,
            "schema_name": self.schema_name
        }

