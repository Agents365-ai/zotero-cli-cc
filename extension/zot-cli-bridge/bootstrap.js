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
 *   POST /zot-cli/rename        — body {"attachmentKey","newName","libraryID"?,"force"?}
 *                                  renames the attachment's stored file via
 *                                  renameAttachmentFile and syncs its title
 *   POST /zot-cli/import-file   — body {"parentKey","path","libraryID"?,"groupID"?,"title"?}
 *                                  imports a local file as an attachment via
 *                                  Zotero.Attachments.importFromFile so the
 *                                  binary lands in local storage immediately.
 *                                  Pass "groupID" (the Web-API group id) to
 *                                  target a group library — it is mapped to the
 *                                  desktop's internal libraryID.
 *
 * The whole point of going through Zotero (rather than fetching the PDF
 * directly from Python) is that Zotero's "Find Full Text" reuses the user's
 * configured PDF resolvers AND the authenticated sessions / proxies they've
 * set up in the desktop app, which Web-API access cannot do. import-file
 * exists for the same reason in reverse: a Web-API upload only lands the file
 * in zotero.org cloud storage, so it never appears in local storage/ until a
 * file-sync pulls it back down — and that race breaks plugins that move
 * attachments on import (e.g. zotero-attanger). Importing through the desktop
 * writes straight to local storage and syncs *up*.
 *
 * License: CC-BY-NC-4.0 (matches the parent zotero-cli-cc repo).
 */

/* global Zotero, ChromeUtils */

const PLUGIN_VERSION = "0.4.0";

// Map a Web-API group id to the desktop client's internal libraryID. The two
// differ: the group id is what the Zotero Web API / `--library group:<id>`
// uses, while items on disk are keyed by libraryID. Both Zotero.Groups
// accessors are synchronous cache reads populated at startup. Returns null when
// the group is unknown (not joined / not yet synced on this desktop).
function libraryIDFromGroupID(groupID) {
  const gid = parseInt(groupID, 10);
  if (!gid) return null;
  if (typeof Zotero.Groups.getLibraryIDFromGroupID === "function") {
    return Zotero.Groups.getLibraryIDFromGroupID(gid) || null;
  }
  const group = Zotero.Groups.get(gid);
  return group ? group.libraryID : null;
}

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

async function handleRename(options) {
  // Body: {"attachmentKey": "...", "newName": "X.pdf", "libraryID"?, "force"?}
  let attachmentKey = null;
  let newName = null;
  let libraryID = null;
  let force = false;
  if (options.data && typeof options.data === "object") {
    attachmentKey = options.data.attachmentKey || null;
    newName = options.data.newName || null;
    libraryID = options.data.libraryID || null;
    force = options.data.force === true;
  }
  if (!attachmentKey || !newName) {
    return [400, "application/json", JSON.stringify({ ok: false, error: "missing 'attachmentKey' or 'newName'" })];
  }
  libraryID = libraryID || Zotero.Libraries.userLibraryID;

  let att;
  try {
    att = await Zotero.Items.getByLibraryAndKeyAsync(libraryID, attachmentKey);
  } catch (e) {
    return [500, "application/json", JSON.stringify({ ok: false, error: "lookup failed: " + e })];
  }
  if (!att) {
    return [
      404,
      "application/json",
      JSON.stringify({ ok: false, error: "attachment not found", key: attachmentKey, libraryID }),
    ];
  }
  if (!att.isAttachment || !att.isAttachment()) {
    return [400, "application/json", JSON.stringify({ ok: false, error: "item is not an attachment", key: attachmentKey })];
  }

  let oldName = null;
  try {
    oldName = att.attachmentFilename;
  } catch (_) {
    /* tolerate */
  }

  let status;
  try {
    status = await att.renameAttachmentFile(newName, force, false);
  } catch (e) {
    Zotero.logError(e);
    return [500, "application/json", JSON.stringify({ ok: false, error: "rename failed: " + e, key: attachmentKey })];
  }

  if (status === -1) {
    return [
      409,
      "application/json",
      JSON.stringify({
        ok: false,
        error: "destination file already exists (pass force to overwrite)",
        code: "exists",
        key: attachmentKey,
        new_name: newName,
      }),
    ];
  }
  if (status !== true) {
    return [
      404,
      "application/json",
      JSON.stringify({ ok: false, error: "attachment file not found on disk", key: attachmentKey }),
    ];
  }

  // Keep the displayed title in sync with the new filename.
  try {
    if (newName !== att.getField("title")) {
      att.setField("title", newName);
      await att.saveTx();
    }
  } catch (e) {
    Zotero.logError(e);
  }

  return [
    200,
    "application/json",
    JSON.stringify({ ok: true, renamed: true, attachment_key: attachmentKey, old_name: oldName, new_name: newName }),
  ];
}

