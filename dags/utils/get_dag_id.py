"""
Extract the dag_id from an Airflow DAG file using AST parsing.
Exits 0 and prints the dag_id if found; exits 1 if not.

Usage:
    python get_dag_id.py /opt/airflow/dags/download_files.py
"""

import ast
import sys


def get_dag_id(filepath: str) -> str | None:
    try:
        with open(filepath) as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except (OSError, SyntaxError):
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_dag_call = (isinstance(func, ast.Name) and func.id == "DAG") or (
            isinstance(func, ast.Attribute) and func.attr == "DAG"
        )
        if is_dag_call and node.args:
            try:
                return str(ast.literal_eval(node.args[0]))
            except (ValueError, TypeError):
                pass
        # Also handle dag_id as keyword argument: DAG(dag_id="foo")
        if is_dag_call:
            for kw in node.keywords:
                if kw.arg == "dag_id":
                    try:
                        return str(ast.literal_eval(kw.value))
                    except (ValueError, TypeError):
                        pass
    return None


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <dag_file>", file=sys.stderr)
        sys.exit(1)

    dag_id = get_dag_id(sys.argv[1])
    if dag_id is None:
        sys.exit(1)

    print(dag_id)
