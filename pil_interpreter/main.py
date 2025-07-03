import argparse
import sys
import pprint # For pretty printing the parsed structure

from .parser import load_pil_file
from .exceptions import PILSyntaxError, PILError # PILError for more general catches if needed

def main():
    parser = argparse.ArgumentParser(description="PIL Interpreter")
    parser.add_argument("file", help="PIL file to execute")
    parser.add_argument("--trace", action="store_true", help="Enable detailed execution tracing")
    # Future arguments: --config, --validate-only, etc.

    args = parser.parse_args()

    if args.trace:
        print("Tracing enabled.") # This will be used more later

    try:
        print(f"Loading PIL file: {args.file}...")
        pil_program_data = load_pil_file(args.file)
        print("PIL file loaded and parsed successfully.")

        if args.trace:
            print("\nParsed PIL Program Structure:")
            pprint.pprint(pil_program_data)
            print("-" * 30)

        # TODO:
        # 1. Build the execution context (from pil_interpreter.context)
        # 2. Evaluate the PIL program (using pil_interpreter.evaluator)
        #    - This will involve iterating through pil_program_data['workflow']['steps']
        # 3. Output results or handle program completion.

    except FileNotFoundError:
        print(f"Error: PIL file not found at '{args.file}'.", file=sys.stderr)
        sys.exit(1)
    except PILSyntaxError as e:
        print(f"Syntax Error in PIL file '{args.file}':\n{e}", file=sys.stderr)
        sys.exit(1)
    except PILError as e: # Catch other potential PIL-specific errors
        print(f"An error occurred during PIL processing: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e: # Catch any other unexpected errors
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        if args.trace:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
