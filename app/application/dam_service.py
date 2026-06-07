from __future__ import annotations

import json as json_mod
import json
import math
import re
import shutil
from typing import Any

from bs4 import BeautifulSoup
import httpx

from app.application.dto import ServiceResult
from app.domain.entities import CharacterProfile

_DAM_QUOTE_CHARS = {'"', '\u201c', '\u201d', '\u00ab', '\u00bb'}
_DAM_ITALICS_QUOTE_CHARS = set('*')

_DAM_SYSTEM_PROMPT = """Attribute dialogue to characters from the list. You MUST process ALL paragraphs provided.

FORBIDDEN ACTIONS:
- NEVER merge multiple separate quotes from the same paragraph into a single string.
- Example 1: If the text is: "I have a flight to catch," she says. "I'm seeing my parents.", it is FORBIDDEN to output "I have a flight to catch, I'm seeing my parents."
- Example 2: If the text is: "You're doing good," she mumbles. "I need this.", it is FORBIDDEN to output "You're doing good, I need this."
- Instead, you MUST treat them as completely separate quotes and output a separate JSON object for each.

JSON OUTPUT FORMAT:
[{"par": <int>, "char": "<character_id>", "quote": "<exact_dialogue>"}, ...]

CRITICAL RULES:
1. `par` must match the paragraph number from its header (e.g. if the paragraph is under the header `[Paragraph 12]`, then `par` must be `12`).
2. `quote` must be ONLY the exact words inside the quotation marks. No narration.
3. If a paragraph has multiple separate quotes, you MUST create a separate JSON object in the array for EACH individual quote.
4. Do not stop until you have extracted and attributed EVERY quote from EVERY paragraph.
5. If a POV character is given, untagged quotes likely belong to them."""


_DAM_ITALICS_SYSTEM_PROMPT = """Attribute dialogue to characters from the list. You MUST process ALL paragraphs provided.

FORBIDDEN ACTIONS:
- NEVER merge multiple separate quotes from the same paragraph into a single string.
- Example 1: If the text is: *I have a flight to catch,* she thought. *I'm seeing my parents.*, it is FORBIDDEN to output *I have a flight to catch, I'm seeing my parents.*
- Example 2: If the text is: *You're doing good,* she thought. *I need this.*, it is FORBIDDEN to output *You're doing good, I need this.*
- Instead, you MUST treat them as completely separate quotes and output a separate JSON object for each.

JSON OUTPUT FORMAT:
[{"par": <int>, "char": "<character_id>", "quote": "*<exact_dialogue>*"}, ...]

CRITICAL RULES:
1. `par` must match the paragraph number from its header (e.g. if the paragraph is under the header `[Paragraph 12]`, then `par` must be `12`).
2. `quote` must be ONLY the exact words inside the asterisks `*` AND MUST INCLUDE the asterisks `*` themselves! No narration.
3. If a paragraph has multiple separate asterisk quotes, you MUST create a separate JSON object in the array for EACH individual quote.
4. Do not stop until you have extracted and attributed EVERY asterisk quote from EVERY paragraph. Keep going until the end of the text.
5. If a POV character is given, untagged quotes likely belong to them."""


def _dam_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "dam_response",
            "strict": True,
            "schema": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "par": {"type": "integer"},
                        "char": {"type": "string"},
                        "quote": {"type": "string"},
                    },
                    "required": ["par", "char", "quote"],
                    "additionalProperties": False,
                },
            },
        },
    }


