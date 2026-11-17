"""Command-line interface for ExperimentLens."""

import argparse
import os
from pathlib import Path
import sys
from typing import Sequence

from .analyzer import analyze_experiments
from .errors import ConnectorError, DataValidationError, ExperimentLensError, InputError
from .importer import load_experiments
from .reporter import export_summary_csv, generate_html_report, generate_report


def _parse_directions(items: list[str] | None) -> dict[str, str]:
    directions: dict[str, str] = {}
    for item in items or ():
        if "=" not in item:
            raise DataValidationError(
                f"invalid --direction {item!r}; expected format METRIC=higher or METRIC=lower"
            )
        metric, direction = item.split("=", 1)
        metric = metric.strip()
        direction = direction.strip()
        if not metric or not direction:
            raise DataValidationError(
                f"invalid --direction {item!r}; metric and direction must be non-empty"
            )
        directions[metric] = direction
    return directions


def _is_same_file_or_resolved(p1: Path, p2: Path) -> bool:
    """Check if two paths point to the same physical file (resolving symlinks and hardlinks)."""
    try:
        resolved_1 = p1.resolve()
    except OSError:
        resolved_1 = p1.absolute()
    try:
        resolved_2 = p2.resolve()
    except OSError:
        resolved_2 = p2.absolute()

    if resolved_1 == resolved_2:
        return True

    # Use os.path.samefile to detect hard links on existing files
    try:
        if p1.exists() and p2.exists() and os.path.samefile(p1, p2):
            return True
    except (OSError, ValueError):
        pass

    return False


def _validate_output_paths(
    imported_sources: set[str],
    output_markdown: str | None,
    output_csv: str | None,
    output_html: str | None,
) -> None:
    """Ensure output destination paths do not overwrite any input data files or collide with each other."""
    input_paths: list[Path] = []
    for src in imported_sources:
        try:
            p = Path(src)
            if p.exists():
                input_paths.append(p)
        except OSError:
            pass

    out_map: dict[str, Path] = {}
    if output_markdown:
        out_map["--output"] = Path(output_markdown)
    if output_csv:
        out_map["--csv-output"] = Path(output_csv)
    if output_html:
        out_map["--html-output"] = Path(output_html)

    # Check for collision with imported input files (handles path equality, symlinks, and hard links)
    for opt_name, out_p in out_map.items():
        for in_p in input_paths:
            if _is_same_file_or_resolved(out_p, in_p):
                raise InputError(
                    f"output path {str(out_p)!r} specified by {opt_name} conflicts with input data file {str(in_p)!r}"
                )

    # Check for collision among output paths
    checked_outputs: list[tuple[str, Path]] = []
    for opt_name, out_p in out_map.items():
        for prev_opt, prev_p in checked_outputs:
            if _is_same_file_or_resolved(out_p, prev_p):
                raise InputError(
                    f"output path {str(out_p)!r} specified by {opt_name} conflicts with {prev_opt}"
                )
        checked_outputs.append((opt_name, out_p))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="experimentlens",
        description="ExperimentLens: unified experiment import, comparability validation, and report generation.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="Experiment files or directories to import (e.g., examples/experiments).",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Path to write the Markdown report. Prints to stdout if omitted.",
    )
    parser.add_argument(
        "--csv-output",
        help="Optional path to export the standardized CSV summary table.",
    )
    parser.add_argument(
        "--html-output",
        help="Optional path to export a static HTML report with charts.",
    )
    parser.add_argument(
        "--sort-by",
        help="Metric name used to sort comparable experiments (e.g., f1).",
    )
    parser.add_argument(
        "--direction",
        action="append",
        default=[],
        metavar="METRIC=DIR",
        help="Override metric optimization direction, e.g. --direction f1=higher --direction loss=lower.",
    )
    parser.add_argument(
        "--disable-connector",
        action="append",
        default=[],
        metavar="NAME",
        help="Disable a connector by name (e.g., --disable-connector json).",
    )
    parser.add_argument(
        "--filter-dataset",
        help="Only analyze experiments matching this dataset name.",
    )
    parser.add_argument(
        "--filter-model",
        help="Only analyze experiments matching this model name.",
    )
    parser.add_argument(
        "--filter-id",
        action="append",
        default=[],
        metavar="EXP_ID",
        help="Only analyze experiments with the specified experiment_id (repeatable).",
    )
    parser.add_argument(
        "--strict-comparability",
        action="store_true",
        help="Fail with a validation error if imported experiments are not comparable or have missing metrics.",
    )
    parser.add_argument(
        "--title",
        default="ExperimentLens 实验结果统一分析报告",
        help="Custom title for generated reports.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        disabled = {name.strip() for name in args.disable_connector if name.strip()} or None
        directions = _parse_directions(args.direction)
        records = load_experiments(args.paths, disabled_connectors=disabled)

        # Guard against output paths overwriting input files or each other (including hardlinks/symlinks)
        imported_sources = {r.source for r in records if r.source}
        _validate_output_paths(imported_sources, args.output, args.csv_output, args.html_output)

        analysis = analyze_experiments(
            records,
            sort_by=args.sort_by,
            metric_directions=directions,
            strict_comparability=args.strict_comparability,
            filter_dataset=args.filter_dataset,
            filter_model=args.filter_model,
            filter_ids=args.filter_id or None,
        )
        markdown = generate_report(analysis, title=args.title)

        if args.output:
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(markdown, encoding="utf-8")
        else:
            sys.stdout.write(markdown + "\n")

        if args.csv_output:
            export_summary_csv(analysis, args.csv_output)

        if args.html_output:
            html_path = Path(args.html_output)
            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text(generate_html_report(analysis, title=args.title), encoding="utf-8")

        return 0
    except ConnectorError as exc:
        sys.stderr.write(f"[ERROR] ({type(exc).__name__}) {exc}\n")
        return 3
    except ExperimentLensError as exc:
        sys.stderr.write(f"[ERROR] ({type(exc).__name__}) {exc}\n")
        return 2
    except OSError as exc:
        sys.stderr.write(f"[ERROR] (OSError) cannot write output file: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
