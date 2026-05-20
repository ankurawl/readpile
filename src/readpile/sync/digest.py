"""Digest builder and sender — group items by topic, email to user."""

from __future__ import annotations

import logging
import os
import smtplib
from datetime import date, datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
import tempfile

from readpile.sync.state import SyncState

log = logging.getLogger("readpile.sync")


class DigestBuilder:
    """Group items into topic-based markdown files using LLM."""

    def __init__(self, config: dict) -> None:
        self.config = config
        self._max_topics = config.get("sync", {}).get("digest", {}).get("max_topic_files", 5)

    def build(
        self,
        items: list[dict],
        state: SyncState,
        skipped_unknown_senders: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> tuple[str, list[Path]]:
        """Build digest email body and topic .md attachments.

        Returns (email_body, list_of_md_file_paths).
        """
        if not items:
            return "", []

        today = date.today().isoformat()
        subject = f"readpile — {today} ({len(items)} new items)"

        item_map: dict[str, str] = {}
        for i, item in enumerate(items, 1):
            path = item.get("source_path", "")
            item_map[str(i)] = path

        state.set_digest_state(subject, f"digest_{today}", item_map)

        files: list[Path] = []
        tmp_dir = Path(tempfile.mkdtemp(prefix="readpile-digest-"))

        if len(items) <= 2:
            md_content = self._build_flat_list(items, 1)
            md_path = tmp_dir / "digest.md"
            md_path.write_text(md_content, encoding="utf-8")
            files.append(md_path)
        else:
            groups = self._group_items(items)
            for topic_name, topic_items in groups.items():
                slug = topic_name.lower().replace(" ", "-")[:30]
                md_content = self._build_topic_file(topic_name, topic_items)
                md_path = tmp_dir / f"{slug}.md"
                md_path.write_text(md_content, encoding="utf-8")
                files.append(md_path)

        body_lines = [f"# readpile digest — {today}", f"", f"**{len(items)} new items**", ""]

        for i, item in enumerate(items, 1):
            title = item.get("title", "Untitled")
            wc = item.get("word_count", 0)
            ct = item.get("content_type", "article")
            body_lines.append(f"{i}. **{title}** ({ct}, {wc} words)")

        body_lines.append("")

        if skipped_unknown_senders:
            body_lines.append(f"*{len(skipped_unknown_senders)} emails from unknown senders skipped:*")
            for sender in skipped_unknown_senders:
                body_lines.append(f"  - {sender}")
            body_lines.append("")

        if errors:
            body_lines.append(f"*{len(errors)} items failed:*")
            for err in errors:
                body_lines.append(f"  - {err}")
            body_lines.append("")

        body_lines.extend([
            "---",
            "",
            "Reply to this email to control synthesis.",
            "Items auto-synthesize after 7 days if no reply.",
            "Examples:",
            "  'Synthesize items 1, 3, 4'",
            "  'Skip item 2'",
            "  'Add https://newblog.com to my sources'",
            "  'Remove Old Blog from sources'",
        ])

        return "\n".join(body_lines), files

    def _group_items(self, items: list[dict]) -> dict[str, list[dict]]:
        try:
            from readpile.sync.llm import generate
            system = (
                "Group the following items into 3-5 coherent topics. "
                "Return ONLY a raw JSON object with topic names as keys "
                "and lists of item numbers (integers) as values. "
                "No markdown, no code fences, no explanation."
            )
            item_lines = []
            for i, item in enumerate(items, 1):
                item_lines.append(f"{i}. {item.get('title', 'Untitled')} ({item.get('content_type', 'article')})")
            user = "\n".join(item_lines)

            response = generate(system, user, self.config)
            if not response or not response.strip():
                raise ValueError("LLM returned empty response")

            import json
            import re
            cleaned = response.strip()
            cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)
            groups_raw = json.loads(cleaned)
            groups: dict[str, list[dict]] = {}
            for topic, indices in groups_raw.items():
                topic_items = []
                for idx in indices:
                    if 1 <= idx <= len(items):
                        topic_items.append(items[idx - 1])
                if topic_items:
                    groups[topic] = topic_items

            if len(groups) > self._max_topics:
                sorted_groups = sorted(groups.items(), key=lambda x: -len(x[1]))
                groups = dict(sorted_groups[:self._max_topics])

            if groups:
                return groups
        except Exception as exc:
            log.warning("LLM grouping failed, using flat list: %s", exc)

        return {"All Items": items}

    def _build_flat_list(self, items: list[dict], start_num: int = 1) -> str:
        lines = ["# Digest", ""]
        for i, item in enumerate(items, start_num):
            title = item.get("title", "Untitled")
            url = item.get("url", "")
            ct = item.get("content_type", "article")
            wc = item.get("word_count", 0)
            preview = item.get("preview", "")
            lines.append(f"## {i}. {title}")
            lines.append(f"- Source: {url}")
            lines.append(f"- Type: {ct} | Words: {wc}")
            if preview:
                lines.append(f"- Preview: {preview}")
            lines.append("")
        return "\n".join(lines)

    def _build_topic_file(self, topic: str, items: list[dict]) -> str:
        lines = [f"# {topic}", f"", f"*{len(items)} items*", ""]
        for item in items:
            title = item.get("title", "Untitled")
            url = item.get("url", "")
            ct = item.get("content_type", "article")
            wc = item.get("word_count", 0)
            preview = item.get("preview", "")
            lines.append(f"## {title}")
            lines.append(f"- Source: {url}")
            lines.append(f"- Type: {ct} | Words: {wc}")
            if preview:
                lines.append(f"- Preview: {preview}")
            lines.append("")
        return "\n".join(lines)


