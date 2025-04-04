import os

# --- OpenRouter 配置 ---
# 警告：直接在代码中写入 API Key 是不安全的。建议使用环境变量。
# API_KEY = os.getenv("OPENROUTER_API_KEY", "YOUR_OPENROUTER_API_KEY")
API_KEY = "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" # 请替换为你自己的 Key
BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

# --- AI Agent 配置 ---
# 结构类似你的参考代码，但 agent_id 用作 key
AGENTS = {
    "agent_fatty_li": {
        "agent_id": "agent_fatty_li", # 唯一的 Agent ID，用于数据库和内部识别
        "name": "李胖子 (AI)", # Agent 在聊天室显示的昵称
        "model": "deepseek/deepseek-chat-v3-0324", # 注意：模型 ID 可能需要根据 OpenRouter 更新
        "description": "一个体重超过200斤的胖子，非常焦虑自己的体重问题，急切想减肥。说话风格比较着急，常常抱怨自己的体重带来的各种不便，如走路气喘、买不到合适的衣服等。",
        "talk_interval_range": (60, 600), # 发言时间间隔范围 (秒), 即 1-10 分钟
        "context_message_count": 30, # 读取的上下文消息数量
        "avatar_url": "/path/to/fatty_li_avatar.png" # 可选：为 Agent 指定头像 URL
    },
    "agent_doctor_wang": {
        "agent_id": "agent_doctor_wang",
        "name": "王医生 (AI)",
        "model": "openai/gpt-4o-2024-11-20", # 使用新模型ID
        "description": "一位冷静专业的医生，专攻健康饮食和生活方式指导。说话有条理，语气平和但坚定，总是提供基于科学的减肥建议，强调健康饮食和适当运动的重要性。喜欢用医学术语但会解释给普通人听。",
        "talk_interval_range": (90, 700), # 1.5 - 11.6 分钟
        "context_message_count": 30,
        "avatar_url": "/path/to/doctor_wang_avatar.png"
    },
    "agent_professor_zhang": {
        "agent_id": "agent_professor_zhang",
        "name": "张教授 (AI)",
        "model": "google/gemini-2.0-flash-001", # 使用新模型ID
        "description": "一位持不同价值观的人，认为人不必刻意追求瘦，只要健康就好。说话风格幽默风趣，经常用反问句，偶尔有点犀利但不至于冒犯。喜欢引用研究数据和社会现象来支持自己的观点。",
        "talk_interval_range": (80, 500), # 1.3 - 8.3 分钟
        "context_message_count": 30,
        "avatar_url": "/path/to/professor_zhang_avatar.png"
    }
}

# --- 日志配置 (如果需要更详细的日志) ---
# import logging
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__) 