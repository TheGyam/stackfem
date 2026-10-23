"""Command line: `stackfem <command> params/module.toml`."""

import argparse
import shutil
import sys
from pathlib import Path

from . import geometry, mesh, params, post, quality, study


def main(argv=None):
    parser = argparse.ArgumentParser(prog="stackfem", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in [
        ("geometry", "write the stack as a STEP file"),
        ("mesh", "mesh one level and run the quality checks, without solving"),
        ("run", "mesh, check and solve one level (the baseline is level 0)"),
        ("study", "run every level, then write the convergence table and plots"),
        ("post", "redo the table and plots from an existing results folder"),
    ]:
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("params", help="the parameter file, e.g. params/module.toml")
        sub.add_argument("--out", help="results folder (default: results/<name>)")
        if name in ("mesh", "run"):
            sub.add_argument("--level", type=int, default=0)
    args = parser.parse_args(argv)

    try:
        p = params.load(args.params)
    except (ValueError, KeyError) as e:
        sys.exit(f"{args.params}: {e}")
    out = Path(args.out or Path("results") / p["name"])
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy(args.params, out / "params.toml")  # keep the inputs next to the results

    try:
        if args.command == "geometry":
            geometry.write_step(p, out / f"{p['name']}.step")
            print(f"wrote {out / (p['name'] + '.step')}")
        elif args.command == "mesh":
            data = mesh.generate(p, args.level, msh_path=out / f"mesh_level_{args.level}.msh")
            print(f"level {args.level}: {len(data['nodes'])} nodes")
            print(quality.table(data["quality"]))
        elif args.command == "run":
            row = study.run_level(p, args.level, out)
            study.write_summary([row], out / "summary.csv")
            print(post.report(p, out))
        elif args.command == "study":
            study.run_all(p, out)
            print(post.report(p, out))
        elif args.command == "post":
            print(post.report(p, out))
    except (quality.QualityError, FileNotFoundError, RuntimeError) as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
