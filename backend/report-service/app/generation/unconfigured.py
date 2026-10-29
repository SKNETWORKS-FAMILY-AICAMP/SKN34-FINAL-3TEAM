"""The #50 foundation must not invent records or report a false completion."""


class GeneratorNotConfigured(RuntimeError):
    pass


class UnconfiguredGenerator:
    async def generate(self, command, report):
        raise GeneratorNotConfigured("Calculation/rendering pipeline is not configured")
