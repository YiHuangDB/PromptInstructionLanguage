import asyncio
import logging

from pygls.server import LanguageServer
from pygls.lsp.types import (
    InitializeParams,
    InitializeResult,
    ServerCapabilities,
    TextDocumentSyncOptions,
    TextDocumentSyncKind,
    DidOpenTextDocumentParams,
    DidChangeTextDocumentParams,
    MessageType,
    Diagnostic,
    DiagnosticSeverity,
    Position,
    Range as LspRange,
    CompletionOptions, # Added
    CompletionParams,
    CompletionList,
    CompletionItem,
    CompletionItemKind,
    Hover,             # Added
    HoverParams,       # Added
    MarkupContent,     # Added
    MarkupKind         # Added
)
from ruamel.yaml import YAML as RuamelYAML # Changed from 'import yaml'
from ruamel.yaml.error import YAMLError as RuamelYAMLError # Specific error type
import re
from pil_engine.interpreter import PilParser
from pil_engine.exceptions import PilEngineError, PILParsingError # Added PILParsingError

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

class PilLanguageServer(LanguageServer):
    CMD_SHOW_INFO_MESSAGE = "pil/showInfoMessage"
    SOURCE_NAME = "PIL Parser"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pil_parser = PilParser() # Initialize parser instance
        self.yaml_parser = RuamelYAML() # For parsing with location info
        logger.info("PIL Language Server initialized.")

    # Overriding capabilities directly in the class definition
    # This is a simpler way if capabilities are static.
    # If they need to be dynamic based on init options, an initialize handler is better.
    # For now, let's define them statically.

    # server_capabilities = ServerCapabilities(
    #     text_document_sync=TextDocumentSyncOptions(
    #         open_close=True,
    #         change=TextDocumentSyncKind.FULL,
    #         save=None
    #     )
    # )
    # pygls examples often define capabilities in the initialize handler or as a property.
    # Let's use the initialize handler as it's more flexible.


# Create the server instance
pil_server = PilLanguageServer("pil-server", "v0.1")

# --- Completion Data ---
# Using dictionaries for parameters to store more info like documentation or type
TOP_LEVEL_KEYWORDS_DOC = {
    "config": "Global configuration for the PIL program.",
    "persona": "Defines the LLM's persona.",
    "input": "Declares input variables for the program.",
    "outputSchema": "Defines the JSON Schema for the final program output.",
    "workflow": "The main block containing executable steps.",
    "constraints": "Top-level constraints for the final program output."
}
STEP_TYPE_KEYWORDS_DOC = {
    "prompt": "Interact with an LLM.",
    "retrieve": "Retrieve data from a knowledge source.",
    "tool": "Execute a predefined tool.",
    "code": "Execute a Python script.",
    "if": "Conditional execution branch. Condition is specified by the 'if' key itself.",
    # 'for' and 'while' are handled by 'loop' with specific expression parsing.
    # For autocompletion, we can offer 'loop' and then guide expression.
    # Or directly offer "for:", "while:" as starting points for a loop step.
    # Let's keep them for now as they are valid keys that imply a LoopStep.
    "for": "Iterate over a collection or range. Expression follows 'for'.",
    "while": "Execute steps while a condition is true. Condition follows 'while'.",
    "loop": "Defines a loop (can be for-each, for-range, or while based on expression)."
}
COMMON_STEP_PARAMS_DOC = {
    "def": "Variable name to store the step's output."
}

