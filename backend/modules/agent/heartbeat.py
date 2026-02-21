"""Heartbeat 主动问候系统"""

import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from loguru import logger

# 北京时区 UTC+8
SHANGHAI_TZ = timezone(timedelta(hours=8))

# 内置 heartbeat cron job 的固定 ID（用于去重，避免重复创建）
HEARTBEAT_JOB_ID = "builtin:heartbeat"
HEARTBEAT_JOB_NAME = "系统问候（内置）"
HEARTBEAT_SCHEDULE = "0 * * * *"  # 每小时整点检查
HEARTBEAT_MESSAGE = "__heartbeat__"  # 特殊标记，executor 识别后交给 HeartbeatService

# 默认配置
DEFAULT_IDLE_THRESHOLD_HOURS = 4
DEFAULT_ACTIVE_START = 8   # 北京时间
DEFAULT_ACTIVE_END = 22    # 北京时间
DEFAULT_GREET_PROBABILITY = 0.5
DEFAULT_MAX_GREETS_PER_DAY = 2  # 每天最多问候次数



class HeartbeatService:
    """主动问候服务 - 由 cron executor 调用，只负责生成问候语"""

    def __init__(
        self,
        provider,
        model: str,
        workspace: Path,
        db_session_factory,
        ai_name: str = "小C",
        user_name: str = "主人",
        user_address: str = "",
        personality: str = "professional",
        custom_personality: str = "",
        idle_threshold_hours: int = DEFAULT_IDLE_THRESHOLD_HOURS,
        quiet_start: int = 21,
        quiet_end: int = 8,
        max_greets_per_day: int = DEFAULT_MAX_GREETS_PER_DAY,
    ):
        self.provider = provider
        self.model = model
        self.workspace = workspace
        self.db_session_factory = db_session_factory
        self.ai_name = ai_name
        self.user_name = user_name
        self.user_address = user_address
        self.personality = personality
        self.custom_personality = custom_personality
        self.idle_threshold_hours = idle_threshold_hours
        self.quiet_start = quiet_start
        self.quiet_end = quiet_end
        self.max_greets_per_day = max_greets_per_day
        self._greet_count_today: dict[str, int] = {}  # {"YYYY-MM-DD": count}

        logger.debug(
            f"HeartbeatService initialized: idle>{idle_threshold_hours}h, "
            f"quiet {quiet_start}:00-{quiet_end}:00 Asia/Beijing, "
            f"max {max_greets_per_day} greets/day"
        )

    @staticmethod
    def _now_shanghai() -> datetime:
        """获取当前北京时间"""
        return datetime.now(SHANGHAI_TZ)

    def _is_quiet_hour(self, hour: int) -> bool:
        """判断当前小时是否在免打扰时段内
        
        支持跨午夜的时段，比如 quiet_start=22, quiet_end=8 表示 22:00-08:00 免打扰。
        """
        if self.quiet_start <= self.quiet_end:
            # 不跨午夜：比如 1:00-6:00
            return self.quiet_start <= hour < self.quiet_end
        else:
            # 跨午夜：比如 22:00-8:00
            return hour >= self.quiet_start or hour < self.quiet_end

    async def execute(self) -> str:
        """cron executor 调用入口。返回问候语或空字符串。

        流程：
        1. 时间窗口检查（北京时间免打扰时段）
        2. 今日已发检查
        3. 用户空闲检查（>= idle_threshold_hours）
        4. 随机概率（让时间分布自然）
        5. LLM 生成问候
        6. 返回问候语，由 CronExecutor 负责渠道投递
        """
        now = self._now_shanghai()

        # 1. 免打扰时段检查
        if self._is_quiet_hour(now.hour):
            logger.debug(f"Heartbeat skipped: {now.hour}:00 is in quiet hours ({self.quiet_start}:00-{self.quiet_end}:00 Beijing)")
            return ""

        # 2. 今日已达上限
        today = now.strftime("%Y-%m-%d")
        greet_count = self._greet_count_today.get(today, 0)
        if greet_count >= self.max_greets_per_day:
            logger.debug(f"Heartbeat skipped: already greeted {greet_count} times today (max: {self.max_greets_per_day})")
            return ""

        # 3. 空闲检测
        idle_hours = await self._get_user_idle_hours()
        if idle_hours is None or idle_hours < self.idle_threshold_hours:
            logger.debug(f"Heartbeat skipped: idle {idle_hours}h < threshold {self.idle_threshold_hours}h")
            return ""

        # 4. 随机概率
        if random.random() > DEFAULT_GREET_PROBABILITY:
            logger.debug("Heartbeat skipped: random probability")
            return ""

        # 5. 生成问候
        logger.info(f"Heartbeat triggered: idle {idle_hours:.1f}h, Beijing time {now.strftime('%H:%M')}, greet #{greet_count + 1}")
        greeting = await self._generate_greeting(now, idle_hours)
        if not greeting:
            return ""

        # 更新今日问候计数
        self._greet_count_today[today] = greet_count + 1
        # 清理旧日期的计数（保留最近3天）
        if len(self._greet_count_today) > 3:
            old_dates = sorted(self._greet_count_today.keys())[:-3]
            for old_date in old_dates:
                del self._greet_count_today[old_date]
        
        logger.info(f"Heartbeat greeting generated (#{greet_count + 1}/{self.max_greets_per_day}): {greeting[:60]}")
        return greeting

    async def _get_user_idle_hours(self) -> Optional[float]:
        """查询所有会话中用户最近一条消息的时间，计算空闲时长"""
        from sqlalchemy import select, func
        from backend.models.message import Message

        try:
            async with self.db_session_factory() as db:
                result = await db.execute(
                    select(func.max(Message.created_at)).where(Message.role == "user")
                )
                last_msg_time = result.scalar()
                if last_msg_time is None:
                    return None

                now_utc = datetime.now(timezone.utc)
                if last_msg_time.tzinfo is None:
                    last_msg_time = last_msg_time.replace(tzinfo=timezone.utc)

                return (now_utc - last_msg_time).total_seconds() / 3600
        except Exception as e:
            logger.error(f"Failed to get user idle hours: {e}")
            return None

    async def _generate_greeting(self, now: datetime, idle_hours: float) -> str:
        """用 LLM 生成问候语"""
        from backend.modules.agent.prompts import HEARTBEAT_GREETING_PROMPT
        from backend.modules.agent.personalities import get_personality_prompt

        hour = now.hour
        if hour < 12:
            time_desc = f"上午{hour}点"
        elif hour < 14:
            time_desc = f"中午{hour}点"
        elif hour < 18:
            time_desc = f"下午{hour}点"
        else:
            time_desc = f"晚上{hour}点"

        # 尝试读取最近记忆作为上下文
        memory_context = ""
        try:
            memory = MemoryStore(self.workspace / "memory")
            recent = memory.get_recent(5)
            if recent and "记忆为空" not in recent:
                memory_context = f"最近的记忆（可参考但不必提及）:\n{recent}"
        except Exception:
            pass

        # 获取性格描述
        personality_desc = get_personality_prompt(
            self.personality, 
            self.custom_personality
        )

        # 用户信息上下文
        user_context = f"用户称呼: {self.user_name}"
        if self.user_address:
            user_context += f"\n用户地址: {self.user_address}"

        prompt = HEARTBEAT_GREETING_PROMPT.format(
            ai_name=self.ai_name,
            user_name=self.user_name,
            time_desc=time_desc,
            idle_hours=f"{idle_hours:.0f}",
            personality_desc=personality_desc,
            user_context=user_context,
            memory_context=memory_context,
        )

        try:
            parts = []
            async for chunk in self.provider.chat_stream(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.8,
            ):
                if chunk.is_content and chunk.content:
                    parts.append(chunk.content)
            greeting = "".join(parts).strip()
            # 过滤掉空结果或异常长结果
            if not greeting or len(greeting) > 200:
                return ""
            return greeting
        except Exception as e:
            logger.error(f"Failed to generate greeting: {e}")
            return ""



