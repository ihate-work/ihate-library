import random
from collections.abc import Hashable, Iterator

import plotly.graph_objects as go


class PrefixCounter:
    @staticmethod
    def from_tuples(values: Iterator[tuple[Hashable, ...]]) -> "PrefixCounter":
        pc = PrefixCounter()
        for v in values:
            pc.add(v)
        return pc

    @staticmethod
    def build_treemap(root: "PrefixCounter") -> go.Treemap:
        colors = [
            "pink",
            "royalblue",
            "lightgray",
            "cyan",
            "lightgray",
            "lightblue",
            "lightgreen",
        ]
        x = []
        stack: list[tuple[str, PrefixCounter]] = [("", root)]
        while stack:
            prefix, node = stack.pop()
            x.append(
                dict(
                    id=prefix,
                    label=prefix.split("/")[-1] if prefix else "root",
                    value=node.count,
                    parent="/".join(prefix.split("/")[:-1]) if prefix else "",
                    marker_color=colors[node.depth % len(colors)],
                )
            )
            for child_key, child_node in node.__children.items():
                child_prefix = f"{prefix}/{child_key}" if prefix else str(child_key)
                stack.append((child_prefix, child_node))
        return go.Treemap(
            labels=[item["label"] for item in x],
            ids=[item["id"] for item in x],
            parents=[item["parent"] for item in x],
            values=[item["value"] for item in x],
            marker_colors=[item["marker_color"] for item in x],
        )

    def __init__(self, prefix: Hashable | None = None) -> None:
        self.__children: dict[Hashable, PrefixCounter] = {}
        self.count: int = 0
        self.prefix = prefix
        # a reservoir of samples at the leaf node
        self.leaf_samples: list[Hashable] = []

    def add(self, value: tuple[Hashable, ...]) -> None:
        self.count += 1
        if len(value) == 0:
            return
        elif len(value) == 1:
            head = value[0]
            _add_reservoir(self.leaf_samples, head, 10)
            return

        head, *tail = value
        if head not in self.__children:
            self.__children[head] = PrefixCounter(prefix=head)
        self.__children[head].add(tuple(tail))

    @property
    def is_leaf(self) -> bool:
        return len(self.__children) == 0

    @property
    def depth(self) -> int:
        if self.is_leaf:
            return 0
        return 1 + max(child.depth for child in self.__children.values())

    @property
    def own_count(self) -> int:
        if self.is_leaf:
            return self.count

        return self.count - sum(child.count for child in self.__children.values())

    def __str__(self) -> str:
        return f"PrefixCounter(prefix={repr(self.prefix)} own_count={self.own_count}, count={self.count}, own_count_ratio={float(self.own_count) / self.count} depth={self.depth}, leaf_samples={repr(self.leaf_samples)})"

    def pprint(self, indent=0) -> list[str]:
        this = " " * indent + str(self)
        ret = [this]
        for child in sorted(self.__children.values(), key=lambda c: c.count, reverse=True):
            ret += child.pprint(indent + 2)

        return ret


def _add_reservoir(reservoir: list[Hashable], v: Hashable, capacity=100):
    if len(reservoir) < capacity:
        reservoir.append(v)
    else:
        idx = random.randint(0, len(reservoir) - 1)
        if idx < capacity:
            reservoir[idx] = v
