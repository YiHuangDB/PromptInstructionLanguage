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
import yaml
import re # Added for word extraction in hover/completion
from pil_engine.interpreter import PilParser
from pil_engine.exceptions import PilEngineError # For catching general PIL errors

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

class PilLanguageServer(LanguageServer):
    CMD_SHOW_INFO_MESSAGE = "pil/showInfoMessage"
    SOURCE_NAME = "PIL Parser"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pil_parser = PilParser() # Initialize parser instance
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
TOP_LEVEL_KEYWORDS = ["config", "persona", "input", "outputSchema", "workflow", "constraints"]
STEP_TYPE_KEYWORDS = ["prompt", "retrieve", "tool", "code", "if", "for", "while", "loop"] # 'loop' is alias for while
COMMON_STEP_PARAMS = ["def"] # 'def' is common to most steps

STEP_SPECIFIC_PARAMS = {
    "prompt": ["text", "examples", "constraints", "max_retries"],
    "retrieve": ["from", "query", "k"],
    "tool": ["name", "args"],
    "code": ["lang", "script"],
    "if": ["if", "then", "else"], # 'if' is also the condition key
    "for": ["for", "steps"],      # 'for' is also the expression key
    "while": ["while", "steps"],  # 'while' is also the expression key
    "loop": ["loop", "steps"],    # 'loop' is also the expression key
}
ALL_STEP_PARAM_KEYWORDS = list(set(COMMON_STEP_PARAMS + [p for params in STEP_SPECIFIC_PARAMS.values() for p in params]))