# ============================================================================
# Cron 集成辅助函数
# ============================================================================

from backend.modules.agent.memory import MemoryStore


async def ensure_heartbeat_job(db_session_factory, heartbeat_config=None):
    """确保内置 heartbeat cron job 存在并与配置同步（app 启动时调用）"""
    from sqlalchemy import select
    from backend.models.cron_job import CronJob

    try:
        async with db_session_factory() as db:
            result = await db.execute(
                select(CronJob).where(CronJob.id == HEARTBEAT_JOB_ID)
            )
            existing = result.scalar_one_or_none()

            # 从配置中读取参数
            enabled = heartbeat_config.enabled if heartbeat_config else False
            channel = heartbeat_config.channel if heartbeat_config and heartbeat_config.channel else None
            chat_id = heartbeat_config.chat_id if heartbeat_config and heartbeat_config.chat_id else None
            schedule = heartbeat_config.schedule if heartbeat_config and heartbeat_config.schedule else HEARTBEAT_SCHEDULE

            if existing:
                # 同步配置到已有 job
                changed = False
                if existing.enabled != enabled:
                    existing.enabled = enabled
                    changed = True
                if existing.channel != channel:
                    existing.channel = channel
                    changed = True
                if existing.chat_id != chat_id:
                    existing.chat_id = chat_id
                    changed = True
                if existing.schedule != schedule:
                    existing.schedule = schedule
                    changed = True
                if not existing.deliver_response:
                    existing.deliver_response = True
                    changed = True

                if changed:
                    existing.updated_at = datetime.now(SHANGHAI_TZ).replace(tzinfo=None)
                    if existing.enabled:
                        from croniter import croniter
                        now_sh = datetime.now(SHANGHAI_TZ).replace(tzinfo=None)
                        existing.next_run = croniter(existing.schedule, now_sh).get_next(datetime)
                    else:
                        existing.next_run = None
                    await db.commit()
                    logger.info(f"Synced heartbeat cron job config: enabled={enabled}, channel={channel}")
                else:
                    logger.debug("Heartbeat cron job already in sync")
                return

            job = CronJob(
                id=HEARTBEAT_JOB_ID,
                name=HEARTBEAT_JOB_NAME,
                schedule=schedule,
                message=HEARTBEAT_MESSAGE,
                enabled=enabled,
                channel=channel,
                chat_id=chat_id,
                deliver_response=True,
                created_at=datetime.now(SHANGHAI_TZ).replace(tzinfo=None),
                updated_at=datetime.now(SHANGHAI_TZ).replace(tzinfo=None),
            )
            # 计算 next_run
            if enabled:
                from croniter import croniter
                now_sh = datetime.now(SHANGHAI_TZ).replace(tzinfo=None)
                job.next_run = croniter(schedule, now_sh).get_next(datetime)

            db.add(job)
            await db.commit()
            logger.info(f"Created built-in heartbeat cron job: enabled={enabled}, channel={channel}")
    except Exception as e:
        logger.error(f"Failed to ensure heartbeat cron job: {e}")
