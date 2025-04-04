# backend/main.py
import uvicorn
import asyncio # 导入 asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Depends, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware # 导入 CORS 中间件
from typing import List, Optional, Union
import logging
import os
import shutil
import uuid # 导入 uuid 库
from connection_manager import ConnectionManager # 稍后创建
from sqlalchemy.orm import Session # 导入 Session
from database import init_db, get_db # 导入数据库相关函数
from models import Message as MessageModel, MessageTypeEnum # 导入模型和枚举
from datetime import datetime # 导入 datetime
# --- Agent 相关导入 ---
import config # 导入配置，虽然不直接用，但 agent_manager 和 scheduler 会用
from agent_manager import AgentManager
from scheduler import AgentScheduler
from sqlalchemy import desc # 导入 desc

# 配置日志记录
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 全局变量 (用于在启动和关闭事件中访问) ---
connection_manager: ConnectionManager | None = None
agent_manager: AgentManager | None = None
agent_scheduler: AgentScheduler | None = None

# --- 应用启动事件 ---
@app.on_event("startup")
async def on_startup(): # 改为 async
    global connection_manager, agent_manager, agent_scheduler
    logger.info("应用程序启动...")

    # 1. 初始化数据库
    logger.info("开始初始化数据库...")
    init_db()
    logger.info("数据库初始化完成。")

    # 2. 初始化 ConnectionManager
    connection_manager = ConnectionManager()
    logger.info("ConnectionManager 初始化完成。")

    # 3. 初始化 AgentManager (需要 ConnectionManager)
    agent_manager = AgentManager(connection_manager)
    logger.info("AgentManager 初始化完成。")

    # 4. 初始化并启动 AgentScheduler (需要 AgentManager)
    agent_scheduler = AgentScheduler(agent_manager)
    agent_scheduler.start_all_agents()
    logger.info("AgentScheduler 初始化并启动完成。")

app = FastAPI()

# --- CORS 配置 ---
# 定义允许的前端来源 (根据你的前端开发服务器地址修改)
origins = [
    "http://localhost:5173", # Vite 默认端口
    "http://127.0.0.1:5173",
    "http://localhost:3000", # Create React App 默认端口
    "http://127.0.0.1:3000",
    # 如果你有其他前端访问地址，也需要加在这里
    # "http://your-frontend-domain.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, # 允许指定的来源
    allow_credentials=True, # 允许携带 cookie
    allow_methods=["*"], # 允许所有 HTTP 方法 (GET, POST, etc.)
    allow_headers=["*"], # 允许所有请求头
)


# 创建用于存储上传文件的目录
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 挂载静态文件目录，用于访问上传的图片
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# manager = ConnectionManager() # 不再在这里实例化，改为在 startup 事件中实例化并赋值给全局变量

# --- WebSocket 端点 --- (修改以使用全局 connection_manager)
@app.websocket("/ws/{user_id}/{user_name}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    user_name: str,
    db: Session = Depends(get_db)
):
    """
    处理 WebSocket 连接、接收消息、存储消息到数据库和广播消息。
    使用全局的 connection_manager。
    """
    if not connection_manager:
        logger.error("ConnectionManager 尚未初始化!")
        await websocket.close(code=1011) # 内部服务器错误
        return

    await connection_manager.connect(websocket, user_id, user_name)
    await connection_manager.broadcast_user_list()

    # --- 不再在此处发送历史消息，改为通过 API 获取 ---

    try:
        while True:
            data = await websocket.receive_json()
            logger.info(f"收到来自 {user_id} ({user_name}) 的消息: {data}")

            message_type = data.get("type")
            content = data.get("content")
            msg_type_str = data.get("messageType", "TEXT").upper() # 获取并转大写

            # 将字符串类型转换为枚举类型
            try:
                msg_type_enum = MessageTypeEnum[msg_type_str]
            except KeyError:
                logger.warning(f"收到无效的消息类型 '{msg_type_str}' 来自 {user_id}，默认为 TEXT")
                msg_type_enum = MessageTypeEnum.TEXT

            if message_type == "message":

                # --- 1. 存储消息到数据库 ---
                db_message = MessageModel(
                    sender_id=user_id,
                    sender_name=user_name,
                    content=content,
                    message_type=msg_type_enum
                    # timestamp 由数据库自动生成
                )
                try:
                    db.add(db_message)
                    db.commit()
                    db.refresh(db_message) # 获取数据库生成的数据，如 id 和 timestamp
                    logger.info(f"消息已存入数据库: ID={db_message.id}")
                except Exception as e:
                    db.rollback() # 如果存储失败，回滚事务
                    logger.error(f"存储消息到数据库失败 for {user_id}: {e}", exc_info=True)
                    # 可以考虑通知发送者存储失败
                    # await websocket.send_json({"type": "error", "message": "消息存储失败"})
                    continue # 跳过广播等后续步骤


                # --- 2. 构建要广播的消息体 (包含数据库生成的时间戳) ---
                message_to_broadcast = {
                    "type": "message",
                    "content": db_message.content,
                    "messageType": db_message.message_type.name,
                    "sender": {"id": db_message.sender_id, "name": db_message.sender_name},
                    "timestamp": db_message.timestamp.isoformat() + "Z" # 添加 ISO 格式的时间戳
                }

                # --- 3. 广播消息给所有连接的客户端 --- (使用全局 manager)
                await connection_manager.broadcast(message_to_broadcast)

                # --- 4. AI Agent 触发点 --- (这里的 TODO 可以移除了，因为 Agent 是后台任务)
                # (不再需要在这里显式触发 AI)

            else:
                logger.warning(f"收到非 'message' 类型的消息: {data}")

    except WebSocketDisconnect:
        logger.info(f"用户 {user_id} ({user_name}) 断开连接")
        if connection_manager:
            connection_manager.disconnect(websocket, user_id)
            await connection_manager.broadcast_user_list()
        # user_name_disconnected = connection_manager.get_user_name(user_id) or "未知用户"
        # await connection_manager.broadcast_system_message(f"{user_name_disconnected} 离开了聊天")
    except Exception as e:
        logger.error(f"WebSocket 处理出错 for {user_id}: {e}", exc_info=True)
        if connection_manager:
            connection_manager.disconnect(websocket, user_id)
            await connection_manager.broadcast_user_list()
    finally:
        # 确保数据库会话在端点结束时关闭 (get_db 依赖项会自动处理)
        pass


