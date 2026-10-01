import re
import unicodedata
from typing import Dict, List, Set, Union

from bs4 import Comment, Tag


class TextCleaner:
    """Cleans chapter HTML down to a flat sequence of <p> blocks.

    Ported from upstream lightnovel-crawler; the giant control-character map was
    replaced with a per-character category check to avoid building a ~1M entry
    dict for every crawler instance.
    """

    def __init__(self) -> None:
        self.line_separator = "<br>"

        self.bad_text_regex: Set[Union[str, re.Pattern]] = set()
        self.bad_tag_text_pairs: Dict[str, Union[str, re.Pattern, List]] = {}

        self.bad_tags: Set[str] = {
            "address", "amp-auto-ads", "audio", "button", "figcaption", "footer",
            "form", "header", "iframe", "input", "ins", "map", "nav", "noscript",
            "object", "output", "script", "select", "source", "style", "textarea",
            "tfoot", "video",
        }
        self.bad_css: Set[str] = {
            ".adblock-service", ".sharedaddy", ".saboxplugin-wrap", ".adbox",
            ".ads-middle", ".ads", ".adsbygoogle", ".adsense-code",
            ".cb_p6_patreon_button", ".code-block", ".ezoic-ad-adaptive",
            ".ezoic-ad", ".ezoic-adpicker-ad", ".googlepublisherads",
            ".inline-ad-slot", ".jp-relatedposts", ".wp-post-navigation",
            "a[href*='patreon.com']", "a[href*='paypal.me']",
        }
        self.p_block_tags: Set[str] = {
            "article", "aside", "div", "h1", "h2", "h3", "h4", "h5", "h6",
            "main", "p", "section",
        }
        self.unchanged_tags: Set[str] = {"canvas", "img", "pre"}
        self.plain_text_tags: Set[str] = {"a", "abbr", "acronym", "label", "span", "time"}
        self.substitutions: Dict[str, str] = {
            "<": "&lt;",
            ">": "&gt;",
            r"\u003c": "&lt;",
            r"\u003e": "&gt;",
        }
        self.whitelist_attributes: Set[str] = {
            "src", "style", "colspan", "rowspan", "headers", "scope", "axis", "id",
        }
        self.whitelist_css_property: Set[str] = {"font-style", "font-weight"}
        self.image_src_attributes: Set[str] = {"data-lazy-src", "data-src", "src"}

    # ------------------------------------------------------------------ #

    @staticmethod
    def _strip_nonprintable(text: str) -> str:
        return "".join(
            ch for ch in text if unicodedata.category(ch) not in ("Cf", "Cc")
        )

    def extract_contents(self, tag) -> str:
        self.clean_contents(tag)
        body = self.extract_paragraphs(tag)
        paragraphs = " ".join(body).split(self.line_separator)
        return "".join(
            f"<p>{p.strip()}</p>"
            for p in paragraphs
            if not self.contains_bad_texts(p)
        )

    def clean_contents(self, div):
        if not isinstance(div, Tag):
            return div

        if self.bad_css:
            for bad in div.select(",".join(self.bad_css)):
                bad.extract()

        if self.bad_tag_text_pairs:
            for tag in div.select(",".join(self.bad_tag_text_pairs.keys())):
                if self.tag_contains_bad_text(tag):
                    tag.extract()

        for tag in div.find_all(True):
            if isinstance(tag, Comment):
                tag.extract()
                continue
            if not isinstance(tag, Tag):
                continue
            if tag.name in self.bad_tags:
                tag.extract()
            elif tag.name in ("br", "hr"):
                self.extract_on_duplicate_sibling(tag)
            elif tag.name == "img":
                self.clean_image(tag)
            else:
                self.clean_attributes(tag)

        self.clean_attributes(div)
        return div

    def clean_text(self, text) -> str:
        text = self._strip_nonprintable(str(text)).strip()
        if not hasattr(self, "_subs_"):
            self._subs_ = re.compile(
                "|".join(f"({re.escape(x)})" for x in self.substitutions.keys()),
                flags=re.IGNORECASE,
            )
        text = self._subs_.sub(lambda m: self.substitutions[m.group(0).lower()], text)
        return text

    def extract_on_duplicate_sibling(self, tag: Tag) -> None:
        next_tag = tag.next_sibling
        if not isinstance(next_tag, Tag):
            return
        if next_tag.name == tag.name:
            tag.extract()

    def clean_attributes(self, tag: Tag) -> None:
        attrs = {}
        for name, value in tag.attrs.items():
            if name not in self.whitelist_attributes:
                continue
            if name == "style":
                value = self.clean_style_value(str(value))
            if value:
                attrs[name] = value
        tag.attrs = attrs

    def tag_contains_bad_text(self, tag: Tag) -> bool:
        pattern = self.bad_tag_text_pairs.get(tag.name)
        if not tag.text:
            return True
        if not pattern:
            return False
        if isinstance(pattern, list):
            pattern = "|".join(f"({x})" for x in pattern if x)
        if not isinstance(pattern, re.Pattern):
            pattern = re.compile(pattern, re.M)
            self.bad_tag_text_pairs[tag.name] = pattern
        return bool(pattern.search(tag.text))

    def clean_image(self, tag: Tag) -> None:
        src = None
        for name in self.image_src_attributes:
            src = tag.get(name)
            if src:
                break
        if not src:
            tag.extract()
        else:
            tag.attrs = {"src": src}

    def clean_style_value(self, style: str) -> str:
        clean_css = []
        css = {
            item[0].strip().lower(): item[1].strip()
            for item in [x.split(":", 1) for x in style.split(";")]
            if len(item) == 2 and item[0].strip()
        }
        for name in self.whitelist_css_property:
            value = css.get(name)
            if value:
                clean_css.append(f"{name}:{value}")
        return ";".join(clean_css)

    def extract_paragraphs(self, tag) -> list:
        if not isinstance(tag, Tag):
            return []

        body = []
        for elem in tag.contents:
            if isinstance(elem, Comment):
                continue
            if not isinstance(elem, Tag):
                body.append(self.clean_text(elem))
                continue
            if elem.name in self.unchanged_tags:
                body.append(str(elem))
                continue
            if elem.name in ("hr", "br"):
                body.append(self.line_separator)
                continue

            is_block = elem.name in self.p_block_tags
            is_plain = elem.name in self.plain_text_tags
            content = " ".join(self.extract_paragraphs(elem))

            if is_block:
                body.append(self.line_separator)

            for line in content.split(self.line_separator):
                line = line.strip()
                if not line:
                    continue
                if not (is_plain or is_block):
                    line = "<%s>%s</%s>" % (elem.name, line, elem.name)
                body.append(line)
                body.append(self.line_separator)

            if body and body[-1] == self.line_separator and not is_block:
                body.pop()

        return [x.strip() for x in body if x.strip()]

    def contains_bad_texts(self, text: str) -> bool:
        if not text.strip():
            return True
        if not self.bad_text_regex:
            return False
        if not hasattr(self, "__blacklist__"):
            pattern = re.compile("|".join("(%s)" % p for p in self.bad_text_regex))
            self.__blacklist__ = pattern
        return bool(self.__blacklist__.search(text))
