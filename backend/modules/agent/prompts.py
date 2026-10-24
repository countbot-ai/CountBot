"""Agent Prompts - prompt templates.

All built-in prompts are English to keep token usage low; every prompt that
produces user-visible text instructs the model to answer in the conversation's
language, so Chinese users still get Chinese output.
"""

# 对话总结 → 记忆条目提示词
# 让 LLM 直接把对话总结为一行记忆格式
CONVERSATION_TO_MEMORY_PROMPT = """You summarize conversations into memory entries.

Rules:
1. Output ONE line; separate multiple items with a semicolon.
2. Record only durable facts:
   - preferences and habits the user stated
   - important decisions and conclusions
   - project config and technical details
   - anything the user asked to remember
3. Never record: greetings, confirmations, repetition, one-off query results
   (weather/news/search), intermediate tool output, small talk or tests.
4. Every item must contain concrete details (names, numbers, dates, paths).
5. If nothing is worth remembering, output exactly: NOTHING_TO_RECORD
6. Write in the same language as the conversation.

Conversation:
{messages}

Output (one line):"""


# 短期上下文压缩提示词（用于下一轮继续对话）
SHORT_CONTEXT_SUMMARY_PROMPT = """You compress older conversation history into context that lets the next model turn continue the work.

Rules:
1. This is working context, not long-term memory.
2. Keep: the current goal and user requirements; confirmed decisions, constraints
   and boundaries; key facts, files, configs, errors and conclusions; open
   questions and next steps.
3. Drop: greetings, repeated confirmations, small talk, one-off query results,
   verbose tool output.
4. Plain text, no markdown headings. Stay under {char_limit} characters.
5. Write in the same language as the conversation.

Conversation:
{messages}

Context summary:"""


# 递归短期上下文总结提示词（用于增量刷新）
RECURSIVE_SHORT_CONTEXT_SUMMARY_PROMPT = """You merge new conversation content into an existing short-term context summary.

Existing summary:
{previous_summary}

New conversation:
{past_messages}

Rules:
1. Keep the current goal, key constraints, confirmed conclusions, open questions
   and next steps.
2. Remove outdated, duplicated or irrelevant content.
3. Plain text, no markdown headings. Stay under {char_limit} characters.
4. Write in the same language as the conversation.

Updated context summary:"""


# 记忆条目模板（写入 MEMORY.md 的格式）
MEMORY_ENTRY_TEMPLATE = "{date}|{source}|{content}"

# 模型判定"无需写入记忆"时的输出标记。
# 保留中文标记以兼容旧版提示词/历史模型输出。
MEMORY_NOOP_SENTINELS = ("NOTHING_TO_RECORD", "无需记录")


def is_memory_noop(text: str) -> bool:
    """判断总结结果是否表示"没有值得记录的内容"。

    只把「整段输出就是该标记」视为无内容：早先的实现做子串匹配，模型正常
    总结里出现「无需记录」这类词会被整条丢弃。
    """
    normalized = (text or "").strip().strip("。.!！,，;；:：\"'“”‘’()（）[]【】")
    if not normalized:
        return True
    return normalized in MEMORY_NOOP_SENTINELS


def render_prompt(template: str, **values) -> str:
    """填充提示词模板。

    不使用 str.format：模板里一旦混入字面花括号（例如 JSON 示例）就会整段
    抛错或退化，导致所有占位符都填不上。这里逐个替换已知占位符，未提供值的
    占位符与字面花括号原样保留。
    """
    if not template:
        return ""
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered


# 上下文溢出总结提示词（滚动窗口截断前，将旧消息写入记忆）
OVERFLOW_SUMMARY_PROMPT = """You summarize old conversation history that is about to be truncated into durable memory entries.

Rules:
1. Output ONE line; separate multiple items with a semicolon.
2. Record only durable facts:
   - preferences and habits the user stated
   - important decisions and conclusions
   - project config and technical details
   - key results of tool calls (not one-off queries)
3. Never record: greetings, confirmations, repetition, one-off query results,
   intermediate tool output or temporary data.
4. Every item must contain concrete details (names, numbers, dates, paths).
5. If nothing is worth remembering, output exactly: NOTHING_TO_RECORD
6. Write in the same language as the conversation.

Conversation:
{messages}

Output (one line):"""


# Heartbeat 问候提示词
HEARTBEAT_GREETING_PROMPT = """You are the user's assistant "{ai_name}". It is {time_desc} and the user "{user_name}" has not talked to you for {idle_hours} hours.

{user_context}

Personality:
{personality_desc}

Write one short, natural, warm greeting that checks in on the user.

Rules:
1. Match the time of day (energetic morning, relaxed afternoon, cozy evening).
2. Reflect the personality, but sound like a friend, not a corporate bot.
3. Optionally reference time or weather.
4. If a location is known, you may mention something local.
5. Keep it under 50 characters.
6. No emoji.
7. Never say "How can I help you".
8. You may address the user by name.
9. Write in the user's language (default: the language of {user_name} / the
   configured output language).

{memory_context}

Greeting:"""


# 定时任务执行提示词
CRON_TASK_EXECUTION_PROMPT = """This is an automated scheduled task run.

Task: {task_message}

Rules:
1. Classify the task:
   - Simple reminder ("drink water", "meeting time"): produce a friendly notification.
   - Actionable task ("fetch the weather and report", "generate a report"): run it
     with tools and return the result.
2. Reminders: phrase the reminder naturally; do not comment on the reminder itself.
3. Actionable tasks: call the proper tools and report the outcome.
4. Be concise and professional; no filler.
5. No emoji.
6. Write in the user's language.

Execute the task and return the result:"""
