"""Translation prompts for EN→ZH translation."""

from typing import Any


class PlanningPrompt:
    """Prompt for pre-translation planning and analysis."""

    SYSTEM_PROMPT = """你是一个学术翻译规划专家，负责在翻译前分析文本片段并提供翻译策略。

分析要点：
1. 片段类型识别：标题、摘要、引言、方法、结果、讨论、结论、参考文献等
2. 关键术语识别：专业术语、领域特定概念、人名地名
3. 特殊格式识别：引用、数字、公式、表格内容
4. 翻译策略建议：如何处理特定术语、保持什么语气

输出格式必须是严格的JSON，不要包含任何其他内容："""

    USER_TEMPLATE = """请分析以下英文片段并提供翻译策略：

原文：
{source_text}

上下文（如果有）：
{context_before}
{context_after}

术语库（如果有）：
{termbank}

输出必须是严格的JSON格式：
{{
  "segment_type": "标题|摘要|引言|方法|结果|讨论|结论|参考文献|其他",
  "key_terms": [
    {{"term": "英文术语", "context": "上下文", "suggested_translation": "建议翻译"}}
  ],
  "special_formats": [
    {{"type": "引用|数字|公式|表格", "content": "..."}}
  ],
  "translation_strategy": "具体的翻译策略建议"
}}"""

    @staticmethod
    def build(
        source_text: str,
        context_before: str | None = None,
        context_after: str | None = None,
        termbank: dict[str, Any] | None = None,
    ) -> list[dict]:
        """
        Build prompt messages for planning analysis.

        Args:
            source_text: Source text to analyze.
            context_before: Context before this segment.
            context_after: Context after this segment.
            termbank: Dictionary of term translations.

        Returns:
            List of message dicts for LLM API.
        """
        context_before_str = f"前文：{context_before}" if context_before else "无"
        context_after_str = f"后文：{context_after}" if context_after else "无"

        termbank_str = ""
        if termbank:
            termbank_str = "术语库：\n"
            for source, target in termbank.items():
                termbank_str += f"  - {source} → {target}\n"

        user_content = PlanningPrompt.USER_TEMPLATE.format(
            source_text=source_text,
            context_before=context_before_str,
            context_after=context_after_str,
            termbank=termbank_str if termbank_str else "无",
        )

        return [
            {"role": "system", "content": PlanningPrompt.SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    @staticmethod
    def get_response_schema() -> dict:
        """
        Get JSON schema for LLM response.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "properties": {
                "segment_type": {
                    "type": "string",
                    "enum": ["标题", "摘要", "引言", "方法", "结果", "讨论", "结论", "参考文献", "其他"],
                    "description": "片段类型",
                },
                "key_terms": {
                    "type": "array",
                    "description": "关键术语列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "term": {"type": "string", "description": "英文术语"},
                            "context": {"type": "string", "description": "上下文"},
                            "suggested_translation": {"type": "string", "description": "建议翻译"},
                        },
                        "required": ["term"],
                    },
                },
                "special_formats": {
                    "type": "array",
                    "description": "特殊格式列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["引用", "数字", "公式", "表格"], "description": "格式类型"},
                            "content": {"type": "string", "description": "格式内容"},
                        },
                        "required": ["type", "content"],
                    },
                },
                "translation_strategy": {
                    "type": "string",
                    "description": "翻译策略建议",
                },
            },
            "required": ["segment_type", "key_terms", "special_formats", "translation_strategy"],
        }


class DraftTranslationPrompt:
    """Prompt for drafting initial translation."""

    SYSTEM_PROMPT = """你是一个学术翻译专家，负责将英文学术论文翻译成中文。

翻译规则：
1. 不要添加新的引用
2. 必须保留引用文本的完全相同（逐字符）
3. 必须保留数字的完全相同
4. 使用学术中文语气（正式、客观、准确）
5. 使用术语库和短语库（如果提供）
6. 确保术语翻译的一致性
7. 记录非显而易见的翻译决策（例如术语选择、习语处理）

输出格式必须是严格的JSON，不要包含任何其他内容："""

    USER_TEMPLATE = """请翻译以下英文段落成中文：

原文：
{source_text}

上下文（如果有）：
{context_before}
{context_after}

术语库（如果有）：
{termbank}

短语库（如果有）：
{phrasebank}

翻译策略分析：
{planning}

输出必须是严格的JSON格式：
{{
  "translation": "string",
  "uncertainties": [
    {{"type": "TERM", "span": "...", "question": "...", "options": ["...", "..."}}
  ],
  "notes": ["translation decision note 1", "translation decision note 2"]
}}"""

    @staticmethod
    def build(
        source_text: str,
        context_before: str | None = None,
        context_after: str | None = None,
        termbank: dict[str, Any] | None = None,
        phrasebank: dict[str, list[str]] | None = None,
        planning_analysis: dict[str, Any] | None = None,
        style_preferences: dict | None = None,
    ) -> list[dict]:
        """
        Build prompt messages for draft translation.

        Args:
            source_text: Source text to translate.
            context_before: Context before this segment.
            context_after: Context after this segment.
            termbank: Dictionary of term translations.
            phrasebank: Dictionary of phrase patterns.
            planning_analysis: Planning analysis from pre-translation step.
            style_preferences: Style and terminology preferences.

        Returns:
            List of message dicts for LLM API.
        """
        context_before_str = f"前文：{context_before}" if context_before else "无"
        context_after_str = f"后文：{context_after}" if context_after else "无"

        merged_termbank = dict(termbank) if termbank else {}
        if style_preferences and "terminology_overrides" in style_preferences:
            merged_termbank.update(style_preferences["terminology_overrides"])

        termbank_str = ""
        if merged_termbank:
            termbank_str = "术语翻译：\n"
            for source, target in merged_termbank.items():
                termbank_str += f"  - {source} → {target}\n"

        phrasebank_str = ""
        if phrasebank:
            phrasebank_str = "短语模式：\n"
            for func_type, phrases in phrasebank.items():
                phrasebank_str += f"  - {func_type}: {', '.join(phrases)}\n"

        planning_str = ""
        if planning_analysis:
            planning_str += f"  - 片段类型：{planning_analysis.get('segment_type', '未识别')}\n"
            planning_str += f"  - 翻译策略：{planning_analysis.get('translation_strategy', '无')}\n"

            key_terms = planning_analysis.get('key_terms', [])
            if key_terms:
                planning_str += "  - 关键术语：\n"
                for term_info in key_terms:
                    term = term_info.get('term', '')
                    suggested = term_info.get('suggested_translation', '')
                    if term and suggested:
                        planning_str += f"    * {term} → {suggested}\n"

            special_formats = planning_analysis.get('special_formats', [])
            if special_formats:
                planning_str += "  - 特殊格式：\n"
                for fmt in special_formats:
                    fmt_type = fmt.get('type', '')
                    content = fmt.get('content', '')
                    if fmt_type:
                        planning_str += f"    * {fmt_type}: {content[:50]}...\n"

        user_content = DraftTranslationPrompt.USER_TEMPLATE.format(
            source_text=source_text,
            context_before=context_before_str,
            context_after=context_after_str,
            termbank=termbank_str if termbank_str else "无",
            phrasebank=phrasebank_str if phrasebank_str else "无",
            planning=planning_str if planning_str else "无",
        )

        return [
            {"role": "system", "content": DraftTranslationPrompt.SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    @staticmethod
    def get_response_schema() -> dict:
        """
        Get JSON schema for LLM response.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "properties": {
                "translation": {
                    "type": "string",
                    "description": "翻译后的中文文本",
                },
                "uncertainties": {
                    "type": "array",
                    "description": "不确定的术语或含义",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["TERM", "MEANING"],
                                "description": "不确定的类型",
                            },
                            "span": {
                                "type": "string",
                                "description": "不确定的原文片段",
                            },
                            "question": {
                                "type": "string",
                                "description": "向用户提出的问题",
                            },
                            "options": {
                                "type": "array",
                                "description": "可选答案",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["type", "span", "question"],
                    },
                },
                "notes": {
                    "type": "array",
                    "description": "非显而易见的翻译决策说明",
                    "items": {"type": "string"},
                },
            },
            "required": ["translation", "uncertainties", "notes"],
        }


class CriticReviewPrompt:
    """Prompt for LLM critic review of translation."""

    SYSTEM_PROMPT = """你是一个学术翻译审稿人，负责审查翻译质量。

审查要点：
1. 意思偏差：翻译是否改变了原文含义
2. 遗漏：是否遗漏了重要内容
3. 添加：是否添加了原文中没有的内容
4. 术语不一致：是否使用了不一致的术语

输出格式必须是严格的JSON，不要包含任何其他内容："""

    USER_TEMPLATE = """请审查以下翻译：

原文：
{source_text}

译文：
{translation}

术语库（如果有）：
{termbank}

输出必须是严格的JSON格式：
{{
  "issues": [
    {{
      "code": "MEANING_DRIFT",
      "detail": "翻译改变了原文含义：..."
    }},
    {{
      "code": "OMISSION",
      "detail": "遗漏了内容：..."
    }},
    {{
      "code": "ADDITION",
      "detail": "添加了原文没有的内容：..."
    }},
    {{
      "code": "TERM_INCONSISTENCY",
      "detail": "术语使用不一致：..."
    }}
  ]
}}

如果没有问题，返回空的issues数组。"""

    @staticmethod
    def build(
        source_text: str,
        translation: str,
        termbank: dict[str, Any] | None = None,
    ) -> list[dict]:
        """
        Build prompt messages for critic review.

        Args:
            source_text: Original source text.
            translation: Translated text.
            termbank: Dictionary of term translations.

        Returns:
            List of message dicts for LLM API.
        """
        # Build termbank string
        termbank_str = ""
        if termbank:
            termbank_str = "术语库：\n"
            for source, target in termbank.items():
                termbank_str += f"  - {source} → {target}\n"

        user_content = CriticReviewPrompt.USER_TEMPLATE.format(
            source_text=source_text,
            translation=translation,
            termbank=termbank_str if termbank_str else "无",
        )

        return [
            {"role": "system", "content": CriticReviewPrompt.SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    @staticmethod
    def get_response_schema() -> dict:
        """
        Get JSON schema for LLM response.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "properties": {
                "issues": {
                    "type": "array",
                    "description": "翻译问题列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "enum": [
                                    "MEANING_DRIFT",
                                    "OMISSION",
                                    "ADDITION",
                                    "TERM_INCONSISTENCY",
                                ],
                                "description": "问题类型",
                            },
                            "detail": {
                                "type": "string",
                                "description": "问题详细描述",
                            },
                        },
                        "required": ["code", "detail"],
                    },
                },
            },
            "required": ["issues"],
        }


class RevisionPrompt:
    """Prompt for revising translation based on feedback."""

    SYSTEM_PROMPT = """你是一个学术翻译专家，负责根据反馈修订翻译。

修订规则：
1. 解决所有指出的翻译问题
2. 回答用户的问题
3. 保持引用格式完全相同
4. 保持数字完全相同
5. 保持学术中文语气

输出格式必须是严格的JSON，不要包含任何其他内容："""

    USER_TEMPLATE = """请根据以下反馈修订翻译：

原文：
{source_text}

当前译文：
{current_translation}

审稿意见：
{critic_issues}

用户反馈：
{user_feedback}

结构化反馈：
{structured_feedback}

用户问题答案：
{user_answers}

风格偏好：
{style_preferences}

术语库（如果有）：
{termbank}

输出必须是严格的JSON格式：
{{
  "translation": "string",
  "uncertainties": [],
  "notes": ["revision decision note"]
}}"""

    @staticmethod
    def build(
        source_text: str,
        current_translation: str,
        critic_issues: list[dict],
        user_feedback: list[str],
        user_answers: dict[str, str],
        termbank: dict[str, Any] | None = None,
        structured_feedback: list[dict] | None = None,
        style_preferences: dict | None = None,
    ) -> list[dict]:
        """
        Build prompt messages for revision.

        Args:
            source_text: Original source text.
            current_translation: Current translation.
            critic_issues: Issues from critic review.
            user_feedback: User comments/feedback.
            user_answers: User answers to uncertainty questions.
            termbank: Dictionary of term translations.
            structured_feedback: Categorized feedback items.
            style_preferences: Style and terminology preferences.

        Returns:
            List of message dicts for LLM API.
        """
        critic_str = ""
        if critic_issues:
            critic_str = "审稿意见：\n"
            for issue in critic_issues:
                critic_str += f"  - [{issue.get('code')}] {issue.get('detail')}\n"

        feedback_str = "\n".join(user_feedback) if user_feedback else "无"

        sf_str = "无"
        if structured_feedback:
            lines = []
            for fb in structured_feedback:
                cat = fb.get("category", "OTHER")
                detail = fb.get("detail", "")
                line = f"  - [{cat}] {detail}"
                if fb.get("span"):
                    line += f" (原文: {fb['span']})"
                if fb.get("suggested_fix"):
                    line += f" (建议修改: {fb['suggested_fix']})"
                lines.append(line)
            sf_str = "\n".join(lines)

        answers_str = ""
        if user_answers:
            answers_str = "用户回答：\n"
            for question, answer in user_answers.items():
                answers_str += f"  - {question}: {answer}\n"

        sp_str = "无"
        if style_preferences:
            lines = []
            for k, v in style_preferences.items():
                if k != "terminology_overrides":
                    lines.append(f"  - {k}: {v}")
            sp_str = "\n".join(lines) if lines else "无"

        termbank_str = ""
        if termbank:
            termbank_str = "术语库：\n"
            for source, target in termbank.items():
                termbank_str += f"  - {source} → {target}\n"

        user_content = RevisionPrompt.USER_TEMPLATE.format(
            source_text=source_text,
            current_translation=current_translation,
            critic_issues=critic_str if critic_str else "无",
            user_feedback=feedback_str,
            structured_feedback=sf_str,
            user_answers=answers_str if answers_str else "无",
            style_preferences=sp_str,
            termbank=termbank_str if termbank_str else "无",
        )

        return [
            {"role": "system", "content": RevisionPrompt.SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    @staticmethod
    def get_response_schema() -> dict:
        """
        Get JSON schema for LLM response.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "properties": {
                "translation": {
                    "type": "string",
                    "description": "修订后的中文文本",
                },
                "uncertainties": {
                    "type": "array",
                    "description": "修订后仍有的不确定（应该为空）",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "span": {"type": "string"},
                            "question": {"type": "string"},
                            "options": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "notes": {
                    "type": "array",
                    "description": "非显而易见的翻译决策说明",
                    "items": {"type": "string"},
                },
            },
            "required": ["translation", "uncertainties", "notes"],
        }