# Parameter details: (description, insert_text_suffix, kind)
# insert_text_suffix: e.g., ": " for simple values, ":\n  " for blocks
PARAM_DETAILS = {
    "text": ("The main prompt text (supports {{templating}}).", ": |\n  ", CompletionItemKind.PROPERTY),
    "examples": ("List of input/output examples for few-shot prompting.", ":\n  - input: \n    output: \n  ", CompletionItemKind.PROPERTY),
    "constraints": ("Validation rules for the step's output.", ":\n  type: \n  ", CompletionItemKind.PROPERTY),
    "max_retries": ("Max self-correction retries if constraints fail.", ": 0", CompletionItemKind.PROPERTY),
    "from": ("Source of the knowledge base (e.g., file path).", ": ", CompletionItemKind.PROPERTY),
    "query": ("Query string for retrieval (supports {{templating}}).", ": ", CompletionItemKind.PROPERTY),
    "k": ("Maximum number of documents to retrieve.", ": 3", CompletionItemKind.PROPERTY),
    "name": ("Registered name of the tool or input variable name.", ": ", CompletionItemKind.PROPERTY), # Context dependent
    "args": ("Dictionary of arguments for the tool.", ":\n  ", CompletionItemKind.PROPERTY),
    "lang": ("Language of the script (e.g., 'python').", ": python", CompletionItemKind.PROPERTY),
    "script": ("Block of code to execute.", ": |\n  ", CompletionItemKind.PROPERTY),
    "if": ("Condition expression for an if-step.", ": ", CompletionItemKind.PROPERTY), # Also a step type
    "then": ("Steps to execute if condition is true.", ":\n  - ", CompletionItemKind.PROPERTY),
    "else": ("Steps to execute if condition is false.", ":\n  - ", CompletionItemKind.PROPERTY),
    "for": ("Expression for a for-loop (e.g., 'item in {{my_list}}' or 'i in range(5)').", ": ", CompletionItemKind.PROPERTY), # Also a step type
    "while": ("Condition expression for a while-loop.", ": ", CompletionItemKind.PROPERTY), # Also a step type
    "loop": ("Expression for any loop type (for, while).", ": ", CompletionItemKind.PROPERTY), # Also a step type
    "steps": ("List of steps within a workflow, if, or loop.", ":\n  - ", CompletionItemKind.PROPERTY),
    "def": ("Variable name to store step output.", ": ", CompletionItemKind.PROPERTY),
}


STEP_SPECIFIC_PARAMS = {
    "prompt": ["text", "examples", "constraints", "max_retries"],
    "retrieve": ["from", "query", "k"],
    "tool": ["name", "args"],
    "code": ["lang", "script"],
    "if": ["if", "then", "else"],
    # Loop expressions are part of the main key ('for', 'while', 'loop')
    # The 'steps' key is common for blocks within loops.
    "for": ["steps"], # Expression is the value of 'for'
    "while": ["steps"],# Expression is the value of 'while'
    "loop": ["steps"], # Expression is the value of 'loop'
}
# ALL_STEP_PARAM_KEYWORDS = list(set(COMMON_STEP_PARAMS + [p for params in STEP_SPECIFIC_PARAMS.values() for p in params])) # Old

CONFIG_KEYWORDS_DOC = {
    "model": ("LLM model identifier.", ": ", CompletionItemKind.PROPERTY),
    "api_key": ("API key for the LLM service (use environment variables for security).", ": YOUR_API_KEY", CompletionItemKind.PROPERTY),
    "parameters": ("LLM call parameters (e.g., temperature).", ":\n  temperature: 0.7\n  ", CompletionItemKind.PROPERTY),
    "max_program_retries": ("Max program-level self-correction retries.", ": 0", CompletionItemKind.PROPERTY)
}
PERSONA_KEYWORDS_DOC = {
    "role": ("Primary role for LLM.", ": ", CompletionItemKind.PROPERTY),
    "style": ("Writing style for LLM.", ": ", CompletionItemKind.PROPERTY),
    "tone": ("Emotional tone for LLM.", ": ", CompletionItemKind.PROPERTY),
    "audience": ("Intended audience for LLM.", ": ", CompletionItemKind.PROPERTY)
}
INPUT_KEYWORDS_DOC = {
    "vars": ("Defines input variables (name: type or list of {name, type, desc}).", ":\n  ", CompletionItemKind.PROPERTY)
}
OUTPUTSCHEMA_KEYWORDS_DOC = {
    "schema": ("JSON Schema object for output validation.", ":\n  type: object\n  properties:\n    ", CompletionItemKind.PROPERTY)
}
CONSTRAINTS_KEYWORDS_DOC = {
    "type": ("Expected data type (string, integer, number, boolean, list, object).", ": ", CompletionItemKind.PROPERTY),
    "regex": ("Python regex pattern for string validation.", ": ", CompletionItemKind.PROPERTY),
    "choices": ("List of allowed string values.", ":\n  - ", CompletionItemKind.PROPERTY),
    "custom_validator": ("Path to custom validator function (module:function).", ": ", CompletionItemKind.PROPERTY)
}
LANG_PYTHON_COMPLETION = [create_completion_item("python", CompletionItemKind.VALUE, insert_text="python", detail="Python language for CodeStep")]
TYPE_CONSTRAINT_VALUES = ["string", "integer", "number", "boolean", "list", "object"]


def create_completion_item(label: str, kind: CompletionItemKind, insert_text: str = None, documentation: str = None, detail: str = None) -> CompletionItem:
    return CompletionItem(
        label=label,
        kind=kind,
        insert_text=insert_text or label, # Default to label if no specific insert text
        documentation=documentation,
        detail=detail
    )

