# backend/main.py
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from typing import List, Optional
import logging
import os
import shutil
from connection_manager import ConnectionManager # 稍后创建

# 配置日志记录
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# 创建用于存储上传文件的目录
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 挂载静态文件目录，用于访问上传的图片
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

manager = ConnectionManager() # 实例化连接管理器

# --- WebSocket 端点 ---
@app.websocket("/ws/{user_id}/{user_name}")
async def websocket_endpoint(websocket: WebSocket, user_id: str, user_name: str):
    """
    处理 WebSocket 连接、接收消息和广播消息。
    路径参数包含用户 ID 和用户名。
    """
    await manager.connect(websocket, user_id, user_name)
    # 广播用户列表更新
    await manager.broadcast_user_list()
    # 广播用户加入消息 (可选)
    # await manager.broadcast_system_message(f"{user_name} 加入了聊天")

    try:
        while True:
            data = await websocket.receive_json()
            logger.info(f"收到来自 {user_id} ({user_name}) 的消息: {data}")

            message_type = data.get("type")
            content = data.get("content")
            msg_type = data.get("messageType", "TEXT") # 默认文本消息

            if message_type == "message":
                # 构建要广播的消息体
                message_to_broadcast = {
                    "type": "message",
                    "content": content,
                    "messageType": msg_type,
                    "sender": {"id": user_id, "name": user_name},
                    # 可以添加时间戳等元数据
                }
                # 广播消息给所有连接的客户端
                await manager.broadcast(message_to_broadcast)

                # --- AI Agent 触发点 ---
                # TODO: 在这里添加调用 AI Agent 的逻辑
                # ai_response = await trigger_ai_agent(content, user_id, user_name)
                # if ai_response:
                #     await manager.broadcast(ai_response) # 广播 AI 的回复

            else:
                logger.warning(f"收到未知类型的消息: {data}")

    except WebSocketDisconnect:
        logger.info(f"用户 {user_id} ({user_name}) 断开连接")
        manager.disconnect(websocket, user_id)
        # 广播用户列表更新
        await manager.broadcast_user_list()
        # 广播用户离开消息 (可选)
        # await manager.broadcast_system_message(f"{user_name} 离开了聊天")
    except Exception as e:
        logger.error(f"WebSocket 处理出错: {e}", exc_info=True)
        manager.disconnect(websocket, user_id)
        await manager.broadcast_user_list()


# --- HTTP 端点 ---
@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)):
    """
    处理图片上传请求。
    接收图片文件，保存到服务器，并返回图片的访问 URL。
    """
    try:
        # 使用安全的文件名 (例如，可以加上时间戳或 UUID 防止重名)
        safe_filename = f"{user_id}_{os.path.basename(file.filename)}" # 示例，后续可优化
        file_path = os.path.join(UPLOAD_DIR, safe_filename)

        # 保存上传的文件
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 构建图片的访问 URL
        # 注意：这里的 URL 依赖于 FastAPI 应用的运行地址和端口
        # 在实际部署中，可能需要配置 Nginx 或其他反向代理
        file_url = f"/uploads/{safe_filename}" # 相对路径，前端需要拼接基础 URL
        logger.info(f"图片已保存: {file_path}, URL: {file_url}")

        return {"success": True, "url": file_url}
    except Exception as e:
        logger.error(f"图片上传失败: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
    finally:
        # 关闭文件对象
        if hasattr(file, 'file') and not file.file.closed:
            file.file.close()


@app.get("/api/users")
async def get_active_users():
    """
    获取当前在线用户列表。
    """
    return manager.get_active_users_list()


# --- 用于本地开发运行 ---
if __name__ == "__main__":
    # 注意：生产环境应使用 Gunicorn + Uvicorn worker
    # 例如: gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
