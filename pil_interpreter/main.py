import argparse
import sys
import pprint
import os
from dotenv import load_dotenv
import openai # Import OpenAI

from .parser import load_pil_file
from .context import ExecutionContext
from .evaluator import Evaluator
from .exceptions import PILSyntaxError, PILSemanticError, PILError

def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="PIL Interpreter")
    parser.add_argument("file", help="PIL file to execute")
    parser.add_argument("--trace", action="store_true", help="Enable detailed execution tracing")
    parser.add_argument("-i", "--input", action="append", help="Set input variables (e.g., -i name=value). Can be used multiple times.")

    args = parser.parse_args()

    if args.trace:
        print("Tracing enabled.")

    api_key = os.getenv("OPENAI_API_KEY")
    openai_client = None

    if api_key:
        try:
            openai_client = openai.OpenAI(api_key=api_key)
            if args.trace: print("OpenAI client initialized successfully.")
        except Exception as e:
            print(f"Warning: Failed to initialize OpenAI client: {e}", file=sys.stderr)
            openai_client = None # Ensure client is None if initialization fails
    else:
        if args.trace:
            print("Warning: OPENAI_API_KEY not found. LLM calls will be mocked.", file=sys.stderr)
            print("           Please set it in your environment or a .env file for actual LLM calls.", file=sys.stderr)

    try:
        if args.trace: print(f"Loading PIL file: {args.file}...")
        pil_program_data = load_pil_file(args.file)
        if args.trace: print("PIL file loaded and parsed successfully.")

        if args.trace:
            print("\nParsed PIL Program Structure:")
            pprint.pprint(pil_program_data)
            print("-" * 30)

        context = ExecutionContext()

        if args.input:
            if args.trace: print("\nLoading input variables from CLI:")
            for item in args.input:
                if '=' not in item:
                    print(f"Warning: Invalid input format '{item}'. Use 'name=value'. Skipping.", file=sys.stderr)
                    continue
                name, value = item.split('=', 1)
                context.set_variable(name, value)
                if args.trace: print(f"  Set variable: {name} = {value}")

        if args.trace: print("\nInitializing Evaluator...")
        evaluator = Evaluator(pil_program_data, context, openai_client=openai_client)

        if args.trace:
            print("\nInitial Execution Context (before workflow):")
            print(context)
            print("-" * 30)

        evaluator.run_workflow()

        if args.trace:
            print("\nFinal Execution Context (after workflow):")
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