# --- HTTP 端点 ---
@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...), user_id: str = Form(...)):
    """
    处理图片上传请求。
    接收图片文件和用户 ID (来自表单)，保存到服务器，并返回图片的访问 URL。
    使用 UUID 生成唯一文件名。
    """
    try:
        # 从原始文件名中获取扩展名
        original_filename = file.filename or ""
        file_extension = os.path.splitext(original_filename)[1]
        # 基本的文件类型验证 (可选，但推荐)
        allowed_extensions = {".jpg", ".jpeg", ".png", ".gif"}
        if file_extension.lower() not in allowed_extensions:
            logger.warning(f"用户 {user_id} 上传了不支持的文件类型: {original_filename}")
            return {"success": False, "error": f"不支持的文件类型: {file_extension}"}

        # 生成唯一的 UUID 文件名，保留原始扩展名
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(UPLOAD_DIR, unique_filename)

        # 保存上传的文件
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 构建图片的访问 URL (相对路径)
        file_url = f"/uploads/{unique_filename}"
        logger.info(f"用户 {user_id} 成功上传图片: {original_filename} -> {unique_filename}, URL: {file_url}")

        return {"success": True, "url": file_url}
    except Exception as e:
        logger.error(f"用户 {user_id} 图片上传失败: {e}", exc_info=True)
        return {"success": False, "error": f"服务器内部错误: {str(e)}"}
    finally:
        # 确保文件对象被关闭
        if hasattr(file, 'file') and not file.file.closed:
            await file.close() # 对于 UploadFile，使用 await file.close()


@app.get("/api/users")
async def get_active_users():
    """
    获取当前在线用户列表。
    """
    if not connection_manager:
        return [] # 或者返回错误
    return connection_manager.get_active_users_list()


# --- 应用关闭事件 ---
@app.on_event("shutdown")
async def on_shutdown():
    global agent_scheduler
    logger.info("应用程序关闭...")
    if agent_scheduler:
        await agent_scheduler.stop_all_agents()
        logger.info("Agent 任务已停止。")
    # 清理 HTTP 客户端 (如果 AgentManager 中有)
    if agent_manager and hasattr(agent_manager, 'http_client'):
        await agent_manager.http_client.aclose()
        logger.info("HTTP 客户端已关闭。")


# --- 新增：获取历史消息 API --- (时间戳分页)
@app.get("/api/messages", response_model=List[dict]) # 定义响应模型
async def get_history_messages(
    before_timestamp: Optional[str] = Query(None, description="ISO 格式的时间戳，用于获取此时间之前的消息"),
    limit: int = Query(30, gt=0, le=100, description="每次加载的消息数量"), # 限制每次最多100条
    db: Session = Depends(get_db)
):
    """
    获取历史聊天记录，支持基于时间戳的分页。
    返回按时间升序排列的消息列表。
    """
    query = db.query(MessageModel)

    if before_timestamp:
        try:
            # 将 ISO 格式字符串解析为带时区的 datetime 对象
            before_dt = datetime.fromisoformat(before_timestamp.replace('Z', '+00:00'))
            # 查询时间戳早于指定时间的消息
            query = query.filter(MessageModel.timestamp < before_dt)
        except ValueError:
            logger.warning(f"无效的时间戳格式: {before_timestamp}")
            # 可以选择返回错误或忽略此参数
            return [] # 返回空列表

    # 按时间戳降序排序，获取最近的 N 条
    history_messages_desc = query.order_by(desc(MessageModel.timestamp)).limit(limit).all()

    # 将结果转换为字典列表，并按时间升序返回给前端
    results = []
    for msg in reversed(history_messages_desc): # 反转列表以获得升序
        results.append({
            "type": "message", # 保持和 WebSocket 消息一致的结构
            "content": msg.content,
            "messageType": msg.message_type.name,
            "sender": {"id": msg.sender_id, "name": msg.sender_name},
            "timestamp": msg.timestamp.isoformat() + "Z" # 使用 ISO 格式
        })
    logger.info(f"返回 {len(results)} 条历史消息 (limit={limit}, before={before_timestamp})")
    return results


# --- 用于本地开发运行 ---
if __name__ == "__main__":
    # 注意：生产环境应使用 Gunicorn + Uvicorn worker
    # 例如: gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) # 添加 reload=True 以便开发时自动重启