CONFIG_KEYWORDS = ["model", "api_key", "parameters"]
PERSONA_KEYWORDS = ["role", "style", "tone", "audience"]
INPUT_KEYWORDS = ["vars"] # Under vars, it's dynamic
OUTPUTSCHEMA_KEYWORDS = ["schema"]
CONSTRAINTS_KEYWORDS = ["type", "regex", "choices", "custom_validator"]


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
            parsed_yaml_content = yaml.safe_load(content)
            if not isinstance(parsed_yaml_content, dict):
                # If YAML is valid but not a dictionary at the root, it's not a valid PIL program.
                # Create a basic diagnostic for this.
                # For now, make a document-level diagnostic if not a dict.
                diagnostics.append(
                    Diagnostic(
                        range=LspRange(start=Position(line=0, character=0), end=Position(line=0, character=max(0,len(document.lines[0])-1 if document.lines else 0))), # Highlight first line
                        message="PIL program root must be a YAML mapping (dictionary).",
                        severity=DiagnosticSeverity.ERROR,
                        source=ls.SOURCE_NAME
                    )
                )
            else:
                # If YAML parsing is fine and it's a dict, try parsing with PilParser
                ls.pil_parser.parse_dict(parsed_yaml_content)
                logger.info(f"Document {doc_uri} parsed successfully by PilParser.")
        except yaml.YAMLError as e:
            logger.warning(f"YAML parsing error in {doc_uri}: {e}")
            # Try to get line/column information from YamlError if available
            # PyYAML's Mark object has line, column (0-indexed)
            start_line = e.problem_mark.line if hasattr(e, 'problem_mark') and e.problem_mark else 0
            start_char = e.problem_mark.column if hasattr(e, 'problem_mark') and e.problem_mark else 0
            # For end position, we might just highlight the line or a few chars.
            # A simple approach is to highlight from the error char to end of line, or a fixed length.
            end_char = start_char + 1 # Default to highlighting one character
            if start_line < len(document.lines):
                end_char = max(start_char + 1, len(document.lines[start_line]))


            diagnostics.append(
                Diagnostic(
                    range=LspRange(
                        start=Position(line=start_line, character=start_char),
                        end=Position(line=start_line, character=end_char)
                    ),
                    message=f"YAML Error: {e.problem}", # e.problem is usually more concise
                    severity=DiagnosticSeverity.ERROR,
                    source=ls.SOURCE_NAME
                )
            )
        except (ValueError, TypeError, PilEngineError) as e: # Catch errors from PilParser.parse_dict
            logger.warning(f"PIL parsing error in {doc_uri}: {e}")
            # These errors currently don't have line/char info from PilParser.
            # Report as a document-level error (e.g., on the first line).
            diagnostics.append(
                Diagnostic(
                    range=LspRange(start=Position(line=0, character=0), end=Position(line=0, character=max(0,len(document.lines[0])-1 if document.lines else 0))),
                    message=f"PIL Structure/Validation Error: {str(e)}",
                    severity=DiagnosticSeverity.ERROR,
                    source=ls.SOURCE_NAME
                )
            )
        # This generic except is usually not recommended for production, but helpful during dev
        except Exception as e:
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

    # For now, just a test item if typing "conf"
    # if current_word.lower().startswith("conf"):
    #      completion_items.append(CompletionItem(label="config:", kind=CompletionItemKind.KEYWORD, insert_text="config:\n  "))

    # Rudimentary context determination for top-level keys
    # This assumes that if indent is 0 and the line is empty or contains the start of a word,
    # we might be at the top level.
    if indent_level == 0:
        if not text_before_cursor.strip() or current_word: # Empty line or typing a word
            for keyword in TOP_LEVEL_KEYWORDS:
                if keyword.startswith(current_word):
                    completion_items.append(
                        create_completion_item(f"{keyword}:", CompletionItemKind.KEYWORD, insert_text=f"{keyword}:\n  ", detail=f"PIL top-level section: {keyword}")
                    )

    # Rudimentary context for step types (e.g. after "- ")
    # This is a very simplified check. A proper YAML parser or state machine would be better.
    stripped_line_before_cursor = text_before_cursor.strip()
    if stripped_line_before_cursor == "-" or stripped_line_before_cursor == "- ":
        for keyword in STEP_TYPE_KEYWORDS:
            # If current_word is part of "- keyword", this won't work well yet.
            # This primarily works when cursor is just after "- ".
             completion_items.append(
                create_completion_item(f"{keyword}: ", CompletionItemKind.KEYWORD, insert_text=f"{keyword}:\n  ", detail=f"PIL step type: {keyword}")
            )
    elif stripped_line_before_cursor.startswith("- ") and len(stripped_line_before_cursor) > 2:
        partial_step_type = stripped_line_before_cursor[2:]
        for keyword in STEP_TYPE_KEYWORDS:
            if keyword.startswith(partial_step_type):
                completion_items.append(
                    create_completion_item(f"{keyword}:", CompletionItemKind.KEYWORD, insert_text=f"{keyword}:\n  ", detail=f"PIL step type: {keyword}")
                )

    # Suggest '{{' for starting a template, or '}}' if inside one
    if text_before_cursor.endswith('{'):
        completion_items.append(create_completion_item(label="{{", insert_text="{", kind=CompletionItemKind.TEXT, detail="Complete template expression start"))
    # Basic check for being inside a template - very naive.
    # A proper approach would count unmatched {{ and }}.
    # if text_before_cursor.count("{{") > text_before_cursor.count("}}") and not text_before_cursor.endswith("}}"):
    #     # This is where context variable completion would go
    #     pass


    # Get parent key context for parameter suggestions
    parent_key_info = _get_parent_key_info(document.lines, current_line_num, indent_level)

    if parent_key_info:
        parent_key, parent_indent = parent_key_info
        logger.info(f"Parent key: '{parent_key}' at indent {parent_indent}")

        # Only suggest parameters if current indent is greater than parent's key indent
        if indent_level > parent_indent:
            suggestions = []
            detail_prefix = ""

            if parent_key in STEP_TYPE_KEYWORDS:
                suggestions.extend(COMMON_STEP_PARAMS)
                suggestions.extend(STEP_SPECIFIC_PARAMS.get(parent_key, []))
                detail_prefix = f"Parameter for '{parent_key}' step"
            elif parent_key == "config":
                suggestions.extend(CONFIG_KEYWORDS)
                detail_prefix = "Parameter for 'config' section"
            elif parent_key == "persona":
                suggestions.extend(PERSONA_KEYWORDS)
                detail_prefix = "Parameter for 'persona' section"
            elif parent_key == "input":
                suggestions.extend(INPUT_KEYWORDS) # mainly "vars"
                detail_prefix = "Parameter for 'input' section"
            elif parent_key == "vars": # under input
                 # Suggest 'type:' or 'description:' if line looks like "var_name:" (handled by current_word being empty after ':')
                if text_before_cursor.strip().endswith(":"):
                    completion_items.append(create_completion_item("type:", CompletionItemKind.PROPERTY, insert_text="type: ", detail="Data type of the input variable"))
                    completion_items.append(create_completion_item("description:", CompletionItemKind.PROPERTY, insert_text="description: ", detail="Description of the input variable"))
            elif parent_key == "outputSchema":
                suggestions.extend(OUTPUTSCHEMA_KEYWORDS) # mainly "schema"
                detail_prefix = "Parameter for 'outputSchema' section"
            elif parent_key == "constraints": # Top-level or step-level
                suggestions.extend(CONSTRAINTS_KEYWORDS)
                detail_prefix = "Parameter for 'constraints' section"
            elif parent_key == "parameters": # under config
                # Dynamic, no static keywords here, but could offer common LLM params if known
                pass
            elif parent_key == "examples": # under prompt (is a list of dicts)
                 # If the current line starts with "- " and is properly indented under "examples:"
                if text_before_cursor.strip().startswith("- ") and indent_level > parent_indent + 1: # typical list item indent
                    completion_items.append(create_completion_item("input:", CompletionItemKind.PROPERTY, insert_text="input: ", detail="Example input"))
                    completion_items.append(create_completion_item("output:", CompletionItemKind.PROPERTY, insert_text="output: ", detail="Example output"))


            for keyword in suggestions:
                if keyword.startswith(current_word):
                    # Add colon and space for typical YAML key-value, and newline with indent for block
                    insert_text_formatted = f"{keyword}:\n{' ' * (indent_level + 2)}"
                    # Simpler insert for some keys that take simple values on same line or specific structures
                    if keyword in ["type", "lang", "from", "query", "k", "name", "if", "for", "while", "loop", "def", "model", "api_key", "role", "style", "tone", "audience", "custom_validator", "regex"]:
                        insert_text_formatted = f"{keyword}: "

                    completion_items.append(
                        create_completion_item(keyword, CompletionItemKind.PROPERTY, insert_text=insert_text_formatted, detail=detail_prefix)
                    )

            # Special case for 'lang: python' under 'code:'
            if parent_key == "code" and text_before_cursor.strip() == "lang:":
                completion_items.append(create_completion_item("python", CompletionItemKind.VALUE, insert_text="python", detail="Language type for code step"))


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

    # Step Types
    "prompt": "A step to interact with an LLM by sending a prompt and receiving a response.",
    "retrieve": "A step to retrieve relevant data from a knowledge source (e.g., RAG).",
    "tool": "A step to execute a predefined Python tool/function.",
    "code": "A step to execute a block of Python code in a sandboxed environment.",
    "if": "A control flow step for conditional execution of branches (`then`, `else`). Also the key for the condition expression itself.",
    "for": "A control flow step for iterating over a collection or a range. Also the key for the loop expression.",
    "while": "A control flow step for executing a block of steps while a condition is true. Also the key for the condition expression.",
    "loop": "Alias for a `while` loop; executes steps while a condition is true. Also the key for the condition expression.",

    # Common Parameters
    "def": "Defines a variable name to store the output of this step in the context.",
    "steps": "A list of steps to be executed, typically within `workflow`, `if`, or `loop` blocks.",

    # PromptStep Specific
    "text": "The main prompt text for an LLM (supports {{templating}}).",
    "examples": "A list of input/output examples for few-shot prompting.",
    "max_retries": "Maximum self-correction retries if prompt constraints fail (default: 0).",

    # RetrieveStep Specific
    "from": "Specifies the source of the knowledge base (e.g., file path to JSON).",
    "query": "The query string for retrieval (supports {{templating}}).",
    "k": "The maximum number of documents to retrieve (default: 3).",

    # ToolStep Specific
    "name": "The registered name of the tool to execute OR the name of an input variable.", # Used in multiple contexts
    "args": "A dictionary of arguments to pass to the tool.",

    # CodeStep Specific
    "lang": "The language of the script (currently only 'python').",
    "script": "The block of code to execute.",

    # IfStep Specific
    "then": "Block of steps to execute if the 'if' condition is true.",
    "else": "Block of steps to execute if the 'if' condition is false.",

    # Constraints Object Keys (can be top-level or under a step)
    "constraints": "Defines validation rules for an output (e.g., type, regex, choices, custom_validator).",
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
