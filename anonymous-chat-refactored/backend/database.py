from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# 定义 SQLite 数据库文件路径
# 将数据库文件放在项目根目录下的 backend 文件夹中
DATABASE_FILE = "chat.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///./{DATABASE_FILE}"
# 如果你想放在 backend 的上一级目录:
# SQLALCHEMY_DATABASE_URL = f"sqlite:///../{DATABASE_FILE}"

# 创建 SQLAlchemy 引擎
# connect_args={"check_same_thread": False} 是 SQLite 特有的配置，
# 因为 FastAPI 默认在多线程中运行，而 SQLite 默认只允许创建它的线程访问它。
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# 创建数据库会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建一个 Base 类，我们的 ORM 模型将继承这个类
Base = declarative_base()

# --- 数据库初始化函数 ---
def init_db():
    # 在这里导入所有定义模型的模块，这样它们就会被正确的注册到 Base 上
    # 否则，SQLAlchemy 可能不知道这些表的存在
    import models # 确保 models.py 被导入
    logger.info("正在创建数据库表...")
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("数据库表创建成功 (如果尚不存在)。")
    except Exception as e:
        logger.error(f"创建数据库表失败: {e}", exc_info=True)

# --- 获取数据库会话的依赖项 ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 添加日志记录器 (可选，但推荐)
import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO) # 确保日志被输出 