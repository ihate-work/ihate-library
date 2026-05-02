from .meta import create_redirection_getattr

__getattr__ = create_redirection_getattr(
    __name__,
    [
        ("Rater", "ihate_work.util.perf.rater", "Rater"),
    ],
)
