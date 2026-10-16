from enum import Enum


class OutputFormat(str, Enum):
    json = "json"
    epub = "epub"
    text = "text"
