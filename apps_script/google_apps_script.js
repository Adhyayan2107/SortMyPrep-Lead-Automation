// ─────────────────────────────────────────────────────────────────────────────
// sortmyprep Lead Manager — Google Apps Script
//
// FIRST-TIME SETUP (do this once after pasting the script):
//   1. Save the script (Ctrl+S)
//   2. Function dropdown → select "setup" → Run ▶ → Allow permissions
//   3. Function dropdown → select "authorizeAll" → Run ▶ → Allow ALL permissions
//   4. Open your Google Sheet → SortMyPrep menu → Sync New Leads
//
// UPGRADING FROM OLD VERSION:
//   Run "Full Resync (replace all)" once to pull the Zone column into existing rows.
//   After that, use "Sync New Leads" for every subsequent pipeline run.
// ─────────────────────────────────────────────────────────────────────────────

const BACKEND_URL  = "https://sortmyprep-lead-automation.onrender.com";
const SENDER_NAME  = "Ananya | sortmyprep";

// Sheet column headers — order must match _buildRows()
const HEADERS = [
  "Lead ID", "Contact Name", "Title", "Level", "Email", "LinkedIn",
  "Company", "Website", "Address", "Country", "Zone", "Phone",
  "Avg Rating", "Review Count", "Generated At",
  "Generate Script", "Send Email", "Email Script", "Sent At",
];

// 1-based column index lookup: COL["Email"] === 5
const COL = {};
HEADERS.forEach((h, i) => { COL[h] = i + 1; });

// Maps sheet header → MongoDB field name for the batch-sync endpoint.
const FIELD_MAP = {
  "Contact Name":    "contact_name",
  "Title":           "contact_title",
  "Level":           "contact_level",
  "Email":           "email",
  "LinkedIn":        "linkedin",
  "Company":         "company",
  "Website":         "company_website",
  "Address":         "company_address",
  "Phone":           "company_phone",
  "Avg Rating":      "company_reviews_avg",
  "Review Count":    "company_reviews_count",
  "Generate Script": "generate_script",
  "Send Email":      "send_email",
  "Email Script":    "email_script",
  "Sent At":         "sent_at",
  // "Zone" and "Country" are pipeline-stamped — not editable from the sheet
};


// ── One-time setup ────────────────────────────────────────────────────────────

function setup() {
  ScriptApp.getProjectTriggers()
    .filter(t => ["onEditHandler", "flushEdits"].includes(t.getHandlerFunction()))
    .forEach(t => ScriptApp.deleteTrigger(t));

  ScriptApp.newTrigger("onEditHandler")
    .forSpreadsheet(SpreadsheetApp.getActive())
    .onEdit()
    .create();

  ScriptApp.newTrigger("flushEdits")
    .timeBased()
    .everyMinutes(1)
    .create();

  SpreadsheetApp.getUi().alert(
    "✅ Triggers installed!\n\nNow run authorizeAll() to grant all permissions."
  );
}


function authorizeAll() {
  UrlFetchApp.fetch("https://www.google.com");
  SpreadsheetApp.getUi().alert(
    "✅ All permissions granted!\n\nGenerate Script and Send Email will now work."
  );
}


// ── Menu ─────────────────────────────────────────────────────────────────────

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("SortMyPrep")
    .addItem("Sync New Leads",            "syncLeads")
    .addItem("Full Resync (replace all)", "fullResync")
    .addItem("Flush Pending Edits Now",   "flushEdits")
    .addSeparator()
    .addItem("About", "showAbout")
    .addToUi();
}

function showAbout() {
  SpreadsheetApp.getUi().alert(
    "sortmyprep Lead Manager\n\n" +
    "• Sync New Leads    — append only leads not already in the sheet\n" +
    "• Full Resync       — replace all rows with fresh data from backend\n" +
    "• Generate Script   — set column to Yes to generate a personalised email\n" +
    "• Send Email        — set column to Yes to send via Gmail\n" +
    "• Cell edits auto-sync to backend within 1 minute\n\n" +
    "Tip: Use the Zone column filter to work on one pipeline run at a time."
  );
}


// ── Sync leads: APPEND-ONLY (Fix B) ──────────────────────────────────────────
// Only adds leads whose IDs are not already in the sheet.
// Existing rows — including email scripts and sent status — are untouched.

