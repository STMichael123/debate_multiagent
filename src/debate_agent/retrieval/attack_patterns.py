from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AttackPattern:
    """A reusable attack strategy pattern extracted from benchmark analysis."""
    attack_type: str
    label_zh: str
    description: str
    when_to_use: str
    example_tactic: str


ATTACK_PATTERNS: dict[str, AttackPattern] = {
    "definition_challenge": AttackPattern(
        attack_type="definition_challenge",
        label_zh="定义攻击",
        description="重新界定核心概念的范围、边界或性质，使对方立论基础动摇。",
        when_to_use="当对方依赖某个关键概念的特定理解、且该理解并非唯一合理时",
        example_tactic="先给出对方隐含使用的定义，然后展示一个更合理的替代定义，最后说明替代定义下对方结论不成立。例：「对方把'谈热爱'理解为'随便聊聊'，但'谈'在公共语境中更合理的理解是'以传播、传承为目的的表达'——一旦'谈'带有公共责任，就必须追问表达者是否具备足够内容支撑。」",
    ),
    "causal_challenge": AttackPattern(
        attack_type="causal_challenge",
        label_zh="因果攻击",
        description="质疑对方声称的因果链条——A 真的不一定导致 B。",
        when_to_use="对方论点依赖因果推理、且因果链条存在替代解释或中间变量时",
        example_tactic="承认对方前提但提出替代因果路径：「即便承认'不够擅长的人谈热爱可能产生误导'，导致误导的直接原因是'缺乏复盘习惯'而非'不够擅长'本身——一个不够擅长但愿意复盘的新手，比一个天赋好但从不复盘的老手更不容易误导他人。」",
    ),
    "threshold_challenge": AttackPattern(
        attack_type="threshold_challenge",
        label_zh="门槛攻击",
        description="质疑对方提出的标准或门槛是否达到、是否可操作。",
        when_to_use="对方设定了某种'足够好'的标准但该标准模糊、过高或无法检验时",
        example_tactic="要求对方明确门槛：「请对方明确'足够擅长'的检验标准是什么？省级冠军？还是只要不犯事实性错误？如果对方给不出可操作的门槛，那'足够擅长'就是一个空洞的前提，无法作为限制'谈热爱'的合理条件。」",
    ),
    "framing_challenge": AttackPattern(
        attack_type="framing_challenge",
        label_zh="框架攻击",
        description="重新设定讨论框架，使对方的优势框架失效。",
        when_to_use="对方通过特定框架（如权利框架 vs 效用框架）获得优势、且另一框架对你更有利时",
        example_tactic="「对方一直在用'个人自由'框架——想说什么就说什么。但这道题的真正框架应该是'公共表达的责任'：当你的'谈'影响他人对某个领域的认知时，就不只是个人行为了。换到这个框架下，'是否擅长'就不再是限制自由，而是对他人负责。」",
    ),
    "logical_challenge": AttackPattern(
        attack_type="logical_challenge",
        label_zh="逻辑攻击",
        description="直接指出推理中的逻辑漏洞：循环论证、以偏概全、滑坡谬误等。",
        when_to_use="对方的论证中出现可识别的逻辑谬误时",
        example_tactic="「对方的推理链是：热爱 → 想谈 → 谈了 → 可能有误导。这是典型的滑坡论证——从'想谈'到'谈了会有误导'中间跳过了太多环节：是否会核实信息？是否会标注不确定性？对方把这些全部假定为'不会'，这恰恰是需要证明的。」",
    ),
    "impact_challenge": AttackPattern(
        attack_type="impact_challenge",
        label_zh="影响攻击",
        description="削弱或翻转对方论点的影响——即使前提成立，后果也不严重、甚至可能是好事。",
        when_to_use="对方论点的核心力量在于某种严重后果、且该后果可以重新评估时",
        example_tactic="「就算不够擅长的人谈了热爱，所谓的'误导'影响有多大？粉丝在更多对局、更多复盘中自然会修正认知。反倒是禁止不够擅长的人谈热爱，会制造一道'资格门槛'，把无数真心想进入这个领域的人挡在门外——这个影响的量级远大于几个网文新手的误解。」",
    ),
}


def get_attack_pattern(attack_type: str) -> AttackPattern | None:
    return ATTACK_PATTERNS.get(attack_type)


def get_all_attack_patterns() -> list[AttackPattern]:
    return list(ATTACK_PATTERNS.values())


def format_attack_pattern_guidance(preferred_types: list[str] | None = None) -> str:
    """Format attack pattern guidance for prompt injection."""
    patterns = get_all_attack_patterns()
    if preferred_types:
        # Sort: preferred first
        preferred_set = set(preferred_types)
        patterns = sorted(
            patterns,
            key=lambda p: (0 if p.attack_type in preferred_set else 1),
        )

    lines = ["可用攻击策略（按推荐优先级排序）："]
    for i, pattern in enumerate(patterns, start=1):
        lines.append(
            f"{i}. {pattern.label_zh} ({pattern.attack_type})\n"
            f"   适用场景：{pattern.when_to_use}\n"
            f"   战术示例：{pattern.example_tactic[:150]}…"
        )
    return "\n\n".join(lines)
