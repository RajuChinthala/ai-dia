from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

try:  # Optional dependency when notebook execution is needed
    import nbformat  # type: ignore
    from nbclient import NotebookClient  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    nbformat = None  # type: ignore
    NotebookClient = None  # type: ignore


def run_notebook(
    notebook_path: str,
    working_dir: Optional[str] = None,
    output_path: Optional[str] = None,
    timeout: int = 1200,
) -> Optional[str]:
    """
    Execute a Jupyter notebook and optionally persist the executed copy.
    Returns the output path if written, otherwise None.
    """
    if nbformat is None or NotebookClient is None:
        raise ImportError(
            "Notebook execution requires nbformat and nbclient. "
            "Install them to enable notebook-driven forecasts."
        )

    nb_path = Path(notebook_path)
    if not nb_path.exists():
        raise FileNotFoundError(f"Notebook not found: {nb_path}")

    exec_dir = Path(working_dir).resolve() if working_dir else nb_path.parent.resolve()
    if not exec_dir.exists():
        raise FileNotFoundError(f"Working directory not found: {exec_dir}")

    project_root = Path(__file__).resolve().parents[1]
    previous_pythonpath = os.environ.get("PYTHONPATH")
    pythonpath_parts = [str(project_root)]
    if previous_pythonpath:
        pythonpath_parts.append(previous_pythonpath)
    os.environ["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    try:
        nb = nbformat.read(nb_path, as_version=4)
        kernel_name = (
            nb.get("metadata", {})
            .get("kernelspec", {})
            .get("name", "python3")
        )
        client = NotebookClient(
            nb,
            timeout=timeout,
            kernel_name=kernel_name,
            resources={"metadata": {"path": str(exec_dir)}},
        )
        client.execute()
    finally:
        if previous_pythonpath is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = previous_pythonpath

    if output_path:
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        nbformat.write(nb, out_path)
        return str(out_path)
    return None
