/*
 * Zot CLI Bridge — Zotero 7 bootstrap plugin.
 *
 * Registers two HTTP endpoints on Zotero's built-in local server
 * (127.0.0.1:23119):
 *
 *   GET  /zot-cli/ping          — health probe, returns version + Zotero version
 *   POST /zot-cli/find-pdf      — body {"key": "ABCD1234"} (or "?key=" query)
 *                                  triggers Zotero.Attachments.addAvailableFile
 *                                  for that item, returns the attachment key on success
 *
 * The whole point of going through Zotero (rather than fetching the PDF
 * directly from Python) is that Zotero's "Find Full Text" reuses the user's
 * configured PDF resolvers AND the authenticated sessions / proxies they've
 * set up in the desktop app, which Web-API access cannot do.
 *
 * License: CC-BY-NC-4.0 (matches the parent zotero-cli-cc repo).
 */

/* global Zotero, ChromeUtils */

const PLUGIN_VERSION = "0.1.0";

function buildEndpoint(handler, { methods = ["GET"], dataTypes = ["application/json"] } = {}) {
  const Endpoint = function () {};
  Endpoint.prototype = {
    supportedMethods: methods,
    supportedDataTypes: dataTypes,
    init: handler,
  };
  return Endpoint;
}

async function handlePing(_options) {
  return [
    200,
    "application/json",
    JSON.stringify({
      ok: true,
      bridge_version: PLUGIN_VERSION,
      zotero_version: Zotero.version,
      user_library_id: Zotero.Libraries.userLibraryID,
    }),
  ];
}

async function handleFindPdf(options) {
  // Accept the item key from either the JSON body or the query string so
  // the CLI can use whichever fits a given call shape.
  let key = null;
  let libraryID = null;
  if (options.data && typeof options.data === "object") {
    key = options.data.key || null;
    libraryID = options.data.libraryID || null;
  }
  if (!key && options.searchParams) {
    key = options.searchParams.get("key");
    const lib = options.searchParams.get("libraryID");
    if (lib) libraryID = parseInt(lib, 10);
  }
  if (!key) {
    return [400, "application/json", JSON.stringify({ ok: false, error: "missing 'key'" })];
  }
  libraryID = libraryID || Zotero.Libraries.userLibraryID;

  let item;
  try {
    item = await Zotero.Items.getByLibraryAndKeyAsync(libraryID, key);
  } catch (e) {
    return [500, "application/json", JSON.stringify({ ok: false, error: "lookup failed: " + e })];
  }
  if (!item) {
    return [404, "application/json", JSON.stringify({ ok: false, error: "item not found", key, libraryID })];
  }
  if (!item.isRegularItem()) {
    return [
      400,
      "application/json",
      JSON.stringify({ ok: false, error: "item is not a regular item (note/attachment)", key }),
    ];
  }

  // Zotero 7+ exposes addAvailableFile; older builds still have addAvailablePDF
  // which Zotero forwards to the new name.
  const fn =
    (Zotero.Attachments && Zotero.Attachments.addAvailableFile) ||
    (Zotero.Attachments && Zotero.Attachments.addAvailablePDF);
  if (!fn) {
    return [
      500,
      "application/json",
      JSON.stringify({
        ok: false,
        error: "Zotero.Attachments.addAvailableFile is unavailable on this build",
      }),
    ];
  }

  let attachment;
  try {
    attachment = await fn.call(Zotero.Attachments, item);
  } catch (e) {
    Zotero.logError(e);
    return [500, "application/json", JSON.stringify({ ok: false, error: "find-pdf failed: " + e, key })];
  }

  if (!attachment) {
    return [
      200,
      "application/json",
      JSON.stringify({
        ok: true,
        found: false,
        key,
        message: "No PDF found via configured resolvers (check Preferences → Find Full Text)",
      }),
    ];
  }

  let filename = null;
  let contentType = null;
  try {
    filename = attachment.attachmentFilename;
    contentType = attachment.attachmentContentType;
  } catch (_) {
    /* tolerate missing accessors on older builds */
  }

  return [
    200,
    "application/json",
    JSON.stringify({
      ok: true,
      found: true,
      key,
      attachment_key: attachment.key,
      filename,
      content_type: contentType,
    }),
  ];
}

const PING_ENDPOINT = buildEndpoint(handlePing, { methods: ["GET"] });
const FIND_PDF_ENDPOINT = buildEndpoint(handleFindPdf, {
  methods: ["POST", "GET"],
  dataTypes: ["application/json", "application/x-www-form-urlencoded"],
});

function install() {}
function uninstall() {}

async function startup({ id, version }) {
  Zotero.debug("[zot-cli-bridge] startup " + id + " v" + version);
  Zotero.Server.Endpoints["/zot-cli/ping"] = PING_ENDPOINT;
  Zotero.Server.Endpoints["/zot-cli/find-pdf"] = FIND_PDF_ENDPOINT;
}

function shutdown() {
  Zotero.debug("[zot-cli-bridge] shutdown");
  if (Zotero && Zotero.Server && Zotero.Server.Endpoints) {
    delete Zotero.Server.Endpoints["/zot-cli/ping"];
    delete Zotero.Server.Endpoints["/zot-cli/find-pdf"];
  }
}