function syncLeads() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const ui    = SpreadsheetApp.getUi();

  let data;
  try {
    const resp = UrlFetchApp.fetch(BACKEND_URL + "/api/leads");
    data = JSON.parse(resp.getContentText());
  } catch (e) {
    ui.alert("Failed to reach backend: " + e.message);
    return;
  }

  // Ensure header row exists
  if (sheet.getLastRow() < 1) {
    sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);
    styleHeader(sheet);
  }

  // Collect Lead IDs already in the sheet
  const existingIds = new Set();
  const lastRow = sheet.getLastRow();
  if (lastRow > 1) {
    sheet.getRange(2, COL["Lead ID"], lastRow - 1, 1)
         .getValues()
         .forEach(function(r) { if (r[0]) existingIds.add(String(r[0])); });
  }

  const newLeads = data.filter(function(lead) {
    return !existingIds.has(String(lead.id));
  });

  if (!newLeads.length) {
    ui.alert("No new leads to sync.\n(Use Full Resync to replace all rows with fresh backend data.)");
    return;
  }

  const rows     = _buildRows(newLeads);
  const appendAt = sheet.getLastRow() + 1;
  sheet.getRange(appendAt, 1, rows.length, HEADERS.length).setValues(rows);
  styleDataRows(sheet, rows.length, appendAt);
  ui.alert("Added " + rows.length + " new lead(s).");
}


// ── Full Resync: wipe + rewrite (for recovery / schema changes) ───────────────

function fullResync() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const ui    = SpreadsheetApp.getUi();

  const confirm = ui.alert(
    "Full Resync",
    "This will REPLACE ALL rows in the sheet with fresh data from the backend.\n\n" +
    "Any local edits not yet flushed to the backend will be lost.\n\nContinue?",
    ui.ButtonSet.YES_NO
  );
  if (confirm !== ui.Button.YES) return;

  let data;
  try {
    const resp = UrlFetchApp.fetch(BACKEND_URL + "/api/leads");
    data = JSON.parse(resp.getContentText());
  } catch (e) {
    ui.alert("Failed to reach backend: " + e.message);
    return;
  }

  sheet.clearContents();
  sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);
  styleHeader(sheet);

  if (!data.length) {
    ui.alert("No leads found in the backend.");
    return;
  }

  const rows = _buildRows(data);
  sheet.getRange(2, 1, rows.length, HEADERS.length).setValues(rows);
  styleDataRows(sheet, rows.length, 2);
  ui.alert("Synced " + rows.length + " leads.");
}


// ── Row builder (shared by both sync functions) ───────────────────────────────

function _buildRows(data) {
  const LEVEL_DISPLAY = { "level1": "Senior (L1)", "level2": "Mid (L2)" };
  return data.map(function(lead) {
    return [
      lead.id,
      lead.contact_name          || "",
      lead.contact_title         || "",
      LEVEL_DISPLAY[lead.contact_level] || lead.contact_level || "",
      lead.email                 || "",
      lead.linkedin              || "",
      lead.company               || "",
      lead.company_website       || "",
      lead.company_address       || "",
      lead.country               || "",
      lead.zone_name             || "",   // Fix C — pipeline-stamped zone
      lead.company_phone         || "",
      lead.company_reviews_avg   || "",
      lead.company_reviews_count || "",
      lead.generated_at          || "",
      lead.generate_script       || "No",
      lead.send_email            || "No",
      lead.email_script          || "",
      lead.sent_at               || "",
    ];
  });
}


// ── onEdit handler (installable trigger) ─────────────────────────────────────

function onEditHandler(e) {
  const sheet = e.source.getActiveSheet();
  const row   = e.range.getRow();
  const col   = e.range.getColumn();
  const value = (e.value || "").toString().trim();

  if (row === 1) return;

  const header = HEADERS[col - 1];
  const leadId = sheet.getRange(row, COL["Lead ID"]).getValue();

  if (!leadId || !header) return;

  // Fix A — guard: only trigger if the action hasn't already been completed
  if (header === "Generate Script" && value.toLowerCase() === "yes") {
    const existingScript = sheet.getRange(row, COL["Email Script"]).getValue();
    if (existingScript && existingScript.toString().trim() !== "") return;
    handleGenerateScript(sheet, row, leadId);
    return;
  }
  if (header === "Send Email" && value.toLowerCase() === "yes") {
    const sentAt = sheet.getRange(row, COL["Sent At"]).getValue();
    if (sentAt && sentAt.toString().trim() !== "") return;
    handleSendEmail(sheet, row, leadId);
    return;
  }

  const field = FIELD_MAP[header];
  if (field) {
    queueEdit(String(leadId), field, value);
  }
}


// ── Edit queue (PropertiesService) ────────────────────────────────────────────

