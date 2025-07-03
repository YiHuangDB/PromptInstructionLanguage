import sys # For print to stderr
import openai
from openai import APIError
import jinja2 # Added
import json # Added

from .context import ExecutionContext
from .exceptions import PILSemanticError, PILSyntaxError, PILError

DEFAULT_MODEL = "gpt-3.5-turbo"

class Evaluator:
    def __init__(self, pil_program_data: dict, context: ExecutionContext, openai_client: openai.OpenAI | None = None):
        if not isinstance(pil_program_data, dict):
            raise PILSyntaxError("PIL program data must be a dictionary.")
        if not isinstance(context, ExecutionContext):
            raise TypeError("Context must be an instance of ExecutionContext.")
        if openai_client is not None and not isinstance(openai_client, openai.OpenAI):
            raise TypeError("openai_client must be an instance of openai.OpenAI or None.")

        self.program_data = pil_program_data
        self.context = context
        self.openai_client = openai_client

        # Initialize Jinja2 environment
        self.jinja_env = jinja2.Environment(
            loader=jinja2.BaseLoader(), # We're loading templates from strings, not files
            undefined=jinja2.Undefined # Default behavior: undefined variables render as empty strings
            # For stricter undefined variable handling, use: undefined=jinja2.StrictUndefined
        )

        if "config" in self.program_data and isinstance(self.program_data["config"], dict):
            self.context.set_global_parameters(self.program_data["config"].get("parameters", {}))
            if "model" in self.program_data["config"]:
                 self.context.global_parameters["model"] = self.program_data["config"]["model"]

        if "persona" in self.program_data and isinstance(self.program_data["persona"], dict):
            self.context.set_persona(self.program_data["persona"])

    def _substitute_variables(self, text: str) -> str:
        if not isinstance(text, str):
            return text # Or raise a TypeError if strict typing is preferred for text inputs

        try:
            template = self.jinja_env.from_string(text)
            # Provide all context variables to the template
            rendered_text = template.render(self.context.variables)
            return rendered_text
        except jinja2.exceptions.TemplateSyntaxError as e:
            # Handle cases where the text itself might have Jinja2 syntax errors
            # For example, an unclosed {{ or an invalid filter.
            print(f"Warning: Jinja2 syntax error during variable substitution: {e}", file=sys.stderr)
            # Fallback: return original text or raise a specific PIL error
            return text
        except Exception as e:
            # Catch other potential rendering errors
            print(f"Warning: Unexpected error during Jinja2 variable substitution: {e}", file=sys.stderr)
            return text

    def _handle_retrieve_step(self, step_config: dict):
        if not isinstance(step_config, dict):
            raise PILSemanticError("Retrieve step configuration must be a dictionary.")

        from_source = step_config.get("from")
        query_template = step_config.get("query")
        k = step_config.get("k", 3) # Default to k=3 if not specified
        output_var_name = step_config.get("def")

        if not from_source or not isinstance(from_source, str):
            raise PILSemanticError("Retrieve step must have a 'from' field as a string (filepath).")
        if not query_template or not isinstance(query_template, str): # Original check restored
            raise PILSemanticError("Retrieve step must have a 'query' field as a string template.")
        if not output_var_name or not isinstance(output_var_name, str):
            raise PILSemanticError("Retrieve step must have a 'def' field as a string (variable name).")
        if not isinstance(k, int) or k < 0:
            raise PILSemanticError("Retrieve step 'k' must be a non-negative integer.")

        # Substitute variables in 'from' and 'query'
        actual_from_source = self._substitute_variables(from_source)
        actual_query = self._substitute_variables(query_template).lower() # Lowercase query for case-insensitive match

        print(f"    Retrieving from: '{actual_from_source}', Query: '{actual_query}', k: {k}")

        retrieved_documents = []
        try:
            with open(actual_from_source, 'r', encoding='utf-8') as f:
                knowledge_base = json.load(f)

            if not isinstance(knowledge_base, list):
                raise PILSemanticError(f"Knowledge base file '{actual_from_source}' must contain a JSON list of documents.")

            # Very basic mock retrieval: keyword matching in 'content' or 'keywords'
            # This is a placeholder for more sophisticated retrieval (e.g., semantic search)
            for doc in knowledge_base:
                if not isinstance(doc, dict):
                    print(f"    Warning: Skipping invalid document (not a dict) in '{actual_from_source}'.", file=sys.stderr)
                    continue

                content_to_search = str(doc.get("content", "")).lower()
                keywords_to_search = [str(kw).lower() for kw in doc.get("keywords", []) if isinstance(kw, str)]
                title_to_search = str(doc.get("title", "")).lower()

                # Simple query splitting for "AND" logic on keywords
                query_terms = [term.strip() for term in actual_query.split() if term.strip()]

                match_score = 0
                if all(term in content_to_search for term in query_terms):
                    match_score += 2 # Higher weight for content match
                if any(all(term in kw for term in query_terms) for kw in keywords_to_search): # Check if all query terms are in any single keyword phrase
                    match_score +=1
                if all(term in title_to_search for term in query_terms):
                     match_score +=1


                if actual_query in content_to_search: # Broader match
                    match_score +=1
                if actual_query in title_to_search:
                    match_score +=1

                if any(actual_query in kw for kw in keywords_to_search):
                     match_score +=1


                if match_score > 0:
                    retrieved_documents.append({"doc": doc, "score": match_score})

            # Sort by score (descending) and then take top k
            retrieved_documents.sort(key=lambda x: x["score"], reverse=True)
            final_docs = [item["doc"] for item in retrieved_documents[:k]]


        except FileNotFoundError:
            raise PILError(f"Knowledge base file not found: {actual_from_source}")
        except json.JSONDecodeError as e: # Capture original exception
            raise PILSyntaxError(f"Invalid JSON in knowledge base file: {actual_from_source}. Details: {e}")
        except (PILSyntaxError, PILSemanticError): # Let these specific PIL errors propagate
            raise
        except Exception as e: # Catch-all for other *unexpected* errors during retrieval
            # Consider if this should also be a more specific PILError subtype
            raise PILError(f"Unexpected error during retrieval from '{actual_from_source}': {e}")

        self.context.set_variable(output_var_name, final_docs)
        print(f"    Retrieved {len(final_docs)} documents and stored in context variable: '{output_var_name}'")


    def _handle_prompt_step(self, step_config: dict):
        if not isinstance(step_config, dict):
            raise PILSemanticError("Prompt step configuration must be a dictionary.")

        prompt_text = step_config.get("text")
        if not prompt_text or not isinstance(prompt_text, str):
            raise PILSemanticError("Prompt step must have a 'text' field as a string.")

        output_var_name = step_config.get("def")
        # examples = step_config.get("examples") # TODO: Handle few-shot examples

        substituted_prompt_text = self._substitute_variables(prompt_text)
        print(f"    Substituted Prompt: \"{substituted_prompt_text[:100]}{'...' if len(substituted_prompt_text)>100 else ''}\"")

        llm_response_content = ""

        if not self.openai_client:
            print("    Warning: OpenAI client not available. Using mocked LLM response.", file=sys.stderr)
            llm_response_content = f"Mocked LLM Response to: \"{substituted_prompt_text[:50]}...\""
        else:
            messages = []
            persona = self.context.get_persona()
            if persona and persona.get("role"): # Using 'role' from persona as system message content
                messages.append({"role": "system", "content": persona.get("role")})

            history = self.context.get_history()
            messages.extend(history) # History should already be in {"role": ..., "content": ...} format

            messages.append({"role": "user", "content": substituted_prompt_text})

            model_name = self.context.get_global_parameters().get("model", DEFAULT_MODEL)
            # Other parameters like temperature can be fetched from context.global_parameters
            temperature = self.context.get_global_parameters().get("temperature", 0.7) # Default if not set

            print(f"    Making LLM call to model: {model_name} with temperature: {temperature}...")
            try:
                api_response = self.openai_client.chat.completions.create(
                    model=model_name,
                    messages=messages, # type: ignore # Pyright complains about list[dict[str,str]] vs MessagesParam
                    temperature=float(temperature) # Ensure temperature is float
                    # TODO: Add other parameters like max_tokens, top_p from context
                )
                llm_response_content = api_response.choices[0].message.content or ""
                print(f"    LLM Response: \"{llm_response_content[:100]}{'...' if len(llm_response_content)>100 else ''}\"")
            except APIError as e:
                error_message = f"OpenAI API Error: {e}"
                print(f"    {error_message}", file=sys.stderr)
                # Option 1: Raise an error and stop execution
                # raise PILError(error_message)
                # Option 2: Store error message as response and continue (might be useful for some flows)
                llm_response_content = f"ERROR: {error_message}"
                # Option 3: Fallback to mocked response (less ideal for real use)
                # llm_response_content = f"Mocked LLM Response due to API Error for: \"{substituted_prompt_text[:50]}...\""
            except Exception as e: # Catch other unexpected errors during API call
                error_message = f"Unexpected error during LLM call: {e}"
                print(f"    {error_message}", file=sys.stderr)
                llm_response_content = f"ERROR: {error_message}"


        if output_var_name:
            if not isinstance(output_var_name, str):
                raise PILSemanticError("Prompt step 'def' field must be a string (variable name).")
            self.context.set_variable(output_var_name, llm_response_content)
            print(f"    Stored response in context variable: '{output_var_name}'")

        self.context.add_history_entry(role="user", content=substituted_prompt_text)
        self.context.add_history_entry(role="assistant", content=llm_response_content) # Store actual or error response
        print(f"    Added user prompt and assistant response to history.")


    def run_workflow(self):
        if "workflow" not in self.program_data:
            raise PILSyntaxError("No 'workflow' block found in the PIL program.")
        if not isinstance(self.program_data["workflow"], dict):
            raise PILSyntaxError("'workflow' block must be a dictionary.")

        steps = self.program_data["workflow"].get("steps")
        if not steps:
            print("Warning: Workflow has no steps.", file=sys.stderr)
            return
        if not isinstance(steps, list):
            raise PILSyntaxError("'steps' in workflow must be a list.")

        print("Starting PIL workflow execution...")
        for i, step_data in enumerate(steps):
            if not isinstance(step_data, dict) or len(step_data) != 1:
                raise PILSemanticError(f"Step {i+1} in workflow is not a valid dictionary with a single type key. Found: {step_data}")

            step_type = list(step_data.keys())[0]
            step_config = step_data[step_type]

            print(f"\nProcessing Step {i+1} (Type: {step_type}):")

            if step_type == "prompt":
                self._handle_prompt_step(step_config)
            elif step_type == "retrieve":
                self._handle_retrieve_step(step_config)
            elif step_type == "tool":
                print(f"  Tool step found. Config: {step_config}") # Placeholder
            elif step_type == "code":
                print(f"  Code step found. Config: {step_config}") # Placeholder
            else:
                print(f"  Warning: Unknown step type '{step_type}' at step {i+1}. Content: {step_config}", file=sys.stderr)

        print("\nPIL workflow execution finished.")
