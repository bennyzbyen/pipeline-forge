#!/usr/bin/env python3
"""Track explicit requirement-section roles within one document."""

from __future__ import annotations

import re


class DocumentSection:
    def __init__(self) -> None:
        self.role = ""
        self.level = 9

    def feed(self, text: str, style: str = "") -> str:
        if style in {"CodeBlock", "Metadata", "Quote"}:
            return "ignored"
        text = " ".join(text.split())
        if not text:
            return self.role
        lower = re.sub(r"^[\d.、)）\s]+", "", text.lower())
        heading = re.fullmatch(r"Heading([1-6])", style, re.IGNORECASE)
        level = int(heading.group(1)) if heading else 9
        if self.role == "example" and level > self.level:
            return self.role
        if re.match(r"^(?:data\s+sources?\b|数据源)", lower):
            self.role, self.level = "source", level
        elif re.match(r"^(?:data\s+targets?\b|target\s+management\b|data\s+storage\b|目标表|目标管理)", lower):
            self.role, self.level = "target", level
        elif re.match(r"^(?:examples?\b|references?\b|示例|历史|旧版|参考)", lower):
            self.role, self.level = "example", level
        elif re.match(r"^(?:datahub\s+pipeline|data\s+pipeline\s+management|data\s+transformation|pipeline\s+planning|调度|数据处理)", lower):
            self.role, self.level = "other", level
        elif heading and self.role and level <= self.level and not any(word in lower for word in ("clickhouse", "hbase")):
            self.role, self.level = "other", level
        return self.role