@pil_server.feature("initialize")
async def initialize(ls: PilLanguageServer, params: InitializeParams):
    """Handles the initialize request and returns server capabilities."""
    logger.info(f"Client capabilities: {params.capabilities}")

    # Store client capabilities if your server needs them
    # ls.client_capabilities = params.capabilities

    server_capabilities = ServerCapabilities(
        text_document_sync=TextDocumentSyncOptions(
            open_close=True,
            change=TextDocumentSyncKind.FULL,
            save=None
        ),
        completion_provider=CompletionOptions(
            trigger_characters=[':', ' ', '-', '{'],
            # resolve_provider=False
        ),
        hover_provider=True # Enabled hover provider
        # Future capabilities (definition) will be added here
    )
    logger.info(f"Server capabilities: {server_capabilities}")
    return InitializeResult(capabilities=server_capabilities)

def _get_line_indent(line: str) -> int:
    """Calculates the leading whitespace indentation of a line."""
    return len(line) - len(line.lstrip(' '))

def _get_parent_key_info(document_lines: List[str], current_line_num: int, current_indent: int) -> Optional[tuple[str, int]]:
    """
    Finds the parent key and its indent for the current line.
    Looks upwards for a line with less indentation that ends with a colon.
    Returns (parent_key_name, parent_key_indent_level) or None.
    """
    for i in range(current_line_num - 1, -1, -1):
        line = document_lines[i]
        line_stripped = line.strip()

        if not line_stripped: # Skip empty lines
            continue

        indent = _get_line_indent(line)

        if indent < current_indent:
            if line_stripped.endswith(':'):
                key_name = line_stripped[:-1].strip()
                # Further check if it's not part of a flow style mapping on the same line, e.g. "key: { sub_key: value }"
                # This simple check assumes keys are on their own lines or followed by simple values/newlines.
                return key_name, indent
            # If we find a line with less indent that isn't a key, it might be an unindented list item or something else.
            # For now, we stop searching upwards if the structure is broken in a way that's not a clear parent key.
            return None
    return None