function queueEdit(leadId, field, value) {
  const props = PropertiesService.getScriptProperties();
  const queue = JSON.parse(props.getProperty("editQueue") || "[]");

  const idx   = queue.findIndex(function(q) { return q.id === leadId && q.field === field; });
  const entry = { id: leadId, field: field, value: value };
  if (idx >= 0) queue[idx] = entry;
  else queue.push(entry);

  props.setProperty("editQueue", JSON.stringify(queue));
}

function flushEdits() {
  const props = PropertiesService.getScriptProperties();
  const raw   = props.getProperty("editQueue");
  if (!raw) return;

  const queue = JSON.parse(raw);
  if (!queue.length) return;

  props.deleteProperty("editQueue");

  try {
    UrlFetchApp.fetch(BACKEND_URL + "/api/leads/batch-update", {
      method:      "PATCH",
      contentType: "application/json",
      payload:     JSON.stringify({ updates: queue }),
      muteHttpExceptions: true,
    });
  } catch (e) {
    console.error("flushEdits failed: " + e.message);
  }
}


// ── Generate Script ───────────────────────────────────────────────────────────

function handleGenerateScript(sheet, row, leadId) {
  const cell = sheet.getRange(row, COL["Generate Script"]);
  cell.setValue("Generating...");

  let script;
  try {
    const resp = UrlFetchApp.fetch(
      BACKEND_URL + "/api/leads/" + leadId + "/generate", {
        method:      "post",
        contentType: "application/json",
        payload:     JSON.stringify({ email_number: 1 }),
        muteHttpExceptions: true,
      }
    );
    const data = JSON.parse(resp.getContentText());
    if (data.error) throw new Error(data.error);
    script = data.script;
  } catch (e) {
    cell.setValue("No");
    SpreadsheetApp.getUi().alert("Script generation failed: " + e.message);
    return;
  }

  sheet.getRange(row, COL["Email Script"]).setValue(script);
  cell.setValue("Yes");
  styleScriptReady(sheet, row);
}


// ── Send Email ────────────────────────────────────────────────────────────────

function handleSendEmail(sheet, row, leadId) {
  const toEmail = sheet.getRange(row, COL["Email"]).getValue();
  const script  = sheet.getRange(row, COL["Email Script"]).getValue();
  const cell    = sheet.getRange(row, COL["Send Email"]);

  if (!toEmail) {
    cell.setValue("No");
    SpreadsheetApp.getUi().alert("No email address for this lead.");
    return;
  }
  if (!script) {
    cell.setValue("No");
    SpreadsheetApp.getUi().alert("Generate the script first (set Generate Script → Yes).");
    return;
  }

  const lines    = script.split("\n");
  const subjLine = lines.find(function(l) { return l.toLowerCase().startsWith("subject:"); }) || "";
  const subject  = subjLine.replace(/^subject:\s*/i, "").trim()
                   || "Partnership Opportunity | sortmyprep";
  const body     = lines.filter(function(l) { return !l.toLowerCase().startsWith("subject:"); })
                        .join("\n").trim();

  cell.setValue("Sending...");

  try {
    GmailApp.sendEmail(toEmail, subject, body, {
      name:     SENDER_NAME,
      replyTo:  "ananya@sortmyprep.com",
      htmlBody: plainToHtml(body),
    });
  } catch (e) {
    cell.setValue("No");
    SpreadsheetApp.getUi().alert("Failed to send email: " + e.message);
    return;
  }

  try {
    UrlFetchApp.fetch(BACKEND_URL + "/api/leads/" + leadId + "/send", {
      method: "post", contentType: "application/json", muteHttpExceptions: true,
    });
  } catch (_) {}

  const now = new Date();
  const ts  = Utilities.formatDate(now, Session.getScriptTimeZone(), "dd MMM yyyy, hh:mm a");
  sheet.getRange(row, COL["Sent At"]).setValue(ts);
  cell.setValue("Yes");
  styleEmailSent(sheet, row);
}


// ── Plain-text → HTML email converter ────────────────────────────────────────

function _esc(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

function _fmt(s) {
  const parts = s.split(/(https?:\/\/[^\s]+)/g);
  let out = "";
  parts.forEach(function(part, i) {
    if (i % 2 === 1) {
      const url = part.replace(/[.,;!?)]+$/, "");
      out += '<a href="' + url + '" style="color:#1155CC;font-weight:600;text-decoration:none;">View Demo →</a>';
    } else {
      let t = _esc(part);
      t = t.replace(/^(Hi\s+)(\w+)([,!.]?\s)/, "$1<strong>$2</strong>$3");
      t = t.replace(/\bsortmyprep\b/gi, "<strong>sortmyprep</strong>");
      t = t.replace(/\b2,000\+/g, "<strong>2,000+</strong>");
      t = t.replace(/\b1,000\b/g, "<strong>1,000</strong>");
      out += t;
    }
  });
  return out;
}

