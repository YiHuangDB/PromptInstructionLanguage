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
)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

class PilLanguageServer(LanguageServer):
    CMD_SHOW_INFO_MESSAGE = "pil/showInfoMessage" # Example custom command

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
            save=None
        )
        # Add other capabilities here as they are implemented
        # e.g., completion_provider=CompletionOptions(trigger_characters=['{', '.']),
        # hover_provider=True,
        # definition_provider=True
    )
    logger.info(f"Server capabilities: {server_capabilities}")
    return InitializeResult(capabilities=server_capabilities)


@pil_server.feature("textDocument/didOpen")
async def did_open(ls: PilLanguageServer, params: DidOpenTextDocumentParams):
    logger.info(f"Document opened: {params.text_document.uri}")
    # Example: Accessing document text (pygls automatically manages it in ls.workspace)
    # document = ls.workspace.get_document(params.text_document.uri)
    # if document:
    #     logger.info(f"   Content (first 50 chars): {document.source[:50]}")
    #     # Here you could trigger initial diagnostics
    # else:
    #     logger.warning(f"Could not get document from workspace: {params.text_document.uri}")


@pil_server.feature("textDocument/didChange")
async def did_change(ls: PilLanguageServer, params: DidChangeTextDocumentParams):
    logger.info(f"Document changed: {params.text_document.uri}")
    # If TextDocumentSyncKind.FULL, the full text is in the last contentChange.
    # pygls updates the document in ls.workspace automatically.
    # document = ls.workspace.get_document(params.text_document.uri)
    # if document:
    #     logger.info(f"   New content (first 50 chars): {document.source[:50]}")
    #     # Here you could trigger diagnostics on change
    # else:
    #     logger.warning(f"Could not get document from workspace after change: {params.text_document.uri}")


@pil_server.command(PilLanguageServer.CMD_SHOW_INFO_MESSAGE)
async def show_info_message_command(ls: PilLanguageServer, args: list): # args is a list
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