async def _validate_document(ls: PilLanguageServer, doc_uri: str):
    """Helper function to validate a document and publish diagnostics."""
    diagnostics = []
    document = ls.workspace.get_document(doc_uri)
    if not document:
        logger.warning(f"Could not get document from workspace: {doc_uri}")
        return

    try:
        logger.info(f"Validating document: {doc_uri}")
        content = document.source
        if not content.strip(): # If content is empty or whitespace
            logger.info(f"Document {doc_uri} is empty, clearing diagnostics.")
            ls.publish_diagnostics(doc_uri, [])
            return

        # Attempt to parse YAML first
        try:
            # Use ruamel.yaml for parsing to get line/column info
            parsed_yaml_content = ls.yaml_parser.load(content)

            if not isinstance(parsed_yaml_content, dict):
                diagnostics.append(
                    Diagnostic(
                        range=LspRange(start=Position(line=0, character=0), end=Position(line=0, character=max(0,len(document.lines[0])-1 if document.lines else 0))),
                        message="PIL program root must be a YAML mapping (dictionary).",
                        severity=DiagnosticSeverity.ERROR,
                        source=ls.SOURCE_NAME
                    )
                )
            else:
                # If YAML parsing is fine and it's a dict, try parsing with PilParser
                # TODO: Refactor PilParser().parse_dict or relevant component from_yaml methods
                # to accept ruamel.yaml nodes or handle location data passed alongside.
                # For now, it will still raise errors without location from the core parser.
            # PASSING is_lsp_parse=True to enable location-aware parsing
            ls.pil_parser.parse_dict(parsed_yaml_content, is_lsp_parse=True)
                logger.info(f"Document {doc_uri} parsed successfully by PilParser (semantic validation).")

        except RuamelYAMLError as e: # Catch ruamel.yaml specific errors
            logger.warning(f"YAML parsing error in {doc_uri} (ruamel.yaml): {e}")
            start_line = e.problem_mark.line if hasattr(e, 'problem_mark') and e.problem_mark else 0
            start_char = e.problem_mark.column if hasattr(e, 'problem_mark') and e.problem_mark else 0
            end_char = start_char + 1
            if start_line < len(document.lines) and hasattr(e, 'problem_mark') and e.problem_mark:
                 # Try to highlight the problematic token or a small range
                problem_text_segment = getattr(e, 'problem', '')
                if problem_text_segment and isinstance(problem_text_segment, str):
                    # A more robust way would be to find the token boundaries if possible
                    end_char = start_char + len(problem_text_segment.split('\n')[0]) # Length of first line of problem segment
                else: # Fallback to end of line
                    end_char = len(document.lines[start_line])

            diagnostics.append(
                Diagnostic(
                    range=LspRange(
                        start=Position(line=start_line, character=start_char),
                        end=Position(line=start_line, character=max(start_char + 1, end_char))
                    ),
                    message=f"YAML Syntax Error: {e.problem}",
                    severity=DiagnosticSeverity.ERROR,
                    source=ls.SOURCE_NAME
                )
            )
        except PILParsingError as e: # Custom error that should contain location info
            logger.warning(f"PIL parsing error in {doc_uri}: {e.message} at L{e.line} C{e.column}")
            line = e.line or 0
            col = e.column or 0
            # Create a small range for the error, e.g., 1 character or until end of word
            # This needs to be improved if end_line/end_column are available.
            end_col = col + 1
            if line < len(document.lines):
                # Attempt to find a sensible end column (e.g., end of word or line)
                line_content = document.lines[line]
                match_word_after = re.match(r'\w*', line_content[col:])
                if match_word_after:
                    end_col = col + len(match_word_after.group(0)) if match_word_after.group(0) else col + 1

            diagnostics.append(
                Diagnostic(
                    range=LspRange(start=Position(line=line, character=col), end=Position(line=line, character=max(col+1, end_col))),
                    message=f"PIL Error: {e.message}",
                    severity=DiagnosticSeverity.ERROR,
                    source=ls.SOURCE_NAME
                )
            )
        except (ValueError, TypeError, PilEngineError) as e: # Fallback for other PIL errors without location
            logger.warning(f"Generic PIL parsing error in {doc_uri}: {e}")
            diagnostics.append(
                Diagnostic(
                    range=LspRange(start=Position(line=0, character=0), end=Position(line=0, character=max(0,len(document.lines[0])-1 if document.lines else 0))),
                    message=f"PIL Structure/Validation Error: {str(e)}",
                    severity=DiagnosticSeverity.ERROR,
                    source=ls.SOURCE_NAME
                )
            )
        except Exception as e: # Catch-all for unexpected issues during validation
            logger.error(f"Unexpected error during validation of {doc_uri}: {e}", exc_info=True)
            diagnostics.append(
                Diagnostic(
                    range=LspRange(start=Position(line=0, character=0), end=Position(line=0, character=1)),
                    message=f"Unexpected validation error: {str(e)}",
                    severity=DiagnosticSeverity.ERROR,
                    source=ls.SOURCE_NAME
                )
            )

    finally:
        logger.info(f"Publishing {len(diagnostics)} diagnostics for {doc_uri}.")
        ls.publish_diagnostics(doc_uri, diagnostics)


@pil_server.feature("textDocument/didOpen")
async def did_open(ls: PilLanguageServer, params: DidOpenTextDocumentParams):
    logger.info(f"Document opened: {params.text_document.uri}")
    await _validate_document(ls, params.text_document.uri)


@pil_server.feature("textDocument/didChange")
async def did_change(ls: PilLanguageServer, params: DidChangeTextDocumentParams):
    logger.info(f"Document changed: {params.text_document.uri}")
    # Since TextDocumentSyncKind.FULL, the whole content is resent and pygls updates the workspace.
    await _validate_document(ls, params.text_document.uri)


@pil_server.command(PilLanguageServer.CMD_SHOW_INFO_MESSAGE)
async def show_info_message_command(ls: PilLanguageServer, args: list):
    logger.info(f"Command {PilLanguageServer.CMD_SHOW_INFO_MESSAGE} triggered with args: {args}")
    message_to_show = "PIL Server Info: Command executed!"
    if args and len(args) > 0 and isinstance(args[0], str):
        message_to_show = args[0]
    ls.show_message(message_to_show, msg_type=MessageType.INFO)


