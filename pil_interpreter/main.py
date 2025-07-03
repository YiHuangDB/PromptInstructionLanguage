import argparse
import sys
import pprint

from .parser import load_pil_file
from .context import ExecutionContext
from .evaluator import Evaluator
from .exceptions import PILSyntaxError, PILSemanticError, PILError

def main():
    parser = argparse.ArgumentParser(description="PIL Interpreter")
    parser.add_argument("file", help="PIL file to execute")
    parser.add_argument("--trace", action="store_true", help="Enable detailed execution tracing")
    parser.add_argument("-i", "--input", action="append", help="Set input variables (e.g., -i name=value). Can be used multiple times.")
    # Future arguments: --config-file, --validate-only, etc.

    args = parser.parse_args()

    if args.trace:
        print("Tracing enabled.")

    try:
        if args.trace: print(f"Loading PIL file: {args.file}...")
        pil_program_data = load_pil_file(args.file)
        if args.trace: print("PIL file loaded and parsed successfully.")

        if args.trace:
            print("\nParsed PIL Program Structure:")
            pprint.pprint(pil_program_data)
            print("-" * 30)

        # Initialize ExecutionContext
        context = ExecutionContext()

        # Load input variables from CLI arguments into the context
        if args.input:
            if args.trace: print("\nLoading input variables from CLI:")
            for item in args.input:
                if '=' not in item:
                    print(f"Warning: Invalid input format '{item}'. Use 'name=value'. Skipping.", file=sys.stderr)
                    continue
                name, value = item.split('=', 1)
                context.set_variable(name, value)
                if args.trace: print(f"  Set variable: {name} = {value}")

        # Initialize Evaluator and run the workflow
        if args.trace: print("\nInitializing Evaluator...")
        evaluator = Evaluator(pil_program_data, context)

        if args.trace:
            print("\nInitial Execution Context:")
            print(context) # Print context after evaluator init (which might load config/persona)
            print("-" * 30)

        evaluator.run_workflow()

        if args.trace:
            print("\nFinal Execution Context:")
            print(context)
            print("-" * 30)
            print("PIL execution finished successfully.")


    except FileNotFoundError:
        print(f"Error: PIL file not found at '{args.file}'.", file=sys.stderr)
        sys.exit(1)
    except (PILSyntaxError, PILSemanticError) as e:
        print(f"Error in PIL file '{args.file}':\n{e}", file=sys.stderr)
        sys.exit(1)
    except PILError as e:
        print(f"An error occurred during PIL processing: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        if args.trace:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
