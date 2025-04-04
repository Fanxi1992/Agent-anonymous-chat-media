# backend/connection_manager.py
from fastapi import WebSocket
from typing import List, Dict, Tuple, Any
import logging
import json

logger = logging.getLogger(__name__)

class ConnectionManager:
    """管理 WebSocket 连接、用户和消息广播"""
    def __init__(self):
        # 存储活跃的连接，键是 user_id，值是包含 WebSocket 连接和用户名的元组
        self.active_connections: Dict[str, Tuple[WebSocket, str]] = {}

    async def connect(self, websocket: WebSocket, user_id: str, user_name: str):
        """接受新的 WebSocket 连接并存储"""
        await websocket.accept()
        self.active_connections[user_id] = (websocket, user_name)
        logger.info(f"用户 {user_id} ({user_name}) 连接成功. 当前在线: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket, user_id: str):
        """断开指定用户的 WebSocket 连接"""
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            logger.info(f"用户 {user_id} 连接已移除. 当前在线: {len(self.active_connections)}")
        # 注意: FastAPI 的 WebSocket 对象不需要显式 close()

    def get_user_name(self, user_id: str) -> str | None:
        """根据 user_id 获取用户名"""
        conn_info = self.active_connections.get(user_id)
        return conn_info[1] if conn_info else None

    def get_active_users_list(self) -> List[Dict[str, str]]:
        """获取当前所有在线用户的列表 [{id: 'xxx', name: 'yyy'}, ...]"""
        return [{"id": uid, "name": info[1]} for uid, info in self.active_connections.items()]

    async def broadcast(self, message: Dict[str, Any]):
        """将 JSON 消息广播给所有连接的客户端"""
        message_json = json.dumps(message) # 序列化一次即可
        disconnected_users = []
        active_users = list(self.active_connections.items()) # 创建副本以允许在迭代时修改字典

        for user_id, (websocket, user_name) in active_users:
            try:
                await websocket.send_text(message_json)
                logger.debug(f"消息已发送给 {user_id} ({user_name})")
            except Exception as e:
                # 发送失败，可能连接已断开
                logger.warning(f"发送消息给 {user_id} ({user_name}) 失败: {e}. 标记为断开连接.")
                disconnected_users.append(user_id)

        # 清理广播时发现已断开的连接
        for user_id in disconnected_users:
            if user_id in self.active_connections: # 再次检查，防止并发问题
                 del self.active_connections[user_id]
                 logger.info(f"在广播期间清理了断开的连接: {user_id}")
                 # 可选：在这里也广播用户离开消息
                 # await self.broadcast_system_message(f"{self.get_user_name(user_id) or user_id} 离开了聊天")
                 await self.broadcast_user_list() # 需要更新用户列表


    async def broadcast_user_list(self):
        """广播当前在线用户列表"""
        user_list_message = {
            "type": "user_list_update",
            "users": self.get_active_users_list()
        }
        await self.broadcast(user_list_message)
        logger.info("已广播用户列表更新")

    async def broadcast_system_message(self, content: str):
        """广播系统消息"""
        system_message = {
            "type": "system",
            "content": content
        }
        await self.broadcast(system_message)
        logger.info(f"已广播系统消息: {content}")

    async def send_personal_message(self, message: Dict[str, Any], user_id: str):
        """向特定用户发送消息"""
        conn_info = self.active_connections.get(user_id)
        if conn_info:
            websocket, user_name = conn_info
            try:
                await websocket.send_json(message)
                logger.info(f"私信已发送给 {user_id} ({user_name})")
                return True
            except Exception as e:
                logger.warning(f"发送私信给 {user_id} ({user_name}) 失败: {e}")
                # 可以考虑在这里处理断开连接
                self.disconnect(websocket, user_id)
                await self.broadcast_user_list()
                return False
        else:
            logger.warning(f"尝试向不存在或已断开的用户 {user_id} 发送私信")
            return False