def _dam_extract_paragraphs(chapter_html: str, include_italics: bool = False) -> list[dict[str, Any]]:
    """Extract block elements from chapter HTML, returning pid + text for each."""
    soup = BeautifulSoup(chapter_html or "", "lxml")
    body = soup.body or soup
    
    # Exclude author's notes and summaries from paragraph extraction
    for node in body.select("#chapter-preface-notes, #chapter-end-notes, #chapter-summary"):
        node.decompose()
        
    if include_italics:
        for tag in body.find_all(['i', 'em']):
            tag.insert_before("*")
            tag.insert_after("*")
            tag.unwrap()
        
    blocks: list[dict[str, Any]] = []
    for node in body.find_all(["p", "blockquote", "div"]):
        if node.name == "div" and node.find(["p", "blockquote", "div"]):
            continue
        text = node.get_text(" ", strip=True)
        if text:
            blocks.append({"pid": len(blocks), "text": text})
    return blocks


def _dam_has_dialogue(text: str, is_italics: bool = False) -> bool:
    chars = _DAM_ITALICS_QUOTE_CHARS if is_italics else _DAM_QUOTE_CHARS
    return bool(chars.intersection(text))


def _dam_extract_all_quotes(text: str, is_italics: bool = False) -> list[str]:
    """Robustly extract all text bounded by quotation marks, handling missing closing quotes."""
    quotes = []
    in_quote = False
    current_quote = []
    quote_chars = {'*'} if is_italics else {'"', '\u201c', '\u201d', '\u00ab', '\u00bb'}
    open_chars = quote_chars
    close_chars = quote_chars
    
    for char in text:
        if not in_quote:
            if char in open_chars:
                in_quote = True
                if is_italics:
                    current_quote.append(char)
        else:
            if char in close_chars or (is_italics and char == current_quote[0]):
                in_quote = False
                if is_italics:
                    current_quote.append(char)
                val = "".join(current_quote).strip()
                if val:
                    quotes.append(val)
                current_quote = []
            else:
                current_quote.append(char)
                
    if in_quote:
        val = "".join(current_quote).strip()
        if val:
            quotes.append(val)
            
    return quotes


def _normalize_snippet(t: str) -> str:
    return t.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"').casefold()


def _build_fuzzy_pattern(snippet: str) -> str:
    norm = _normalize_snippet(snippet)
    punct_chars = set(',.!?;:*""\u201c\u201d\u00ab\u00bb\u2018\u2019\'')
    pattern_parts = []
    for c in norm:
        if c.isspace():
            pattern_parts.append(r"\s*")
        elif c in punct_chars:
            pattern_parts.append(r"\s*" + re.escape(c) + r"\s*")
        else:
            pattern_parts.append(re.escape(c))
    pattern = "".join(pattern_parts)
    pattern = re.sub(r"(\\s\*)+", r"\\s*", pattern)
    return pattern


def _dam_match_snippet(snippet: str, paragraph_text: str, is_italics: bool = False) -> str:
    """Expand a quote snippet to the full dialogue string, rejecting if not in quotes."""
    snippet_clean = snippet.strip('""\u201c\u201d\u00ab\u00bb\u2018\u2019 .…*,')
    if len(snippet_clean) < 2:
        return ""
    
    snippet_norm = _normalize_snippet(snippet_clean)
    all_quotes = _dam_extract_all_quotes(paragraph_text, is_italics)
    
    # 1. Exact match (after stripping quotes/punctuation from both)
    for q in all_quotes:
        q_clean = _normalize_snippet(q).strip('""\u201c\u201d\u00ab\u00bb\u2018\u2019 .…*,')
        if snippet_norm == q_clean:
            return q
            
    # 2. Fuzzy regex match for spacing issues
    pattern = _build_fuzzy_pattern(snippet_clean)
    for q in all_quotes:
        q_norm = _normalize_snippet(q)
        if re.search(pattern, q_norm):
            return q
            
    return ""


