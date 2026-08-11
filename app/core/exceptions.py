class AppError(Exception):
    pass


class NotFoundError(AppError):
    def __init__(self, entity: str, entity_id: int) -> None:
        self.entity = entity
        self.entity_id = entity_id
        super().__init__(f"{entity} sa id={entity_id} ne postoji")


class AlreadyExistsError(AppError):
    def __init__(self, entity: str, field: str, value: str) -> None:
        self.entity = entity
        self.field = field
        self.value = value
        super().__init__(f"{entity} sa {field}='{value}' vec postoji")


class AuthenticationError(AppError):
    def __init__(self, detail: str = "Neispravni kredencijali") -> None:
        super().__init__(detail)


class PermissionDeniedError(AppError):
    def __init__(self, detail: str = "Nemate pravo pristupa") -> None:
        super().__init__(detail)


class RateLimitedError(AppError):
    def __init__(self, retry_after: int, detail: str = "Previse pokusaja") -> None:
        self.retry_after = retry_after
        super().__init__(detail)


class MeasurementRejectedError(AppError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