async function handleImportFile(options) {
  // Body: {"parentKey": "...", "path": "/abs/file.pdf", "libraryID"?, "groupID"?, "title"?}
  let parentKey = null;
  let path = null;
  let libraryID = null;
  let groupID = null;
  let title = null;
  if (options.data && typeof options.data === "object") {
    parentKey = options.data.parentKey || null;
    path = options.data.path || null;
    libraryID = options.data.libraryID || null;
    groupID = options.data.groupID || null;
    title = options.data.title || null;
  }
  if (!parentKey || !path) {
    return [400, "application/json", JSON.stringify({ ok: false, error: "missing 'parentKey' or 'path'" })];
  }
  // A group library's Web-API id is not the desktop's internal libraryID; map it.
  if (groupID != null) {
    const mapped = libraryIDFromGroupID(groupID);
    if (!mapped) {
      return [404, "application/json", JSON.stringify({ ok: false, error: "group not found", groupID })];
    }
    libraryID = mapped;
  }
  libraryID = libraryID || Zotero.Libraries.userLibraryID;

  // The CLI and Zotero share the machine (loopback), so the desktop can read
  // the absolute path directly. Reject early if it can't see the file.
  let fileExists = false;
  try {
    fileExists = Zotero.File.pathToFile(path).exists();
  } catch (_) {
    fileExists = false;
  }
  if (!fileExists) {
    return [404, "application/json", JSON.stringify({ ok: false, error: "file not found on disk", path })];
  }

  let parent;
  try {
    parent = await Zotero.Items.getByLibraryAndKeyAsync(libraryID, parentKey);
  } catch (e) {
    return [500, "application/json", JSON.stringify({ ok: false, error: "lookup failed: " + e })];
  }
  if (!parent) {
    return [
      404,
      "application/json",
      JSON.stringify({ ok: false, error: "parent item not found", key: parentKey, libraryID }),
    ];
  }
  if (!parent.isRegularItem()) {
    return [
      400,
      "application/json",
      JSON.stringify({ ok: false, error: "parent is not a regular item (note/attachment)", key: parentKey }),
    ];
  }

  const fn = Zotero.Attachments && Zotero.Attachments.importFromFile;
  if (!fn) {
    return [
      500,
      "application/json",
      JSON.stringify({ ok: false, error: "Zotero.Attachments.importFromFile is unavailable on this build" }),
    ];
  }

  let attachment;
  try {
    const opts = { file: path, parentItemID: parent.id, libraryID };
    if (title) opts.title = title;
    attachment = await fn.call(Zotero.Attachments, opts);
  } catch (e) {
    Zotero.logError(e);
    return [500, "application/json", JSON.stringify({ ok: false, error: "import failed: " + e, key: parentKey })];
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
      imported: true,
      parent_key: parentKey,
      attachment_key: attachment.key,
      filename,
      content_type: contentType,
    }),
  ];
}

const PING_ENDPOINT = buildEndpoint(handlePing, { methods: ["GET"] });
const RENAME_ENDPOINT = buildEndpoint(handleRename, {
  methods: ["POST"],
  dataTypes: ["application/json"],
});
const FIND_PDF_ENDPOINT = buildEndpoint(handleFindPdf, {
  methods: ["POST", "GET"],
  dataTypes: ["application/json", "application/x-www-form-urlencoded"],
});
const IMPORT_FILE_ENDPOINT = buildEndpoint(handleImportFile, {
  methods: ["POST"],
  dataTypes: ["application/json"],
});

function install() {}
function uninstall() {}

async function startup({ id, version }) {
  Zotero.debug("[zot-cli-bridge] startup " + id + " v" + version);
  Zotero.Server.Endpoints["/zot-cli/ping"] = PING_ENDPOINT;
  Zotero.Server.Endpoints["/zot-cli/find-pdf"] = FIND_PDF_ENDPOINT;
  Zotero.Server.Endpoints["/zot-cli/rename"] = RENAME_ENDPOINT;
  Zotero.Server.Endpoints["/zot-cli/import-file"] = IMPORT_FILE_ENDPOINT;
}

function shutdown() {
  Zotero.debug("[zot-cli-bridge] shutdown");
  if (Zotero && Zotero.Server && Zotero.Server.Endpoints) {
    delete Zotero.Server.Endpoints["/zot-cli/ping"];
    delete Zotero.Server.Endpoints["/zot-cli/find-pdf"];
    delete Zotero.Server.Endpoints["/zot-cli/rename"];
    delete Zotero.Server.Endpoints["/zot-cli/import-file"];
  }
}