def _dam_character_alias_map(characters: list[CharacterProfile]) -> dict[str, list[str]]:
    """Build {character_id: [name, alias1, ...]} from character profiles."""
    result: dict[str, list[str]] = {}
    for character in characters:
        aliases: list[str] = []
        for source in (character.name, character.full_name):
            clean = " ".join(str(source or "").split())
            if clean and clean not in aliases:
                aliases.append(clean)
            first = re.split(r"\s+", clean, maxsplit=1)[0].strip()
            if first and len(first) >= 3 and first not in aliases:
                aliases.append(first)
        for tag_url in character.tag_urls or []:
            parts = str(tag_url or "").strip("/").rsplit("/", 1)
            if len(parts) >= 2:
                label = parts[-1].replace("*s*", "'").replace("%20", " ").replace("*a*", "&").replace("_", " ").strip()
                if label and label not in aliases:
                    aliases.append(label)
        if aliases:
            result[character.id] = aliases
    return result


class DamService:
    """Dialogue attribution via LM Studio for Tinted Dialogue Mode."""

    def __init__(
        self,
        dam_repo: Any,
        lmstudio_provider: Any,
        character_repo: Any,
        reader_asset_repo: Any,
        settings_repo: Any,
    ) -> None:
        self.dam_repo = dam_repo
        self.lmstudio = lmstudio_provider
        self.characters = character_repo
        self.reader_assets = reader_asset_repo
        self.settings = settings_repo

    def get_attributions(self, work_id: str, chapter_idx: int) -> list[dict]:
        return self.dam_repo.get_attributions(work_id, chapter_idx)

    def get_dam_status(self, work_id: str, chapter_idx: int) -> str:
        return self.dam_repo.get_dam_status(work_id, chapter_idx)

    def clear_attributions(self, work_id: str, chapter_idx: int) -> ServiceResult:
        from app.infrastructure.config.paths import AUDIO_CACHE_DIR

        try:
            self.dam_repo.clear_attributions(work_id, chapter_idx)
            audio_dir = AUDIO_CACHE_DIR / str(work_id) / f"ch{chapter_idx}"
            if audio_dir.exists():
                shutil.rmtree(audio_dir, ignore_errors=True)
            return ServiceResult(True, "Attributions cleared.")
        except Exception as exc:  # noqa: BLE001
            return ServiceResult(False, f"Failed to clear attributions: {exc}")

    def mark_stale(self, work_id: str) -> None:
        self.dam_repo.mark_stale_for_work(work_id)

    def run_attribution(
        self,
        work_id: str,
        chapter_idx: int,
        chapter_html: str,
        fandom_key: str,
        pov_character_id: str | None = None,
        auto_unload: bool = True,
    ) -> ServiceResult:
        model = None
        try:
            self.dam_repo.set_dam_status(work_id, chapter_idx, "pending")
            
            characters = self.characters.list_for_fandom(fandom_key)
            alias_map = _dam_character_alias_map(characters)
            if not alias_map:
                self.dam_repo.set_dam_status(work_id, chapter_idx, "none")
                return ServiceResult(False, "No characters found for fandom.")

            # Create short IDs for the LLM payload to save tokens
            short_to_uuid = {}
            uuid_to_short = {}
            for i, cid in enumerate(alias_map.keys(), 1):
                short_id = f"c{i}"
                short_to_uuid[short_id.casefold()] = cid
                uuid_to_short[cid] = short_id
                for alias in alias_map[cid]:
                    short_to_uuid[alias.strip().casefold()] = cid

            char_lines_list = []
            for cid, aliases in alias_map.items():
                short_id = uuid_to_short[cid]
                char_profile = next((c for c in characters if c.id == cid), None)
                
                pronoun_str = ""
                if char_profile and char_profile.pronoun_type == "F":
                    pronoun_str = " (female - she/her)"
                elif char_profile and char_profile.pronoun_type == "M":
                    pronoun_str = " (male - he/him)"
                
                char_lines_list.append(f"{short_id}: {aliases[0]}{pronoun_str}")
            char_lines = "\n".join(char_lines_list)
            
            pov_line = ""
            if pov_character_id and pov_character_id in alias_map:
                pov_name = alias_map[pov_character_id][0]
                short_pov = uuid_to_short[pov_character_id]
                pov_line = f"POV: {pov_name} ({short_pov})\n"

            model = self.lmstudio.model
            if not model:
                self.dam_repo.set_dam_status(work_id, chapter_idx, "none")
                return ServiceResult(False, "Choose an LM Studio model in Settings first.")

            flat: list[dict] = []
            dam_seq = 0
            
            passes = [
                ("standard", False, _DAM_SYSTEM_PROMPT),
                ("italics", True, _DAM_ITALICS_SYSTEM_PROMPT)
            ]
            
            debug_logs = {}

            for pass_name, is_italics, sys_prompt in passes:
                paragraphs = _dam_extract_paragraphs(chapter_html, include_italics=is_italics)
                if not paragraphs:
                    continue
                    
                dialogue_pids = [p["pid"] for p in paragraphs if _dam_has_dialogue(p["text"], is_italics=is_italics)]
                if not dialogue_pids:
                    continue

                if not is_italics:
                    selected_paragraphs = paragraphs
                else:
                    included_indices = set()
                    n_paras = len(paragraphs)
                    for pid in dialogue_pids:
                        for offset in (-1, 0, 1):
                            idx = pid + offset
                            if 0 <= idx < n_paras:
                                included_indices.add(idx)
                    sorted_indices = sorted(list(included_indices))
                    selected_paragraphs = [paragraphs[i] for i in sorted_indices]

                total_words = sum(len(p["text"].split()) for p in selected_paragraphs)
                
                if total_words <= 5000:
                    chunks_paragraphs = [selected_paragraphs]
                else:
                    N = math.ceil(total_words / 5000)
                    cum_words = []
                    w_sum = 0
                    for p in selected_paragraphs:
                        w_sum += len(p["text"].split())
                        cum_words.append(w_sum)
                        
                    boundaries = [0]
                    for k in range(1, N):
                        target = k * (total_words / N)
                        closest_idx = min(range(len(cum_words)), key=lambda i: abs(cum_words[i] - target))
                        if closest_idx > boundaries[-1]:
                            boundaries.append(closest_idx)
                        else:
                            boundaries.append(boundaries[-1] + 1)
                    boundaries.append(len(selected_paragraphs))
                    
                    chunks_paragraphs = []
                    for idx in range(N):
                        s_idx = boundaries[idx]
                        e_idx = boundaries[idx+1]
                        if idx > 0:
                            s_idx = max(0, s_idx - 5)
                        chunks_paragraphs.append(selected_paragraphs[s_idx:e_idx])

                all_chunk_results = []
                all_chunk_payloads = []
                pid_to_text = {p["pid"]: p["text"] for p in paragraphs}

                for chunk_idx, chunk_paragraphs in enumerate(chunks_paragraphs):
                    chunk_dialogue_pids = [p["pid"] for p in chunk_paragraphs if _dam_has_dialogue(p["text"], is_italics=is_italics)]
                    if is_italics and not chunk_dialogue_pids:
                        continue

                    para_lines = "\n\n".join(
                        f"[Paragraph {p['pid']}]\n{p['text']}" for p in chunk_paragraphs
                    )
                    user_content = (
                        f"Characters:\n{char_lines}\n\n"
                        f"{pov_line}"
                        f"Paragraphs:\n{para_lines}"
                    )

                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": user_content},
                        ],
                        "response_format": _dam_response_format(),
                        "stream": False,
                    }

                    temp_val = self.settings.get("lmstudio_temperature")
                    if temp_val is not None:
                        payload["temperature"] = float(temp_val)

                    ctx_len = self.settings.get("lmstudio_context_length")
                    if ctx_len:
                        payload["max_tokens"] = int(ctx_len)

                    with httpx.Client(timeout=self.lmstudio.timeout) as client:
                        response = client.post(
                            f"{self.lmstudio.base_url}/chat/completions",
                            json=payload,
                        )
                        response.raise_for_status()
                        data = response.json()

                    content = data["choices"][0]["message"]["content"]
                    result = json.loads(content)
                    all_chunk_results.extend(result)
                    all_chunk_payloads.append(payload)

                debug_logs[pass_name] = {
                    "payload": all_chunk_payloads[0] if len(all_chunk_payloads) == 1 else {"chunks": len(all_chunk_payloads), "first": all_chunk_payloads[0]} if all_chunk_payloads else {},
                    "raw_response": json.dumps(all_chunk_results),
                    "parsed": all_chunk_results,
                    "chunk_count": len(chunks_paragraphs),
                }
                
                seen_attributions = set()
                for entry in all_chunk_results:
                    if not isinstance(entry, dict):
                        continue
                    pid = int(entry.get("par", -1))
                    short_sid = str(entry.get("char", "")).strip().casefold()
                    q_text = str(entry.get("quote", "")).strip()
                    
                    sid = short_to_uuid.get(short_sid, "")
                    if pid < 0 or not sid or len(q_text) < 2:
                        continue
                        
                    dup_key = (pid, q_text.lower())
                    if dup_key in seen_attributions:
                        continue
                    seen_attributions.add(dup_key)
                        
                    p_text = pid_to_text.get(pid, "")
                    if p_text:
                        q_text = _dam_match_snippet(q_text, p_text, is_italics)
                    else:
                        q_text = q_text.strip('""\u201c\u201d\u00ab\u00bb\u2018\u2019 *')
                    
                    if not q_text:
                        continue
                        
                    if is_italics:
                        # Strip asterisks
                        if q_text.startswith("*") and q_text.endswith("*"):
                            inner_text = q_text[1:-1].strip()
                            if len(inner_text.split()) == 1:
                                is_alias = False
                                lower_inner = inner_text.lower()
                                for aliases in alias_map.values():
                                    if lower_inner in [a.lower() for a in aliases]:
                                        is_alias = True
                                        break
                                if is_alias:
                                    continue
                            q_text = inner_text
                        else:
                            # Might be malformed from match snippet
                            q_text = q_text.replace("*", "")

                    flat.append({
                        "pid": pid,
                        "dam_seq": dam_seq,
                        "quote_text": q_text,
                        "speaker_id": sid,
                        "confidence": "high",
                        "is_italics": 1 if is_italics else 0
                    })
                    dam_seq += 1

            # Debug logs to logs directory
            from app.infrastructure.config.paths import ROOT_DIR
            log_dir = ROOT_DIR / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            for pass_name, log_data in debug_logs.items():
                log_file_path = log_dir / f"dam_debug_log_{pass_name}.json"
                with open(log_file_path, "w", encoding="utf-8") as f:
                    json_mod.dump(log_data, f, indent=2)

            if not flat:
                self.dam_repo.set_dam_status(work_id, chapter_idx, "none")
                return ServiceResult(False, "No valid dialogue matched after processing.")

            self.dam_repo.upsert_attributions(work_id, chapter_idx, flat, model)
            count = len(flat)
            return ServiceResult(
                True,
                f"Attributed {count} dialogue{'s' if count != 1 else ''}.",
                payload={"count": count},
            )

        except httpx.HTTPStatusError as exc:
            self.dam_repo.set_dam_status(work_id, chapter_idx, "none")
            return ServiceResult(False, f"LM Studio HTTP error: {exc.response.status_code}")
        except httpx.ConnectError:
            self.dam_repo.set_dam_status(work_id, chapter_idx, "none")
            return ServiceResult(False, "Cannot connect to LM Studio. Is it running?")
        except Exception as exc:  # noqa: BLE001
            self.dam_repo.set_dam_status(work_id, chapter_idx, "none")
            return ServiceResult(False, f"Attribution failed: {exc}")
        finally:
            if model and auto_unload and self.settings.get("lmstudio_auto_unload", False):
                try:
                    instance_id = self.lmstudio.loaded_instance_id(model)
                    if instance_id:
                        self.lmstudio.unload_model(instance_id)
                except Exception:
                    pass
