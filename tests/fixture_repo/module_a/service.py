from module_b.util import helper


class Service:
    def run(self, value: int) -> int:
        return helper(value)


def public_api(value: int) -> int:
    return helper(value)
