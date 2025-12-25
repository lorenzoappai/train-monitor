function doGet(e) {
  return ContentService.createTextOutput(JSON.stringify({
    "status": "online",
    "message": "Train Monitor API is accessible. method=GET"
  })).setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  try {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Train Logs");
    if (!sheet) {
      sheet = SpreadsheetApp.getActiveSpreadsheet().insertSheet("Train Logs");
      // Optional: Add headers if new sheet
      sheet.appendRow([
        "timestamp", "station", "name", "to", "category", "number", "operator", 
        "departure_iso", "departure_planned", "departure_effective", 
        "gate_planned", "gate_effective", "cancelled", 
        "arrival_planned", "arrival_effective", "arrival_gate_planned", "arrival_gate_effective", 
        "max_delay", "train_type"
      ]);
    }
    
    var json = JSON.parse(e.postData.contents);
    var data = json.data;
    
    if (!data || !Array.isArray(data)) {
      return ContentService.createTextOutput(JSON.stringify({"status": "error", "message": "Invalid format, 'data' array missing"}))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
    // Lock to prevent concurrent edit issues
    var lock = LockService.getScriptLock();
    lock.waitLock(30000);
    
    try {
      var rows = data.map(function(item) {
        return [
          item.timestamp,
          item.station,
          item.name,
          item.to,
          item.category,
          item.number,
          item.operator,
          item.departure_iso,
          item.departure_planned || "",
          item.departure_effective || "",
          item.gate_planned || "",
          item.gate_effective || "",
          item.cancelled || false,
          item.arrival_planned || "",
          item.arrival_effective || "",
          item.arrival_gate_planned || "",
          item.arrival_gate_effective || "",
          item.max_delay || 0,
          item.train_type || ""
        ];
      });
      
      // Batch append
      var lastRow = sheet.getLastRow();
      sheet.getRange(lastRow + 1, 1, rows.length, rows[0].length).setValues(rows);
      
      return ContentService.createTextOutput(JSON.stringify({"status": "success", "rows": rows.length}))
        .setMimeType(ContentService.MimeType.JSON);
        
    } finally {
      lock.releaseLock();
    }
    
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({"status": "error", "message": error.toString()}))
      .setMimeType(ContentService.MimeType.JSON);
  }
}
