"""Runtime options. Kept intentionally tiny; the API runs with sane defaults."""


class Args:
    # Chapter body handling
    add_source_url: bool = False
    ignore_images: bool = False
    pack_by_volume: bool = False

    # Login (unused in the API flow, present for source compatibility)
    login: bool = False
    username: str = ""
    password: str = ""


_args = Args()


def get_args() -> Args:
    return _args
