import json
import sqlite3
from pathlib import Path
from typing import Annotated

import typer
import yaml

from qualitybridge.config import ConfigurationError, load_config
from qualitybridge.controller import run_project
from qualitybridge.history import HistoryStore

app = typer.Typer(
    no_args_is_help=True, help="QualityBridge — agente de testes pytest, Playwright e Jest."
)
ConfigOption = Annotated[Path, typer.Option("--config", "-c", help="Arquivo YAML do projeto.")]


@app.command()
def init(
    runner: Annotated[str, typer.Option(help="pytest, playwright ou jest")] = "pytest",
    config: ConfigOption = Path("qualitybridge.yaml"),
    name: Annotated[str, typer.Option(help="Nome do projeto")] = "Meu projeto",
):
    """Cria uma configuração inicial sem sobrescrever arquivos."""
    if runner not in ("pytest", "playwright", "jest"):
        raise typer.BadParameter("Use pytest, playwright ou jest.")

    quick_filter = {
        "pytest": "smoke",
        "playwright": "@smoke",
        "jest": "smoke",
    }

    data = {
        "version": 1,
        "project": name,
        "runner": runner,
        "root": ".",
        "output_dir": ".qualitybridge",
        "timeout_seconds": 300,
        "suites": {
            "full": {"paths": ["tests"]},
            "quick": {"paths": ["tests"], "filter": quick_filter[runner]},
        },
    }

    try:
        with config.open("x", encoding="utf-8") as stream:
            yaml.safe_dump(data, stream, allow_unicode=True, sort_keys=False)
    except FileExistsError:
        typer.echo(f"Arquivo já existe: {config}", err=True)
        raise typer.Exit(2)
    except OSError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2)

    typer.echo(f"Configuração criada: {config}. Ajuste os caminhos e marcadores dos testes.")


@app.command()
def validate(config: ConfigOption = Path("qualitybridge.yaml")):
    """Valida o YAML e os caminhos, sem executar testes."""
    try:
        settings, root, output = load_config(config)
    except ConfigurationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2)
    typer.echo(f"Configuração válida: {settings.project} ({settings.runner})")
    typer.echo(f"Projeto: {root}\nResultados: {output}\nSuítes: {', '.join(settings.suites)}")


@app.command()
def run(
    config: ConfigOption = Path("qualitybridge.yaml"),
    suite: Annotated[str, typer.Option("--suite", "-s")] = "full",
    docker: Annotated[
        bool, typer.Option(help="Executa na imagem docker definida no YAML.")
    ] = False,
    timeout: Annotated[int | None, typer.Option(min=1, max=86400)] = None,
):
    """Executa testes existentes, gera relatórios e registra o histórico."""
    try:
        result, directory = run_project(config, suite, docker, timeout)
    except (ConfigurationError, OSError) as exc:
        typer.echo(f"Erro: {exc}", err=True)
        raise typer.Exit(2)
    counts = result.counts
    typer.echo(
        f"{result.project}: {result.status.upper()} | {len(result.cases)} testes | "
        f"{counts['passed']} aprovados | {counts['failed']} falhas | "
        f"{counts['error']} erros | {counts['skipped']} ignorados"
    )
    typer.echo(f"Relatório: {directory / 'report.html'}")
    for message in result.diagnostics:
        typer.echo(message, err=True)
    code = {"passed": 0, "failed": 1, "error": 2, "no_tests": 2, "timeout": 124, "cancelled": 130}[
        result.status
    ]
    raise typer.Exit(code)


@app.command()
def history(
    config: ConfigOption = Path("qualitybridge.yaml"),
    limit: Annotated[int, typer.Option(min=1, max=1000)] = 10,
    as_json: Annotated[bool, typer.Option("--json")] = False,
):
    """Consulta o histórico de execuções do projeto."""
    try:
        settings, _, output = load_config(config)
        results = HistoryStore(output / "history.sqlite3").recent(settings.project, limit)
    except (ConfigurationError, sqlite3.Error, OSError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2)
    if as_json:
        typer.echo(
            json.dumps([r.model_dump(mode="json") for r in results], ensure_ascii=False, indent=2)
        )
    elif not results:
        typer.echo("Nenhuma execução registrada.")
    else:
        for result in results:
            typer.echo(
                f"{result.id} | {result.suite} | {result.status} | "
                f"{len(result.cases)} testes | {result.duration_seconds:.2f}s"
            )
