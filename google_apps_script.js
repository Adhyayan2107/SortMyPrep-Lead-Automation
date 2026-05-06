// ─────────────────────────────────────────────────────────────────────────────
// sortmyprep Lead Manager — Google Apps Script
//
// FIRST-TIME SETUP (do this once after pasting the script):
//   1. Save the script (Ctrl+S)
//   2. Function dropdown → select "setup" → Run ▶ → Allow permissions
//   3. Function dropdown → select "authorizeAll" → Run ▶ → Allow ALL permissions
//   4. Open your Google Sheet → SortMyPrep menu → Sync Leads
// ─────────────────────────────────────────────────────────────────────────────

const BACKEND_URL  = "https://sortmyprep-lead-automation.onrender.com";
const SENDER_NAME  = "Ananya | sortmyprep";

// Sheet column headers — order must match syncLeads() row builder
const HEADERS = [
  "Lead ID", "Contact Name", "Title", "Level", "Email", "LinkedIn",
  "Company", "Website", "Address", "Phone", "Avg Rating", "Review Count",
  "Generate Script", "Send Email", "Email Script", "Sent At",
];

// 1-based column index lookup: COL["Email"] === 5
const COL = {};
HEADERS.forEach((h, i) => { COL[h] = i + 1; });

// Maps sheet header → MongoDB field name for the batch-sync endpoint.
// Headers NOT in this map (Lead ID) are never synced back.
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
};


// ── One-time setup ────────────────────────────────────────────────────────────

function setup() {
  // Remove any existing onEditHandler / flushEdits triggers to avoid duplicates
  ScriptApp.getProjectTriggers()
    .filter(t => ["onEditHandler", "flushEdits"].includes(t.getHandlerFunction()))
    .forEach(t => ScriptApp.deleteTrigger(t));

  // Installable onEdit — needed for UrlFetchApp + Gmail access
  ScriptApp.newTrigger("onEditHandler")
    .forSpreadsheet(SpreadsheetApp.getActive())
    .onEdit()
    .create();

  // Time-based trigger: flush queued cell edits to backend every minute
  ScriptApp.newTrigger("flushEdits")
    .timeBased()
    .everyMinutes(1)
    .create();

  SpreadsheetApp.getUi().alert(
    "✅ Triggers installed!\n\nNow run authorizeAll() to grant all permissions."
  );
}


function authorizeAll() {
  // Touches UrlFetchApp so Apps Script requests external_request scope.
  // gmail.send is declared in appsscript.json — sendEmail() will work automatically.
  UrlFetchApp.fetch("https://www.google.com");
  SpreadsheetApp.getUi().alert(
    "✅ All permissions granted!\n\nGenerate Script and Send Email will now work."
  );
}


// ── Menu ─────────────────────────────────────────────────────────────────────

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("SortMyPrep")
    .addItem("Sync Leads from Pipeline", "syncLeads")
    .addItem("Flush Pending Edits Now",  "flushEdits")
    .addSeparator()
    .addItem("About", "showAbout")
    .addToUi();
}

function showAbout() {
  SpreadsheetApp.getUi().alert(
    "sortmyprep Lead Manager\n\n" +
    "• Sync Leads      — pull all leads from the backend\n" +
    "• Generate Script — set column to Yes to generate a personalised email\n" +
    "• Send Email      — set column to Yes to send via Gmail\n" +
    "• Cell edits auto-sync to backend within 1 minute"
  );
}


// ── Sync leads from backend → sheet ──────────────────────────────────────────

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

  sheet.clearContents();
  sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);
  styleHeader(sheet);

  if (!data.length) {
    ui.alert("No leads found in the backend.");
    return;
  }

  const rows = data.map(lead => [
    lead.id,
    lead.contact_name          || "",
    lead.contact_title         || "",
    lead.contact_level         || "",
    lead.email                 || "",
    lead.linkedin              || "",
    lead.company               || "",
    lead.company_website       || "",
    lead.company_address       || "",
    lead.company_phone         || "",
    lead.company_reviews_avg   || "",
    lead.company_reviews_count || "",
    lead.generate_script       || "No",
    lead.send_email            || "No",
    lead.email_script          || "",
    lead.sent_at               || "",
  ]);

  sheet.getRange(2, 1, rows.length, HEADERS.length).setValues(rows);
  styleDataRows(sheet, rows.length);
  ui.alert("Synced " + rows.length + " leads.");
}


