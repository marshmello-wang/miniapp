"""
工具执行上下文管理
"""
from typing import Dict, Any, Optional


class ToolContext:
    """
    工具执行上下文
    
    仅支持简单的 key-value 存取，用于在工具间共享状态
    
    session_id: 会话 ID，用于沙盒绑定、资源隔离等场景
    """
    
    def __init__(
        self, 
        session_id: Optional[str] = None,
        initial_data: Optional[Dict[str, Any]] = None
    ):
        """
        初始化工具上下文
        
        Args:
            session_id: 会话 ID（可选）
            initial_data: 初始数据（可选）
        """
        self.session_id = session_id
        self._storage: Dict[str, Any] = initial_data or {}

    def set(self, key: str, value: Any) -> None:
        """
        存储数据到上下文
        
        Args:
            key: 键名
            value: 值
        """
        self._storage[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """
        从上下文获取数据
        
        Args:
            key: 键名
            default: 默认值
        
        Returns:
            存储的值或默认值
        """
        return self._storage.get(key, default)

    def update(self, data: Dict[str, Any]) -> None:
        """
        批量更新上下文数据
        
        Args:
            data: 要更新的数据字典
        """
        self._storage.update(data)
    
    def has(self, key: str) -> bool:
        """
        检查键是否存在
        
        Args:
            key: 键名
        
        Returns:
            是否存在
        """
        return key in self._storage
    
    def clear(self) -> None:
        """清空上下文数据"""
        self._storage.clear()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        将上下文转换为字典
        
        Returns:
            包含 session_id 和上下文数据的字典
        """
        result = self._storage.copy()
        if self.session_id:
            result["session_id"] = self.session_id
        return result

