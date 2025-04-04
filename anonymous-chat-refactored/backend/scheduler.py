import asyncio
import random
import logging
from agent_manager import AgentManager
import config

logger = logging.getLogger(__name__)

class AgentScheduler:
    def __init__(self, agent_manager: AgentManager):
        self.agent_manager = agent_manager
        self.tasks = {} # 用于存储每个 agent 的后台任务

    async def _agent_loop(self, agent_id: str):
        """单个 Agent 的后台循环任务"""
        agent_config = config.AGENTS.get(agent_id)
        if not agent_config:
            logger.error(f"无法启动 Agent 循环：未找到配置 {agent_id}")
            return

        min_interval, max_interval = agent_config['talk_interval_range']
        logger.info(f"启动 Agent {agent_id} ({agent_config['name']}) 的发言循环，间隔 {min_interval}-{max_interval} 秒")

        while True:
            try:
                # 随机等待时间
                wait_time = random.uniform(min_interval, max_interval)
                logger.debug(f"Agent {agent_id} 下次发言将在 {wait_time:.1f} 秒后")
                await asyncio.sleep(wait_time)

                # 执行发言逻辑
                await self.agent_manager.agent_speak(agent_id)

            except asyncio.CancelledError:
                logger.info(f"Agent {agent_id} 的发言循环被取消。")
                break # 退出循环
            except Exception as e:
                # 记录错误并继续循环，防止一个 Agent 错误导致所有任务停止
                logger.error(f"Agent {agent_id} 循环出错: {e}", exc_info=True)
                # 可以增加错误后的等待时间，避免频繁出错
                await asyncio.sleep(60) # 例如，出错后等待 60 秒

    def start_all_agents(self):
        """为所有配置的 Agent 启动后台任务"""
        logger.info("正在启动所有 AI Agent 的后台发言任务...")
        for agent_id in config.AGENTS.keys():
            if agent_id not in self.tasks or self.tasks[agent_id].done():
                logger.info(f"为 Agent {agent_id} 创建新的发言任务。")
                # 创建并存储任务
                task = asyncio.create_task(self._agent_loop(agent_id))
                self.tasks[agent_id] = task
            else:
                 logger.info(f"Agent {agent_id} 的任务已在运行。")

        logger.info(f"已启动 {len(self.tasks)} 个 Agent 任务。")

    async def stop_all_agents(self):
        """优雅地停止所有 Agent 任务"""
        logger.info("正在停止所有 AI Agent 的后台任务...")
        tasks_to_wait = []
        for agent_id, task in self.tasks.items():
            if task and not task.done():
                task.cancel() # 发送取消请求
                tasks_to_wait.append(task)
                logger.info(f"已发送取消请求给 Agent {agent_id} 的任务。")

        if tasks_to_wait:
            # 等待任务实际完成 (或抛出 CancelledError)
            await asyncio.gather(*tasks_to_wait, return_exceptions=True)
            logger.info("所有 Agent 任务已停止。")
        else:
            logger.info("没有正在运行的 Agent 任务需要停止。")
        self.tasks.clear() # 清空任务字典 