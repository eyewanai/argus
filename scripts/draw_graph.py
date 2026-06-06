"""Generate runtime graph artifacts for Argus."""

from __future__ import annotations

from pathlib import Path

from argus.config import load_config
from argus.graph import build_graph

OUTPUT_DIR = Path("/tmp/argus")
MERMAID_PATH = OUTPUT_DIR / "runtime_graph.mmd"
PNG_PATH = OUTPUT_DIR / "runtime_graph.png"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if PNG_PATH.exists():
        PNG_PATH.unlink()

    config = load_config()
    graph = build_graph(config).get_graph()

    MERMAID_PATH.write_text(graph.draw_mermaid(), encoding="utf-8")

    png_warning: str | None = None
    try:
        graph.draw_mermaid_png(output_file_path=str(PNG_PATH))
    except Exception as exc:
        png_warning = str(exc)

    print(f"Runtime Mermaid graph: {MERMAID_PATH}")
    if PNG_PATH.exists():
        print(f"Runtime PNG graph: {PNG_PATH}")
    else:
        if png_warning:
            print(f"PNG graph warning: {png_warning}")
        else:
            print("PNG graph warning: rendering unavailable")


if __name__ == "__main__":
    main()
