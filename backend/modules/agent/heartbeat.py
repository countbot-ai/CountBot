"""Heartbeat 主动问候系统"""

import json
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional

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
        self._state_file = workspace / "memory" / "heartbeat_state.json"
        self._state_loaded = False

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

    def _load_state(self) -> dict:
        """从文件加载状态"""
        try:
            if self._state_file.exists():
                with open(self._state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load heartbeat state: {e}")
        return {}

    def _save_state(self, state: dict):
        """保存状态到文件"""
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save heartbeat state: {e}")

    def _generate_random_times(self, date: str) -> List[int]:
        """为指定日期生成随机问候时间点（分钟数），每天不同且跨进程重启稳定（幂等）。

        种子：北京时间当天 0 点的 UTC 时间戳，跨平台确定性，不依赖 PYTHONHASHSEED。
        分布：把活跃时段等分为 N 段，每段内随机取一点，保证时间点充分分散。

        Returns:
            List[int]: 升序分钟数列表，如 [615, 780] 表示 10:15, 13:00
        """
        # 确定性种子：北京时间当天 0 点 → UTC 时间戳（不依赖本机时区）
        try:
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            beijing_midnight = date_obj.replace(tzinfo=SHANGHAI_TZ)
            seed = int(beijing_midnight.timestamp())
        except Exception:
            seed = 0
        rng = random.Random(seed)

        # 计算活跃时段（分钟数区间列表，支持跨午夜和非跨午夜两种配置）
        qs = self.quiet_start  # 免打扰开始小时
        qe = self.quiet_end    # 免打扰结束小时
        total = 24 * 60

        if qs > qe:
            # 跨午夜免打扰，如 quiet_start=21, quiet_end=8 → 免打扰 21:00-08:00
            # 活跃时段：一个连续段 [qe*60, qs*60)
            active_segments = [(qe * 60, qs * 60)]
        elif qs < qe:
            # 非跨午夜免打扰，如 quiet_start=1, quiet_end=6 → 免打扰 01:00-06:00
            # 活跃时段：两段 [0, qs*60) 和 [qe*60, 24*60)
            active_segments = []
            if qs * 60 > 0:
                active_segments.append((0, qs * 60))
            if qe * 60 < total:
                active_segments.append((qe * 60, total))
        else:
            # quiet_start == quiet_end：无免打扰，全天活跃
            active_segments = [(0, total)]

        # 计算总活跃分钟数
        active_total = sum(end - start for start, end in active_segments)
        if active_total <= 0 or self.max_greets_per_day <= 0:
            return []

        # 分段均匀随机：把虚拟连续活跃区间等分为 N 段，每段随机取一点
        segment_size = active_total // self.max_greets_per_day
        if segment_size < 1:
            segment_size = 1

        def virtual_to_real(v: int) -> int:
            """将虚拟连续偏移量映射到真实分钟数"""
            for seg_start, seg_end in active_segments:
                seg_len = seg_end - seg_start
                if v < seg_len:
                    return seg_start + v
                v -= seg_len
            # fallback：返回最后一段末尾
            last_start, last_end = active_segments[-1]
            return last_end - 1

        times = []
        for i in range(self.max_greets_per_day):
            v_start = i * segment_size
            v_end = v_start + segment_size
            if v_end > active_total:
                v_end = active_total
            v = rng.randint(v_start, v_end - 1)
            times.append(virtual_to_real(v))

        return sorted(times)

    def _get_today_state(self, today: str) -> dict:
        """获取今天的状态"""
        state = self._load_state()
        
        if today not in state:
            # 为今天生成随机时间点
            random_times = self._generate_random_times(today)
            state[today] = {
                "scheduled_times": random_times,
                "greeted_times": [],
                "count": 0
            }
            self._save_state(state)
            logger.info(f"Generated random greeting times for {today}: {[f'{t//60}:{t%60:02d}' for t in random_times]}")
        
        return state[today]

    def _mark_greeted(self, today: str, scheduled_time: int):
        """标记某个计划时间点已问候过（记录 scheduled_time 而非 current_minute）"""
        state = self._load_state()
        
        if today not in state:
            state[today] = {
                "scheduled_times": [],
                "greeted_times": [],
                "count": 0
            }
        
        if scheduled_time not in state[today]["greeted_times"]:
            state[today]["greeted_times"].append(scheduled_time)
            state[today]["count"] = len(state[today]["greeted_times"])
        
        # 清理旧数据（保留最近7天）
        dates = sorted(state.keys())
        if len(dates) > 7:
            for old_date in dates[:-7]:
                del state[old_date]
        
        self._save_state(state)

    def _should_greet_now(self, today: str, current_minute: int) -> Optional[int]:
        """判断当前时间是否应该问候。

        返回匹配的计划时间点（分钟数），若不应问候则返回 None。
        使用计划时间点本身作为标识，避免 current_minute 漂移导致同一槽位重复触发。
        """
        today_state = self._get_today_state(today)
        scheduled_times = today_state["scheduled_times"]
        greeted_times = today_state["greeted_times"]

        # 检查是否已达到每日上限
        if today_state["count"] >= self.max_greets_per_day:
            return None

        # 找到当前时间最近且未问候过的计划时间点
        for scheduled_time in scheduled_times:
            if scheduled_time in greeted_times:
                continue
            if abs(current_minute - scheduled_time) <= 30:
                return scheduled_time

        return None

    async def execute(self) -> str:
        """cron executor 调用入口。返回问候语或空字符串。

        流程：
        1. 时间窗口检查（北京时间免打扰时段）
        2. 随机时间点检查（是否在计划时间窗口内）
        3. 今日已发检查
        4. 用户空闲检查（>= idle_threshold_hours）
        5. LLM 生成问候
        6. 返回问候语，由 CronExecutor 负责渠道投递
        """
        now = self._now_shanghai()
        today = now.strftime("%Y-%m-%d")
        current_minute = now.hour * 60 + now.minute

        # 1. 免打扰时段检查
        if self._is_quiet_hour(now.hour):
            logger.debug(f"Heartbeat skipped: {now.hour}:00 is in quiet hours ({self.quiet_start}:00-{self.quiet_end}:00 Beijing)")
            return ""

        # 2. 随机时间点检查
        matched_time = self._should_greet_now(today, current_minute)
        if matched_time is None:
            logger.debug(f"Heartbeat skipped: not in scheduled time window (current: {now.hour}:{now.minute:02d})")
            return ""

        # 3. 空闲检测
        idle_hours = await self._get_user_idle_hours()
        if idle_hours is None or idle_hours < self.idle_threshold_hours:
            logger.debug(f"Heartbeat skipped: idle {idle_hours}h < threshold {self.idle_threshold_hours}h")
            return ""

        # 4. 生成问候
        today_state = self._get_today_state(today)
        greet_num = today_state["count"] + 1
        
        logger.info(
            f"Heartbeat triggered: idle {idle_hours:.1f}h, "
            f"Beijing time {now.strftime('%H:%M')}, "
            f"greet #{greet_num}/{self.max_greets_per_day}"
        )
        
        greeting = await self._generate_greeting(now, idle_hours)
        if not greeting:
            return ""

        # 5. 标记已问候（记录计划时间点，防止同一槽位重复触发）
        self._mark_greeted(today, matched_time)
        
        logger.info(f"Heartbeat greeting generated (#{greet_num}/{self.max_greets_per_day}): {greeting[:60]}")
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
            account_id = (
                str(getattr(heartbeat_config, "account_id", "default") or "default")
                if heartbeat_config
                else "default"
            )
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
                if existing.account_id != account_id:
                    existing.account_id = account_id
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
                account_id=account_id,
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