# --- Autocompletion Handler (Initial Stub) ---
@pil_server.feature("textDocument/completion")
async def completions(ls: PilLanguageServer, params: CompletionParams) -> CompletionList:
    """Provides completion items."""
    doc_uri = params.text_document.uri
    position = params.position
    logger.info(f"Completion requested for {doc_uri} at {position}")

    # TODO:
    # 1. Get document from workspace: ls.workspace.get_document(doc_uri)
    # 1. Get document from workspace
    document = ls.workspace.get_document(doc_uri)
    if not document:
        logger.warning(f"Completion: Could not get document {doc_uri}")
        return CompletionList(is_incomplete=False, items=[])

    # 2. Analyze text around params.position to determine context.
    current_line_num = params.position.line
    cursor_char_num = params.position.character

    current_line_text = ""
    if 0 <= current_line_num < len(document.lines):
        current_line_text = document.lines[current_line_num]

    text_before_cursor = current_line_text[:cursor_char_num]
    # Word before cursor can be useful for partial matches
    # A simple way to get the current "word" being typed for filtering completions:
    match = re.search(r'([a-zA-Z0-9_]*)$', text_before_cursor)
    current_word = match.group(1) if match else ""

    indent_level = len(text_before_cursor) - len(text_before_cursor.lstrip(' '))

    logger.info(f"Completion context: Line {current_line_num}, Char {cursor_char_num}")
    logger.info(f"Text before cursor: '{text_before_cursor}'")
    logger.info(f"Current word/prefix: '{current_word}'")
    logger.info(f"Indent level: {indent_level}")

    # 3. Generate completion items based on context (Logic for this will be in Step 4)
    # For now, this step is about gathering context.
    # We can pass these context variables (current_line_text, text_before_cursor, current_word, indent_level, document itself)
    # to a helper function that generates completion items.

    completion_items: List[CompletionItem] = []

    # Placeholder for where Step 4 logic will go
    # Example of how it might be structured:
    # if is_top_level_context(indent_level, text_before_cursor):
    #     completion_items.extend(get_top_level_key_completions(current_word))
    # elif is_step_type_context(indent_level, text_before_cursor, document, current_line_num):
    #     completion_items.extend(get_step_type_completions(current_word))
    # elif is_parameter_context(indent_level, text_before_cursor, document, current_line_num):
    #     parent_key = get_parent_key(document, current_line_num, indent_level)
    #     if parent_key:
    #         completion_items.extend(get_parameter_completions(parent_key, current_word))
    # elif text_before_cursor.endswith("{{"):
    #    completion_items.append(CompletionItem(label="}}", insert_text="}}", kind=CompletionItemKind.TEXT, detail="Close template expression"))
        # Potentially add context variable completions here in the future

    # --- Main Completion Logic ---
    completion_items: List[CompletionItem] = []
    parent_key_info = _get_parent_key_info(document.lines, current_line_num, indent_level)
    parent_key = parent_key_info[0] if parent_key_info else None
    parent_indent = parent_key_info[1] if parent_key_info else -1

    # 1. Top-level keywords
    if indent_level == 0 and (not text_before_cursor.strip() or current_word):
        for keyword, doc_string in TOP_LEVEL_KEYWORDS_DOC.items():
            if keyword.startswith(current_word):
                completion_items.append(
                    create_completion_item(f"{keyword}:", CompletionItemKind.KEYWORD, insert_text=f"{keyword}:\n{' ' * (indent_level + 2)}", documentation=doc_string, detail="PIL Top-Level Section")
                )

    # 2. Step type keywords (e.g., after "- ")
    stripped_line_before_cursor = text_before_cursor.strip()
    if stripped_line_before_cursor.startswith("-") and (stripped_line_before_cursor == "-" or stripped_line_before_cursor.endswith(" ")):
        # If cursor is just after "- " or "- k" (for "keyword")
        prefix_for_step_type = current_word if stripped_line_before_cursor.endswith(current_word) else ""
        for keyword, doc_string in STEP_TYPE_KEYWORDS_DOC.items():
            if keyword.startswith(prefix_for_step_type):
                completion_items.append(
                    create_completion_item(f"{keyword}:", CompletionItemKind.MODULE, insert_text=f"{keyword}:\n{' ' * (indent_level + 2)}", documentation=doc_string, detail="PIL Step Type")
                )

    # 3. Parameters based on parent key
    if parent_key:
        # Common params for all steps if under a step type
        if parent_key in STEP_TYPE_KEYWORDS_DOC:
            for param, doc_string in COMMON_STEP_PARAMS_DOC.items():
                if param.startswith(current_word):
                    desc, suffix, kind = PARAM_DETAILS.get(param, (doc_string, ": ", CompletionItemKind.PROPERTY))
                    completion_items.append(create_completion_item(param, kind, insert_text=f"{param}{suffix}", documentation=desc, detail=f"Parameter for '{parent_key}' step"))

            # Step-specific parameters
            for param in STEP_SPECIFIC_PARAMS.get(parent_key, []):
                if param.startswith(current_word):
                    desc, suffix, kind = PARAM_DETAILS.get(param, (f"Parameter for {parent_key}", ": ", CompletionItemKind.PROPERTY))
                    completion_items.append(create_completion_item(param, kind, insert_text=f"{param}{suffix}", documentation=desc, detail=f"Parameter for '{parent_key}' step"))

        # Config parameters
        elif parent_key == "config":
            for param, (doc_string, suffix, kind) in CONFIG_KEYWORDS_DOC.items():
                if param.startswith(current_word):
                    completion_items.append(create_completion_item(param, kind, insert_text=f"{param}{suffix}", documentation=doc_string, detail="Config Parameter"))

        # Persona parameters
        elif parent_key == "persona":
            for param, (doc_string, suffix, kind) in PERSONA_KEYWORDS_DOC.items():
                if param.startswith(current_word):
                    completion_items.append(create_completion_item(param, kind, insert_text=f"{param}{suffix}", documentation=doc_string, detail="Persona Parameter"))

        # Input parameters
        elif parent_key == "input":
             for param, (doc_string, suffix, kind) in INPUT_KEYWORDS_DOC.items(): # usually 'vars'
                if param.startswith(current_word):
                    completion_items.append(create_completion_item(param, kind, insert_text=f"{param}{suffix}", documentation=doc_string, detail="Input Section Parameter"))

        # OutputSchema parameters
        elif parent_key == "outputSchema":
            for param, (doc_string, suffix, kind) in OUTPUTSCHEMA_KEYWORDS_DOC.items(): # usually 'schema'
                if param.startswith(current_word):
                    completion_items.append(create_completion_item(param, kind, insert_text=f"{param}{suffix}", documentation=doc_string, detail="OutputSchema Parameter"))

        # Constraints parameters (can be nested under steps or top-level)
        elif parent_key == "constraints":
            for param, (doc_string, suffix, kind) in CONSTRAINTS_KEYWORDS_DOC.items():
                if param.startswith(current_word):
                    completion_items.append(create_completion_item(param, kind, insert_text=f"{param}{suffix}", documentation=doc_string, detail="Constraint Parameter"))
            # If typing after "type: ", suggest type values
            if text_before_cursor.strip().startswith("type:"):
                type_prefix = text_before_cursor.strip()[len("type:"):].lstrip()
                for val in TYPE_CONSTRAINT_VALUES:
                    if val.startswith(type_prefix):
                        completion_items.append(create_completion_item(val, CompletionItemKind.ENUM_MEMBER, insert_text=val, detail="Constraint Type Value"))

        # Specific value completions
        if parent_key == "code" and text_before_cursor.strip().startswith("lang:"):
            lang_prefix = text_before_cursor.strip()[len("lang:"):].lstrip()
            if "python".startswith(lang_prefix):
                completion_items.extend(LANG_PYTHON_COMPLETION)

        # Input variable definition (under input -> vars: var_name: type)
        grandparent_key_info = _get_parent_key_info(document.lines, parent_indent // 2 * 2, parent_indent) # Approx grandparent
        if parent_key == "vars" or (grandparent_key_info and grandparent_key_info[0] == "vars"):
             # If line is "  var_name:" and current_word is empty (just typed colon)
            if text_before_cursor.strip().endswith(":") and not current_word:
                 completion_items.append(create_completion_item("type", CompletionItemKind.PROPERTY, insert_text=" type: string", documentation="Data type of the input variable"))


    # 4. Template variable completions `{{...}}`
    if "{{" in text_before_cursor and text_before_cursor.rfind("}}") < text_before_cursor.rfind("{{"):
        # Basic: try to get 'input' vars
        try:
            parsed_content = ls.yaml_parser.load(document.source) # Use ruamel to preserve structure if needed for deep parsing
            if isinstance(parsed_content, dict) and "input" in parsed_content and "vars" in parsed_content["input"]:
                input_vars_node = parsed_content["input"]["vars"]
                vars_to_suggest = []
                if isinstance(input_vars_node, dict):
                    vars_to_suggest.extend(input_vars_node.keys())
                elif isinstance(input_vars_node, list):
                    for item in input_vars_node:
                        if isinstance(item, dict) and "name" in item:
                            vars_to_suggest.append(item["name"])

                # Extract prefix inside {{ for filtering
                template_prefix_match = re.search(r'\{\{\s*([\w_]*)$', text_before_cursor)
                template_prefix = template_prefix_match.group(1) if template_prefix_match else ""

                for var_name in vars_to_suggest:
                    if var_name.startswith(template_prefix):
                        completion_items.append(
                            create_completion_item(var_name, CompletionItemKind.VARIABLE, insert_text=var_name, detail="Input Variable")
                        )
        except RuamelYAMLError: # If YAML is broken, can't parse for vars
            pass
        # Always suggest closing braces if inside template
        completion_items.append(create_completion_item("}}", CompletionItemKind.TEXT, insert_text="}}", detail="Close template expression"))


    return CompletionList(is_incomplete=False, items=completion_items)


def main():
    logger.info("Starting PIL Language Server...")
    # For stdio communication (typical for LSP)
    pil_server.start_io()

    # Example for TCP server (less common for editor integration, good for testing)
    # loop = asyncio.new_event_loop()
    # asyncio.set_event_loop(loop)
    # try:
    #     loop.run_until_complete(pil_server.start_tcp("127.0.0.1", 8080))
    # except KeyboardInterrupt:
    #     logger.info("PIL Language Server stopping (TCP).")
    # finally:
    #     loop.close()

    logger.info("PIL Language Server stopped.")

# --- Hover Handler (Initial Stub) ---
@pil_server.feature("textDocument/hover")
async def hover(ls: PilLanguageServer, params: HoverParams) -> Optional[Hover]:
    doc_uri = params.text_document.uri
    position = params.position
    logger.info(f"Hover requested for {doc_uri} at {position}")

    # TODO:
    # 1. Get document from workspace.
    # 2. Identify the word/token under the cursor at params.position.
    # 1. Get document from workspace.
    document = ls.workspace.get_document(doc_uri)
    if not document:
        logger.warning(f"Hover: Could not get document {doc_uri}")
        return None

    # 2. Identify the word/token under the cursor at params.position.
    current_line_num = params.position.line
    cursor_char_num = params.position.character

    if not (0 <= current_line_num < len(document.lines)):
        logger.warning(f"Hover: Invalid line number {current_line_num}")
        return None

    line_text = document.lines[current_line_num]

    # Iterate backwards from cursor to find start of word
    start_char = cursor_char_num
    # Allow alphanumeric, underscore, and hyphen (common in YAML keys)
    while start_char > 0 and (line_text[start_char - 1].isalnum() or line_text[start_char - 1] in ['_', '-']):
        start_char -= 1

    # Iterate forwards from original cursor position to find end of word
    end_char = cursor_char_num
    while end_char < len(line_text) and (line_text[end_char].isalnum() or line_text[end_char] in ['_', '-']):
        end_char += 1

    hovered_word = line_text[start_char:end_char].strip()

    # Handle cases where the cursor might be on punctuation like ':', or part of '{{' '}}'
    if not hovered_word:
        if cursor_char_num > 0 and line_text[cursor_char_num - 1] == ':':
            # If on ':', try to get the key to its left
            temp_start = cursor_char_num - 1
            while temp_start > 0 and (line_text[temp_start - 1].isalnum() or line_text[temp_start - 1] in ['_', '-']):
                temp_start -= 1
            hovered_word = line_text[temp_start:cursor_char_num - 1].strip()
            logger.info(f"Hover identified key before colon: '{hovered_word}' (cursor was on colon)")
        elif cursor_char_num > 1 and line_text[cursor_char_num-2:cursor_char_num] == '{{':
            hovered_word = '{{'
        elif cursor_char_num < len(line_text) and line_text[cursor_char_num:cursor_char_num+1] == '{' and \
             cursor_char_num > 0 and line_text[cursor_char_num-1:cursor_char_num] == '{': # Cursor is on the second { of {{
            hovered_word = '{{'
        elif cursor_char_num < len(line_text) and line_text[cursor_char_num:cursor_char_num+1] == '}' and \
             cursor_char_num > 0 and line_text[cursor_char_num-1:cursor_char_num] == '}': # Cursor is on the second } of }}
            hovered_word = '}}'
        elif cursor_char_num < len(line_text) -1 and line_text[cursor_char_num:cursor_char_num+2] == '}}':
             hovered_word = '}}'


    logger.info(f"Hover context: Line='{line_text.strip()}', Position=({current_line_num}, {cursor_char_num}), Word='{hovered_word}'")

    # 3. Fetch documentation/information based on the token. (Step 4)
    # 4. Format and return Hover object. (Step 4)

    # For now, this step is about identifying the word.
    # Step 4 will use 'hovered_word' to generate the Hover object.
    # 3. Fetch documentation/information based on the token.
    # 4. Format and return Hover object.
    documentation = HOVER_DOCUMENTATION.get(hovered_word)

    if documentation:
        markup_content = MarkupContent(kind=MarkupKind.Markdown, value=documentation)
        # Determine the range of the hovered word for more precise hover highlighting
        # This can be tricky if the word extraction isn't perfect or if it's part of a larger token
        # For now, use the extracted word's boundaries.
        hover_range = LspRange(start=Position(line=current_line_num, character=start_char),
                               end=Position(line=current_line_num, character=end_char))

        return Hover(contents=markup_content, range=hover_range)

    return None


# --- Hover Information Dictionary ---
HOVER_DOCUMENTATION = {
    # Top Level
    "config": "Global configuration for the PIL program (e.g., LLM model, API keys, parameters).",
    "persona": "Defines the role, style, and tone the LLM should adopt.",
    "input": "Declares input variables and their expected types for the program.",
    "outputSchema": "Defines the JSON Schema for the final program output.",
    "workflow": "The main block containing a sequence of executable steps.",
    # "constraints" (top-level) is covered by the generic constraints key below

    # Step Types & their primary expression keys
    "prompt": "A step to interact with an LLM by sending a prompt and receiving a response. Requires a `text` parameter.",
    "retrieve": "A step to retrieve relevant data from a knowledge source. Requires `from` (source) and `query` parameters.",
    "tool": "A step to execute a predefined Python tool/function. Requires `name` (tool name) and `args` parameters.",
    "code": "A step to execute a block of Python code in a sandboxed environment. Requires `lang` and `script` parameters.",
    "if": "A control flow step for conditional execution. The value of 'if' is the condition expression. Requires `then` block, `else` is optional.",
    "for": "A control flow step for iterating. Expression (e.g., 'item in {{collection}}' or 'i in range(5)') is the value of 'for'. Requires `steps` block.",
    "while": "A control flow step for conditional looping. Expression (condition) is the value of 'while'. Requires `steps` block.",
    "loop": "A flexible loop step. Expression (e.g., 'item in {{collection}}', 'i in range(5)', or 'condition for while') is the value of 'loop'. Requires `steps` block.",

    # Common Parameters for most steps
    "def": "Defines a variable name in the context to store the output of this step.",

    # Common block parameter
    "steps": "A list of steps to be executed, typically within `workflow`, `if`, or `loop` blocks.",

    # PromptStep Specific Parameters
    "text": "The main prompt text for an LLM (supports {{templating}}).",
    "examples": "A list of input/output examples for few-shot prompting. Each example is a dict with 'input' and 'output' keys.",
    "max_retries": "Maximum self-correction retries for this prompt step if its constraints fail (default: 0).",

    # RetrieveStep Specific Parameters
    "from": "Specifies the source of the knowledge base (e.g., file path to a JSON document list).",
    "query": "The query string for information retrieval (supports {{templating}}).",
    "k": "The maximum number of documents to retrieve (default: 3).",

    # ToolStep Specific Parameters
    # "name" (for tool) is covered by the generic "name" below.
    "args": "A dictionary of arguments (key-value pairs) to pass to the specified tool.",

    # CodeStep Specific Parameters
    "lang": "The language of the script to be executed (currently only 'python' is supported).",
    "script": "The block of code to execute. The result should be assigned to a variable named 'result'.",

    # IfStep Specific Parameters
    # "if" (condition) is covered by the step type "if".
    "then": "A block of steps to execute if the 'if' condition evaluates to true.",
    "else": "An optional block of steps to execute if the 'if' condition evaluates to false.",

    # Constraints Object Keys (can be top-level or under a step like PromptStep)
    "constraints": "Defines validation rules for an output (e.g., program output or step output).",
    "type": "Specifies the expected data type (e.g., string, integer, boolean). Can perform coercion.",
    "regex": "A Python regular expression pattern that the value must match.",
    "choices": "A list of allowed values.",
    "custom_validator": "Path to a custom Python validator function (e.g., 'module:function').",

    # Config Specific
    "model": "Identifier of the LLM to be used (e.g., 'gpt-4o-mini').",
    "api_key": "API key for the LLM service (environment variable preferred).",
    "parameters": "Dictionary of parameters for LLM calls (e.g., temperature).",

    # Persona Specific
    "role": "The primary role the LLM should adopt.",
    "style": "The writing or communication style for the LLM.",
    "tone": "The emotional tone for the LLM's responses.",
    "audience": "The intended audience for the LLM's responses.",

    # Input Specific
    "vars": "Defines input variables for the program (name, type, description).",

    # OutputSchema Specific
    "schema": "A JSON Schema object defining the output structure.",

    # Template braces
    "{{": "Start of a PIL template expression. Evaluates to a context variable.",
    "}}": "End of a PIL template expression."
}


if __name__ == "__main__":
    main()
