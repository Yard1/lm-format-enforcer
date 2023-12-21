from collections import defaultdict
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
import json

class TokenizerPrefixTreeNode:
    def __init__(self):
        self.tokens: List[int] = []
        self.children: Dict[str, TokenizerPrefixTreeNode] = {}

class ShortcutKey(Enum):
    JSON_FREETEXT = "json_freetext"
    BACKSLASH_ESCAPE = "backslash_escape"

class Shortcut(list):
    def __init__(self, iterable, *, key: ShortcutKey, characters_to_explore_processor: Optional[callable]):
        super().__init__(iterable)
        self.key = key
        self.characters_to_explore_processor = characters_to_explore_processor

class TokenizerPrefixTree:
    def __init__(self, regular_tokens: List[Tuple[int, str, bool]]):
        self.root = TokenizerPrefixTreeNode()
        self._create_shortcuts()
        self.new_word_tokens: Set[int] = set()
        self.tokens_to_strs = {token_idx: token_str for token_idx, token_str, _ in regular_tokens}

        from lmformatenforcer.characterlevelparser import JsonEscapingParser
        json_escaping_parser = JsonEscapingParser()

        for token_idx, decoded, is_new_word in regular_tokens:
            self._add_token_to_tree(decoded, token_idx, self.root)

            # Performance optimization - cache tokens that can appear immediately after a backslash.
            # We only cache tokens that are 100% valid after a backslash.
            parser = json_escaping_parser
            evaluated_len = 0
            if decoded[0] != "u" and '"' not in decoded[1:]:
                for character in decoded:
                    allowed_characters = parser.get_allowed_characters()
                    if character in allowed_characters:
                        parser = parser.add_character(character)
                    else:
                        break
                    evaluated_len += 1
                if evaluated_len > 0:
                    self.shortcuts[ShortcutKey.BACKSLASH_ESCAPE].append(token_idx)

            # Performance optimization - cache the tokens of all the strings that don't contain a quote in the middle, or a line break.
            # When we are in a JSON freetext string field, they will all be permitted and this will save a lot of tree iterations.
            has_quote_before_end = '"' in decoded[0:-1]
            has_newline = "\n" in decoded or "\r" in decoded

            if not (has_quote_before_end or has_newline):
                if '\\' in decoded[:-1]:
                    # If there is a backslash that is not trailing, we might be in an illegal json territory. Need to verify
                    # that is is a legal json character streak
                    try:
                        json.loads(f'"{decoded}"')
                    except json.decoder.JSONDecodeError:
                        continue
                self.shortcuts[ShortcutKey.JSON_FREETEXT].append(token_idx)
            if is_new_word:
                self.new_word_tokens.add(token_idx)

    def _create_shortcuts(self):
        self.shortcuts: Dict[ShortcutKey, Shortcut] = {}
        self.shortcuts[ShortcutKey.JSON_FREETEXT] = Shortcut([], key=ShortcutKey.JSON_FREETEXT, characters_to_explore_processor=lambda characters_to_explore: characters_to_explore.intersection(['"']))
        self.shortcuts[ShortcutKey.BACKSLASH_ESCAPE] = Shortcut([], key=ShortcutKey.BACKSLASH_ESCAPE, characters_to_explore_processor=lambda characters_to_explore: characters_to_explore.intersection(['u', '"']))


    def _add_token_to_tree(self, token_str: str, token_idx: int, node: TokenizerPrefixTreeNode):
        for character in token_str:
            if character not in node.children:
                node.children[character] = TokenizerPrefixTreeNode()
            node = node.children[character]
        node.tokens.append(token_idx)
