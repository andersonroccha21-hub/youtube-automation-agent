"""One bounded local worker; the orchestrator remains the source of truth."""

from concurrent.futures import Future, ThreadPoolExecutor
from threading import RLock

from pipeline.approvals import PendingApproval
from pipeline.orchestrator import Orchestrator


class BusyRun(ValueError):
    pass


class Runner:
    def __init__(self):
        self.guard = RLock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="youtube-web")
        self.jobs: dict[str, Future] = {}
        self.errors: dict[str, str] = {}
        self.closed = False

    @staticmethod
    def key(run: Orchestrator) -> str:
        return str(run.root)

    def busy(self, run: Orchestrator) -> bool:
        with self.guard:
            return self.key(run) in self.jobs

    def assert_idle(self, run: Orchestrator):
        if self.busy(run):
            raise BusyRun("Esta execução já está rodando ou está na fila.")

    def submit(self, run: Orchestrator):
        with self.guard:
            self.assert_idle(run)
            if self.closed:
                raise BusyRun("O servidor está sendo encerrado.")
            if len(self.jobs) >= 8:
                raise BusyRun("A fila local está cheia. Aguarde uma execução terminar.")
            key = self.key(run)
            self.errors.pop(key, None)
            future = self.pool.submit(self._execute, run)
            self.jobs[key] = future

            def finished(done):
                with self.guard:
                    if not done.cancelled() and done.exception():
                        self.errors[key] = str(done.exception())
                    self.jobs.pop(key, None)

            future.add_done_callback(finished)

    @staticmethod
    def _execute(run: Orchestrator):
        try:
            run.run(interactive=False)
        except PendingApproval:
            pass

    def error(self, run: Orchestrator) -> str | None:
        with self.guard:
            return self.errors.get(self.key(run))

    def shutdown(self):
        with self.guard:
            self.closed = True
        self.pool.shutdown(wait=True, cancel_futures=True)
