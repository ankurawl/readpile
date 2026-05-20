"""Reply processor — parse user replies to digest emails."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from readpile.sync.email.base import EmailMessage, EmailProvider
from readpile.sync.state import SyncState

log = logging.getLogger("readpile.sync")


@dataclass
class SynthesizeAction:
    source_paths: list[str]


@dataclass
class SkipAction:
    source_paths: list[str]


@dataclass
class AddFeedAction:
    url: str
    name: str = ""
    kind: str = "rss"


@dataclass
class RemoveFeedAction:
    name: str


ReplyAction = SynthesizeAction | SkipAction | AddFeedAction | RemoveFeedAction


class ReplyProcessor:
    """Find and process replies to recent digest emails."""

    def __init__(self, config: dict) -> None:
        self.config = config
        digest_cfg = config.get("sync", {}).get("digest", {})
        self._expected_sender = digest_cfg.get("to", "").lower()

    async def process(
        self,
        provider: EmailProvider,
        state: SyncState,
    ) -> list[ReplyAction]:
        history = state.get_digest_history()
        if not history:
            return []

        from datetime import datetime, timedelta, timezone
        since = datetime.now(timezone.utc) - timedelta(days=7)

        try:
            messages = await provider.fetch_messages(["INBOX"], since, max_results=50)
        except Exception as exc:
            log.warning("Failed to fetch messages for reply processing: %s", exc)
            return []

        digest_message_ids = {
            entry["message_id"]: entry for entry in history
        }
        digest_subjects = {
            entry["subject"]: entry for entry in history
        }

        replies: list[tuple[EmailMessage, dict]] = []

        for msg in messages:
            from email.utils import parseaddr
            _, sender_addr = parseaddr(msg.sender)
            if sender_addr.lower() != self._expected_sender:
                continue

            in_reply_to = msg.headers.get("In-Reply-To", "")
            matched_entry = None

            if in_reply_to and in_reply_to in digest_message_ids:
                matched_entry = digest_message_ids[in_reply_to]

            if not matched_entry:
                subject = msg.subject or ""
                for digest_subj, entry in digest_subjects.items():
                    if digest_subj.lower() in subject.lower().replace("re: ", "").replace("re:", ""):
                        matched_entry = entry
                        break

            if matched_entry:
                replies.append((msg, matched_entry))

        if not replies:
            return []

        replies.sort(key=lambda x: x[0].date)

        all_actions: list[ReplyAction] = []
        for msg, entry in replies:
            actions = await self._parse_reply(msg, entry)
            all_actions.extend(actions)

        return self._resolve_conflicts(all_actions)

    async def _parse_reply(
        self, msg: EmailMessage, digest_entry: dict,
    ) -> list[ReplyAction]:
        text = msg.text_body or msg.html_body or ""

        try:
            from email_reply_parser import EmailReplyParser
            reply = EmailReplyParser.parse_reply(text)
            text = reply
        except Exception:
            pass

        if not text.strip():
            return []

        item_map = digest_entry.get("item_map", {})

        try:
            from readpile.sync.llm import generate
            system = """Parse the user's reply to a readpile digest email. The user may reference items by number.
Return a JSON array of actions. Each action has a "type" and relevant fields:
- {"type": "synthesize", "items": [1, 3, 4]}
- {"type": "skip", "items": [2]}
- {"type": "add_feed", "url": "https://example.com"}
- {"type": "remove_feed", "name": "Blog Name"}

Available items: """ + ", ".join(f"{k}: {v}" for k, v in item_map.items())

            response = generate(system, text, self.config)

            import json
            raw = response.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            actions_data = json.loads(raw)

            actions: list[ReplyAction] = []
            for a in actions_data:
                atype = a.get("type", "")
                if atype == "synthesize":
                    paths = [item_map[str(i)] for i in a.get("items", []) if str(i) in item_map]
                    if paths:
                        actions.append(SynthesizeAction(paths))
                elif atype == "skip":
                    paths = [item_map[str(i)] for i in a.get("items", []) if str(i) in item_map]
                    if paths:
                        actions.append(SkipAction(paths))
                elif atype == "add_feed":
                    actions.append(AddFeedAction(
                        url=a.get("url", ""),
                        name=a.get("name", ""),
                        kind=a.get("kind", "rss"),
                    ))
                elif atype == "remove_feed":
                    actions.append(RemoveFeedAction(name=a.get("name", "")))

            return actions
        except Exception as exc:
            log.warning("Failed to parse reply via LLM: %s", exc)
            return []

    def _resolve_conflicts(self, actions: list[ReplyAction]) -> list[ReplyAction]:
        synthesize_paths: set[str] = set()
        skip_paths: set[str] = set()

        for action in actions:
            if isinstance(action, SynthesizeAction):
                synthesize_paths.update(action.source_paths)
            elif isinstance(action, SkipAction):
                skip_paths.update(action.source_paths)

        skip_paths -= synthesize_paths

        resolved: list[ReplyAction] = []
        if synthesize_paths:
            resolved.append(SynthesizeAction(sorted(synthesize_paths)))
        if skip_paths:
            resolved.append(SkipAction(sorted(skip_paths)))

        for action in actions:
            if isinstance(action, (AddFeedAction, RemoveFeedAction)):
                resolved.append(action)

        return resolved
