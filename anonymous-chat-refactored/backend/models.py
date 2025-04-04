from sqlalchemy import Column, Integer, String, DateTime, Enum as SQLAlchemyEnum
from sqlalchemy.sql import func
from database import Base
import enum

# 使用 Python 的 enum 定义消息类型
class MessageTypeEnum(enum.Enum):
    TEXT = "TEXT"
    IMAGE = "IMAGE"
    SYSTEM = "SYSTEM" # 可以添加系统消息类型

class Message(Base):
    """聊天消息的数据模型"""
    __tablename__ = "messages" # 数据库中的表名

    id = Column(Integer, primary_key=True, index=True) # 自动递增的主键
    sender_id = Column(String, index=True, nullable=False) # 发送者 ID
    sender_name = Column(String, nullable=False) # 发送者昵称 (冗余存储，方便查询)
    content = Column(String, nullable=False) # 消息内容 (文本或图片 URL)
    message_type = Column(SQLAlchemyEnum(MessageTypeEnum), default=MessageTypeEnum.TEXT, nullable=False) # 消息类型
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False) # 消息时间戳 (数据库生成)

    def __repr__(self):
        return f"<Message(id={self.id}, sender='{self.sender_name}', type='{self.message_type.name}')>" 