from dataclasses import dataclass, field


@dataclass
class DomainError(Exception):
    code: str
    message: str
    retryable: bool = False
    repair: dict = field(default_factory=dict)

    def as_dict(self):
        return {"code": self.code, "message": self.message,
                "retryable": self.retryable, "repair": self.repair}


def fail(code, message, retryable=False, **repair):
    raise DomainError(code, message, retryable, repair)
