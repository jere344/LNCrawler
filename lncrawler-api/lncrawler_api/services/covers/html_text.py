from html.parser import HTMLParser


class HTMLTextExtractor(HTMLParser):
    """Strip HTML tags from a synopsis string."""

    def __init__(self):
        super().__init__()
        self.text = []

    def handle_data(self, data):
        self.text.append(data)

    def get_text(self):
        return ' '.join(self.text)
