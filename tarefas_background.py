from __future__ import annotations

import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class _Tarefa:
    future: Future
    percentual: float = 0.0
    etapa: str = "Iniciando"
    detalhe: str = ""
    lock: threading.Lock = field(default_factory=threading.Lock)


class GerenciadorTarefas:
    """Gerenciador simples de tarefas em background para uso com Streamlit.

    A função iniciada deve aceitar os argumentos normais e, por último,
    um callback ``progresso(percentual, etapa, detalhe='')``.
    """

    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="deep-bg")
        self._tarefas: dict[str, _Tarefa] = {}
        self._lock = threading.Lock()

    def iniciar(self, funcao: Callable[..., Any], *args: Any) -> str:
        tarefa_id = uuid.uuid4().hex

        # Criamos a entrada antes de executar para que o callback consiga atualizá-la.
        placeholder: dict[str, _Tarefa] = {}

        def progresso(percentual: float, etapa: str, detalhe: str = "") -> None:
            tarefa = placeholder.get("tarefa")
            if tarefa is None:
                return
            with tarefa.lock:
                tarefa.percentual = max(0.0, min(1.0, float(percentual)))
                tarefa.etapa = str(etapa)
                tarefa.detalhe = str(detalhe or "")

        def runner():
            return funcao(*args, progresso)

        future = self._executor.submit(runner)
        tarefa = _Tarefa(future=future)
        placeholder["tarefa"] = tarefa

        with self._lock:
            self._tarefas[tarefa_id] = tarefa

        return tarefa_id

    def obter(self, tarefa_id: str) -> _Tarefa | None:
        with self._lock:
            return self._tarefas.get(str(tarefa_id))

    def remover(self, tarefa_id: str) -> None:
        with self._lock:
            self._tarefas.pop(str(tarefa_id), None)

    def progresso(self, tarefa_id: str) -> tuple[float, str, str] | None:
        tarefa = self.obter(tarefa_id)
        if tarefa is None:
            return None
        with tarefa.lock:
            return tarefa.percentual, tarefa.etapa, tarefa.detalhe


_GERENCIADOR = GerenciadorTarefas()


def obter_gerenciador_tarefas() -> GerenciadorTarefas:
    return _GERENCIADOR


def acompanhar_tarefa(tarefa_id: str):
    """Aguarda a tarefa terminar e devolve o resultado.

    Mantém a interface que ``pagina_desmembramento.py`` espera.
    """
    tarefa = _GERENCIADOR.obter(str(tarefa_id))
    if tarefa is None:
        raise RuntimeError("A tarefa não está mais disponível no servidor.")

    try:
        return tarefa.future.result()
    finally:
        _GERENCIADOR.remover(str(tarefa_id))
