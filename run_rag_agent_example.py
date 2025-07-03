from pil_engine.interpreter import PilParser, Interpreter
from pil_engine.core.context import Context
import yaml # For printing dicts nicely
import sys
import os

# Ensure the pil_engine module can be found
# This is for running the script directly from the project root
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

def main():
    parser = PilParser()
    example_file_path = "examples/rag_agent.pil"

    print(f"--- Loading PIL Program: {example_file_path} ---")
    try:
        pil_program = parser.parse_yaml_file(example_file_path)
        print("PIL Program loaded successfully.")
    except Exception as e:
        print(f"Error loading PIL program: {e}")
        return

    print("\n--- Initializing Interpreter ---")
    # No initial variables needed for context here, as they come from 'inputs' to run()
    interpreter = Interpreter(pil_program)

    user_question = "What is the capital of France and what are its main attractions according to the retrieved context?"
    inputs_for_run = {
        "question": user_question
    }

    print(f"\n--- Running RAG Agent with Question: '{user_question}' ---")
    try:
        # The 'output_object' defined in the last step of rag_agent.pil
        # is implicitly the final result if we consider the last def_var.
        # The interpreter's run method currently returns the output of the last step.
        final_result = interpreter.run(inputs=inputs_for_run)

        print("\n--- RAG Agent Execution Finished ---")

        print("\n--- Final Output Object (from last step 'output_object') ---")
        if isinstance(final_result, dict):
            print(yaml.dump(final_result, indent=2, sort_keys=False, default_flow_style=False))
        else:
            print(final_result)

        print("\n--- Full Context After Execution ---")
        all_context_vars = interpreter.context.get_all_variables()
        # Remove persona from context for cleaner printing if it exists
        if '__persona__' in all_context_vars:
            del all_context_vars['__persona__']
        print(yaml.dump(all_context_vars, indent=2, sort_keys=False, default_flow_style=False))

    except ValueError as e:
        print(f"Input validation or execution error: {e}")
    except KeyError as e:
        print(f"Context variable error during execution: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during interpretation: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
