// ─────────────────────────────────────────────────────────────────────────────
// sortmyprep Lead Manager — Google Apps Script
//
// SETUP:
//   1. Open script.google.com → New project → paste this file
//   2. Replace BACKEND_URL below with your Render URL
//   3. Run onOpen() once manually to grant Gmail + Sheets permissions
//   4. Add triggers: onOpen → On open | onEdit → On edit (from spreadsheet)
// ─────────────────────────────────────────────────────────────────────────────

const BACKEND_URL  = "https://your-app.onrender.com"; // ← replace after deploy
const SENDER_EMAIL = "adhyayan2107@gmail.com";         // ← update if sender changes
const SENDER_NAME  = "Ananya | sortmyprep";

// Column headers in the exact order used by syncLeads()
const HEADERS = [
  "Lead ID", "Contact Name", "Title", "Level", "Email", "LinkedIn",
  "Company", "Website", "Address", "Phone", "Avg Rating", "Review Count",
  "Generate Script", "Send Email", "Email Script", "Sent At",
];

// Column indices (1-based) — derived from HEADERS so they stay in sync
const COL = {};
HEADERS.forEach((h, i) => { COL[h] = i + 1; });


// ── Menu ─────────────────────────────────────────────────────────────────────

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("SortMyPrep")
    .addItem("Sync Leads from Pipeline", "syncLeads")
    .addSeparator()
    .addItem("About", "showAbout")
    .addToUi();
}

function showAbout() {
  SpreadsheetApp.getUi().alert(
    "sortmyprep Lead Manager\n\n" +
    "• Sync Leads — pulls all leads from the pipeline backend\n" +
    "• Generate Script — change column to 'Yes' to generate a personalised email\n" +
    "• Send Email — change column to 'Yes' to send via your Gmail"
  );
}


// ── Sync leads from backend ───────────────────────────────────────────────────

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

  // Write header row
  sheet.clearContents();
  sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);
  styleHeader(sheet);

  if (!data.length) {
    ui.alert("No leads found in the backend.");
    return;
  }

  // Build rows
  const rows = data.map(lead => [
    lead.id,
    lead.contact_name    || "",
    lead.contact_title   || "",
    lead.contact_level   || "",
    lead.email           || "",
    lead.linkedin        || "",
    lead.company         || "",
    lead.company_website || "",
    lead.company_address || "",
    lead.company_phone   || "",
    lead.company_reviews_avg   || "",
    lead.company_reviews_count || "",
    lead.generate_script || "No",
    lead.send_email      || "No",
    lead.email_script    || "",
    lead.sent_at         || "",
  ]);

  sheet.getRange(2, 1, rows.length, HEADERS.length).setValues(rows);
  styleDataRows(sheet, rows.length);

  ui.alert("Synced " + rows.length + " leads.");
}


// ── onEdit trigger ────────────────────────────────────────────────────────────

function onEdit(e) {
  const sheet = e.source.getActiveSheet();
  const range = e.range;
  const row   = range.getRow();
  const col   = range.getColumn();
  const value = (e.value || "").toString().trim();

  if (row === 1) return; // ignore header edits

  if (col === COL["Generate Script"] && value.toLowerCase() === "yes") {
    handleGenerateScript(sheet, row);
  } else if (col === COL["Send Email"] && value.toLowerCase() === "yes") {
    handleSendEmail(sheet, row);
  }
}


// ── Generate Script ───────────────────────────────────────────────────────────

function handleGenerateScript(sheet, row) {
  const leadId = sheet.getRange(row, COL["Lead ID"]).getValue();
  if (!leadId) return;

  // Visual feedback
  const cell = sheet.getRange(row, COL["Generate Script"]);
  cell.setValue("Generating...");

  let script;
  try {
    const resp = UrlFetchApp.fetch(BACKEND_URL + "/api/leads/" + leadId + "/generate", {
      method: "post",
      contentType: "application/json",
      payload: JSON.stringify({ email_number: 1 }),
      muteHttpExceptions: true,
    });
    const data = JSON.parse(resp.getContentText());
    if (data.error) throw new Error(data.error);
    script = data.script;
  } catch (e) {
    cell.setValue("No");
    SpreadsheetApp.getUi().alert("Script generation failed: " + e.message);
    return;
  }

  // Write script to Email Script column and mark done
  sheet.getRange(row, COL["Email Script"]).setValue(script);
  cell.setValue("Yes");
  styleScriptReady(sheet, row);
}