function plainToHtml(plain) {
  const blocks = plain.trim().split(/\n\s*\n/);
  let body = "";

  blocks.forEach(function(block) {
    const lines = block.split("\n").map(function(l){ return l.trim(); }).filter(Boolean);
    if (!lines.length) return;

    const isItem = function(l){ return /^\d+\.\s/.test(l); };
    const items  = lines.filter(isItem);

    if (items.length >= 2) {
      const header = lines.filter(function(l){ return !isItem(l); }).join(" ");
      if (header) {
        body += '<p style="margin:12px 0 2px 0;"><strong>' + _esc(header) + "</strong></p>";
      }
      body += '<ol style="margin:4px 0 12px 0;padding-left:22px;">';
      items.forEach(function(item) {
        body += '<li style="margin:4px 0;">' + _fmt(item.replace(/^\d+\.\s*/, "")) + "</li>";
      });
      body += "</ol>";
    } else {
      body += '<p style="margin:10px 0;">' + _fmt(lines.join(" ")) + "</p>";
    }
  });

  return (
    '<div style="font-family:Arial,sans-serif;font-size:14px;color:#222222;' +
    'line-height:1.75;max-width:580px;">' +
    body +
    "</div>"
  );
}


// ── Styling ───────────────────────────────────────────────────────────────────

function styleHeader(sheet) {
  sheet.getRange(1, 1, 1, HEADERS.length)
       .setBackground("#1F4E79")
       .setFontColor("#FFFFFF")
       .setFontWeight("bold")
       .setFontSize(11)
       .setFontFamily("Arial")
       .setHorizontalAlignment("center")
       .setVerticalAlignment("middle");
  sheet.setRowHeight(1, 28);
  sheet.setFrozenRows(1);

  const widths = {
    "Lead ID":         160,
    "Contact Name":    160,
    "Title":           160,
    "Level":           110,
    "Email":           200,
    "LinkedIn":        220,
    "Company":         180,
    "Website":         150,
    "Address":         240,
    "Country":          80,
    "Zone":            100,
    "Phone":           130,
    "Avg Rating":       90,
    "Review Count":    110,
    "Generated At":    160,
    "Generate Script": 130,
    "Send Email":      110,
    "Email Script":    420,
    "Sent At":         160,
  };
  Object.entries(widths).forEach(function([h, w]) {
    if (COL[h]) sheet.setColumnWidth(COL[h], w);
  });

  const yesNo = SpreadsheetApp.newDataValidation()
    .requireValueInList(["No", "Yes"], true).build();
  sheet.getRange(2, COL["Generate Script"], 500, 1).setDataValidation(yesNo);
  sheet.getRange(2, COL["Send Email"],      500, 1).setDataValidation(yesNo);
}

// startRow defaults to 2 — pass appendAt when styling newly appended rows only
function styleDataRows(sheet, count, startRow) {
  startRow = startRow || 2;
  if (count < 1) return;

  const levels = sheet.getRange(startRow, COL["Level"], count, 1).getValues();

  sheet.getRange(startRow, 1, count, HEADERS.length)
       .setFontFamily("Arial")
       .setFontSize(10)
       .setVerticalAlignment("middle")
       .setBorder(true, true, true, true, true, true,
                  "#DDDDDD", SpreadsheetApp.BorderStyle.SOLID);

  for (let i = 0; i < count; i++) {
    const level = levels[i][0];
    const bg    = level === "Senior (L1)" ? "#D6E4F0" : "#FFFFFF";
    sheet.getRange(startRow + i, 1, 1, HEADERS.length).setBackground(bg);
    sheet.setRowHeight(startRow + i, 22);
  }
}

function styleScriptReady(sheet, row) {
  sheet.getRange(row, COL["Generate Script"])
       .setBackground("#C6EFCE").setFontColor("#276221");
}

function styleEmailSent(sheet, row) {
  sheet.getRange(row, COL["Send Email"])
       .setBackground("#C6EFCE").setFontColor("#276221");
  sheet.getRange(row, 1, 1, HEADERS.length).setBackground("#F0FFF0");
}
