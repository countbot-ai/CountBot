"""记忆相关的提示词文案。"""

# 系统提示词中的记忆区块：说明记忆的存在与检索方式
SYSTEM_MEMORY_RULES = (
    "## Memory\n"
    "- Persistent memory is a store of assertions keyed by subject; the entries that "
    "matter most are injected into every turn above.\n"
    "- Call `memory` with action `recall` before assuming an older fact is unknown: "
    "archived entries stay searchable but are not injected.\n"
    "- Store durable facts only: explicit requests to remember, stable preferences, "
    "key decisions, long-term configuration. Skip small talk, tests, one-off query "
    "results and temporary state; call the tool silently.\n"
    "- Record what the user actually said. Do not append rules they did not state: an "
    "embellished entry is indistinguishable from a real one once injected.\n"
    "- One assertion per key, one short sentence per value. Every injected entry is "
    "charged to a 300-token budget, so a paragraph costs the slot of four facts.\n"
    "- Pinning is the user's decision: `remember` always lands in `recent`."
)