// ── Send Email ────────────────────────────────────────────────────────────────

function handleSendEmail(sheet, row) {
  const leadId      = sheet.getRange(row, COL["Lead ID"]).getValue();
  const toEmail     = sheet.getRange(row, COL["Email"]).getValue();
  const script      = sheet.getRange(row, COL["Email Script"]).getValue();
  const contactName = sheet.getRange(row, COL["Contact Name"]).getValue();

  const cell = sheet.getRange(row, COL["Send Email"]);

  if (!toEmail) {
    cell.setValue("No");
    SpreadsheetApp.getUi().alert("No email address for this lead.");
    return;
  }
  if (!script) {
    cell.setValue("No");
    SpreadsheetApp.getUi().alert("Generate the email script first (set 'Generate Script' to Yes).");
    return;
  }

  // Parse subject from the first line ("Subject: ...")
  const lines   = script.split("\n");
  const subjLine = lines.find(l => l.toLowerCase().startsWith("subject:")) || "";
  const subject  = subjLine.replace(/^subject:\s*/i, "").trim() || "Partnership Opportunity | sortmyprep";
  const body     = lines.filter(l => !l.toLowerCase().startsWith("subject:")).join("\n").trim();

  cell.setValue("Sending...");

  try {
    GmailApp.sendEmail(toEmail, subject, body, {
      from:  SENDER_EMAIL,
      name:  SENDER_NAME,
      replyTo: "ananya@sortmyprep.com",
    });
  } catch (e) {
    cell.setValue("No");
    SpreadsheetApp.getUi().alert("Failed to send email: " + e.message);
    return;
  }

  // Mark sent in backend
  try {
    UrlFetchApp.fetch(BACKEND_URL + "/api/leads/" + leadId + "/send", {
      method: "post",
      contentType: "application/json",
      muteHttpExceptions: true,
    });
  } catch (_) { /* non-critical */ }

  const sentAt = new Date().toLocaleString();
  sheet.getRange(row, COL["Sent At"]).setValue(sentAt);
  cell.setValue("Yes");
  styleEmailSent(sheet, row);
}


// ── Styling helpers ───────────────────────────────────────────────────────────

function styleHeader(sheet) {
  const header = sheet.getRange(1, 1, 1, HEADERS.length);
  header.setBackground("#1F4E79")
        .setFontColor("#FFFFFF")
        .setFontWeight("bold")
        .setHorizontalAlignment("center");
  sheet.setFrozenRows(1);

  // Wider columns for script and long text
  sheet.setColumnWidth(COL["Email Script"], 400);
  sheet.setColumnWidth(COL["Company"],      200);
  sheet.setColumnWidth(COL["LinkedIn"],     200);
  sheet.setColumnWidth(COL["Address"],      200);

  // Dropdown validation for Generate Script and Send Email
  const yesNo = SpreadsheetApp.newDataValidation()
    .requireValueInList(["No", "Yes"], true)
    .build();
  sheet.getRange(2, COL["Generate Script"], 500, 1).setDataValidation(yesNo);
  sheet.getRange(2, COL["Send Email"],      500, 1).setDataValidation(yesNo);
}

function styleDataRows(sheet, count) {
  // Alternating row shading
  for (let r = 2; r <= count + 1; r++) {
    const level = sheet.getRange(r, COL["Level"]).getValue();
    const color = level === "level1" ? "#D6E4F0" : "#FFFFFF";
    sheet.getRange(r, 1, 1, HEADERS.length).setBackground(color);
  }
}

function styleScriptReady(sheet, row) {
  sheet.getRange(row, COL["Generate Script"]).setBackground("#C6EFCE").setFontColor("#276221");
}

function styleEmailSent(sheet, row) {
  sheet.getRange(row, COL["Send Email"]).setBackground("#C6EFCE").setFontColor("#276221");
  sheet.getRange(row, 1, 1, HEADERS.length).setBackground("#F0FFF0"); // pale green = sent
}