class DigestSender:
    """Send digest email via SMTP with .md attachments."""

    def __init__(self, config: dict) -> None:
        self.config = config
        digest_cfg = config.get("sync", {}).get("digest", {})
        self.smtp_host = digest_cfg.get("smtp_host", "smtp.gmail.com")
        self.smtp_port = digest_cfg.get("smtp_port", 587)
        self.from_addr = digest_cfg.get("from", "")
        self._max_pending = digest_cfg.get("max_pending_digests", 7)

    def send(
        self, subject: str, body: str, attachments: list[Path], to: str,
    ) -> None:
        password = os.environ.get("READPILE_SMTP_PASSWORD", "")
        if not password:
            log.warning("READPILE_SMTP_PASSWORD not set, saving digest to pending")
            self._save_pending(subject, body, attachments)
            return

        msg = MIMEMultipart()
        msg["From"] = self.from_addr
        msg["To"] = to
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain", "utf-8"))

        for path in attachments:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(path.read_bytes())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{path.name}"')
            msg.attach(part)

        try:
            if self.smtp_port == 465:
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as server:
                    server.login(self.from_addr, password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                    server.starttls()
                    server.login(self.from_addr, password)
                    server.send_message(msg)

            self._send_pending(to, password)
            log.info("Digest sent to %s", to)
        except Exception as exc:
            log.error("Failed to send digest: %s", exc)
            self._save_pending(subject, body, attachments)

    def _save_pending(self, subject: str, body: str, attachments: list[Path]) -> None:
        pending_dir = Path("~/.readpile/pending-digest").expanduser()
        today_dir = pending_dir / date.today().isoformat()
        today_dir.mkdir(parents=True, exist_ok=True)

        (today_dir / "subject.txt").write_text(subject, encoding="utf-8")
        (today_dir / "body.md").write_text(body, encoding="utf-8")
        for att in attachments:
            import shutil
            shutil.copy2(att, today_dir / att.name)

        all_dirs = sorted(pending_dir.iterdir())
        if len(all_dirs) > self._max_pending:
            for old_dir in all_dirs[:-self._max_pending]:
                import shutil
                shutil.rmtree(old_dir, ignore_errors=True)

        log.info("Digest saved to pending: %s", today_dir)

    def _send_pending(self, to: str, password: str) -> None:
        pending_dir = Path("~/.readpile/pending-digest").expanduser()
        if not pending_dir.exists():
            return

        for day_dir in sorted(pending_dir.iterdir()):
            if not day_dir.is_dir():
                continue
            subject_file = day_dir / "subject.txt"
            body_file = day_dir / "body.md"
            if not subject_file.exists() or not body_file.exists():
                continue

            try:
                subject = subject_file.read_text(encoding="utf-8")
                body = body_file.read_text(encoding="utf-8")
                attachments = [p for p in day_dir.iterdir() if p.suffix == ".md" and p.name != "body.md"]

                msg = MIMEMultipart()
                msg["From"] = self.from_addr
                msg["To"] = to
                msg["Subject"] = f"[Delayed] {subject}"
                msg.attach(MIMEText(body, "plain", "utf-8"))

                for path in attachments:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(path.read_bytes())
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", f'attachment; filename="{path.name}"')
                    msg.attach(part)

                with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                    server.starttls()
                    server.login(self.from_addr, password)
                    server.send_message(msg)

                import shutil
                shutil.rmtree(day_dir, ignore_errors=True)
                log.info("Sent pending digest from %s", day_dir.name)
            except Exception as exc:
                log.warning("Failed to send pending digest %s: %s", day_dir.name, exc)
                break
