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
      // Updated schema with 28 columns
      sheet.appendRow([
        "created_at", "station", "train_name", "destination", "category", "number", 
        "operator", "partner_operator", "raw_departure_iso", "planned_departure", "predicted_departure", 
        "delay_minutes", "delay", "status", "status_arrival", "planned_platform", "predicted_platform", 
        "planned_arrival", "predicted_arrival", "arrival_delay", "is_cancelled", 
        "cancellation_reason", "train_speed", "journey_duration", "stops_count", 
        "api_response_time", "journey_id", "record_id", "data_quality", "raw_json"
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
          item.created_at,
          item.station,
          item.train_name,
          item.destination,
          item.category,
          item.number,
          item.operator,
          item.partner_operator || "",
          item.raw_departure_iso,
          item.planned_departure || "",
          item.predicted_departure || "",
          item.delay_minutes || 0,
          item.delay || 0,
          item.status || "",
          item.status_arrival || "",
          item.planned_platform || "",
          item.predicted_platform || "",
          item.planned_arrival || "",
          item.predicted_arrival || "",
          item.arrival_delay || 0,
          item.is_cancelled || false,
          item.cancellation_reason || "",
          item.train_speed || "",
          item.journey_duration || "",
          item.stops_count || 0,
          item.api_response_time || 0,
          item.journey_id || "",
          item.record_id || "",
          item.data_quality || 0,
          item.raw_json || ""
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
