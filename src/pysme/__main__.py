# -*- coding: utf-8 -*-
import argparse
import sys

from .gui import plot_plotly
from .sme import SME_Structure
from .solve import SME_Solver
from .synthesize import Synthesizer


def main():
    parser = argparse.ArgumentParser(
        "pysme",
        description=(
            "Synthesizes stellar spectra and determines best fit parameters "
            "to observations."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # 'run' subcommand (default behavior)
    run_parser = subparsers.add_parser(
        "run",
        help="Run synthesis or fitting on an SME file",
    )
    run_parser.add_argument("file", help=".sme input file")
    run_parser.add_argument(
        "-s",
        "--synthesize",
        action="store_true",
        help="Only synthesize the spectrum, no fitting",
    )
    run_parser.add_argument("-o", "--output", help="Store the output to this file instead")
    run_parser.add_argument(
        "-p",
        "--plot",
        nargs="?",
        const=True,
        default=False,
        help="Create a plot with the results",
    )

    # 'gui' subcommand
    gui_parser = subparsers.add_parser(
        "gui",
        help="Start the web GUI server",
    )
    gui_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    gui_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)",
    )
    gui_parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't open browser automatically",
    )

    args = parser.parse_args()

    if args.command == "gui":
        from .gui.server import run_server

        run_server(host=args.host, port=args.port, open_browser=not args.no_browser)
    elif args.command == "run" or (args.command is None and len(sys.argv) > 1):
        if args.command is None:
            args = run_parser.parse_args()

        synthesize_only = args.synthesize
        filename = args.file
        output = args.output
        plot = args.plot
        if output is None:
            output = filename

        sme = SME_Structure.load(filename)
        if synthesize_only:
            syn = Synthesizer()
            sme = syn.synthesize_spectrum(sme)
        else:
            solver = SME_Solver()
            sme = solver.solve(sme, sme.fitparameters)
        sme.save(output)

        if plot:
            fig = plot_plotly.FinalPlot(sme)
            if plot is True:
                fig.show()
            else:
                fig.save(filename=plot, auto_open=False)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