// ── onEdit handler (installable trigger) ─────────────────────────────────────
// Named onEditHandler (not onEdit) so the automatic simple trigger
// — which lacks UrlFetchApp permission — never runs this code.

function onEditHandler(e) {
  const sheet = e.source.getActiveSheet();
  const row   = e.range.getRow();
  const col   = e.range.getColumn();
  const value = (e.value || "").toString().trim();

  if (row === 1) return; // header row — ignore

  const header  = HEADERS[col - 1];
  const leadId  = sheet.getRange(row, COL["Lead ID"]).getValue();

  if (!leadId || !header) return;

  // Control columns — handle immediately
  if (header === "Generate Script" && value.toLowerCase() === "yes") {
    handleGenerateScript(sheet, row, leadId);
    return;
  }
  if (header === "Send Email" && value.toLowerCase() === "yes") {
    handleSendEmail(sheet, row, leadId);
    return;
  }

  // All other columns — queue for batch sync
  const field = FIELD_MAP[header];
  if (field) {
    queueEdit(String(leadId), field, value);
  }
}


// ── Edit queue (PropertiesService) ────────────────────────────────────────────

function queueEdit(leadId, field, value) {
  const props = PropertiesService.getScriptProperties();
  const queue = JSON.parse(props.getProperty("editQueue") || "[]");

  // Last-write-wins: replace any existing entry for same lead+field
  const idx = queue.findIndex(q => q.id === leadId && q.field === field);
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

  // Clear queue immediately — if the fetch fails we don't want infinite retries
  props.deleteProperty("editQueue");

  try {
    UrlFetchApp.fetch(BACKEND_URL + "/api/leads/batch-update", {
      method:      "PATCH",
      contentType: "application/json",
      payload:     JSON.stringify({ updates: queue }),
      muteHttpExceptions: true,
    });
  } catch (e) {
    // Non-fatal — changes are in the sheet; user can Flush manually
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
  const subjLine = lines.find(l => l.toLowerCase().startsWith("subject:")) || "";
  const subject  = subjLine.replace(/^subject:\s*/i, "").trim()
                   || "Partnership Opportunity | sortmyprep";
  const body     = lines.filter(l => !l.toLowerCase().startsWith("subject:"))
                        .join("\n").trim();

  cell.setValue("Sending...");

  try {
    GmailApp.sendEmail(toEmail, subject, body, {
      name:    SENDER_NAME,
      replyTo: "ananya@sortmyprep.com",
    });
  } catch (e) {
    cell.setValue("No");
    SpreadsheetApp.getUi().alert("Failed to send email: " + e.message);
    return;
  }

  // Mark sent in backend (non-critical — don't block on failure)
  try {
    UrlFetchApp.fetch(BACKEND_URL + "/api/leads/" + leadId + "/send", {
      method: "post", contentType: "application/json", muteHttpExceptions: true,
    });
  } catch (_) {}

  sheet.getRange(row, COL["Sent At"]).setValue(new Date().toLocaleString());
  cell.setValue("Yes");
  styleEmailSent(sheet, row);
}


// ── Styling ───────────────────────────────────────────────────────────────────

function styleHeader(sheet) {
  sheet.getRange(1, 1, 1, HEADERS.length)
       .setBackground("#1F4E79")
       .setFontColor("#FFFFFF")
       .setFontWeight("bold")
       .setHorizontalAlignment("center");
  sheet.setFrozenRows(1);
  sheet.setColumnWidth(COL["Email Script"], 400);
  sheet.setColumnWidth(COL["Company"],      200);
  sheet.setColumnWidth(COL["LinkedIn"],     200);
  sheet.setColumnWidth(COL["Address"],      200);

  const yesNo = SpreadsheetApp.newDataValidation()
    .requireValueInList(["No", "Yes"], true).build();
  sheet.getRange(2, COL["Generate Script"], 500, 1).setDataValidation(yesNo);
  sheet.getRange(2, COL["Send Email"],      500, 1).setDataValidation(yesNo);
}

function styleDataRows(sheet, count) {
  for (let r = 2; r <= count + 1; r++) {
    const level = sheet.getRange(r, COL["Level"]).getValue();
    sheet.getRange(r, 1, 1, HEADERS.length)
         .setBackground(level === "level1" ? "#D6E4F0" : "#FFFFFF");
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
