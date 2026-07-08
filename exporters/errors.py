"""导出层统一异常。"""


class ExportDependencyError(Exception):
    """某导出格式所需的第三方依赖缺失时抛出。

    携带结构化字段，便于 API 层直接序列化给调用方。
    """

    def __init__(self, fmt: str, missing_package: str, pip_install: str):
        self.format = fmt
        self.missing_package = missing_package
        self.pip_install = pip_install
        super().__init__(
            f"格式 {fmt} 不可用：缺少依赖 {missing_package}，请执行 `{pip_install}`"
        )
