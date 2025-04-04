import httpx
import logging
import random
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from database import SessionLocal # 直接导入 SessionLocal
from models import Message as MessageModel, MessageTypeEnum
from connection_manager import ConnectionManager # 需要 manager 来广播
import config # 导入配置

logger = logging.getLogger(__name__)

class AgentManager:
    def __init__(self, connection_manager: ConnectionManager):
        self.agents = config.AGENTS
        self.api_key = config.API_KEY
        self.base_url = config.BASE_URL
        self.connection_manager = connection_manager # 保存 ConnectionManager 实例
        self.http_client = httpx.AsyncClient(timeout=60.0) # 创建异步 HTTP 客户端，设置超时

    def get_db_session(self) -> Session:
        """为后台任务创建独立的数据库会话"""
        return SessionLocal()

    async def _get_chat_history(self, db: Session, count: int) -> list[MessageModel]:
        """从数据库获取最近的聊天记录"""
        try:
            history = db.query(MessageModel).order_by(MessageModel.timestamp.desc()).limit(count).all()
            return history[::-1] # 返回按时间正序排列
        except Exception as e:
            logger.error(f"获取聊天记录失败: {e}", exc_info=True)
            return []
        finally:
            db.close() # 确保会话关闭

    def _format_history_for_prompt(self, history: list[MessageModel], agent_id: str) -> list[dict]:
        """将数据库消息格式化为 API 需要的格式"""
        formatted_messages = []
        agent_config = self.agents.get(agent_id)
        if not agent_config:
            return []

        for msg in history:
            role = "assistant" if msg.sender_id == agent_id else "user"
            # 对于 user 角色，我们通常需要显示是谁说的
            sender_name = msg.sender_name
            # 如果消息是来自其他 AI Agent，也明确标出
            if msg.sender_id.startswith('agent_') and msg.sender_id != agent_id:
                 other_agent_conf = self.agents.get(msg.sender_id)
                 if other_agent_conf:
                     sender_name = other_agent_conf['name'] # 使用配置中的名字

            formatted_messages.append({
                "role": role,
                "content": f"{sender_name}: {msg.content}" if role == 'user' else msg.content
            })
        return formatted_messages

    def _get_system_prompt(self, agent_id: str) -> str:
        """为指定 Agent 生成系统提示"""
        agent_config = self.agents.get(agent_id)
        if not agent_config:
            return "你是一个通用的聊天助手。"

        # 构建其他参与者的描述
        other_participants_desc = []
        for other_id, other_conf in self.agents.items():
            if other_id != agent_id:
                other_participants_desc.append(f"- {other_conf['name']}: {other_conf['description']}")
        # 也可以加入对普通用户的描述，如果需要的话
        # other_participants_desc.append("- 其他真实用户: 身份随机")

        participants_str = "\n".join(other_participants_desc)
        if not participants_str:
            participants_str = "(当前只有你一个 AI Agent)"

        return f"""你是一个名叫 {agent_config['name']} 的真实人物，正在一个关于"健康生活与减肥"的群聊中（也可能有其他话题）。

你的人物设定：{agent_config['description']}

请根据上面的人物设定和当前的聊天记录，以自然、真实的方式参与讨论。你的回复应该：
1. 始终保持角色一致性，不要跳出角色。
2. 不要过于机械或官方，要像真人聊天一样自然，可以使用表情符号、口头禅或口语化表达。
3. 回复长度适中，不要太长或太短。
4. 回应最近几条消息，或者基于整体聊天氛围发表看法。
5. 偶尔可以提问、表达情绪或适当转换话题，但尽量保持对话的连贯性。
6. 绝对不要提及或暗示你是AI、语言模型或程序。
7. 你不是群主或管理员，只是一个普通的参与者。

你正在和以下人物（可能还包括其他真实用户）聊天：
{participants_str}

请基于当前的聊天历史，给出一个自然、符合你角色的回复。直接输出你的发言内容，不要带任何前缀如 '{agent_config['name']}:'。"""

    async def _call_model_api(self, agent_id: str, history: list[dict]) -> str | None:
        """调用 OpenRouter API 获取模型回复"""
        agent_config = self.agents.get(agent_id)
        if not agent_config or not self.api_key:
            logger.error(f"Agent 配置或 API Key 丢失: {agent_id}")
            return None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        messages = [
            {"role": "system", "content": self._get_system_prompt(agent_id)},
            *history # 将格式化后的历史记录解包传入
        ]

        # 如果历史为空，可能需要引导性发言
        if not history:
             messages.append({"role": "user", "content": "群里好像没人说话，你先根据你的角色设定，围绕健康生活或减肥随便说点什么吧。"})


        data = {
            "model": agent_config["model"],
            "messages": messages,
            "temperature": 0.8, # 增加随机性
            "max_tokens": 200 # 限制回复长度
        }

        try:
            logger.info(f"Agent {agent_id} 正在调用模型 {agent_config['model']}...")
            response = await self.http_client.post(self.base_url, headers=headers, json=data)
            response.raise_for_status() # 检查 HTTP 错误
            result = response.json()
            message = result["choices"][0]["message"]["content"].strip()

            # 后处理：移除可能由模型错误添加的前缀
            possible_prefix = f"{agent_config['name']}:"
            if message.startswith(possible_prefix):
                message = message[len(possible_prefix):].strip()

            logger.info(f"Agent {agent_id} 收到模型回复: {message[:50]}...")
            return message
        except httpx.RequestError as e:
            logger.error(f"调用 OpenRouter API 网络错误 for {agent_id}: {e}")
        except httpx.HTTPStatusError as e:
            logger.error(f"调用 OpenRouter API HTTP 错误 for {agent_id}: {e.response.status_code} - {e.response.text}")
        except (KeyError, IndexError, TypeError) as e:
             logger.error(f"解析 OpenRouter API 响应错误 for {agent_id}: {e} - 响应: {result if 'result' in locals() else 'N/A'}")
        except Exception as e:
            logger.error(f"调用 OpenRouter API 未知错误 for {agent_id}: {e}", exc_info=True)
        return None

    async def agent_speak(self, agent_id: str):
        """核心函数：让指定的 Agent 发言"""
        agent_config = self.agents.get(agent_id)
        if not agent_config:
            logger.warning(f"尝试让不存在的 Agent 发言: {agent_id}")
            return

        logger.info(f"轮到 Agent {agent_id} ({agent_config['name']}) 发言...")
        db = self.get_db_session() # 获取独立会话
        history_models = await self._get_chat_history(db, agent_config["context_message_count"])
        formatted_history = self._format_history_for_prompt(history_models, agent_id)

        ai_response_content = await self._call_model_api(agent_id, formatted_history)

        if ai_response_content:
            logger.info(f"Agent {agent_id} 准备发送消息: {ai_response_content[:50]}...")
            # --- 存储 Agent 消息到数据库 ---
            db_message = MessageModel(
                sender_id=agent_config["agent_id"],
                sender_name=agent_config["name"],
                content=ai_response_content,
                message_type=MessageTypeEnum.TEXT # Agent 只发文本消息
                # timestamp 由数据库自动生成
            )
            try:
                db.add(db_message)
                db.commit()
                db.refresh(db_message)
                logger.info(f"Agent {agent_id} 的消息已存入数据库: ID={db_message.id}")

                # --- 广播 Agent 消息 ---
                message_to_broadcast = {
                    "type": "message",
                    "content": db_message.content,
                    "messageType": db_message.message_type.name,
                    "sender": {"id": db_message.sender_id, "name": db_message.sender_name},
                    "timestamp": db_message.timestamp.isoformat() + "Z"
                }
                await self.connection_manager.broadcast(message_to_broadcast)
                logger.info(f"Agent {agent_id} 的消息已广播.")

            except Exception as e:
                db.rollback()
                logger.error(f"存储或广播 Agent {agent_id} 的消息失败: {e}", exc_info=True)
            finally:
                db.close() # 确保会话关闭
        else:
            logger.warning(f"Agent {agent_id} 未能生成有效回复。")
            db.close() # 即使没有回复也要关闭会话 