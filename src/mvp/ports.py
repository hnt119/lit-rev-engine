"""Only the three capabilities needed by the synchronous MVP service."""

from typing import Callable, Protocol, TypeVar

from .contracts import Paper, PreparedSource, SearchPreview, SearchRequest, WorkspaceHandle, WorkspaceSnapshot

T = TypeVar("T")


class MvpError(ValueError):
    """Safe domain/provider failure. Messages must never contain credentials."""

    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


class ProviderFailure(MvpError):
    pass


class DiscoveryProvider(Protocol):
    def search(self, request: SearchRequest) -> SearchPreview: ...


class SourceProvider(Protocol):
    def prepare(self, paper: Paper) -> PreparedSource: ...


class WorkspaceStorage(Protocol):
    def create(self, question: str) -> WorkspaceHandle: ...
    def create_reserved(self, handle: WorkspaceHandle, question: str) -> WorkspaceHandle: ...
    def read(self, handle: WorkspaceHandle) -> WorkspaceSnapshot: ...
    def read_serialized(self, handle: WorkspaceHandle, callback: Callable[[WorkspaceSnapshot], T]) -> T: ...
    def transact(self, handle: WorkspaceHandle, operation: str, request_id: str, fingerprint: str,
                 callback: Callable[[WorkspaceSnapshot], tuple[WorkspaceSnapshot, dict]]) -> dict: ...
    def transact_guarded(self, handle: WorkspaceHandle, operation: str, request_id: str, fingerprint: str,
                         callback: Callable[[WorkspaceSnapshot], tuple[WorkspaceSnapshot, dict]],
                         commit_guard: Callable) -> dict: ...
    def clear(self, handle: WorkspaceHandle) -> None: ...
    def clear_if_present(self, handle: WorkspaceHandle) -> None: ...
