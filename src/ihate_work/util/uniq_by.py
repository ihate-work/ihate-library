from collections.abc import Callable, Iterable


def uniq_by(values: Iterable, key: Callable) -> list:
    """
    Returns a list of unique items from the input iterable based on the provided key function.

    :param values: An iterable of items to filter for uniqueness.
    :param key: A function that extracts a key from each item.
    :return: A list of unique items based on the key.
    """
    keyed_values = {key(item): item for item in values}
    return list(keyed_values.values())
