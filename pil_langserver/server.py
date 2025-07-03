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
    Diagnostic, # Added
    DiagnosticSeverity, # Added
    Position, # Added
    Range as LspRange, # Added, aliased to avoid conflict with built-in range
)
import yaml # For parsing document content
from pil_engine.interpreter import PilParser # To parse PIL programs
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
            save=None # Can add save options if needed, e.g., TextDocumentSyncSaveOptions(include_text=True)
        )
        # Future capabilities (completion, hover, definition) will be added here
    )
    logger.info(f"Server capabilities: {server_capabilities}")
    return InitializeResult(capabilities=server_capabilities)

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

if __name__ == "__main__":
    main()
